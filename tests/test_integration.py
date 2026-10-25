"""Testit paikallista Telia-jäljitelmää vasten (tests/mock_server.py, käynnistyy fixturessa)."""
import aiohttp
import pytest
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntryState
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.telia_prepaid import api
from custom_components.telia_prepaid.const import DOMAIN

from . import mock_server


@pytest.fixture(autouse=True)
def _server(telia_server):
    yield


async def _setup_entry(hass, wrong_password: bool = False) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=mock_server.USER,
        data={
            "username": mock_server.USER,
            "password": "vaara" if wrong_password else mock_server.PASSWORD,
        },
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _reauth_flows(hass):
    return [
        f
        for f in hass.config_entries.flow.async_progress_by_handler(DOMAIN)
        if f["context"]["source"] == config_entries.SOURCE_REAUTH
    ]


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


async def test_new_subscription_gets_sensors_without_reload(hass, monkeypatch):
    entry = await _setup_entry(hass)
    assert len(hass.states.async_all("sensor")) == 16
    monkeypatch.setattr(mock_server, "SUBS", mock_server.SUBS + [
        {"ulmId": 333, "msisdn": "358501112223", "displayName": "Uusi liittymä",
         "balanceInEuros": 5, "isConfirmed": True},
    ])
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert len(hass.states.async_all("sensor")) == 24
    assert hass.states.get("sensor.uusi_liittyma_prepaid_balance").state == "5.0"


@pytest.mark.parametrize("fault", ["token_fail", "subs_401", "session_403_html", "session_429"])
async def test_temporary_errors_do_not_ask_password(hass, fault):
    """Telian hetkellinen vika ei saa pysäyttää päivityksiä eikä kysyä salasanaa."""
    entry = await _setup_entry(hass)
    coordinator = entry.runtime_data
    mock_server.FAULTS[fault] = 1
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert not coordinator.last_update_success
    assert _reauth_flows(hass) == []
    assert coordinator.last_exception.retry_after == 30 * 60  # seuraava yritys 30 min, ei 6 h
    await coordinator.async_refresh()
    assert coordinator.last_update_success


async def test_single_rejected_login_is_retried(hass):
    mock_server.FAULTS["session_401"] = 1
    entry = await _setup_entry(hass)
    assert entry.state is ConfigEntryState.LOADED
    assert _reauth_flows(hass) == []


async def test_wrong_password_asks_password(hass):
    entry = await _setup_entry(hass, wrong_password=True)
    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert len(_reauth_flows(hass)) == 1


async def test_reauth_reloads_without_update_listener_warning(hass, caplog):
    # Kuten tuotannossa: integraatio on käynnissä, kun Telia hylkää tunnukset
    entry = await _setup_entry(hass)
    mock_server.FAULTS["session_401"] = 2
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    flow = _reauth_flows(hass)[0]
    result = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {"password": mock_server.PASSWORD}
    )
    await hass.async_block_till_done()
    assert result["reason"] == "reauth_successful"
    assert entry.state is ConfigEntryState.LOADED
    assert "update listener" not in caplog.text


async def test_days_remaining_changes_at_finnish_midnight(hass, freezer):
    freezer.move_to("2026-10-18 20:59:00+00:00")  # 23.59 Suomessa
    await _setup_entry(hass)
    assert hass.states.get("sensor.veikon_liittyma_days_remaining").state == "364"
    freezer.move_to("2026-10-18 21:00:05+00:00")
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.veikon_liittyma_days_remaining").state == "363"


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
