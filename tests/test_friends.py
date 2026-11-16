"""Tests for the friend endpoints (reading another account via the friends feature)."""

import json
from datetime import timedelta
from unittest.mock import patch

import pytest

from renpho.cli import main
from renpho.client import RenphoAPIError, RenphoClient
from renpho.constants import ENDPOINTS, FRIEND_TREND_PARAMS
from renpho.crypto import aes_decrypt, encrypt_request


def _encrypted(data):
    return {"code": 101, "msg": "success", "data": encrypt_request(data)["encryptData"]}


def _client():
    client = RenphoClient("a@b.com", "p")
    client.token = "tok"
    client.user_id = 42
    return client


def _payload(call):
    """Decrypt the body passed to a mocked ``_post`` call."""
    return json.loads(aes_decrypt(call.args[1]["encryptData"]))


class TestGetFriends:
    def test_paginates_and_keeps_friends_separate(self):
        client = _client()
        friends = [{"userId": "7"}, {"userId": "8"}, {"userId": "9"}]
        with patch.object(
            client,
            "_post",
            side_effect=[_encrypted({"list": friends[:2]}), _encrypted(friends[2:])],
        ) as post:
            assert client.get_friends(page_size=2) == friends
        assert [_payload(call)["pageNum"] for call in post.call_args_list] == [1, 2]

    def test_repeated_full_page_raises(self):
        client = _client()
        with patch.object(client, "_post", return_value=_encrypted([{"userId": "7"}])):
            with pytest.raises(RenphoAPIError, match="pagination made no progress"):
                client.get_friends(page_size=1)

    def test_invalid_page_size_does_not_log_in(self):
        client = _client()
        with patch.object(client, "login") as login:
            with pytest.raises(ValueError, match="positive"):
                client.get_friends(page_size=0)
        login.assert_not_called()

    def test_returns_list_and_sends_own_user_id(self):
        client = _client()
        friends = [{"userId": "7", "accountName": "Main"}]
        with patch.object(client, "_post", return_value=_encrypted({"list": friends})) as post:
            assert client.get_friends() == friends
        assert post.call_args.args[0] == ENDPOINTS["friends"]
        assert _payload(post.call_args) == {"userId": "42", "pageNum": 1, "pageSize": 50}

    def test_no_friends(self):
        client = _client()
        with patch.object(client, "_post", return_value=_encrypted({"list": []})):
            assert client.get_friends() == []

    def test_empty_data(self):
        client = _client()
        with patch.object(
            client, "_post", return_value={"code": 101, "msg": "success", "data": None}
        ):
            assert client.get_friends() == []

    def test_logs_in_when_needed(self):
        client = RenphoClient("a@b.com", "p")

        def fake_login():
            client.token, client.user_id = "tok", 42

        with (
            patch.object(client, "login", side_effect=fake_login) as login,
            patch.object(client, "_post", return_value=_encrypted({"list": []})),
        ):
            client.get_friends()
        login.assert_called_once()

    def test_api_error_raises(self):
        client = _client()
        with patch.object(client, "_post", return_value={"code": 500, "msg": "nope"}):
            with pytest.raises(RenphoAPIError):
                client.get_friends()


class TestTimeZoneHeader:
    """measure/has and trendV2 return HTTP 400 without a signed timeZone header."""

    @pytest.mark.parametrize("hours", [-8, 0, 2])
    def test_portable_local_offset(self, hours):
        with patch("renpho.client.datetime") as date:
            date.now.return_value.astimezone.return_value.utcoffset.return_value = timedelta(
                hours=hours
            )
            assert RenphoClient.local_utc_offset_hours() == hours

    def test_fractional_offset_requires_explicit_choice(self):
        with patch("renpho.client.datetime") as date:
            date.now.return_value.astimezone.return_value.utcoffset.return_value = timedelta(
                hours=-3, minutes=-30
            )
            with pytest.raises(ValueError, match="whole-hour"):
                RenphoClient.local_utc_offset_hours()

    def test_friend_headers_reach_transport_with_auth(self):
        client = _client()
        with patch.object(client._transport, "post", return_value=_encrypted([])) as post:
            client.get_friend_trend("7", time_zone=-8)
        headers = post.call_args.kwargs["headers"]
        assert headers["timeZone"] == "-8"
        assert headers["token"] == "tok"
        assert headers["userId"] == "42"
        assert headers["appVersion"]
        assert headers["platform"]

    @pytest.mark.parametrize("tz, header", [(0, "+0"), (2, "+2"), (-5, "-5")])
    def test_trend_sends_signed_header_and_int_payload(self, tz, header):
        client = _client()
        with patch.object(client, "_post", return_value=_encrypted({"list": []})) as post:
            client.get_friend_trend("7", "weight", time_zone=tz)
        assert post.call_args.kwargs["extra_headers"] == {"timeZone": header}
        assert _payload(post.call_args)["timeZone"] == tz

    def test_measure_days_sends_header(self):
        client = _client()
        with patch.object(client, "_post", return_value=_encrypted([])) as post:
            client.get_friend_measure_days("7", time_zone=1)
        assert post.call_args.args[0] == ENDPOINTS["friend_measure_days"]
        assert post.call_args.kwargs["extra_headers"] == {"timeZone": "+1"}
        assert _payload(post.call_args) == {"rhFriendIds": "7", "timeZone": 1}

    def test_defaults_to_local_offset(self):
        client = _client()
        with (
            patch.object(RenphoClient, "local_utc_offset_hours", return_value=3),
            patch.object(client, "_post", return_value=_encrypted({"list": []})) as post,
        ):
            client.get_friend_trend("7")
        assert post.call_args.kwargs["extra_headers"] == {"timeZone": "+3"}


