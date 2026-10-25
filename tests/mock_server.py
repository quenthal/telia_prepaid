"""Telia Prepaid -jäljitelmä testeihin (id.telia.fi + prepaid.telia.fi samassa portissa).

Jäljittelee: session/start, OIDC authorize -> callback-sivu, jonka palvelintoiminto
getULMOpenIDToken(code) palauttaa pääsytunnisteen,
tilisivu jonka JS-tiedostossa createServerReference-tunnisteet, ja Next.js
Server Actionit getAllSubscriptions / getSubscriptionByUlmId.

Testit käynnistävät palvelimen itse (tests/conftest.py); käsin: python tests/mock_server.py.
FAULTS-laskureilla simuloidaan Telian hetkellisiä vikoja (laskuri = montako kertaa).
"""
import json
import secrets

from aiohttp import web

PORT = 8765
USER, PASSWORD = "veikko@example.com", "salainen"
ULM_SESSIONS: set[str] = set()
CODES: dict[str, str] = {}
TOKENS: set[str] = set()
A_ALL = "7f" + "a1" * 20
A_ONE = "7f" + "b2" * 20
A_TOKEN = "7f" + "c3" * 20
A_COOKIE = "7f" + "d4" * 20

FAULTS = {
    "session_401": 0,  # session/start hylkää tunnukset (JSON)
    "session_403_html": 0,  # palomuurin HTML-sivu
    "session_429": 0,  # kirjautumisten rajoitus
    "token_fail": 0,  # koodin vaihto palauttaa success: false
    "subs_401": 0,  # liittymähaku palauttaa tilan 401
}


def _fault(name: str) -> bool:
    if FAULTS[name] > 0:
        FAULTS[name] -= 1
        return True
    return False

SUBS = [
    {"ulmId": 42522967, "msisdn": "358408179596", "displayName": "Veikon liittymä",
     "balanceInEuros": 11.41, "bonusBalanceInEuros": 4.93, "isConfirmed": True,
     "expiryDateUtc": "2027-10-16T21:00:00.000Z", "simType": "SIM", "connectionType": "VOICE",
     "status": "ACTIVE", "purchaseHistory": [], "activePackages": []},
    {"ulmId": 111, "msisdn": "358451234567", "displayName": "Mökin reititin",
     "balanceInEuros": 0, "bonusBalanceInEuros": 0, "isConfirmed": True, "activePackages": []},
    {"ulmId": 222, "msisdn": "358409999999", "displayName": None, "balanceInEuros": 0,
     "isConfirmed": False},
]
DETAILS = {
    "42522967": {"ulmId": 42522967, "msisdn": "358408179596",
                 "displayName": "Veikon liittymä", "expiryDateUtc": "$D2027-10-16T21:00:00.000Z",
                 "simType": "SIM", "connectionType": "VOICE", "status": "ACTIVE",
                 "balanceInEuros": 11.41, "bonusBalanceInEuros": 4.93},
    "111": {"validUntil": "2027-02-01", "productName": "Telia Prepaid", "simType": "eSIM",
            "balanceInEuros": 0, "bonusBalanceInEuros": 0},
}


async def session_start(r):
    body = await r.json()
    if _fault("session_403_html"):
        return web.Response(text="<html>Access Denied</html>", status=403, content_type="text/html")
    if _fault("session_429"):
        return web.json_response({"error": "too_many_requests"}, status=429)
    if _fault("session_401") or body.get("username") != USER or body.get("credential") != PASSWORD:
        return web.json_response({"error": "invalid"}, status=401)
    sid = "aB3/" + secrets.token_hex(8) + "+x=="
    ULM_SESSIONS.add(sid)
    resp = web.json_response({"userId": 987654, "processId": "p1", "status": "OK"})
    # Raaka Set-Cookie kuten Javassa: arvoa ei lainausmerkitä
    resp.headers.add("Set-Cookie", f"ULMSESSION={sid}; Path=/; HttpOnly; SameSite=None")
    return resp


