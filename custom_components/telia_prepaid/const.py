"""Vakiot Telia Prepaid -integraatiolle."""
from datetime import timedelta

DOMAIN = "telia_prepaid"
MANUFACTURER = "Telia"

CONF_SCAN_INTERVAL_MIN = "scan_interval_minutes"
DEFAULT_SCAN_INTERVAL_MIN = 360  # 6 h – saldo ei muutu usein, eikä palvelua kannata kuormittaa
MIN_SCAN_INTERVAL_MIN = 30
RETRY_AFTER_ERROR_MIN = 30  # epäonnistuneen haun jälkeen ei odoteta koko päivitysväliä
AUTH_RETRY_DELAY_S = 30  # hylätty kirjautuminen kokeillaan vielä kerran ennen salasanakyselyä

DEBUG_DIR = "telia_prepaid_debug"
