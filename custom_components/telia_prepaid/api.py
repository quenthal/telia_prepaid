"""Telia Prepaid (Minun Prepaid) -asiakas.

Ei riipu Home Assistantista: samaa koodia käyttää myös konsolitesti
(tools/build_console.py kokoaa sen yhteen tiedostoon).

Kirjautumisen kulku (selvitetty prepaid.telia.fi:n Next.js-sovelluksesta):

1. POST https://id.telia.fi/rest/v80/session/start  {"username", "credential"}
   -> id.telia.fi asettaa istuntoevästeen, vastauksessa userId.
2. GET  https://id.telia.fi/oidc/authorize?client_id=...&response_type=code
   -> ohjaus osoitteeseen https://prepaid.telia.fi/auth/callback?code=...&state=...
3. Paluusivun palvelintoiminto getULMOpenIDToken(code) vaihtaa koodin
   ULM-pääsytunnisteeksi ({success, accessToken, expiresIn, username}),
   minkä jälkeen setLoggedInCookie(true).
4. Liittymät haetaan Next.js-palvelintoiminnoilla (Server Actions):
   getAllSubscriptions(accessToken, userId, lang) ja
   getSubscriptionByUlmId(accessToken, ulmId, userId, lang).
   Toimintojen tunnisteet vaihtuvat jokaisessa julkaisussa, joten ne
   poimitaan sivun JavaScript-tiedostoista ajon aikana.
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone, tzinfo
from typing import Any
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

try:  # aiohttp on HA:ssa aina mukana; konsoliversio pärjää ilman
    import aiohttp
except ImportError:  # pragma: no cover
    aiohttp = None

_LOGGER = logging.getLogger(__name__)

PREPAID_BASE = "https://prepaid.telia.fi"
ULM_BASE = "https://id.telia.fi"
ULM_CLIENT_ID = "1fec972e-36b3-4566-96cb-987d3750e7b4"
ULM_REDIRECT_URI = "https://prepaid.telia.fi/auth/callback"
ULM_SCOPE = "pre_paid openid profile email phone com.uxpsystems.ulm"
LANG = "fi"

# Viimeksi tunnetut palvelintoimintojen tunnisteet (käytetään, jos haku sivulta ei onnistu)
FALLBACK_ACTIONS = {
    "getULMOpenIDToken": "7f43ea7f7904a159aabcef9b66c52f292798af1e8a",
    "getAllSubscriptions": "7fa9de34ba8ad829371f435d23e7f4ce813c3f52ec",
    "getSubscriptionByUlmId": "7fe2fe277bac15a8650e3216d53d4c98851feee07d",
    "getSubscriptionCacheExpireSeconds": "7f64e3ca40845608484eaaa820d3c24f0c67a962a4",
    "setLoggedInCookie": "7f81ff6011d20f73dd5e59cb3f29d96e2e4f1a229b",
}

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)
REQUEST_TIMEOUT_S = 30

_JWT_RE = re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}")
_SCRIPT_SRC_RE = re.compile(r"""(?:src|href)=["'](/_next/static/chunks/[^"']+\.js)["']""")
_CHUNK_IN_RSC_RE = re.compile(r"static/chunks/[A-Za-z0-9%()\[\]_./-]+?\.js")
_ACTION_RE = re.compile(
    r"createServerReference\)\(\s*[\"']([0-9a-f]{40,42})[\"'][^)]*?[\"'](\w+)[\"']\s*\)"
)


def new_cookie_jar():
    """aiohttp-evästesäiliö Telian palveluille.

    quote_cookie=False on välttämätön: id.telia.fi:n istuntoevästeen arvossa on
    merkkejä (esim. / ja =), jotka aiohttp muuten lähettäisi lainausmerkeissä,
    jolloin palvelin ei tunnista istuntoa ja ohjaa kirjautumissivulle.
    """
    return aiohttp.CookieJar(quote_cookie=False)


class TeliaPrepaidError(Exception):
    """Yleinen virhe."""


class TeliaPrepaidAuthError(TeliaPrepaidError):
    """Telia Tili hylkäsi tunnuksen tai salasanan.

    Vain tämä virhe johtaa salasanan kysymiseen uudelleen, joten sitä ei käytetä
    kirjautumisen myöhemmissä vaiheissa: kun session/start on hyväksynyt tunnukset,
    niissä ei ole vikaa, vaan virhe on Telian päässä ja menee ohi.
    """


class TeliaPrepaidParseError(TeliaPrepaidError):
    """Palvelun vastausta ei tunnistettu."""


class _StaleActionError(TeliaPrepaidParseError):
    """Palvelintoiminnon tunniste on vanhentunut (Telia julkaisi uuden version)."""


@dataclass
class Subscription:
    """Yhden prepaid-liittymän tiedot."""

    number: str
    name: str | None = None
    subscription_id: str | None = None
    balance: float | None = None
    bonus_balance: float | None = None
    valid_until: datetime | None = None  # tarkka hetki, UTC
    subscription_type: str | None = None
    sim_type: str | None = None
    status: str | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def valid_until_local(self) -> datetime | None:
        """Voimassaolon päättyminen Suomen aikaa."""
        return self.valid_until.astimezone(local_tz()) if self.valid_until else None

    def days_remaining(self, now: datetime | None = None) -> int | None:
        """Kalenteripäiviä jäljellä (Suomen aikaa) päättymispäivään."""
        if self.valid_until is None:
            return None
        tz = local_tz()
        today = (now or datetime.now(timezone.utc)).astimezone(tz).date()
        return (self.valid_until.astimezone(tz).date() - today).days

    @property
    def total_balance(self) -> float | None:
        if self.balance is None and self.bonus_balance is None:
            return None
        return round((self.balance or 0.0) + (self.bonus_balance or 0.0), 2)


@dataclass
class _Response:
    status: int
    text: str
    url: str
    headers: dict[str, str]

    @property
    def location(self) -> str | None:
        loc = self.headers.get("location")
        return urljoin(self.url, loc) if loc else None


# --------------------------------------------------------------------------
# Apufunktiot
# --------------------------------------------------------------------------


def mask(text: str) -> str:
    """Peittää tunnisteet ja kertakäyttökoodit lokeista ja tallennetuista sivuista."""
    text = _JWT_RE.sub("eyJ…[peitetty]", text)
    text = re.sub(r"([?&](?:code|state|id_token|access_token)=)[^&\s\"'<>]+", r"\1[peitetty]", text)
    text = re.sub(
        r'(\\?"(?:[A-Za-z]*[Tt]oken|credential|password|code)\\?"\s*:\s*\\?")[^"\\]{6,}',
        r"\1[peitetty]",
        text,
    )
    return mask_personal(text)


_PERSONAL_KEYS = (
    "msisdn|phoneNumber|displayName|alias|e?[Mm]ail|[Uu]ser[Nn]ame|firstName|lastName|fullName"
    "|streetAddress|address"
)


def mask_personal(text: str) -> str:
    """Peittää puhelinnumerot, nimet ja sähköpostiosoitteet (saldot ja päivät jäävät)."""
    text = re.sub(
        rf'(\\?"(?:{_PERSONAL_KEYS})\\?"\s*:\s*\\?")[^"\\]+', r"\1[peitetty]", text
    )
    text = re.sub(r"[\w.+-]+@[\w-]+\.[\w.-]+", "[sähköposti]", text)
    return re.sub(r"(?<![\w.])(?:\+?358|0)(?:4\d|50)\d{6,8}(?!\d)", "[numero]", text)


def _to_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return round(float(value), 2)
    if isinstance(value, str):
        s = value.replace("\xa0", "").replace("€", "").replace(" ", "").strip()
        if s.startswith("$n"):  # RSC-numero
            s = s[2:]
        s = s.replace(",", ".")
        try:
            return round(float(s), 2)
        except ValueError:
            return None
    if isinstance(value, dict):
        for key in ("amount", "value", "inEuros", "euros"):
            if key in value:
                return _to_float(value[key])
    return None


def local_tz() -> tzinfo:
    """Suomen aikavyöhyke (Windowsissa ei välttämättä tietokantaa -> järjestelmän oma)."""
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo("Europe/Helsinki")
    except Exception:  # noqa: BLE001
        return datetime.now().astimezone().tzinfo or timezone.utc


def _to_datetime(value: Any) -> datetime | None:
    """Muuntaa aikatiedon aikavyöhyketietoiseksi datetimeksi (UTC).

    Telia antaa voimassaolon kentässä expiryDateUtc (ISO 8601, UTC). Pelkkä
    päivämäärä tulkitaan sen päivän alkuhetkeksi Suomen aikaa.
    """
    if not isinstance(value, str):
        return None
    s = (value[2:] if value.startswith("$D") else value).strip()
    if m := re.fullmatch(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", s):
        d = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        return datetime.combine(d, time.min, local_tz()).astimezone(timezone.utc)
    if not re.match(r"\d{4}-\d{2}-\d{2}", s):
        return None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        return datetime.combine(date.fromisoformat(s), time.min, local_tz()).astimezone(timezone.utc)
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:  # kentän nimen mukaan UTC
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _walk(obj: Any, path: str = ""):
    """Käy läpi sisäkkäiset rakenteet: (polku, avain, arvo)."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{path}.{k}" if path else str(k)
            yield p, str(k), v
            yield from _walk(v, p)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk(v, f"{path}[{i}]")


