"""Constants and configuration for the Renpho API."""

# API connection
API_BASE_URL = "https://cloud.renpho.com"
ENCRYPTION_KEY = "ed*wijdi$h6fe3ew"  # 16-byte AES-128 key
APP_VERSION = "6.6.0"
PLATFORM = "android"

# API endpoints (from RenphoApiEndpoints.cs)
ENDPOINTS = {
    "login": "renpho-aggregation/user/login",
    "token_time": "RenphoHealth/app/sync/getTokenTime",
    "device_info": "renpho-aggregation/device/count",
    "family": "RenphoHealth/centerUser/queryFamilyMemberList",
    "measurements": "RenphoHealth/scale/queryAllMeasureDataList",
    "body_composition_measurements": "RenphoHealth/scale/queryBodyCompositionMeasureData",
    "body_composition_scale_count": "RenphoHealth/scale/bodyCompositionScaleCount",
}

# Renpho measurement tables use 24 decimal suffixes.
MEASUREMENT_TABLE_SHARDS = 24
MEASUREMENT_TABLE_NAMES = [
    f"measurements_info_{i}" for i in range(MEASUREMENT_TABLE_SHARDS)
]

# Body weight scale device types
BODY_WEIGHT_SCALES = [
    "01", "02", "03", "04", "05", "06", "07", "08", "09", "0A",
    "0B", "0C", "0D", "0E", "0F", "10", "11", "12", "13", "14",
]

# Success codes returned by the API
SUCCESS_CODES = {0, "0", 101, "101", 200, "200", 20000, "20000"}