class TestGetFriendTrend:
    def test_payload(self):
        client = _client()
        with patch.object(client, "_post", return_value=_encrypted({"list": []})) as post:
            client.get_friend_trend(
                "7", "bodyfat", time_type="WEEK", end_time=1700000000, time_zone=0
            )
        assert post.call_args.args[0] == ENDPOINTS["friend_trend"]
        assert _payload(post.call_args) == {
            "rhFriendId": "7",
            "timeZone": 0,
            "param": "bodyfat",
            "sourceDataType": "",
            "timeType": "WEEK",
            "endTime": 1700000000,
        }

    def test_returns_points(self):
        client = _client()
        points = [{"groupDay": "2026-11-01", "timeStamp": 1, "value": 80.0}]
        with patch.object(client, "_post", return_value=_encrypted({"list": points})):
            assert client.get_friend_trend("7", time_zone=0) == points


class TestGetFriendSummary:
    def test_payload(self):
        client = _client()
        with patch.object(client, "_post", return_value=_encrypted({"avg": 80})) as post:
            assert client.get_friend_summary("7", "water") == {"avg": 80}
        assert post.call_args.args[0] == ENDPOINTS["friend_summary"]
        assert _payload(post.call_args) == {"rhFriendId": "7", "param": "water"}


class TestGetFriendMeasurements:
    @pytest.mark.parametrize("value", [True, float("nan"), float("inf"), -1])
    def test_invalid_numeric_values_are_not_measurements(self, value):
        client = _client()
        with patch.object(
            client,
            "get_friend_trend",
            return_value=[{"groupDay": "2026-11-01", "timeStamp": 100, "value": value}],
        ):
            assert client.get_friend_measurements("7", params=("weight",), time_zone=0) == []

    def test_merges_params_by_day_newest_first(self):
        client = _client()
        trends = {
            "weight": [
                {"groupDay": "2026-11-01", "timeStamp": 100, "value": 80.0},
                {"groupDay": "2026-11-02", "timeStamp": 200, "value": 79.5},
            ],
            "bodyfat": [{"groupDay": "2026-11-02", "timeStamp": 200, "value": 20.1}],
        }
        with patch.object(
            client, "get_friend_trend", side_effect=lambda fid, p, **kw: trends.get(p, [])
        ):
            records = client.get_friend_measurements("7", params=("weight", "bodyfat"), time_zone=0)
        assert records == [
            {"day": "2026-11-02", "timeStamp": 200, "weight": 79.5, "bodyfat": 20.1},
            {"day": "2026-11-01", "timeStamp": 100, "weight": 80.0},
        ]

    def test_drops_zero_and_missing_values(self):
        client = _client()
        points = [
            {"groupDay": "2026-11-01", "timeStamp": 100, "value": 0},
            {"groupDay": "2026-11-02", "timeStamp": 200, "value": None},
            {"groupDay": None, "timeStamp": 300, "value": 80.0},
        ]
        with patch.object(client, "get_friend_trend", return_value=points):
            assert client.get_friend_measurements("7", params=("weight",), time_zone=0) == []

    def test_one_call_per_param_by_default(self):
        client = _client()
        with patch.object(client, "get_friend_trend", return_value=[]) as trend:
            client.get_friend_measurements("7", time_zone=0)
        assert [c.args[1] for c in trend.call_args_list] == list(FRIEND_TREND_PARAMS)


