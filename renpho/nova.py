"""Wire format for historical RENPHO MorphoScan Nova (R-MSC04) Full Reports."""

import math
from datetime import datetime
from zoneinfo import ZoneInfo

from .crypto import decrypt_response
from .exceptions import RenphoAPIError

MORPHOSCAN_NOVA_DEVICE_TYPE = "00053"

# The composition-history response includes account and report IDs. Copy only
# measurement fields into a new report so RENPHO can assign its destination IDs.
_METRICS = {
    "weight",
    "bmi",
    "bodyfat",
    "bmr",
    "bodyage",
    "sinewRatio",
    "muscle",
    "water",
    "subfat",
    "visfat",
    "protein",
    "bone",
    "whr",
    "bodyScore",
    "bodyType",
    "obesityDegree",
    "ffmCtrl",
    "bfmCtrl",
    "smi",
    "weightTarget",
    "weightControl",
    "sinew",
    "fatFreeWeight",
}
_METRICS.update(
    f"z{hz}{part}" for hz in (20, 100) for part in ("Body", "HandL", "HandR", "FootL", "FootR")
)
_METRICS.update(
    part + field
    for part in ("la", "ra", "ll", "rl", "t")
    for field in ("Muscle", "MuscleMass", "MuscleStd", "BodyFatPct", "BodyFatMass", "BodyFatStd")
)
_METRICS.update(field + "Std" for field in ("bmi", "bmr", "bfm", "bfp", "smm", "weight"))
_METRICS.update(
    field + bound
    for bound in ("Min", "Max")
    for field in (
        "bmi",
        "bmr",
        "bfm",
        "bfp",
        "smm",
        "weight",
        "bone",
        "proteinMass",
        "waterMass",
        "muscleMass",
    )
)
_METADATA = (
    "gender",
    "height",
    "birthday",
    "measureAge",
    "pregnantMode",
    "babyMode",
    "headValue",
    "smmMass",
    "protocolVersion",
)


def _device_address(row: dict) -> str:
    value = row.get("mac")
    if not isinstance(value, str):
        raise ValueError("Missing scale address")
    address = value.strip().replace(":", "").replace("-", "").lower()
    if (
        len(address) != 12
        or any(c not in "0123456789abcdef" for c in address)
        or address == "0" * 12
    ):
        raise ValueError("Invalid scale address")
    return address


def prepare_upload(
    report: dict,
    destination: dict,
    user_id: int | str,
    zone: ZoneInfo,
) -> tuple[dict, dict[str, str]]:
    for row in (report, destination):
        if row.get("deviceType") != MORPHOSCAN_NOVA_DEVICE_TYPE or not row.get("reportId"):
            raise ValueError("Expected a MorphoScan Nova Full Report")
    if _device_address(report) != _device_address(destination):
        raise ValueError("Reports must come from the same scale")
    if str(destination.get("bUserId") or destination.get("userId")) != str(user_id):
        raise ValueError("Destination report must belong to the signed-in profile")
    if any(destination.get(k) is None for k in ("displayModuleType", "isAuto")):
        raise ValueError("Destination report lacks device metadata")
    stamp = report.get("timeStamp")
    if type(stamp) is not int or stamp <= 0:
        raise ValueError("Invalid measurement timestamp")
    instant = datetime.fromtimestamp(stamp, zone)
    if instant.strftime("%Y-%m-%d %H:%M:%S") != report.get("localCreatedAt"):
        raise ValueError("Measurement timezone does not match the original local time")
    for field in sorted(_METRICS):
        value = report.get(field)
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise ValueError(f"Missing or invalid Nova measurement field: {field}")

    # The app uses the standard abbreviation in the record even during DST.
    standard = next(
        (day for month in range(1, 13) if not (day := instant.replace(month=month, day=1)).dst()),
        instant,
    )
    data = {k: report[k] for k in _METRICS}
    data.update({k: report[k] for k in _METADATA if report.get(k) is not None})
    data.update(
        id=0,
        userId=int(user_id),
        bUserId=int(user_id),
        dataSource=1,
        mac=destination["mac"],
        deviceType=MORPHOSCAN_NOVA_DEVICE_TYPE,
        isAuto=destination["isAuto"],
        displayModuleType=destination["displayModuleType"],
        timeStamp=stamp,
        localCreatedAt=report["localCreatedAt"],
        timeZone=standard.tzname(),
        WC=data.pop("weightControl"),
    )
    offset = instant.strftime("%z")
    hours = f"{offset[0]}{int(offset[1:3])}"
    minutes = "" if offset[3:] == "00" else ":" + offset[3:]
    return data, {"timeZone": hours + minutes, "zoneId": zone.key}


def acknowledged_report_id(result: dict, timestamp: int) -> int | str:
    data = result.get("data")
    if isinstance(data, str) and data:
        try:
            data = decrypt_response(data)
        except ValueError as exc:
            raise RenphoAPIError(
                "UploadNovaFullReport",
                result.get("code"),
                "Unreadable acknowledgement; check history before retrying",
            ) from exc
    if isinstance(data, list) and len(data) == 1 and isinstance(data[0], dict):
        row = data[0]
        report_id = row.get("reportId")
        if row.get("timeStamp") == timestamp and type(report_id) in (int, str) and report_id:
            return report_id
    raise RenphoAPIError(
        "UploadNovaFullReport",
        result.get("code"),
        "Missing matching report acknowledgement; check history before retrying",
    )
