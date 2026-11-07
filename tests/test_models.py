"""Tests for renpho.models.Measurement and timestamp parsing."""

import datetime
from renpho.models import Measurement, parse_timestamp


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
    assert m.local_created_at is None
    assert m.time_zone is None
    assert m.datetime is None


def test_parse_timestamp_prioritizes_local_created_at_with_timezone():
    raw = {
        "timeStamp": 1730000000,  # potentially offset / skewed server timestamp
        "localCreatedAt": "2026-11-06 10:00:00",
        "timeZone": "-04:00",
    }
    expected_dt = datetime.datetime(2026, 11, 6, 10, 0, 0, tzinfo=datetime.timezone(datetime.timedelta(hours=-4)))
    expected_epoch = int(expected_dt.timestamp())

    parsed = parse_timestamp(raw)
    assert parsed == expected_epoch

    m = Measurement.from_dict(raw)
    assert m.timestamp == expected_epoch
    assert m.local_created_at == "2026-11-06 10:00:00"
    assert m.time_zone == "-04:00"
    assert m.datetime == datetime.datetime.fromtimestamp(expected_epoch, tz=datetime.timezone.utc)


def test_parse_timestamp_handles_single_digit_hour_and_positive_timezone():
    raw = {
        "localCreatedAt": "2026-11-06 15:30:00",
        "timeZone": "+02:00",
    }
    expected_dt = datetime.datetime(2026, 11, 6, 15, 30, 0, tzinfo=datetime.timezone(datetime.timedelta(hours=2)))
    assert parse_timestamp(raw) == int(expected_dt.timestamp())

    raw_neg = {
        "localCreatedAt": "2026-11-06 15:30:00",
        "timeZone": "-4:00",
    }
    expected_neg = datetime.datetime(2026, 11, 6, 15, 30, 0, tzinfo=datetime.timezone(datetime.timedelta(hours=-4)))
    assert parse_timestamp(raw_neg) == int(expected_neg.timestamp())


def test_parse_timestamp_normalizes_millisecond_timestamp():
    raw = {"timeStamp": 1700000000000}
    m = Measurement.from_dict(raw)
    assert m.timestamp == 1700000000


def test_parse_timestamp_falls_back_to_created_at_utc():
    raw = {"createdAt": "2026-11-06 12:00:00"}
    expected_dt = datetime.datetime(2026, 11, 6, 12, 0, 0, tzinfo=datetime.timezone.utc)
    assert parse_timestamp(raw) == int(expected_dt.timestamp())


def test_parse_timestamp_handles_invalid_or_missing_gracefully():
    assert parse_timestamp({}) is None
    assert parse_timestamp({"timeStamp": "invalid"}) is None
    assert parse_timestamp({"localCreatedAt": "not-a-date"}) is None
