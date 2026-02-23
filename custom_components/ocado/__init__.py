"""The Ocado integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import OcadoApiClient
from .const import CONF_REFRESH_TOKEN, CONF_SESSION_TOKEN, DOMAIN
from .coordinator import OcadoCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]

OcadoConfigEntry = ConfigEntry[OcadoCoordinator]  # type alias


async def async_setup_entry(hass: HomeAssistant, entry: OcadoConfigEntry) -> bool:
    """Set up Ocado from a config entry."""
    session = async_get_clientsession(hass)

    client = OcadoApiClient(
        session=session,
        session_token=entry.data[CONF_SESSION_TOKEN],
        refresh_token=entry.data[CONF_REFRESH_TOKEN],
    )

    coordinator = OcadoCoordinator(hass, client, entry)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: OcadoConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