class TestCliFriendMode:
    @pytest.fixture(autouse=True)
    def friend_environment(self, tmp_path, monkeypatch):
        monkeypatch.setenv("RENPHO_EMAIL", "a@b.com")
        monkeypatch.setenv("RENPHO_PASSWORD", "p")
        monkeypatch.setenv("RENPHO_FRIEND_ID", "7")
        monkeypatch.setenv("RENPHO_OUTPUT_DIR", str(tmp_path))
        monkeypatch.setenv("RENPHO_FRIEND_TIME_ZONE", "0")

    def test_explicit_offset_works_on_fractional_offset_host(self, tmp_path, monkeypatch):
        monkeypatch.setenv("RENPHO_FRIEND_TIME_ZONE", "0")
        points = [{"groupDay": "2026-11-02", "timeStamp": 200, "value": 79.5}]
        with (
            patch.object(RenphoClient, "login"),
            patch.object(RenphoClient, "local_utc_offset_hours", side_effect=ValueError),
            patch.object(RenphoClient, "get_friend_trend", return_value=points) as trend,
        ):
            main()
        assert all(call.kwargs["time_zone"] == 0 for call in trend.call_args_list)
        assert json.loads((tmp_path / "friend_daily.json").read_text())[0]["weight"] == 79.5

    @pytest.mark.parametrize("offset", ["5.5", "UTC", "--8"])
    def test_invalid_offset_fails_before_login(self, offset, monkeypatch):
        monkeypatch.setenv("RENPHO_FRIEND_TIME_ZONE", offset)
        with patch.object(RenphoClient, "login") as login:
            with pytest.raises(SystemExit) as error:
                main()
        assert error.value.code == 1
        login.assert_not_called()

    def test_fractional_default_fails_before_login_with_actionable_message(
        self, monkeypatch, capsys
    ):
        monkeypatch.delenv("RENPHO_FRIEND_TIME_ZONE")
        with (
            patch.object(RenphoClient, "local_utc_offset_hours", side_effect=ValueError),
            patch.object(RenphoClient, "login") as login,
        ):
            with pytest.raises(SystemExit) as error:
                main()
        assert error.value.code == 1
        login.assert_not_called()
        assert "RENPHO_FRIEND_TIME_ZONE" in capsys.readouterr().out

    def test_empty_run_for_another_friend_does_not_report_old_exports_as_success(
        self, tmp_path, monkeypatch, capsys
    ):
        records = [{"day": "2026-11-02", "timeStamp": 200, "weight": 79.5}]
        with (
            patch.object(RenphoClient, "login"),
            patch.object(RenphoClient, "local_utc_offset_hours", return_value=0),
            patch.object(RenphoClient, "get_friend_measurements", side_effect=[records, []]),
            patch.object(RenphoClient, "get_friends", return_value=[]),
        ):
            main()
            original_json = (tmp_path / "friend_daily.json").read_bytes()
            original_csv = (tmp_path / "friend_daily.csv").read_bytes()
            monkeypatch.setenv("RENPHO_FRIEND_ID", "8")
            with pytest.raises(SystemExit) as error:
                main()
        assert error.value.code == 1
        assert (tmp_path / "friend_daily.json").read_bytes() == original_json
        assert (tmp_path / "friend_daily.csv").read_bytes() == original_csv
        assert "existing files were not updated" in capsys.readouterr().err

    def test_writes_friend_daily_files_and_skips_device_discovery(self, tmp_path, monkeypatch):
        monkeypatch.setenv("RENPHO_EMAIL", "a@b.com")
        monkeypatch.setenv("RENPHO_PASSWORD", "p")
        monkeypatch.setenv("RENPHO_FRIEND_ID", "7")
        monkeypatch.setenv("RENPHO_OUTPUT_DIR", str(tmp_path))
        records = [{"day": "2026-11-02", "timeStamp": 200, "weight": 79.5}]
        with (
            patch.object(RenphoClient, "login"),
            patch.object(RenphoClient, "get_device_info") as device_info,
            patch.object(RenphoClient, "get_friend_measurements", return_value=records),
        ):
            main()
        device_info.assert_not_called()
        assert json.loads((tmp_path / "friend_daily.json").read_text()) == records
        assert (tmp_path / "friend_daily.csv").read_text().startswith("day,timeStamp,weight")