async def authorize(r):
    # Tiukka tarkistus raa'asta otsakkeesta (lainausmerkitty arvo ei kelpaa)
    raw = dict(
        p.strip().split("=", 1) for p in r.headers.get("Cookie", "").split(";") if "=" in p
    )
    if raw.get("ULMSESSION") not in ULM_SESSIONS:
        return web.Response(text="<html>login</html>", content_type="text/html")
    assert r.query["client_id"] == "1fec972e-36b3-4566-96cb-987d3750e7b4"
    code = secrets.token_hex(8)
    CODES[code] = r.query["state"]
    raise web.HTTPFound(f"{r.query['redirect_uri']}?code={code}&state={r.query['state']}")


async def callback(r):
    if "Next-Action" in r.headers:
        return await action(r)
    # Kuten oikea sivu: pelkkä selainkomponentti, tunniste haetaan palvelintoiminnolla
    return web.Response(
        text='<html><head><script src="/_next/static/chunks/app/(auth)/auth/callback/page-x.js" async="">'
        "</script></head><body></body></html>",
        content_type="text/html",
    )


async def account(r):
    if "Next-Action" in r.headers:
        return await action(r)
    return web.Response(
        text='<html><head><script src="/_next/static/chunks/5333-abc.js" async=""></script></head>'
        "<body></body></html>",
        content_type="text/html",
    )


async def chunk(r):
    if "callback" in r.path:
        js = (
            f'i=(0,n.createServerReference)("{A_TOKEN}",n.callServer,void 0,n.findSourceMapURL,"getULMOpenIDToken");'
            f'o=(0,a.createServerReference)("{A_COOKIE}",a.callServer,void 0,a.findSourceMapURL,"setLoggedInCookie");'
        )
        return web.Response(text=js, content_type="application/javascript")
    js = (
        f'let R=(0,w.createServerReference)("{A_ALL}",w.callServer,void 0,w.findSourceMapURL,"getAllSubscriptions"),'
        f'b=(0,w.createServerReference)("{A_ONE}",w.callServer,void 0,w.findSourceMapURL,"getSubscriptionByUlmId");'
    )
    return web.Response(text=js, content_type="application/javascript")


async def action(r):
    args = json.loads(await r.text())
    if r.headers["Next-Action"] not in (A_TOKEN, A_COOKIE, A_ALL, A_ONE):
        return web.Response(status=404, text="Server action not found")
    if r.headers["Next-Action"] == A_TOKEN:
        if CODES.pop(args[0], None) is None or _fault("token_fail"):
            result = {"success": False}
        else:
            token = "eyJhbGciOiJSUzI1NiJ9." + secrets.token_urlsafe(24) + "." + secrets.token_urlsafe(24)
            TOKENS.add(token)
            result = {"success": True, "accessToken": token, "expiresIn": 3600, "username": USER}
    elif r.headers["Next-Action"] == A_COOKIE:
        result = None
    elif args[0] not in TOKENS or _fault("subs_401"):
        result = {"status": 401, "data": None}
    elif r.headers["Next-Action"] == A_ALL:
        result = {"status": 200, "data": SUBS}
    elif r.headers["Next-Action"] == A_ONE:
        d = DETAILS.get(str(args[1]))
        result = {"status": 200 if d else 404, "data": d}
    else:
        return web.Response(status=404, text="Server action not found")
    text = '0:{"a":"$@1","f":"","b":"build1"}\n1:' + json.dumps(result) + "\n"
    return web.Response(text=text, content_type="text/x-component")


def make_app() -> web.Application:
    app = web.Application()
    app.router.add_post("/rest/v80/session/start", session_start)
    app.router.add_get("/oidc/authorize", authorize)
    app.router.add_route("*", "/auth/callback", callback)
    app.router.add_route("*", "/fi/account", account)
    app.router.add_get("/_next/static/chunks/{name:.+}", chunk)
    return app


if __name__ == "__main__":
    web.run_app(make_app(), port=PORT, print=None)
