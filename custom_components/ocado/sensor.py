"""Sensor platform for Ocado integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import OcadoConfigEntry
from .api import OcadoData
from .const import DOMAIN, MANUFACTURER
from .coordinator import OcadoCoordinator


def _parse_iso_date(dt_str: str) -> datetime | None:
    """Parse an ISO datetime string, returning None on failure."""
    if not dt_str:
        return None
    try:
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


@dataclass(frozen=True, kw_only=True)
class OcadoSensorEntityDescription(SensorEntityDescription):
    """Describe an Ocado sensor."""

    value_fn: Callable[[OcadoData], Any]
    attributes_fn: Callable[[OcadoData], dict[str, Any]] | None = None


# ── Sensor definitions ────────────────────────────────────────────────────

SENSOR_DESCRIPTIONS: tuple[OcadoSensorEntityDescription, ...] = (
    # ── Delivery sensors ──────────────────────────────────────────────────
    OcadoSensorEntityDescription(
        key="upcoming_orders",
        translation_key="upcoming_orders",
        icon="mdi:truck-delivery",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="orders",
        value_fn=lambda d: len(d.upcoming_orders),
        attributes_fn=lambda d: {
            "orders": [
                {
                    "id": o.id,
                    "status": o.status_message,
                    "items": o.items_count,
                    "total": f"{o.currency} {o.total_price}",
                    "delivery_start": o.delivery_slot_start,
                    "delivery_end": o.delivery_slot_end,
                    "address": o.delivery_address,
                    "editable": o.is_editable,
                }
                for o in d.upcoming_orders
            ]
        },
    ),
    OcadoSensorEntityDescription(
        key="next_delivery_date",
        translation_key="next_delivery_date",
        icon="mdi:calendar-truck",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda d: (
            _parse_iso_date(d.upcoming_orders[0].delivery_slot_start)
            if d.upcoming_orders
            else None
        ),
        attributes_fn=lambda d: (
            {
                "order_id": d.upcoming_orders[0].id,
                "delivery_method": d.upcoming_orders[0].delivery_method,
                "address": d.upcoming_orders[0].delivery_address,
            }
            if d.upcoming_orders
            else {}
        ),
    ),
    OcadoSensorEntityDescription(
        key="next_delivery_slot_end",
        translation_key="next_delivery_slot_end",
        icon="mdi:clock-end",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda d: (
            _parse_iso_date(d.upcoming_orders[0].delivery_slot_end)
            if d.upcoming_orders
            else None
        ),
        attributes_fn=lambda d: (
            {
                "slot_start": d.upcoming_orders[0].delivery_slot_start,
                "slot_end": d.upcoming_orders[0].delivery_slot_end,
                "delivery_method": d.upcoming_orders[0].delivery_method,
            }
            if d.upcoming_orders
            else {}
        ),
    ),
    OcadoSensorEntityDescription(
        key="next_delivery_items",
        translation_key="next_delivery_items",
        icon="mdi:package-variant",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="items",
        value_fn=lambda d: (
            d.upcoming_orders[0].items_count if d.upcoming_orders else None
        ),
    ),
    OcadoSensorEntityDescription(
        key="next_delivery_total",
        translation_key="next_delivery_total",
        icon="mdi:currency-gbp",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement="GBP",
        suggested_display_precision=2,
        value_fn=lambda d: (
            float(d.upcoming_orders[0].total_price) if d.upcoming_orders else None
        ),
        attributes_fn=lambda d: (
            {
                "slot_cost": float(d.upcoming_orders[0].slot_cost)
                if d.upcoming_orders[0].slot_cost
                else None,
                "currency": d.upcoming_orders[0].currency,
            }
            if d.upcoming_orders
            else {}
        ),
    ),
    OcadoSensorEntityDescription(
        key="next_delivery_status",
        translation_key="next_delivery_status",
        icon="mdi:truck-check",
        value_fn=lambda d: (
            d.upcoming_orders[0].status_message if d.upcoming_orders else None
        ),
        attributes_fn=lambda d: (
            {
                "status_code": d.upcoming_orders[0].status,
                "is_editable": d.upcoming_orders[0].is_editable,
            }
            if d.upcoming_orders
            else {}
        ),
    ),
    OcadoSensorEntityDescription(
        key="active_order_count",
        translation_key="active_order_count",
        icon="mdi:counter",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="orders",
        value_fn=lambda d: d.active_order_count,
    ),
    # ── Cart sensors ──────────────────────────────────────────────────────
    OcadoSensorEntityDescription(
        key="cart_items",
        translation_key="cart_items",
        icon="mdi:cart",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="items",
        value_fn=lambda d: d.cart.item_count,
    ),
    OcadoSensorEntityDescription(
        key="cart_total",
        translation_key="cart_total",
        icon="mdi:cart-variant",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement="GBP",
        suggested_display_precision=2,
        value_fn=lambda d: float(d.cart.total_price) if d.cart.total_price else 0.0,
    ),
    # ── Slot availability ─────────────────────────────────────────────────
    OcadoSensorEntityDescription(
        key="next_available_slot",
        translation_key="next_available_slot",
        icon="mdi:calendar-clock",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda d: (
            _parse_iso_date(d.next_slot.start_time) if d.next_slot else None
        ),
        attributes_fn=lambda d: (
            {
                "end_time": _parse_iso_date(d.next_slot.end_time),
                "slot_type": d.next_slot.slot_type,
                "delivery_method": d.next_slot.delivery_method,
                "address": d.next_slot.address,
            }
            if d.next_slot
            else {}
        ),
    ),
    # ── Last delivery ─────────────────────────────────────────────────────
    OcadoSensorEntityDescription(
        key="last_delivery_date",
        translation_key="last_delivery_date",
        icon="mdi:truck-check-outline",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda d: (
            _parse_iso_date(d.delivered_orders[0].delivery_slot_start)
            if d.delivered_orders
            else None
        ),
        attributes_fn=lambda d: (
            {
                "order_id": d.delivered_orders[0].id,
                "items": d.delivered_orders[0].items_count,
                "total": float(d.delivered_orders[0].total_price)
                if d.delivered_orders[0].total_price
                else 0.0,
                "currency": d.delivered_orders[0].currency,
            }
            if d.delivered_orders
            else {}
        ),
    ),
    # ── Subscription ──────────────────────────────────────────────────────
    OcadoSensorEntityDescription(
        key="delivery_subscription",
        translation_key="delivery_subscription",
        icon="mdi:star-circle",
        value_fn=lambda d: d.subscription_type if d.has_delivery_subscription else "Inactive",
        attributes_fn=lambda d: {
            "active": d.has_delivery_subscription,
        },
    ),
    # ── Diagnostic sensors (user info) ────────────────────────────────────
    OcadoSensorEntityDescription(
        key="account_name",
        translation_key="account_name",
        icon="mdi:account",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.user.full_name or d.user.first_name or None,
    ),
    OcadoSensorEntityDescription(
        key="account_email",
        translation_key="account_email",
        icon="mdi:email",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.user.username or None,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OcadoConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Ocado sensors from a config entry."""
    coordinator = entry.runtime_data

    async_add_entities(
        OcadoSensor(coordinator, description, entry)
        for description in SENSOR_DESCRIPTIONS
    )


class OcadoSensor(CoordinatorEntity[OcadoCoordinator], SensorEntity):
    """Representation of an Ocado sensor."""

    entity_description: OcadoSensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: OcadoCoordinator,
        description: OcadoSensorEntityDescription,
        entry: OcadoConfigEntry,
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.title,
            "manufacturer": MANUFACTURER,
            "model": "Ocado Account",
            "entry_type": DeviceEntryType.SERVICE,
        }

    @property
    def native_value(self) -> Any:
        """Return the sensor value."""
        if self.coordinator.data is None:
            return None
        try:
            return self.entity_description.value_fn(self.coordinator.data)
        except (IndexError, AttributeError, TypeError):
            return None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return additional attributes."""
        if (
            self.coordinator.data is None
            or self.entity_description.attributes_fn is None
        ):
            return None
        try:
            return self.entity_description.attributes_fn(self.coordinator.data)
        except (IndexError, AttributeError, TypeError):
            return None
