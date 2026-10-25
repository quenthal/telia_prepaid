"""Tietojen päivitys Telia Prepaid -palvelusta."""
from __future__ import annotations

import asyncio
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
from . import const
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
            return await self._get_data()
        except TeliaPrepaidAuthError as err:
            # HA lopettaa päivitykset, kunnes käyttäjä antaa salasanan uudelleen
            raise ConfigEntryAuthFailed(str(err)) from err
        except TeliaPrepaidParseError as err:
            directory = Path(self.hass.config.path(DEBUG_DIR))
            await self.hass.async_add_executor_job(
                _write_debug_pages, directory, dict(self.client.debug_pages)
            )
            raise self._update_failed(
                f"{err} Haetut sivut tallennettiin kansioon {directory} vianetsintää varten."
            ) from err
        except TeliaPrepaidError as err:
            raise self._update_failed(str(err)) from err

    async def _get_data(self) -> dict[str, Subscription]:
        """Hylätty kirjautuminen varmistetaan vielä kerran ennen salasanakyselyä."""
        try:
            return await self.client.async_get_data()
        except TeliaPrepaidAuthError as err:
            _LOGGER.warning(
                "%s Yritetään uudelleen %d s kuluttua.", err, const.AUTH_RETRY_DELAY_S
            )
            await asyncio.sleep(const.AUTH_RETRY_DELAY_S)
            return await self.client.async_get_data()

    def _update_failed(self, message: str) -> UpdateFailed:
        """Seuraava yritys RETRY_AFTER_ERROR_MIN kuluttua eikä vasta koko päivitysvälin päästä."""
        retry_s = const.RETRY_AFTER_ERROR_MIN * 60
        if self.update_interval is None or self.update_interval.total_seconds() <= retry_s:
            return UpdateFailed(message)
        try:
            return UpdateFailed(message, retry_after=retry_s)
        except TypeError:  # HA ennen retry_after-tukea
            return UpdateFailed(message)
