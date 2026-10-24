"""Tests for renpho.client — RenphoClient unit tests."""

from unittest.mock import patch

import pytest
import requests

from renpho.client import RenphoAPIError, RenphoClient, _check_response
from renpho.constants import APP_VERSION, MEASUREMENT_TABLE_NAMES, PLATFORM
from renpho.crypto import encrypt_request


class TestCheckResponse:
    def test_success_by_msg(self):
        _check_response({"code": 999, "msg": "success"})

    @pytest.mark.parametrize("code", [0, "0", 200, "200", 20000, "20000"])
    def test_success_by_code(self, code):
        _check_response({"code": code, "msg": ""})

    def test_raises_on_failure(self):
        with pytest.raises(RenphoAPIError) as exc_info:
            _check_response({"code": 401, "msg": "Unauthorized"})
        assert exc_info.value.code == 401
        assert "Unauthorized" in str(exc_info.value)


class TestExtractRecords:
    def test_list_input(self):
        records = [{"weight": 70}, {"weight": 71}]
        assert RenphoClient._extract_records(records) == records

    def test_empty_list(self):
        assert RenphoClient._extract_records([]) is None

    def test_dict_with_list_key(self):
        data = {"list": [{"weight": 70}]}
        assert RenphoClient._extract_records(data) == [{"weight": 70}]

    def test_dict_with_data_key(self):
        data = {"data": [{"weight": 70}]}
        assert RenphoClient._extract_records(data) == [{"weight": 70}]

    def test_single_measurement_dict(self):
        data = {"weight": 70, "bmi": 22}
        assert RenphoClient._extract_records(data) == [data]

    def test_unknown_dict(self):
        data = {"foo": "bar"}
        assert RenphoClient._extract_records(data) is None

    def test_none_input(self):
        assert RenphoClient._extract_records(None) is None


class TestRenphoClient:
    def test_login_includes_protocol_headers_without_authentication(self):
        client = RenphoClient("test@example.com", "pass123")
        encrypted = encrypt_request({"login": {"token": "test-token", "id": 123}})
        result = {"code": 101, "msg": "success", "data": encrypted["encryptData"]}
        with patch.object(client._transport, "post", return_value=result) as post:
            client.login()

        assert post.call_count == 1
        headers = post.call_args.kwargs["headers"]
        assert headers["appVersion"] == APP_VERSION
        assert headers["platform"] == PLATFORM
        assert "token" not in headers
        assert "userId" not in headers
        assert client.token == "test-token"
        assert client.user_id == 123

    def test_init(self):
        client = RenphoClient("test@example.com", "pass123")
        assert client.email == "test@example.com"
        assert client.password == "pass123"
        assert client.token is None
        assert client.debug is False

    def test_init_debug(self):
        client = RenphoClient("a@b.com", "p", debug=True)
        assert client.debug is True


class TestGetBodyCompositionMeasurements:
    def _make_client(self):
        client = RenphoClient("a@b.com", "p")
        client.token = "tok"
        client.user_id = 123
        return client

    def _encrypted_records(self, records):
        from renpho.crypto import encrypt_request
        return {"code": 101, "msg": "success", "data": encrypt_request(records)["encryptData"]}

    def test_returns_records_single_page(self):
        client = self._make_client()
        records = [{"weight": 70.0, "timeStamp": 1000}]
        with patch.object(client, "_post", return_value=self._encrypted_records(records)):
            result = client.get_body_composition_measurements("measurements_info_0", 123)
        assert result == records

    def test_paginates_until_empty(self):
        client = self._make_client()
        page1 = [{"weight": float(i), "timeStamp": i} for i in range(50)]
        page2 = [{"weight": 99.0, "timeStamp": 9999}]
        responses = [
            self._encrypted_records(page1),
            self._encrypted_records(page2),
            self._encrypted_records([]),
        ]
        with patch.object(client, "_post", side_effect=responses):
            result = client.get_body_composition_measurements("measurements_info_0", 123)
        assert len(result) == 51

    def test_returns_empty_when_no_data(self):
        client = self._make_client()
        no_data = {"code": 101, "msg": "success", "data": None}
        with patch.object(client, "_post", return_value=no_data):
            result = client.get_body_composition_measurements("measurements_info_0", 123)
        assert result == []