def _first(obj: dict, *keys: str) -> Any:
    for k in keys:
        if k in obj and obj[k] not in (None, "", "$undefined"):
            return obj[k]
    return None


def _find_valid_until(obj: dict) -> datetime | None:
    preferred = (
        "expiryDateUtc", "subscriptionValidUntil", "validUntil", "validTo", "validityEndDate",
        "expirationDate", "expiryDate", "expiresAt", "inEffectUntil", "endDate",
        "subscriptionExpirationDate", "lifecycleEndDate",
    )
    for k in preferred:
        if (d := _to_datetime(obj.get(k))) is not None:
            return d
    # Heuristiikka: ensimmäinen päivämäärä avaimessa, joka viittaa voimassaoloon
    for path, key, value in _walk(obj):
        low = path.lower()
        if "package" in low or "topup" in low or "card" in low:
            continue
        if re.search(r"valid|expir|effect|until|end", key, re.I):
            if (d := _to_datetime(value)) is not None:
                return d
    return None


def subscription_from_json(item: dict) -> Subscription:
    sub_id = _first(item, "ulmId", "id")
    number = str(_first(item, "msisdn", "phoneNumber", "number") or sub_id or "?").replace(" ", "")
    if number.startswith("358"):
        number = "0" + number[3:]
    sub = Subscription(
        number=number,
        name=_first(item, "displayName", "name", "alias"),
        subscription_id=str(sub_id) if sub_id is not None else None,
        raw=item,
    )
    merge_subscription_json(sub, item)
    return sub


