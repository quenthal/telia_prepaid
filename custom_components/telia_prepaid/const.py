"""Vakiot Telia Prepaid -integraatiolle."""
from datetime import timedelta

DOMAIN = "telia_prepaid"
MANUFACTURER = "Telia"

CONF_SCAN_INTERVAL_MIN = "scan_interval_minutes"
DEFAULT_SCAN_INTERVAL_MIN = 360  # 6 h – saldo ei muutu usein, eikä palvelua kannata kuormittaa
MIN_SCAN_INTERVAL_MIN = 30

DEBUG_DIR = "telia_prepaid_debug"