class TestGetAllMeasurementsCountZero:
    """get_all_measurements should fetch even when device_info reports count=0."""

    def _make_client(self):
        client = RenphoClient("a@b.com", "p")
        client.token = "tok"
        client.user_id = 123
        return client

    def _encrypted_records(self, records):
        from renpho.crypto import encrypt_request
        return {"code": 101, "msg": "success", "data": encrypt_request(records)["encryptData"]}

    def test_fetches_when_count_is_zero(self):
        client = self._make_client()
        records = [{"weight": 72.0, "timeStamp": 1000}]
        device_info = {
            "scale": [{"tableName": "measurements_info_8", "count": 0, "userIds": [123]}]
        }
        with (
            patch.object(client, "get_device_info", return_value=device_info),
            patch.object(client, "get_body_composition_measurements", return_value=records),
        ):
            result = client.get_all_measurements()
        assert result == records

    def test_falls_back_to_get_measurements_when_body_composition_empty(self):
        client = self._make_client()
        records = [{"weight": 70.0, "timeStamp": 2000}]
        device_info = {
            "scale": [{"tableName": "measurements_info_8", "count": 5, "userIds": [123]}]
        }
        with (
            patch.object(client, "get_device_info", return_value=device_info),
            patch.object(client, "get_body_composition_measurements", return_value=[]),
            patch.object(client, "get_measurements", return_value=records) as mock_get,
        ):
            result = client.get_all_measurements()
        mock_get.assert_called_once_with("measurements_info_8", 123, 5)
        assert result == records


class TestDiscoverUserTables:
    """Discovery uses the 24 decimal shards and the deterministic fast path."""

    def _make_client(self):
        client = RenphoClient("a@b.com", "p")
        client.token = "tok"
        client.user_id = 123
        return client

    def _encrypted_records(self, records):
        return {
            "code": 101,
            "msg": "success",
            "data": encrypt_request(records)["encryptData"],
        }

    def test_computed_shard_short_circuits_the_sweep(self):
        client = self._make_client()
        uid = 6000380382810832768  # real observed id -> shard 16
        with patch.object(
            client, "_shard_has_data", side_effect=lambda user, table: table.endswith("_16")
        ) as probe:
            assert client.discover_user_tables(uid) == ["measurements_info_16"]
        probe.assert_called_once_with(uid, "measurements_info_16")

    def test_falls_back_to_remaining_shards(self):
        client = self._make_client()
        uid = 6000380382810832768
        with patch.object(
            client, "_shard_has_data", side_effect=lambda user, table: table.endswith("_3")
        ) as probe:
            assert client.discover_user_tables(uid) == ["measurements_info_3"]
        assert probe.call_args_list[0].args == (uid, "measurements_info_16")
        assert probe.call_count == len(MEASUREMENT_TABLE_NAMES)



