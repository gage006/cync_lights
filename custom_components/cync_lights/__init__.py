"""The Cync Room Lights integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from .const import DOMAIN
from .cync_hub import CyncHub

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = ["light","binary_sensor","switch","fan"]

SERVICE_REFRESH = "refresh"

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Cync Room Lights from a config entry."""

    hass.data.setdefault(DOMAIN, {})
    remove_options_update_listener = entry.add_update_listener(options_update_listener)
    hub = CyncHub(entry.data, entry.options, remove_options_update_listener)
    hass.data[DOMAIN][entry.entry_id] = hub
    hub.start_tcp_client()

    # Expose a service so users (and automations) can force a full-state refresh
    # on demand — e.g. after changing a light from the Cync app, whose color
    # changes are not pushed to Home Assistant in real time. Register it once,
    # regardless of how many config entries (Cync accounts) are set up.
    if not hass.services.has_service(DOMAIN, SERVICE_REFRESH):

        async def handle_refresh(call: ServiceCall) -> None:
            """Request a full state refresh from every configured Cync hub."""
            for hub in hass.data[DOMAIN].values():
                if hub.loop is None:
                    _LOGGER.warning("Cync refresh skipped: TCP loop not started yet")
                    continue
                if not hub.connected_devices_updated:
                    _LOGGER.warning("Cync refresh skipped: connected devices not yet discovered")
                    continue
                # The hub's TCP work runs on a background-thread event loop, so
                # bridge onto it rather than touching hub state from this loop.
                hub.loop.call_soon_threadsafe(hub._request_full_state)

        hass.services.async_register(DOMAIN, SERVICE_REFRESH, handle_refresh)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True

async def options_update_listener(
    hass: HomeAssistant, config_entry: config_entries.ConfigEntry
):
    """Handle options update."""
    await hass.config_entries.async_reload(config_entry.entry_id)

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    hub = hass.data[DOMAIN][entry.entry_id]
    hub.remove_options_update_listener()
    hub.disconnect()
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
        # Remove the shared refresh service only when the last entry is unloaded.
        if not hass.data[DOMAIN]:
            hass.services.async_remove(DOMAIN, SERVICE_REFRESH)

    return unload_ok
