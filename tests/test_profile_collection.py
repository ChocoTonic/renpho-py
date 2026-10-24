from unittest.mock import patch

import pytest
import requests

from renpho.client import RenphoAPIError, RenphoClient
from renpho.constants import MEASUREMENT_TABLE_NAMES
from renpho.crypto import encrypt_request


class TestMeasurementTableFor:
    def test_computes_decimal_modulo_24_shards(self):
        assert RenphoClient.measurement_table_for(5850419884014272384) == "measurements_info_8"
        assert RenphoClient.measurement_table_for(6000380382810832768) == "measurements_info_16"
        assert RenphoClient.measurement_table_for("48") == "measurements_info_0"

    def test_invalid_user_id_is_underivable(self):
        assert RenphoClient.measurement_table_for("invalid") is None
        assert RenphoClient.measurement_table_for(None) is None

    def test_table_names_are_decimal_zero_through_twenty_three(self):
        assert MEASUREMENT_TABLE_NAMES == [f"measurements_info_{i}" for i in range(24)]


class TestStrictExtraAccounts:
    def _client(self):
        client = RenphoClient("a@b.com", "p")
        client.token = "tok"
        client.user_id = 123
        return client

    def test_empty_extra_account_cannot_return_partial_timeline(self):
        client = self._client()
        with (
            patch.object(client, "get_device_info", return_value={"scale": []}),
            patch.object(client, "discover_user_tables", return_value=[]),
            pytest.raises(RenphoAPIError, match="24 known shards"),
        ):
            client.get_all_measurements(extra_user_ids=["999"], strict=True)

    def test_extra_fetch_error_is_visible_in_strict_mode(self):
        client = self._client()
        with (
            patch.object(client, "get_device_info", return_value={"scale": []}),
            patch.object(client, "discover_user_tables", return_value=["measurements_info_15"]),
            patch.object(
                client,
                "get_body_composition_measurements",
                side_effect=requests.exceptions.ConnectionError("offline"),
            ),
            pytest.raises(requests.exceptions.ConnectionError),
        ):
            client.get_all_measurements(extra_user_ids=["999"], strict=True)

    def test_api_rejection_is_not_a_successful_empty_probe(self):
        client = self._client()
        with (
            patch.object(client, "_post", return_value={"code": 401, "msg": "Unauthorized"}),
            pytest.raises(RenphoAPIError, match="Could not establish"),
        ):
            client.discover_user_tables("999", strict=True)
        assert "999" not in client._table_cache

    def test_strict_probe_can_recover_using_other_endpoint(self):
        client = self._client()
        responses = [
            {"code": 401, "msg": "Unauthorized"},
            {
                "code": 101,
                "msg": "success",
                "data": encrypt_request([{"id": 1, "weight": 70}])["encryptData"],
            },
        ]
        with patch.object(client, "_post", side_effect=responses):
            assert client._shard_has_data("999", "measurements_info_15", strict=True)

    def test_strict_discovery_rechecks_cached_empty_result(self):
        client = self._client()
        client._table_cache["999"] = []
        with patch.object(client, "_shard_has_data", return_value=True) as probe:
            assert client.discover_user_tables("999", strict=True) == ["measurements_info_15"]
        probe.assert_called_once_with("999", "measurements_info_15", strict=True)


class TestExpectedLoginAccount:
    def test_rejects_other_principal_and_clears_session(self):
        client = RenphoClient("a@b.com", "p")
        response = {
            "code": 101,
            "data": encrypt_request(
                {
                    "login": {"id": 123, "token": "password-token"},
                }
            )["encryptData"],
        }
        with (
            patch.object(client, "_post", return_value=response),
            pytest.raises(RenphoAPIError, match="Password login authenticated a different account"),
        ):
            client.login(expected_user_id="999")
        assert client.token is None
        assert client.user_id is None
        assert client.user_info is None

    def test_expected_account_accepts_string_and_integer_ids(self):
        client = RenphoClient("a@b.com", "p")
        response = {
            "code": 101,
            "data": encrypt_request(
                {
                    "login": {"id": 123, "token": "password-token"},
                }
            )["encryptData"],
        }
        with patch.object(client, "_post", return_value=response):
            client.login(expected_user_id="123")
        assert client.user_id == 123
        assert client.token == "password-token"


class TestSelectedProfile:
    def _client(self):
        client = RenphoClient("test@example.invalid", "password")
        client.token = "token"
        client.user_id = 123
        return client

    def test_profile_filters_foreign_and_unknown_rows_and_ignores_extra_accounts(self):
        client = self._client()
        rows = [
            {"id": 1, "bUserId": 999, "timeStamp": 10},
            {"id": 2, "userId": "999", "timeStamp": 20},
            {"id": 3, "bUserId": 123},
            {"id": 4},
            {"id": 5, "bUserId": 123, "userId": 999},
        ]
        with (
            patch.object(
                client,
                "get_device_info",
                return_value={
                    "scale": [
                        {"tableName": "measurements_info_15", "userIds": [999]},
                    ]
                },
            ),
            patch.object(client, "get_body_composition_measurements", return_value=rows) as fetch,
            patch.object(client, "discover_user_tables") as discover,
        ):
            result = client.get_all_measurements(
                profile_user_id="999",
                extra_user_ids=["888"],
                strict=True,
            )
        assert [row["id"] for row in result] == [2, 1]
        fetch.assert_called_once_with("measurements_info_15", "999")
        discover.assert_not_called()

    def test_profile_discovers_missing_table_and_falls_back_to_legacy(self):
        client = self._client()
        with (
            patch.object(client, "get_device_info", return_value={"scale": []}),
            patch.object(
                client, "discover_user_tables", return_value=["measurements_info_15"]
            ) as discover,
            patch.object(client, "get_body_composition_measurements", return_value=[]),
            patch.object(
                client, "get_measurements", return_value=[{"id": 1, "userId": 999}]
            ) as legacy,
        ):
            assert len(client.get_all_measurements(profile_user_id="999", strict=True)) == 1
        discover.assert_called_once_with("999", max_workers=1, strict=True)
        legacy.assert_called_once_with("measurements_info_15", "999")

    @pytest.mark.parametrize("strict", [False, True])
    def test_empty_selected_profile_only_raises_in_strict_mode(self, strict):
        client = self._client()
        with (
            patch.object(client, "get_device_info", return_value={"scale": []}),
            patch.object(client, "discover_user_tables", return_value=[]),
        ):
            if strict:
                with pytest.raises(RenphoAPIError, match="no identifiable records"):
                    client.get_all_measurements(profile_user_id="999", strict=True)
            else:
                assert client.get_all_measurements(profile_user_id="999") == []

    def test_profile_discovery_lists_unique_profiles_without_history(self):
        client = self._client()
        with (
            patch.object(
                client,
                "get_device_info",
                return_value={
                    "scale": [
                        {"userIds": [123, "999", 999]},
                    ]
                },
            ),
            patch.object(client, "get_all_measurements") as history,
        ):
            assert client.get_measurement_profiles() == [
                {"user_id": "123", "is_account_owner": True},
                {"user_id": "999", "is_account_owner": False},
            ]
        history.assert_not_called()

    def test_strict_discovery_does_not_cache_failed_probes(self):
        client = self._client()
        client._table_cache["999"] = ["old-table"]
        with patch.object(client, "_post", return_value={"code": 500, "msg": "failed"}):
            with pytest.raises(RenphoAPIError, match="Could not establish"):
                client.discover_user_tables("999", strict=True)
        assert client._table_cache["999"] == ["old-table"]
