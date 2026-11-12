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


def test_parse_timestamp_resolves_server_offset_mismatch():
    """Verify that a server-shifted timeStamp (+8 hours) is ignored in favor of
    localCreatedAt + timeZone.
    """
    # User weighs in at 10:00:00 AM EDT (UTC-4)
    # Expected UTC: 14:00:00 UTC -> 1794060000
    # Skewed Renpho server timeStamp (e.g. +8 hours ahead in China Standard Time)
    local_time_str = "2026-11-06 10:00:00"
    tz_str = "-04:00"
    tz = datetime.timezone(datetime.timedelta(hours=-4))
    expected_utc = datetime.datetime(2026, 11, 6, 10, 0, 0, tzinfo=tz)
    true_epoch = int(expected_utc.timestamp())

    eight_hours_skewed_epoch = true_epoch + (8 * 3600)

    raw_payload = {
        "id": 1001,
        "timeStamp": eight_hours_skewed_epoch,
        "localCreatedAt": local_time_str,
        "timeZone": tz_str,
        "weight": 82.5,
    }

    parsed = parse_timestamp(raw_payload)
    assert parsed == true_epoch
    assert parsed != eight_hours_skewed_epoch
    assert eight_hours_skewed_epoch - parsed == 8 * 3600

    m = Measurement.from_dict(raw_payload)
    assert m.timestamp == true_epoch
    assert m.datetime == datetime.datetime.fromtimestamp(true_epoch, tz=datetime.timezone.utc)


def test_parse_timestamp_handles_half_hour_and_single_digit_timezones():
    # Negative timezone with half-hour offset (e.g. Newfoundland UTC-03:30)
    raw_nl = {
        "localCreatedAt": "2026-11-06 12:00:00",
        "timeZone": "-03:30",
    }
    expected_nl = datetime.datetime(
        2026, 11, 6, 12, 0, 0, tzinfo=datetime.timezone(datetime.timedelta(hours=-3, minutes=-30))
    )
    assert parse_timestamp(raw_nl) == int(expected_nl.timestamp())

    # Single digit negative timezone (e.g. -4:00 or -5:00)
    raw_single = {
        "localCreatedAt": "2026-11-06 12:00:00",
        "timeZone": "-5:00",
    }
    expected_single = datetime.datetime(
        2026, 11, 6, 12, 0, 0, tzinfo=datetime.timezone(datetime.timedelta(hours=-5))
    )
    assert parse_timestamp(raw_single) == int(expected_single.timestamp())

    # Positive timezone (e.g. +02:00 or +5:30)
    raw_pos = {
        "localCreatedAt": "2026-11-06 12:00:00",
        "timeZone": "+05:30",
    }
    expected_pos = datetime.datetime(
        2026, 11, 6, 12, 0, 0, tzinfo=datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    )
    assert parse_timestamp(raw_pos) == int(expected_pos.timestamp())


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
