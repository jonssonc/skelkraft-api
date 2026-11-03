"""Konstanter för Skellefteå Kraft."""

DOMAIN = "skekraft"
BASE_URL = "https://externalapi.skekraft.se/api/MySkekraft"

CONF_TOKEN = "token"

# Hur ofta data hämtas (minuter)
UPDATE_INTERVAL_MINUTES = 60
# Hur ofta token förnyas oberoende av datahämtning (minuter)
KEEPALIVE_MINUTES = 20
