from datetime import datetime
import pytz

# Centralized Timezone Configuration
# TODO: Load this from DB/Environment later
HOTEL_TIMEZONE_STR = "America/Argentina/Buenos_Aires"
HOTEL_TZ = pytz.timezone(HOTEL_TIMEZONE_STR)

def get_hotel_now() -> datetime:
    """Returns current time in Hotel Timezone"""
    return datetime.now(HOTEL_TZ)

def to_hotel_time(dt: datetime) -> datetime:
    """Converts a datetime to Hotel Timezone"""
    if dt.tzinfo is None:
         # Assume UTC if naive, or handle carefully
         return pytz.utc.localize(dt).astimezone(HOTEL_TZ)
    return dt.astimezone(HOTEL_TZ)

def get_operational_date() -> str:
    """Returns today's date formatted as YYYY-MM-DD in Hotel Timezone"""
    return get_hotel_now().strftime("%Y-%m-%d")
