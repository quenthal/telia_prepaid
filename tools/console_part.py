# --------------------------------------------------------------------------
# Konsoliversio (vain Pythonin vakiokirjasto)
# --------------------------------------------------------------------------
import argparse
import asyncio
import getpass
import http.cookiejar
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class UrllibTeliaPrepaidClient(TeliaPrepaidClient):
    """Sama asiakas kuin integraatiossa, mutta HTTP hoidetaan urllibillä."""

    def __init__(self, username: str, password: str) -> None:
        super().__init__(None, username, password)
        jar = http.cookiejar.CookieJar()
        self._opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        self._opener_noredir = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(jar), _NoRedirect()
        )

    def _fetch_sync(self, method, url, headers, body, follow_redirects):
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        opener = self._opener if follow_redirects else self._opener_noredir
        try:
            with opener.open(req, timeout=REQUEST_TIMEOUT_S) as resp:
                charset = resp.headers.get_content_charset() or "utf-8"
                text = resp.read().decode(charset, "replace")
                hdrs = {k.lower(): v for k, v in resp.headers.items()}
                return _Response(resp.status, text, resp.geturl(), hdrs)
        except urllib.error.HTTPError as err:
            hdrs = {k.lower(): v for k, v in (err.headers or {}).items()}
            text = err.read().decode("utf-8", "replace") if err.fp else ""
            return _Response(err.code, text, url, hdrs)
        except (urllib.error.URLError, OSError) as err:
            raise TeliaPrepaidError(f"Yhteysvirhe ({urllib.parse.urlparse(url).netloc}): {err}") from err

    async def _fetch(self, method, url, headers, body, follow_redirects):
        return await asyncio.to_thread(self._fetch_sync, method, url, headers, body, follow_redirects)


def _dump(pages: dict[str, str], folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for name, html in pages.items():
        (folder / f"{name}.html").write_text(html, encoding="utf-8")
    print(f"\nHaetut sivut tallennettu: {folder.resolve()}")
    print("HUOM: sivuilla näkyy puhelinnumerosi ja saldosi – tarkista ennen jakamista.")


def _fmt_eur(v):
    return "–" if v is None else f"{v:.2f} €".replace(".", ",")


async def _main() -> int:
    global PREPAID_BASE, ULM_BASE, ULM_REDIRECT_URI
    ap = argparse.ArgumentParser(
        description="Telia Prepaid -saldon lukutesti (sama logiikka kuin HA-integraatiossa)."
    )
    ap.add_argument("username", help="Minun Prepaid -tunnus (sähköposti)")
    ap.add_argument("--json", action="store_true", help="tulosta JSON-muodossa")
    ap.add_argument("--dump", nargs="?", const="telia_debug", metavar="KANSIO",
                    help="tallenna haetut sivut aina (oletus ./telia_debug)")
    ap.add_argument("-v", "--verbose", action="store_true", help="näytä pyynnöt ja lomakekentät")
    ap.add_argument("--base-url", help=argparse.SUPPRESS)  # testipalvelinta varten
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s %(message)s",
    )
    if args.base_url:
        PREPAID_BASE = ULM_BASE = args.base_url.rstrip("/")
        ULM_REDIRECT_URI = f"{PREPAID_BASE}/auth/callback"

    password = os.environ.get("TELIA_PASSWORD") or getpass.getpass("Salasana: ")
    client = UrllibTeliaPrepaidClient(args.username, password)

    try:
        data = await client.async_get_data()
    except TeliaPrepaidError as err:
        print(f"\n✗ {err}", file=sys.stderr)
        _dump(client.debug_pages, Path(args.dump or "telia_debug"))
        return 2 if isinstance(err, TeliaPrepaidAuthError) else 1

    if args.json:
        print(json.dumps(
            [{
                "name": s.name, "number": s.number, "subscription_id": s.subscription_id,
                "balance": s.balance, "bonus_balance": s.bonus_balance,
                "total_balance": s.total_balance,
                "valid_until": s.valid_until.isoformat() if s.valid_until else None,
                "days_remaining": s.days_remaining(),
                "subscription_type": s.subscription_type, "sim_type": s.sim_type, "status": s.status,
            } for s in data.values()],
            ensure_ascii=False, indent=2,
        ))
    else:
        print(f"\n✓ Kirjautuminen onnistui, liittymiä: {len(data)}")
        for s in data.values():
            days = s.days_remaining()
            vl = s.valid_until_local
            print(f"\n  {s.name or 'Liittymä'}  {s.number}  (lisätiedot: /fi/account/{s.subscription_id})")
            print(f"    Prepaid-saldo        {_fmt_eur(s.balance)}")
            print(f"    Bonussaldo           {_fmt_eur(s.bonus_balance)}")
            print(f"    Saldo yhteensä       {_fmt_eur(s.total_balance)}")
            print(f"    Liittymä voimassa    "
                  f"{vl.strftime('%d.%m.%Y klo %H.%M') if vl else '–'}"
                  f"{f'  ({days} pv jäljellä)' if days is not None else ''}")
            print(f"    Liittymätyyppi       {s.subscription_type or '–'}")
            print(f"    SIM-kortin tyyppi    {s.sim_type or '–'}")
            print(f"    Liittymän tila       {s.status or '–'}")
        missing = [s.number for s in data.values() if s.valid_until is None]
        if missing:
            print(f"\n! Voimassaolopäivää ei löytynyt liittymille {', '.join(missing)} "
                  "– aja uudelleen valinnalla --dump ja lähetä telia_debug/subscriptions.json.")
    if args.dump:
        _dump(client.debug_pages, Path(args.dump))
        raw = Path(args.dump) / "subscriptions.json"
        raw.write_text(mask(json.dumps([s.raw for s in data.values()], ensure_ascii=False, indent=2)),
                       encoding="utf-8")
        print(f"Liittymien raakadata: {raw.resolve()}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(_main()))
    except KeyboardInterrupt:
        sys.exit(130)