# Rajapinnan koodiarvot -> sivulla näkyvät tekstit
_SIM_TYPES = {"SIM": "SIM-kortti", "PSIM": "SIM-kortti", "ESIM": "eSIM", "E_SIM": "eSIM"}
_CONNECTION_TYPES = {
    "VOICE": "Telia Prepaid",
    "MOBILE": "Telia Prepaid",
    "PREPAID": "Telia Prepaid",
    "DATA": "Telia Prepaid Netti",
    "MBB": "Telia Prepaid Netti",
    "MOBILE_BROADBAND": "Telia Prepaid Netti",
}


def merge_subscription_json(sub: Subscription, item: dict) -> None:
    if (v := _to_float(_first(item, "balanceInEuros", "balance"))) is not None:
        sub.balance = v
    if (v := _to_float(_first(item, "bonusBalanceInEuros", "bonusBalance"))) is not None:
        sub.bonus_balance = v
    if (v := _find_valid_until(item)) is not None:
        sub.valid_until = v
    if name := _first(item, "displayName"):
        sub.name = name
    conn = _first(item, "connectionType", "subscriptionType", "productName")
    if isinstance(conn, str):
        sub.subscription_type = _CONNECTION_TYPES.get(conn.upper(), conn)
    sim = _first(item, "simType", "simCardType")
    if isinstance(sim, str):
        sub.sim_type = _SIM_TYPES.get(sim.upper(), sim)
    if isinstance(status := _first(item, "status"), str):
        sub.status = status
    sub.raw = {**sub.raw, **item}


def parse_rsc(text: str) -> list[Any]:
    """Jäsentää Next.js:n RSC-vastauksen rivit (muotoa `id:json`)."""
    values: list[Any] = []
    for line in text.splitlines():
        m = re.match(r"^[0-9a-f]+:(.*)$", line)
        payload = m.group(1) if m else line
        if not payload or payload[0] not in '[{"0123456789tfn-':
            continue
        try:
            values.append(json.loads(payload))
        except ValueError:
            continue
    return values


