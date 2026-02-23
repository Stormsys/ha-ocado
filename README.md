# Ocado for Home Assistant

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![Version](https://img.shields.io/badge/version-0.1.0--alpha.1-orange)](https://github.com/stormsys/ha-ocado/releases)

A custom Home Assistant integration for [Ocado](https://www.ocado.com) that provides sensors for your deliveries, orders, cart, and account information.

> **⚠️ Alpha Release** — This integration is in early development. Expect breaking changes between versions.

## ⚠️ Important: Authentication

**This integration does NOT support username/password login.**

Ocado's login flow uses reCAPTCHA and QueueIT bot protection, making headless authentication impossible. Instead, you must provide pre-captured **session and refresh tokens** obtained by intercepting traffic from the official Ocado iOS or Android app.

The refresh token (an RS256 JWT with ~1 year expiry) allows the integration to maintain your session indefinitely by automatically refreshing the session token every hour.

## Obtaining Tokens

You'll need a proxy tool to intercept HTTPS traffic from the Ocado app:

1. **Install a proxy tool** — [Charles Proxy](https://www.charlesproxy.com/), [mitmproxy](https://mitmproxy.org/), or [Proxyman](https://proxyman.io/)
2. **Configure SSL proxying** for `api.mol.osp.tech`
3. **Install the proxy's CA certificate** on your phone
4. **Open the Ocado app** and log in normally
5. **Find the `Authorization` header** in any API request — it will look like `token:0WqFY0...`
   - The part after `token:` is your **Session Token**
6. **Find the refresh call** (`POST /v1/authorize/refresh`) — the request body contains your **Refresh Token** (a long JWT starting with `eyJ...`)

> **Tip:** The refresh token is also sent in the `Authorization` header of the refresh request itself.

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Click the three dots menu → **Custom repositories**
3. Add `https://github.com/stormsys/ha-ocado` with category **Integration**
4. Click **Install**
5. Restart Home Assistant

### Manual

1. Download the `custom_components/ocado` folder from this repository
2. Copy it to your Home Assistant `config/custom_components/` directory
3. Restart Home Assistant

## Configuration

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **Ocado**
3. Enter your **Session Token** and **Refresh Token**
4. The integration will validate your tokens and create the device

## Sensors

Each Ocado account appears as a device with the following sensors:

### Delivery Sensors
| Sensor | Description | Type |
|--------|-------------|------|
| **Upcoming Orders** | Number of upcoming deliveries | Count |
| **Next Delivery** | Date/time of next delivery slot | Timestamp |
| **Next Delivery Slot** | Human-readable delivery window | Text |
| **Next Delivery Items** | Number of items in next order | Count |
| **Next Delivery Total** | Total cost of next order | Monetary (GBP) |
| **Next Delivery Status** | Status of next order (e.g. "Picking in progress") | Text |
| **Active Orders** | Total non-cancelled order count | Count |
| **Last Delivery** | Date of most recent completed delivery | Timestamp |

### Cart Sensors
| Sensor | Description | Type |
|--------|-------------|------|
| **Cart Items** | Number of items in your current cart | Count |
| **Cart Total** | Current cart value | Monetary (GBP) |

### Availability
| Sensor | Description | Type |
|--------|-------------|------|
| **Next Available Slot** | Next bookable delivery slot | Timestamp |

### Account
| Sensor | Description | Type |
|--------|-------------|------|
| **Delivery Subscription** | Smart Pass / delivery subscription status | Text |
| **Account Name** | Account holder name | Diagnostic |
| **Account Email** | Account email address | Diagnostic |

## Token Refresh

The integration automatically handles token lifecycle:

- **Session token** is refreshed every **1 hour** (configurable)
- **Data polling** occurs every **10 minutes** (configurable)
- On any `401 Unauthorized` response, an immediate refresh is attempted
- Refreshed tokens are **persisted to the config entry** so they survive HA restarts
- If the refresh token itself expires (~1 year), a **re-authentication flow** will prompt you to provide new tokens

## Automations

Example automation — notify when a delivery is on its way:

```yaml
automation:
  - alias: "Ocado delivery arriving"
    trigger:
      - platform: state
        entity_id: sensor.ocado_next_delivery_status
        to: "Out for delivery"
    action:
      - service: notify.mobile_app
        data:
          title: "🚚 Ocado delivery on its way!"
          message: >
            Your order with {{ states('sensor.ocado_next_delivery_items') }} items
            (£{{ states('sensor.ocado_next_delivery_total') }}) is out for delivery.
```

## Diagnostics

The integration supports Home Assistant's diagnostics download feature. All sensitive data (tokens, email addresses, delivery addresses) is automatically redacted in diagnostic exports.

## Troubleshooting

### "Invalid tokens" during setup
- Ensure you're copying the full token strings without any extra whitespace
- Session tokens are ~100 characters of URL-safe base64
- Refresh tokens are JWTs starting with `eyJ` and are much longer
- Tokens may have expired — try capturing fresh ones from the app

### "Re-authentication required"
- Your refresh token has expired (this happens after ~1 year)
- Capture new tokens from the Ocado app using your proxy tool

### No data showing
- Check **Settings → System → Logs** for errors from `custom_components.ocado`
- The integration polls every 10 minutes — wait for the first update cycle
- Download diagnostics from the device page to inspect raw data

## Privacy & Legal

This integration uses a reverse-engineered, unofficial API. It is not affiliated with, endorsed by, or supported by Ocado Group plc. Use at your own risk.

Your tokens are stored locally in your Home Assistant config and are never sent to any third party. The integration only communicates with Ocado's own API servers.

## License

MIT
