"""Tests for renpho.models.Measurement."""

from renpho.models import Measurement


def test_from_dict_maps_known_fields_and_preserves_raw():
    raw = {
        "id": 42,
        "timeStamp": 1700000000,
        "weight": 70.5,
        "bodyfat": 18.2,
        "fatFreeWeight": 57.6,
        "heartRate": 61,
        "someUnknownKey": "kept",
    }
    m = Measurement.from_dict(raw)

    assert m.id == 42
    assert m.timestamp == 1700000000
    assert m.weight == 70.5
    assert m.bodyfat == 18.2
    # camelCase API keys map to snake_case attributes
    assert m.fat_free_weight == 57.6
    assert m.heart_rate == 61
    # full payload preserved, including unrecognized keys
    assert m.raw is raw
    assert m.raw["someUnknownKey"] == "kept"


def test_from_dict_defaults_missing_to_none():
    m = Measurement.from_dict({"weight": 80.0})
    assert m.weight == 80.0
    assert m.bmi is None
    assert m.id is None
    assert m.timestamp is None