class TestGetAllMeasurementsMultiAccount:
    """extra_user_ids merges other accounts' data and dedupes by record id."""

    def _make_client(self):
        client = RenphoClient("a@b.com", "p")
        client.token = "tok"
        client.user_id = 123
        return client

    def test_merges_extra_accounts_and_dedupes_by_id(self):
        client = self._make_client()
        device_info = {
            "scale": [{"tableName": "measurements_info_1", "count": 0, "userIds": [123]}]
        }
        by_table = {
            # primary account
            "measurements_info_1": [
                {"id": 1, "weight": 70.0, "timeStamp": 100},
                {"id": 2, "weight": 71.0, "timeStamp": 200},
            ],
            # extra account shard — shares id 2 (duplicate) plus a new id 3
            "measurements_info_5": [
                {"id": 2, "weight": 71.0, "timeStamp": 200},
                {"id": 3, "weight": 72.0, "timeStamp": 300},
            ],
        }

        def fake_bc(table_name, uid, **kwargs):
            return by_table.get(table_name, [])

        with (
            patch.object(client, "get_device_info", return_value=device_info),
            patch.object(
                client, "discover_user_tables", return_value=["measurements_info_5"]
            ) as mock_discover,
            patch.object(
                client, "get_body_composition_measurements", side_effect=fake_bc
            ),
        ):
            result = client.get_all_measurements(extra_user_ids=["999"])

        mock_discover.assert_called_once_with("999", max_workers=1)
        # IDs are only unique within a table, so matching IDs in different
        # shards remain distinct; results are newest-first.
        assert [m["id"] for m in result] == [3, 2, 2, 1]

    def test_no_extra_ids_is_backward_compatible(self):
        client = self._make_client()
        device_info = {
            "scale": [{"tableName": "measurements_info_1", "count": 0, "userIds": [123]}]
        }
        records = [
            {"id": 2, "weight": 71.0, "timeStamp": 200},
            {"id": 1, "weight": 70.0, "timeStamp": 100},
        ]
        with (
            patch.object(client, "get_device_info", return_value=device_info),
            patch.object(client, "discover_user_tables") as mock_discover,
            patch.object(
                client, "get_body_composition_measurements", return_value=records
            ),
        ):
            result = client.get_all_measurements()

        # discovery is never invoked on the single-account path.
        mock_discover.assert_not_called()
        assert [m["id"] for m in result] == [2, 1]

    def test_extra_account_failure_is_isolated(self):
        """A failure fetching one extra account must not discard the rest."""
        client = self._make_client()
        device_info = {
            "scale": [{"tableName": "measurements_info_1", "count": 0, "userIds": [123]}]
        }
        primary = [{"id": 1, "weight": 70.0, "timeStamp": 100}]
        with (
            patch.object(client, "get_device_info", return_value=device_info),
            patch.object(
                client,
                "discover_user_tables",
                side_effect=requests.exceptions.ConnectionError("boom"),
            ),
            patch.object(
                client, "get_body_composition_measurements", return_value=primary
            ),
        ):
            result = client.get_all_measurements(extra_user_ids=["999"])

        # The primary account's data survives the extra-account failure.
        assert [m["id"] for m in result] == [1]



class TestDiscoverUserTablesHardening:
    """Token guard, error isolation, caching, and concurrency."""

    def _make_client(self, *, token="tok"):
        client = RenphoClient("a@b.com", "p")
        client.token = token
        client.user_id = 123
        return client

    def _encrypted_records(self, records):
        return {
            "code": 101,
            "msg": "success",
            "data": encrypt_request(records)["encryptData"],
        }

    def _no_data(self):
        return {"code": 101, "msg": "success", "data": None}

    def test_logs_in_when_no_token(self):
        client = self._make_client(token=None)

        def fake_login():
            client.token = "tok"

        with (
            patch.object(client, "login", side_effect=fake_login) as mock_login,
            patch.object(client, "_post", return_value=self._no_data()),
        ):
            client.discover_user_tables("999")

        mock_login.assert_called_once()

    def test_probe_failure_is_isolated(self):
        client = self._make_client()
        responses = [
            requests.exceptions.ConnectionError("flaky"),
            self._encrypted_records([{"id": 1, "weight": 70.0}]),
        ]
        with patch.object(client, "_post", side_effect=responses):
            assert client._shard_has_data("999", "measurements_info_15") is True

    def test_results_are_cached_until_refresh_or_clear(self):
        client = self._make_client()
        n = len(MEASUREMENT_TABLE_NAMES)
        with patch.object(client, "_shard_has_data", return_value=False) as probe:
            client.discover_user_tables("999")
            client.discover_user_tables("999")  # served from cache
            assert probe.call_count == n

            client.discover_user_tables("999", refresh=True)  # re-probe
            assert probe.call_count == 2 * n

            client.clear_table_cache()
            client.discover_user_tables("999")  # cache cleared -> re-probe
            assert probe.call_count == 3 * n

    def test_concurrent_matches_serial(self):
        client = self._make_client()
        hits = {"measurements_info_3", "measurements_info_20"}

        with patch.object(
            client,
            "_shard_has_data",
            side_effect=lambda uid, table, **kw: table in hits,
        ):
            serial = client.discover_user_tables("999", refresh=True, max_workers=1)
            concurrent = client.discover_user_tables("999", refresh=True, max_workers=4)

        # Same set, same canonical order, regardless of concurrency.
        assert serial == concurrent == ["measurements_info_3", "measurements_info_20"]

