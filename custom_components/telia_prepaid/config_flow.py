"""Asetusvirta Telia Prepaid -integraatiolle."""
from __future__ import annotations

import logging
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import (
    new_cookie_jar,
    TeliaPrepaidAuthError,
    TeliaPrepaidClient,
    TeliaPrepaidError,
    TeliaPrepaidParseError,
)
from .const import (
    CONF_SCAN_INTERVAL_MIN,
    DEBUG_DIR,
    DEFAULT_SCAN_INTERVAL_MIN,
    DOMAIN,
    MIN_SCAN_INTERVAL_MIN,
)
from .coordinator import _write_debug_pages

_LOGGER = logging.getLogger(__name__)

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): TextSelector(
            TextSelectorConfig(type=TextSelectorType.EMAIL, autocomplete="username")
        ),
        vol.Required(CONF_PASSWORD): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD, autocomplete="current-password")
        ),
    }
)


async def _validate(hass: HomeAssistant, username: str, password: str) -> dict[str, str]:
    """Kokeilee kirjautumista. Palauttaa virheet lomakkeelle."""
    # Lyhytikäinen oma istunto tunnusten tarkistukseen
    session = aiohttp.ClientSession(cookie_jar=new_cookie_jar())
    client = TeliaPrepaidClient(session, username, password)
    try:
        await client.async_validate()
    except TeliaPrepaidAuthError:
        return {"base": "invalid_auth"}
    except TeliaPrepaidParseError as err:
        _LOGGER.warning("Telia Prepaid: sivua ei tunnistettu: %s", err)
        await hass.async_add_executor_job(
            _write_debug_pages, Path(hass.config.path(DEBUG_DIR)), dict(client.debug_pages)
        )
        return {"base": "cannot_parse"}
    except TeliaPrepaidError as err:
        _LOGGER.warning("Telia Prepaid: yhteysvirhe: %s", err)
        return {"base": "cannot_connect"}
    except Exception:  # noqa: BLE001
        _LOGGER.exception("Odottamaton virhe")
        return {"base": "unknown"}
    finally:
        await session.close()
    return {}


class TeliaPrepaidConfigFlow(ConfigFlow, domain=DOMAIN):
    """Käyttöliittymän asetusvirta."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            username = user_input[CONF_USERNAME].strip()
            await self.async_set_unique_id(username.lower())
            self._abort_if_unique_id_configured()
            errors = await _validate(self.hass, username, user_input[CONF_PASSWORD])
            if not errors:
                return self.async_create_entry(
                    title=f"Telia Prepaid ({username})",
                    data={CONF_USERNAME: username, CONF_PASSWORD: user_input[CONF_PASSWORD]},
                )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(USER_SCHEMA, user_input),
            errors=errors,
            description_placeholders={"debug_dir": DEBUG_DIR},
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = await _validate(
                self.hass, entry.data[CONF_USERNAME], user_input[CONF_PASSWORD]
            )
            if not errors:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_PASSWORD: user_input[CONF_PASSWORD]}
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PASSWORD): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    )
                }
            ),
            errors=errors,
            description_placeholders={"username": entry.data[CONF_USERNAME], "debug_dir": DEBUG_DIR},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> OptionsFlow:
        return TeliaPrepaidOptionsFlow()


class TeliaPrepaidOptionsFlow(OptionsFlowWithReload):
    """Päivitysvälin asetus. HA lataa integraation uudelleen, kun asetus muuttuu."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(
                data={CONF_SCAN_INTERVAL_MIN: int(user_input[CONF_SCAN_INTERVAL_MIN])}
            )
        current = self.config_entry.options.get(CONF_SCAN_INTERVAL_MIN, DEFAULT_SCAN_INTERVAL_MIN)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SCAN_INTERVAL_MIN, default=current): NumberSelector(
                        NumberSelectorConfig(
                            min=MIN_SCAN_INTERVAL_MIN,
                            max=1440,
                            step=15,
                            unit_of_measurement="min",
                            mode=NumberSelectorMode.BOX,
                        )
                    )
                }
            ),
        )
