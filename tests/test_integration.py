"""Testit paikallista Telia-jäljitelmää vasten (tools/mock_server.py, portti 8765)."""
from unittest.mock import patch

import aiohttp
import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType

from custom_components.telia_prepaid import api
from custom_components.telia_prepaid.const import DOMAIN

BASE = "http://localhost:8765"
SESSIONS: list[aiohttp.ClientSession] = []


@pytest.fixture(autouse=True)
def mock_urls(socket_enabled):
    with patch.object(api, "PREPAID_BASE", BASE), patch.object(api, "ULM_BASE", BASE), patch.object(
        api, "ULM_REDIRECT_URI", f"{BASE}/auth/callback"
    ), patch(
        # Testikehyksen jaettu sessio käyttää eri tapahtumasilmukan resolveria
        "custom_components.telia_prepaid.coordinator.async_create_clientsession",
        lambda hass, **kw: SESSIONS.append(aiohttp.ClientSession(**kw)) or SESSIONS[-1],
    ):
        yield


async def test_flow_and_sensors(hass):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM

    bad = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"username": "veikko@example.com", "password": "vaara"}
    )
    assert bad["errors"] == {"base": "invalid_auth"}

    ok = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"username": "veikko@example.com", "password": "salainen"}
    )
    assert ok["type"] is FlowResultType.CREATE_ENTRY, ok
    await hass.async_block_till_done()

    states = {s.entity_id: s for s in hass.states.async_all("sensor")}
    for eid, s in sorted(states.items()):
        print(eid, "=", s.state, s.attributes.get("unit_of_measurement"), s.attributes.get("friendly_name"))
    assert states["sensor.veikon_liittyma_prepaid_balance"].state == "11.41"
    assert states["sensor.veikon_liittyma_bonus_balance"].state == "4.93"
    assert states["sensor.veikon_liittyma_total_balance"].state == "16.34"
    assert states["sensor.veikon_liittyma_valid_until"].state == "2027-10-16T21:00:00+00:00"
    assert states["sensor.veikon_liittyma_valid_until"].attributes["device_class"] == "timestamp"
    # pelkkä päivämäärä -> päivän alku Suomen aikaa
    assert states["sensor.mokin_reititin_valid_until"].state == "2027-01-31T22:00:00+00:00"
    assert states["sensor.veikon_liittyma_sim_type"].state == "SIM-kortti"
    assert states["sensor.veikon_liittyma_subscription_type"].state == "Telia Prepaid"
    assert states["sensor.mokin_reititin_sim_type"].state == "eSIM"
    assert len(states) == 16  # 2 vahvistettua liittymää x 8

    entry = hass.config_entries.async_entries(DOMAIN)[0]
    opt = await hass.config_entries.options.async_init(entry.entry_id)
    opt = await hass.config_entries.options.async_configure(opt["flow_id"], {"scan_interval_minutes": 120})
    assert opt["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert entry.runtime_data.update_interval.total_seconds() == 7200
    await hass.config_entries.async_unload(entry.entry_id)
    for session in SESSIONS:
        await session.close()


async def test_stale_action_ids_are_refreshed():
    """Jos Telia julkaisee uuden version, vanhat toimintotunnisteet haetaan uudelleen."""
    async with aiohttp.ClientSession(cookie_jar=api.new_cookie_jar()) as session:
        client = api.TeliaPrepaidClient(session, "veikko@example.com", "salainen")
        client._actions = {
            "getULMOpenIDToken": "7f" + "00" * 20,
            "getAllSubscriptions": "7f" + "00" * 20,
            "getSubscriptionByUlmId": "7f" + "00" * 20,
        }
        data = await client.async_get_data()
        assert data["0408179596"].balance == 11.41
        assert data["0408179596"].valid_until.isoformat() == "2027-10-16T21:00:00+00:00"
        assert data["0408179596"].valid_until_local.date().isoformat() == "2027-10-17"
