from unittest.mock import patch

import aiohttp
import pytest
from aiohttp import web

from custom_components.telia_prepaid import api

from . import mock_server

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture
async def telia_server(socket_enabled):
    """Käynnistää Telia-jäljitelmän vapaaseen porttiin ja ohjaa integraation siihen."""
    runner = web.AppRunner(mock_server.make_app())
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    # localhost eikä IP: aiohttp:n evästesäiliö ei hyväksy IP-osoitteiden evästeitä
    base = f"http://localhost:{site._server.sockets[0].getsockname()[1]}"
    for name in mock_server.FAULTS:
        mock_server.FAULTS[name] = 0
    sessions: list[aiohttp.ClientSession] = []

    def create_session(hass, **kwargs):
        # Testikehyksen jaettu sessio käyttää eri tapahtumasilmukan resolveria
        sessions.append(aiohttp.ClientSession(**kwargs))
        return sessions[-1]

    with patch.object(api, "PREPAID_BASE", base), patch.object(api, "ULM_BASE", base), patch.object(
        api, "ULM_REDIRECT_URI", f"{base}/auth/callback"
    ), patch(
        "custom_components.telia_prepaid.coordinator.async_create_clientsession", create_session
    ), patch("custom_components.telia_prepaid.const.AUTH_RETRY_DELAY_S", 0):
        yield base
    for session in sessions:
        await session.close()
    await runner.cleanup()
