"""Typed model for a Renpho measurement.

Optional convenience over the raw dicts returned by :class:`RenphoClient`.
The client still returns plain dicts (the API owns the schema); wrap one with
:meth:`Measurement.from_dict` when you want typed attribute access. The full
original payload is always preserved on :attr:`raw`, so nothing is lost even
for keys this model doesn't name.
"""

from dataclasses import dataclass, field


@dataclass
class Measurement:
    """A single body-composition measurement with typed access to common fields."""

    id: int | str | None = None
    timestamp: int | None = None
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
        return cls(
            id=data.get("id"),
            timestamp=data.get("timeStamp"),
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
