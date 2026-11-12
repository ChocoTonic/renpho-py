"""Typed model for a Renpho measurement.

Optional convenience over the raw dicts returned by :class:`RenphoClient`.
The client still returns plain dicts (the API owns the schema); wrap one with
:meth:`Measurement.from_dict` when you want typed attribute access. The full
original payload is always preserved on :attr:`raw`, so nothing is lost even
for keys this model doesn't name.
"""

import datetime
from dataclasses import dataclass, field


def parse_timestamp(data: dict) -> int | None:
    """Extract Unix timestamp in seconds from a measurement dictionary.

    Prioritizes ``localCreatedAt`` + ``timeZone`` because Renpho's raw ``timeStamp``
    integer is frequently offset or misaligned (often by +8 hours) relative to the
    true local measurement time. Normalizes millisecond timestamps to seconds,
    and falls back to ``createdAt`` (UTC).
    """
    local_created = data.get("localCreatedAt")
    tz_str = data.get("timeZone")
    if local_created:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
            try:
                dt = datetime.datetime.strptime(str(local_created), fmt)
                if tz_str:
                    parts = str(tz_str).strip().split(":")
                    is_neg = parts[0].strip().startswith("-")
                    hours = int(parts[0])
                    mins = int(parts[1]) if len(parts) > 1 else 0
                    if is_neg and mins > 0:
                        mins = -mins
                    tz = datetime.timezone(datetime.timedelta(hours=hours, minutes=mins))
                    dt = dt.replace(tzinfo=tz)
                else:
                    dt = dt.astimezone()
                return int(dt.timestamp())
            except (ValueError, IndexError):
                pass

    ts = data.get("timeStamp") or data.get("time_stamp")
    if ts is not None:
        try:
            ts_int = int(float(ts))
            if ts_int > 1e12:
                ts_int //= 1000
            return ts_int
        except (ValueError, TypeError):
            pass

    created_at = data.get("createdAt")
    if created_at:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
            try:
                dt = datetime.datetime.strptime(str(created_at), fmt).replace(
                    tzinfo=datetime.timezone.utc
                )
                return int(dt.timestamp())
            except ValueError:
                pass

    return None


@dataclass
class Measurement:
    """A single body-composition measurement with typed access to common fields."""

    id: int | str | None = None
    timestamp: int | None = None
    local_created_at: str | None = None
    time_zone: str | None = None
    weight: float | None = None
    bmi: float | None = None
    bodyfat: float | None = None
    water: float | None = None
    muscle: float | None = None
    bone: float | None = None
    bmr: float | None = None
    visfat: float | None = None
    subfat: float | None = None
    protein: float | None = None
    bodyage: float | None = None
    sinew: float | None = None
    fat_free_weight: float | None = None
    heart_rate: float | None = None
    raw: dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: dict) -> "Measurement":
        """Build a :class:`Measurement` from a raw API measurement dict."""
        ts = parse_timestamp(data)
        if ts is None and data.get("timeStamp") is not None:
            try:
                ts = int(data["timeStamp"])
            except (ValueError, TypeError):
                pass

        return cls(
            id=data.get("id"),
            timestamp=ts,
            local_created_at=data.get("localCreatedAt"),
            time_zone=data.get("timeZone"),
            weight=data.get("weight"),
            bmi=data.get("bmi"),
            bodyfat=data.get("bodyfat"),
            water=data.get("water"),
            muscle=data.get("muscle"),
            bone=data.get("bone"),
            bmr=data.get("bmr"),
            visfat=data.get("visfat"),
            subfat=data.get("subfat"),
            protein=data.get("protein"),
            bodyage=data.get("bodyage"),
            sinew=data.get("sinew"),
            fat_free_weight=data.get("fatFreeWeight"),
            heart_rate=data.get("heartRate"),
            raw=data,
        )

    @property
    def datetime(self) -> datetime.datetime | None:
        """Return the measurement timestamp as a UTC datetime object."""
        if self.timestamp is not None:
            return datetime.datetime.fromtimestamp(self.timestamp, tz=datetime.timezone.utc)
        return None
