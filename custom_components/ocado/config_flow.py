"""Config flow for Ocado integration."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import OcadoApiClient, OcadoAuthError
from .const import CONF_REFRESH_TOKEN, CONF_SESSION_TOKEN, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_SESSION_TOKEN): str,
        vol.Required(CONF_REFRESH_TOKEN): str,
    }
)


class OcadoConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Ocado."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step — token entry."""
        errors: dict[str, str] = {}

        if user_input is not None:
            session = async_get_clientsession(self.hass)
            client = OcadoApiClient(
                session=session,
                session_token=user_input[CONF_SESSION_TOKEN],
                refresh_token=user_input[CONF_REFRESH_TOKEN],
            )

            try:
                user_profile = await client.async_validate_tokens()
            except OcadoAuthError:
                errors["base"] = "invalid_auth"
            except aiohttp.ClientError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error during Ocado setup")
                errors["base"] = "unknown"
            else:
                # Use the username (email) as the unique ID
                unique_id = user_profile.username or user_profile.customer_id
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=user_profile.full_name or user_profile.username or "Ocado",
                    data={
                        CONF_SESSION_TOKEN: client.tokens.token,
                        CONF_REFRESH_TOKEN: client.tokens.refresh_token,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
            description_placeholders={
                "docs_url": "https://github.com/stormsys/ha-ocado#obtaining-tokens",
            },
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Handle re-authentication when tokens expire."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle re-auth token entry."""
        errors: dict[str, str] = {}

        if user_input is not None:
            session = async_get_clientsession(self.hass)
            client = OcadoApiClient(
                session=session,
                session_token=user_input[CONF_SESSION_TOKEN],
                refresh_token=user_input[CONF_REFRESH_TOKEN],
            )

            try:
                await client.async_validate_tokens()
            except OcadoAuthError:
                errors["base"] = "invalid_auth"
            except aiohttp.ClientError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error during Ocado re-auth")
                errors["base"] = "unknown"
            else:
                entry = self.hass.config_entries.async_get_entry(
                    self.context["entry_id"]
                )
                if entry:
                    self.hass.config_entries.async_update_entry(
                        entry,
                        data={
                            CONF_SESSION_TOKEN: client.tokens.token,
                            CONF_REFRESH_TOKEN: client.tokens.refresh_token,
                        },
                    )
                    await self.hass.config_entries.async_reload(entry.entry_id)
                    return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )
