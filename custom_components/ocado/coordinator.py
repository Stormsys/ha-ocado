"""DataUpdateCoordinator for Ocado integration."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import OcadoApiClient, OcadoAuthError, OcadoData
from .const import (
    CONF_REFRESH_TOKEN,
    CONF_SESSION_TOKEN,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    TOKEN_REFRESH_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


class OcadoCoordinator(DataUpdateCoordinator[OcadoData]):
    """Ocado data update coordinator.

    Handles:
    - Periodic data polling (every 10 minutes)
    - Periodic token refresh (every 1 hour)
    - Persisting refreshed tokens back to config entry
    - Triggering re-auth flow on permanent auth failure
    """

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        client: OcadoApiClient,
        entry: ConfigEntry,
    ) -> None:
        """Initialise the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.client = client
        self.config_entry = entry
        self._refresh_counter = 0
        # How many data polls between token refreshes
        self._refresh_every_n = max(
            1, TOKEN_REFRESH_INTERVAL // DEFAULT_SCAN_INTERVAL
        )

    async def _async_update_data(self) -> OcadoData:
        """Fetch data from Ocado API.

        Also periodically refreshes the session token.
        """
        # Periodic token refresh
        self._refresh_counter += 1
        if self._refresh_counter >= self._refresh_every_n:
            self._refresh_counter = 0
            await self._async_refresh_and_persist()

        try:
            return await self.client.async_get_all_data()
        except OcadoAuthError as err:
            # Try one refresh before giving up
            try:
                await self._async_refresh_and_persist()
                return await self.client.async_get_all_data()
            except OcadoAuthError:
                raise ConfigEntryAuthFailed(
                    "Ocado authentication failed. Please re-authenticate."
                ) from err
        except Exception as err:
            raise UpdateFailed(f"Error fetching Ocado data: {err}") from err

    async def _async_refresh_and_persist(self) -> None:
        """Refresh the token and persist new tokens to the config entry."""
        try:
            new_tokens = await self.client.async_refresh_token()
            # Persist the new tokens so they survive HA restarts
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data={
                    CONF_SESSION_TOKEN: new_tokens.token,
                    CONF_REFRESH_TOKEN: new_tokens.refresh_token,
                },
            )
            _LOGGER.debug("Ocado tokens refreshed and persisted")
        except OcadoAuthError:
            _LOGGER.warning(
                "Ocado token refresh failed — will trigger re-auth on next poll"
            )
            raise
        except Exception:
            _LOGGER.warning("Ocado token refresh failed (non-auth)", exc_info=True)
