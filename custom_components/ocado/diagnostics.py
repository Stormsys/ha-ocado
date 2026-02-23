"""Diagnostics support for Ocado integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import OcadoConfigEntry
from .const import CONF_REFRESH_TOKEN, CONF_SESSION_TOKEN

TO_REDACT_CONFIG = {CONF_SESSION_TOKEN, CONF_REFRESH_TOKEN}
TO_REDACT_DATA = {"username", "account_email", "customer_id", "address", "delivery_address"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: OcadoConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    data = coordinator.data

    diag: dict[str, Any] = {
        "config_entry": async_redact_data(dict(entry.data), TO_REDACT_CONFIG),
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "update_interval": str(coordinator.update_interval),
        },
    }

    if data:
        diag["data"] = {
            "user": {
                "first_name": data.user.first_name,
                "full_name": data.user.full_name,
                "username": "**REDACTED**",
                "customer_id": "**REDACTED**",
            },
            "upcoming_orders_count": len(data.upcoming_orders),
            "delivered_orders_count": len(data.delivered_orders),
            "upcoming_orders": [
                {
                    "id": o.id,
                    "status": o.status,
                    "status_message": o.status_message,
                    "items_count": o.items_count,
                    "total_price": o.total_price,
                    "currency": o.currency,
                    "delivery_address": "**REDACTED**",
                    "delivery_slot_start": o.delivery_slot_start,
                    "delivery_slot_end": o.delivery_slot_end,
                    "delivery_method": o.delivery_method,
                    "is_editable": o.is_editable,
                }
                for o in data.upcoming_orders
            ],
            "cart": {
                "item_count": data.cart.item_count,
                "total_price": data.cart.total_price,
                "currency": data.cart.currency,
            },
            "next_slot": (
                {
                    "slot_id": data.next_slot.slot_id,
                    "slot_type": data.next_slot.slot_type,
                    "start_time": data.next_slot.start_time,
                    "end_time": data.next_slot.end_time,
                    "delivery_method": data.next_slot.delivery_method,
                    "address": "**REDACTED**",
                }
                if data.next_slot
                else None
            ),
            "active_order_count": data.active_order_count,
            "has_delivery_subscription": data.has_delivery_subscription,
            "subscription_type": data.subscription_type,
        }

    return diag
