"""Async Ocado API client for Home Assistant."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

import aiohttp

from .const import API_BASE, API_KEY, BANNER_ID, UA_API

_LOGGER = logging.getLogger(__name__)


@dataclass
class OcadoTokens:
    """Session tokens."""

    token: str
    refresh_token: str


@dataclass
class OcadoOrder:
    """Parsed order."""

    id: str
    status: str
    status_message: str
    items_count: int
    total_price: str
    currency: str
    delivery_address: str
    delivery_slot_start: str
    delivery_slot_end: str
    delivery_method: str
    slot_cost: str = ""
    is_editable: bool = False


@dataclass
class OcadoCart:
    """Simplified cart data."""

    item_count: int = 0
    total_price: str = "0.00"
    currency: str = "GBP"


@dataclass
class OcadoDeliverySlot:
    """Next available delivery slot."""

    slot_id: str = ""
    slot_type: str = ""
    start_time: str = ""
    end_time: str = ""
    address: str = ""
    delivery_method: str = ""


@dataclass
class OcadoUserProfile:
    """User profile data."""

    first_name: str = ""
    full_name: str = ""
    username: str = ""
    customer_id: str = ""


@dataclass
class OcadoData:
    """Container for all Ocado data returned by the coordinator."""

    user: OcadoUserProfile = field(default_factory=OcadoUserProfile)
    upcoming_orders: list[OcadoOrder] = field(default_factory=list)
    delivered_orders: list[OcadoOrder] = field(default_factory=list)
    cart: OcadoCart = field(default_factory=OcadoCart)
    next_slot: Optional[OcadoDeliverySlot] = None
    active_order_count: int = 0
    has_delivery_subscription: bool = False
    subscription_type: str = ""


class OcadoApiError(Exception):
    """Base exception for Ocado API errors."""


class OcadoAuthError(OcadoApiError):
    """Authentication error (invalid/expired tokens)."""


class OcadoApiClient:
    """Async Ocado API client for Home Assistant."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        session_token: str,
        refresh_token: str,
    ) -> None:
        """Initialise the client."""
        self._session = session
        self._tokens = OcadoTokens(token=session_token, refresh_token=refresh_token)
        self._delivery_destination_id: Optional[str] = None
        self._seq_num = 0

    @property
    def tokens(self) -> OcadoTokens:
        """Return current tokens."""
        return self._tokens

    def _next_seq(self) -> str:
        self._seq_num += 1
        return str(self._seq_num)

    def _headers(self, extra: dict | None = None) -> dict[str, str]:
        """Build standard API headers."""
        h = {
            "Accept": "application/json",
            "Accept-Language": "en-GB",
            "Accept-Currency": "GBP",
            "Accept-Encoding": "gzip",
            "User-Agent": UA_API,
            "x-api-key": API_KEY,
            "BannerId": BANNER_ID,
            "Ecom-Request-Source": "ios",
            "Ecom-Request-Source-Version": "1.417.2 (33861072)",
            "Client-Features": "image-http-redirects",
            "sessionsequenceno": self._next_seq(),
            "Connection": "keep-alive",
        }
        if self._tokens:
            h["Authorization"] = f"token:{self._tokens.token}"
        if extra:
            h.update(extra)
        return h

    # ── Auth ──────────────────────────────────────────────────────────────

    async def async_refresh_token(self) -> OcadoTokens:
        """Refresh the session token using the refresh token."""
        if not self._tokens or not self._tokens.refresh_token:
            raise OcadoAuthError("No refresh token available")

        _LOGGER.debug("Refreshing Ocado session token")
        headers = self._headers({"Content-Type": "application/json"})
        headers["Authorization"] = f"token:{self._tokens.refresh_token}"

        async with self._session.post(
            f"{API_BASE}/v1/authorize/refresh",
            headers=headers,
            json={"refreshToken": self._tokens.refresh_token},
        ) as resp:
            if resp.status == 401:
                raise OcadoAuthError(
                    "Refresh token rejected. A new token must be obtained "
                    "from the Ocado app."
                )
            resp.raise_for_status()
            data = await resp.json()

        self._tokens = OcadoTokens(
            token=data["token"],
            refresh_token=data["refreshToken"],
        )
        _LOGGER.debug("Ocado session token refreshed successfully")
        return self._tokens

    async def _request(
        self, method: str, url: str, **kwargs: Any
    ) -> dict | list:
        """Make an API request with auto-retry on 401."""
        if "headers" not in kwargs:
            kwargs["headers"] = self._headers()

        async with self._session.request(method, url, **kwargs) as resp:
            if resp.status == 401 and self._tokens.refresh_token:
                _LOGGER.debug("Got 401, attempting token refresh")
                try:
                    await self.async_refresh_token()
                    kwargs["headers"] = self._headers()
                    async with self._session.request(
                        method, url, **kwargs
                    ) as retry_resp:
                        if retry_resp.status == 401:
                            raise OcadoAuthError("Token refresh did not resolve 401")
                        retry_resp.raise_for_status()
                        return await retry_resp.json()
                except OcadoAuthError:
                    raise
                except Exception as err:
                    raise OcadoApiError(f"Request failed after refresh: {err}") from err

            if resp.status == 401:
                raise OcadoAuthError("Unauthorized and no refresh token available")
            resp.raise_for_status()
            return await resp.json()

    # ── Validate credentials ──────────────────────────────────────────────

    async def async_validate_tokens(self) -> OcadoUserProfile:
        """Validate tokens by fetching the user profile. Raises on failure."""
        data = await self._request("GET", f"{API_BASE}/v1/user/current")
        return OcadoUserProfile(
            first_name=data.get("firstName", ""),
            full_name=data.get("fullName", ""),
            username=data.get("username", ""),
            customer_id=data.get("retailerCustomerId", ""),
        )

    # ── User ──────────────────────────────────────────────────────────────

    async def async_get_user(self) -> OcadoUserProfile:
        """GET /v1/user/current."""
        data = await self._request("GET", f"{API_BASE}/v1/user/current")
        return OcadoUserProfile(
            first_name=data.get("firstName", ""),
            full_name=data.get("fullName", ""),
            username=data.get("username", ""),
            customer_id=data.get("retailerCustomerId", ""),
        )

    # ── Orders ────────────────────────────────────────────────────────────

    async def async_get_recent_orders(self) -> dict[str, list[OcadoOrder]]:
        """GET /v2/orders/recent → parsed upcoming + delivered."""
        data = await self._request("GET", f"{API_BASE}/v2/orders/recent")
        return {
            "upcoming": [self._parse_order(o) for o in data.get("upcoming", [])],
            "delivered": [self._parse_order(o) for o in data.get("delivered", [])],
        }

    async def async_get_active_order_count(self) -> int:
        """GET /v3/orders/not-cancelled-count."""
        data = await self._request(
            "GET", f"{API_BASE}/v3/orders/not-cancelled-count"
        )
        # The response is typically {"count": N} or just an int
        if isinstance(data, dict):
            return data.get("count", data.get("orderCount", 0))
        return int(data) if data else 0

    @staticmethod
    def _parse_order(o: dict) -> OcadoOrder:
        delivery = o.get("delivery", {})
        slot = delivery.get("slot", {})
        addr = delivery.get("address", {})
        price = o.get("totalPrice", {})
        slot_cost = slot.get("cost", {})
        return OcadoOrder(
            id=o.get("id", ""),
            status=o.get("status", ""),
            status_message=o.get("statusMessage", ""),
            items_count=o.get("items", 0),
            total_price=price.get("amount", "0"),
            currency=price.get("currency", "GBP"),
            delivery_address=addr.get("address", ""),
            delivery_slot_start=slot.get("startDate", slot.get("start", "")),
            delivery_slot_end=slot.get("endDate", slot.get("end", "")),
            delivery_method=delivery.get("deliveryMethod", ""),
            slot_cost=slot_cost.get("amount", ""),
            is_editable=o.get("isEditable", False),
        )

    # ── Delivery Slots ────────────────────────────────────────────────────

    async def async_get_delivery_destinations(self) -> list[dict]:
        """POST /v2/delivery/locations → delivery destination IDs."""
        data = await self._request(
            "POST",
            f"{API_BASE}/v2/delivery/locations",
            params={"deliveryMethod": "HOME_DELIVERY"},
        )
        if not isinstance(data, list):
            data = [data] if data else []

        for loc in data:
            addr = loc.get("address", {})
            if addr.get("primary", False):
                self._delivery_destination_id = addr.get("deliveryDestinationId")
                break
        if not self._delivery_destination_id and data:
            self._delivery_destination_id = (
                data[0].get("address", {}).get("deliveryDestinationId")
            )
        return data

    async def async_get_next_slot(self) -> Optional[OcadoDeliverySlot]:
        """GET /v4/slot/next-available."""
        if not self._delivery_destination_id:
            await self.async_get_delivery_destinations()
        if not self._delivery_destination_id:
            return None

        try:
            data = await self._request(
                "GET",
                f"{API_BASE}/v4/slot/next-available",
                params={"deliveryDestinationId": self._delivery_destination_id},
            )
        except Exception:
            _LOGGER.debug("Could not fetch next available slot", exc_info=True)
            return None

        slot = data.get("slot", {})
        delivery = data.get("delivery", {})
        window = slot.get("slotWindow", {})
        addr = delivery.get("address", {})

        return OcadoDeliverySlot(
            slot_id=slot.get("slotId", ""),
            slot_type=slot.get("type", ""),
            start_time=window.get("startTime", ""),
            end_time=window.get("endTime", ""),
            address=addr.get("address", ""),
            delivery_method=delivery.get("deliveryMethod", ""),
        )

    # ── Cart ──────────────────────────────────────────────────────────────

    async def async_get_cart(self) -> OcadoCart:
        """GET /v1/carts/active → simplified cart."""
        try:
            data = await self._request("GET", f"{API_BASE}/v1/carts/active")
        except Exception:
            _LOGGER.debug("Could not fetch cart", exc_info=True)
            return OcadoCart()

        # Cart structure varies; handle gracefully
        if isinstance(data, dict):
            items = data.get("products", data.get("items", []))
            item_count = len(items) if isinstance(items, list) else 0
            total = data.get("totalPrice", data.get("total", {}))
            if isinstance(total, dict):
                price = total.get("amount", "0.00")
                currency = total.get("currency", "GBP")
            else:
                price = str(total) if total else "0.00"
                currency = "GBP"
            return OcadoCart(
                item_count=item_count,
                total_price=price,
                currency=currency,
            )
        return OcadoCart()

    # ── Subscriptions ─────────────────────────────────────────────────────

    async def async_get_delivery_subscription(self) -> dict:
        """GET /v1/user/subscriptions/delivery/active."""
        try:
            data = await self._request(
                "GET",
                f"{API_BASE}/v1/user/subscriptions/delivery/active",
            )
            return data if isinstance(data, dict) else {}
        except Exception:
            _LOGGER.debug("Could not fetch delivery subscription", exc_info=True)
            return {}

    # ── Full data fetch (used by coordinator) ─────────────────────────────

    async def async_get_all_data(self) -> OcadoData:
        """Fetch all data in one go for the coordinator."""
        result = OcadoData()

        # User
        try:
            result.user = await self.async_get_user()
        except Exception:
            _LOGGER.warning("Failed to fetch Ocado user profile", exc_info=True)

        # Orders
        try:
            orders = await self.async_get_recent_orders()
            result.upcoming_orders = orders.get("upcoming", [])
            result.delivered_orders = orders.get("delivered", [])
        except Exception:
            _LOGGER.warning("Failed to fetch Ocado orders", exc_info=True)

        # Active order count
        try:
            result.active_order_count = await self.async_get_active_order_count()
        except Exception:
            _LOGGER.debug("Failed to fetch active order count", exc_info=True)

        # Cart
        try:
            result.cart = await self.async_get_cart()
        except Exception:
            _LOGGER.debug("Failed to fetch Ocado cart", exc_info=True)

        # Next slot
        try:
            result.next_slot = await self.async_get_next_slot()
        except Exception:
            _LOGGER.debug("Failed to fetch next delivery slot", exc_info=True)

        # Subscription
        try:
            sub = await self.async_get_delivery_subscription()
            if sub:
                result.has_delivery_subscription = True
                result.subscription_type = sub.get("type", sub.get("name", "Active"))
        except Exception:
            _LOGGER.debug("Failed to fetch subscription", exc_info=True)

        return result
