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
        # Periodic token refresh — never triggers re-auth directly.
        # If the token is truly dead the data-fetch path will catch it.
        self._refresh_counter += 1
        if self._refresh_counter >= self._refresh_every_n:
            try:
                await self._async_refresh_and_persist()
                self._refresh_counter = 0
            except OcadoAuthError:
                # Might be transient; let the data fetch decide.
                self._refresh_counter = 0
                _LOGGER.warning(
                    "Periodic token refresh returned auth error; "
                    "data fetch will determine if re-auth is needed"
                )
            except Exception:
                # Network / transient error — retry on the next poll.
                self._refresh_counter = self._refresh_every_n - 1
                _LOGGER.debug(
                    "Periodic token refresh failed (transient); "
                    "will retry next poll"
                )

        try:
            return await self.client.async_get_all_data()
        except OcadoAuthError as err:
            # Auth failure — attempt one token refresh before giving up.
            try:
                await self._async_refresh_and_persist()
            except OcadoAuthError:
                raise ConfigEntryAuthFailed(
                    "Ocado authentication failed. Please re-authenticate."
                ) from err
            except Exception as refresh_err:
                # Network/transient error during refresh — not an auth issue.
                raise UpdateFailed(
                    f"Could not refresh Ocado token: {refresh_err}"
                ) from refresh_err
            # Refresh succeeded — retry the data fetch once.
            try:
                return await self.client.async_get_all_data()
            except OcadoAuthError:
                raise ConfigEntryAuthFailed(
                    "Ocado authentication failed. Please re-authenticate."
                ) from err
            except Exception as retry_err:
                raise UpdateFailed(
                    f"Error fetching Ocado data: {retry_err}"
                ) from retry_err
        except Exception as err:
            raise UpdateFailed(f"Error fetching Ocado data: {err}") from err

    async def _async_refresh_and_persist(self) -> None:
        """Refresh the token and persist new tokens to the config entry."""
        try:
            new_tokens = await self.client.async_refresh_token()
        except OcadoAuthError:
            _LOGGER.warning("Ocado token refresh failed — auth error")
            raise
        except Exception:
            _LOGGER.warning("Ocado token refresh failed (non-auth)", exc_info=True)
            raise
        # Persist the new tokens so they survive HA restarts
        self.hass.config_entries.async_update_entry(
            self.config_entry,
            data={
                CONF_SESSION_TOKEN: new_tokens.token,
                CONF_REFRESH_TOKEN: new_tokens.refresh_token,
            },
        )
        _LOGGER.debug("Ocado tokens refreshed and persisted")