def action_result(text: str) -> Any:
    """Poimii palvelintoiminnon paluuarvon RSC-vastauksesta."""
    values = parse_rsc(text)
    for v in values:
        if isinstance(v, dict) and ("status" in v or "data" in v) and "a" not in v:
            return v
    for v in values:
        if not (isinstance(v, dict) and {"a", "f", "b"} & set(v)):
            return v
    return None


# --------------------------------------------------------------------------
# Asiakas
# --------------------------------------------------------------------------


class TeliaPrepaidClient:
    """Kirjautuu Minun Prepaid -palveluun ja lukee liittymien tiedot."""

    def __init__(self, session, username: str, password: str) -> None:
        self._session = session
        self._username = username
        self._password = password
        self._user_id: int | None = None
        self._access_token: str | None = None
        self._actions: dict[str, str] = {}
        self._scanned: set[str] = set()
        self._step = 0
        # Haetut vastaukset vianetsintää varten {nimi: teksti}, salaisuudet peitetty
        self.debug_pages: dict[str, str] = {}

    # ---- HTTP ---------------------------------------------------------------

    async def _fetch(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
        follow_redirects: bool,
    ) -> _Response:
        """HTTP-pyyntö aiohttp:llä."""
        try:
            async with self._session.request(
                method,
                url,
                headers=headers,
                data=body,
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_S),
                allow_redirects=follow_redirects,
            ) as resp:
                text = await resp.text(errors="replace")
                return _Response(
                    resp.status, text, str(resp.url), {k.lower(): v for k, v in resp.headers.items()}
                )
        except (aiohttp.ClientError, TimeoutError) as err:
            raise TeliaPrepaidError(f"Yhteysvirhe ({urlparse(url).netloc}): {err}") from err

    async def _request(
        self,
        method: str,
        url: str,
        name: str,
        *,
        json_body: Any = None,
        text_body: str | None = None,
        headers: dict[str, str] | None = None,
        follow_redirects: bool = True,
        keep: bool = True,
    ) -> _Response:
        all_headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
            "Accept-Language": "fi-FI,fi;q=0.9,en;q=0.8",
            **(headers or {}),
        }
        body = None
        if json_body is not None:
            body = json.dumps(json_body).encode()
            all_headers.setdefault("Content-Type", "application/json")
        elif text_body is not None:
            body = text_body.encode()
        resp = await self._fetch(method, url, all_headers, body, follow_redirects)
        self._step += 1
        _LOGGER.debug(
            "%02d %s %s -> %s%s (%d merkkiä)",
            self._step,
            method,
            mask(url),
            resp.status,
            f" -> {mask(resp.location)}" if resp.location and 300 <= resp.status < 400 else "",
            len(resp.text),
        )
        if keep:
            self.debug_pages[f"{self._step:02d}_{name}"] = mask(
                f"<!-- {method} {url} -> {resp.status} {resp.url} -->\n{resp.text}"
            )
        if resp.status >= 500:
            raise TeliaPrepaidError(f"Palvelinvirhe {resp.status} ({name})")
        return resp

    # ---- Kirjautuminen ------------------------------------------------------

    async def login(self) -> None:
        self._access_token = None
        origin = {"Origin": PREPAID_BASE, "Referer": f"{PREPAID_BASE}/"}

        # 1. Tunnus + salasana
        resp = await self._request(
            "POST",
            f"{ULM_BASE}/rest/v80/session/start",
            "session_start",
            json_body={"username": self._username, "credential": self._password},
            headers={**origin, "Accept": "application/json"},
        )
        if resp.status == 429:
            raise TeliaPrepaidError("Telia Tili rajoittaa kirjautumisia (429), yritetään myöhemmin")
        if resp.status in (400, 401, 403):
            if resp.text.lstrip().startswith("<") or "html" in resp.headers.get("content-type", ""):
                # Palomuurin tai välityspalvelimen sivu, ei Telia Tilin vastaus tunnuksiin
                raise TeliaPrepaidError(f"session/start: {resp.status} HTML-sivulla")
            raise TeliaPrepaidAuthError("Kirjautuminen epäonnistui – tarkista tunnus ja salasana.")
        try:
            data = json.loads(resp.text)
        except ValueError as err:
            raise TeliaPrepaidParseError(f"session/start palautti {resp.status}, ei JSONia") from err
        keys = sorted(data) if isinstance(data, dict) else []
        cookie_names = sorted(
            {c.split("=", 1)[0].strip() for k, c in resp.headers.items() if k == "set-cookie"}
        )
        _LOGGER.debug("session/start -> kentät %s, evästeet %s", keys, cookie_names)
        if not isinstance(data, dict) or not isinstance(data.get("userId"), int):
            raise TeliaPrepaidParseError(f"session/start: userId puuttuu (kentät {keys})")
        self._user_id = data["userId"]

        # 2. OIDC authorize -> paluuosoite
        state = str(uuid.uuid4())
        url = f"{ULM_BASE}/oidc/authorize?" + urlencode(
            {
                "client_id": ULM_CLIENT_ID,
                "redirect_uri": ULM_REDIRECT_URI,
                "scope": ULM_SCOPE,
                "response_type": "code",
                "state": state,
            }
        )
        callback_url = None
        for hop in range(10):
            resp = await self._request(
                "GET", url, f"authorize_{hop}", headers={"Referer": f"{PREPAID_BASE}/"},
                follow_redirects=False,
            )
            loc = resp.location
            if not (300 <= resp.status < 400 and loc):
                raise TeliaPrepaidParseError(
                    f"OIDC-ohjaus pysähtyi: {resp.status} osoitteessa {mask(resp.url)}"
                )
            if "/login" in urlparse(loc).path and not loc.startswith(ULM_REDIRECT_URI):
                raise TeliaPrepaidParseError(
                    "Telia Tili ei tunnistanut kirjautumista seuraavassa pyynnössä "
                    "(istuntoeväste ei kulkenut). Ohjaus: " + mask(loc)
                )
            if loc.startswith(ULM_REDIRECT_URI):
                callback_url = loc
                break
            url = loc
        if callback_url is None:
            raise TeliaPrepaidParseError("OIDC-ohjaus ei palannut prepaid-sivulle.")
        query = parse_qs(urlparse(callback_url).query)
        if "error" in query:
            raise TeliaPrepaidError(
                f"OIDC-virhe: {query.get('error')} {query.get('error_description')}"
            )

        # 3. Paluusivu: koodi vaihdetaan tunnisteeksi palvelintoiminnolla
        code = query.get("code", [""])[0]
        if not code:
            raise TeliaPrepaidParseError("Paluuosoitteessa ei ollut koodia.")
        page = await self._request("GET", callback_url, "callback_page")
        await self._discover_actions(page.text, need=("getULMOpenIDToken",))
        result = await self._call_action("getULMOpenIDToken", [code], callback_url)
        if not isinstance(result, dict):
            raise TeliaPrepaidParseError(
                f"Koodin vaihdon vastausta ei tunnistettu (tyyppi {type(result).__name__})"
            )
        if not result.get("success") or not result.get("accessToken"):
            raise TeliaPrepaidError(
                f"Koodin vaihto tunnisteeksi epäonnistui (vastaus: {sorted(result)})"
            )
        self._access_token = result["accessToken"]
        _LOGGER.debug(
            "Pääsytunniste saatu (pituus %d), voimassa %s s",
            len(self._access_token),
            result.get("expiresIn"),
        )
        try:
            await self._call_action("setLoggedInCookie", [True], callback_url)
        except TeliaPrepaidError as err:  # ei välttämätön liittymähaulle
            _LOGGER.debug("setLoggedInCookie epäonnistui: %s", err)

    # ---- Palvelintoiminnot --------------------------------------------------

    async def _discover_actions(self, html: str, need: tuple[str, ...]) -> None:
        """Poimii palvelintoimintojen tunnisteet sivun JavaScript-tiedostoista."""
        if all(n in self._actions for n in need):
            return
        chunks: list[str] = []
        for src in _SCRIPT_SRC_RE.findall(html) + [
            "/_next/" + c for c in _CHUNK_IN_RSC_RE.findall(html.replace("\\/", "/"))
        ]:
            if src not in chunks:
                chunks.append(src)
        # Sivukohtaiset (app/...) tiedostot ensin – toiminnot ovat yleensä niissä
        chunks.sort(key=lambda c: (0 if "/app/" in c else 1))
        for src in chunks:
            if any(skip in src for skip in ("webpack-", "framework-", "polyfills-", "main-app-")):
                continue
            if src in self._scanned:
                continue
            self._scanned.add(src)
            js = await self._request("GET", urljoin(PREPAID_BASE, src), "chunk", keep=False)
            for action_id, name in _ACTION_RE.findall(js.text):
                self._actions[name] = action_id
            if all(n in self._actions for n in need):
                break
        _LOGGER.debug("Palvelintoiminnot: %s", sorted(self._actions))

    async def _call_action(self, name: str, args: list[Any], page_url: str) -> Any:
        action_id = self._actions.get(name) or FALLBACK_ACTIONS.get(name)
        if not action_id:
            raise TeliaPrepaidParseError(f"Palvelintoimintoa {name} ei löytynyt sivulta")
        resp = await self._request(
            "POST",
            page_url,
            f"action_{name}",
            text_body=json.dumps(args),
            headers={
                "Next-Action": action_id,
                "Accept": "text/x-component",
                "Content-Type": "text/plain;charset=UTF-8",
                "Origin": PREPAID_BASE,
                "Referer": page_url,
            },
        )
        if resp.status == 404:
            raise _StaleActionError(
                f"{name}: palvelintoimintoa ei löytynyt (Telia on ehkä päivittänyt sivunsa)"
            )
        if resp.status >= 400:
            raise TeliaPrepaidParseError(f"{name}: HTTP {resp.status}")
        return action_result(resp.text)

    # ---- Julkinen rajapinta -------------------------------------------------

    async def async_get_data(self) -> dict[str, Subscription]:
        """Palauttaa liittymät numeron mukaan. Kirjautuu joka kerta uudelleen.

        Palvelintoimintojen tunnisteet pidetään muistissa päivitysten välillä;
        jos Telia on julkaissut uuden version, ne haetaan uudelleen.
        """
        try:
            return await self._get_data_once()
        except _StaleActionError as err:
            _LOGGER.debug("%s – haetaan toimintojen tunnisteet uudelleen", err)
            self._actions.clear()
            self._scanned.clear()
            return await self._get_data_once()

    async def _get_data_once(self) -> dict[str, Subscription]:
        self.debug_pages.clear()
        self._step = 0
        await self.login()

        account_url = f"{PREPAID_BASE}/{LANG}/account"
        page = await self._request("GET", account_url, "account_page")
        await self._discover_actions(page.text, need=("getAllSubscriptions", "getSubscriptionByUlmId"))
        result = await self._call_action(
            "getAllSubscriptions", [self._access_token, self._user_id or 0, LANG], account_url
        )
        if isinstance(result, dict) and result.get("status") not in (None, 200):
            status = result.get("status")
            if status in (401, 403):
                raise TeliaPrepaidError(f"Liittymien haku: pääsy estetty ({status})")
            raise TeliaPrepaidParseError(f"Liittymien haku palautti tilan {status}")
        items = result.get("data") if isinstance(result, dict) else result
        if not isinstance(items, list):
            raise TeliaPrepaidParseError(
                f"Liittymälistaa ei tunnistettu (tyyppi {type(items).__name__})"
            )
        _LOGGER.debug(
            "Liittymiä %d, kentät: %s",
            len(items),
            sorted({k for i in items if isinstance(i, dict) for k in i}),
        )

        subs = [
            subscription_from_json(i)
            for i in items
            if isinstance(i, dict) and i.get("isConfirmed", True) is not False
        ]
        if not subs:
            raise TeliaPrepaidParseError("Tililtä ei löytynyt yhtään vahvistettua liittymää.")

        for sub in subs:
            if not sub.subscription_id:
                continue
            try:
                detail = await self._call_action(
                    "getSubscriptionByUlmId",
                    [self._access_token, sub.raw.get("ulmId", sub.subscription_id),
                     self._user_id or 0, LANG],
                    account_url,
                )
                data = detail.get("data") if isinstance(detail, dict) else None
                if isinstance(data, dict):
                    _LOGGER.debug("Lisätietojen kentät: %s", sorted(data))
                    merge_subscription_json(sub, data)
            except TeliaPrepaidError as err:
                _LOGGER.warning("Liittymän %s lisätietoja ei saatu: %s", sub.number, err)

        return {s.number: s for s in subs}

    async def async_validate(self) -> None:
        """Tarkistaa tunnukset (käytetään asetusvaiheessa)."""
        await self.async_get_data()
