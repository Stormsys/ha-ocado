"""Constants for the Ocado integration."""

DOMAIN = "ocado"
MANUFACTURER = "Ocado"

CONF_SESSION_TOKEN = "session_token"
CONF_REFRESH_TOKEN = "refresh_token"

# API constants (extracted from Ocado iOS app traffic)
API_BASE = "https://api.mol.osp.tech/rocket-osp"
API_KEY = "NVpXAmgMAE1Cg5Mblpefg4YaVA2lXMr65AG6J8A1"
BANNER_ID = "eafa5127-d256-497b-9609-4869092accd6"
UA_API = "Ocado-iPhone-Application/1.417.2 (iOS/26.2.1) iPhone18,2"

# Update intervals (seconds)
DEFAULT_SCAN_INTERVAL = 600  # 10 minutes for data
TOKEN_REFRESH_INTERVAL = 3600  # 1 hour for token refresh
