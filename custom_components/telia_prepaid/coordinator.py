"""Tietojen päivitys Telia Prepaid -palvelusta."""
from __future__ import annotations

import logging
from datetime import timedelta
from pathlib import Path

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    new_cookie_jar,
    Subscription,
    TeliaPrepaidAuthError,
    TeliaPrepaidClient,
    TeliaPrepaidError,
    TeliaPrepaidParseError,
)
from .const import CONF_SCAN_INTERVAL_MIN, DEBUG_DIR, DEFAULT_SCAN_INTERVAL_MIN, DOMAIN

_LOGGER = logging.getLogger(__name__)

type TeliaPrepaidConfigEntry = ConfigEntry["TeliaPrepaidCoordinator"]


def _write_debug_pages(directory: Path, pages: dict[str, str]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for name, html in pages.items():
        (directory / f"{name}.html").write_text(html, encoding="utf-8")


class TeliaPrepaidCoordinator(DataUpdateCoordinator[dict[str, Subscription]]):
    """Hakee kaikkien tilin liittymien tiedot kerralla."""

    config_entry: TeliaPrepaidConfigEntry

    def __init__(self, hass: HomeAssistant, entry: TeliaPrepaidConfigEntry) -> None:
        minutes = entry.options.get(CONF_SCAN_INTERVAL_MIN, DEFAULT_SCAN_INTERVAL_MIN)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(minutes=minutes),
        )
        # Oma eväste-säiliö, jotta Telian istunto ei sekoitu muiden integraatioiden kanssa
        session = async_create_clientsession(hass, cookie_jar=new_cookie_jar())
        self.client = TeliaPrepaidClient(
            session, entry.data[CONF_USERNAME], entry.data[CONF_PASSWORD]
        )

    async def _async_update_data(self) -> dict[str, Subscription]:
        try:
            return await self.client.async_get_data()
        except TeliaPrepaidAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except TeliaPrepaidParseError as err:
            directory = Path(self.hass.config.path(DEBUG_DIR))
            await self.hass.async_add_executor_job(
                _write_debug_pages, directory, dict(self.client.debug_pages)
            )
            raise UpdateFailed(
                f"{err} Haetut sivut tallennettiin kansioon {directory} vianetsintää varten."
            ) from err
        except TeliaPrepaidError as err:
            raise UpdateFailed(str(err)) from err
