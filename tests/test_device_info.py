"""Regression coverage for inconsistent device metadata response shapes."""

from unittest.mock import Mock

import pytest
import requests

from renpho import RenphoAPIError, RenphoClient
from renpho.crypto import encrypt_request


def _response(data):
    return {"code": 0, "data": encrypt_request(data)["encryptData"]}


@pytest.fixture
def client():
    instance = RenphoClient("unused", "unused")
    instance.token = "test-token"
    instance.user_id = 123
    return instance


@pytest.mark.parametrize("user_ids", [123, "123", [123], ["123"]])
def test_selected_profile_fetch_accepts_scalar_and_list_ids(client, monkeypatch, user_ids):
    metadata = {"scale": [{"tableName": "measurements_info_3", "userIds": user_ids}]}
    post = Mock(return_value=_response(metadata))
    monkeypatch.setattr(client, "_post", post)
    rows = [{"id": 1, "bUserId": 123, "timeStamp": 1, "weight": 72}]
    fetch = Mock(return_value=rows + [{"id": 2, "bUserId": 456, "weight": 90}])
    monkeypatch.setattr(client, "get_body_composition_measurements", fetch)
    discovery = Mock(side_effect=AssertionError("Valid metadata should identify the table"))
    monkeypatch.setattr(client, "discover_user_tables", discovery)

    assert client.get_all_measurements(profile_user_id="123", strict=True) == rows
    fetch.assert_called_once_with("measurements_info_3", "123")
    assert post.call_count == 1


@pytest.mark.parametrize("user_ids", [456, "456", [456], ["456"]])
def test_profile_listing_accepts_scalar_and_list_ids(client, monkeypatch, user_ids):
    monkeypatch.setattr(
        client, "_post", Mock(return_value=_response({"scale": [{"userIds": user_ids}]}))
    )
    assert client.get_measurement_profiles() == [
        {"user_id": "123", "is_account_owner": True},
        {"user_id": "456", "is_account_owner": False},
    ]


def test_malformed_metadata_is_read_once_more(client, monkeypatch):
    metadata = {"scale": [{"tableName": "measurements_info_3", "userIds": [123]}]}
    post = Mock(side_effect=[_response({"scale": 0}), _response(metadata)])
    monkeypatch.setattr(client, "_post", post)
    rows = [{"id": 1, "bUserId": 123, "weight": 72}]
    monkeypatch.setattr(client, "get_body_composition_measurements", Mock(return_value=rows))

    assert client.get_all_measurements(profile_user_id="123", strict=True) == rows
    assert post.call_count == 2


@pytest.mark.parametrize(
    "metadata",
    [
        0,
        {"scale": 0},
        {"scale": [0]},
        {"scale": [{"userIds": {"id": 123}}]},
        {"scale": [{"userIds": True}]},
        {"scale": [{"userIds": [True]}]},
    ],
)
def test_persistently_malformed_metadata_fails_closed(client, monkeypatch, metadata):
    post = Mock(return_value=_response(metadata))
    monkeypatch.setattr(client, "_post", post)
    fetch = Mock(side_effect=AssertionError("Must not fetch with malformed metadata"))
    monkeypatch.setattr(client, "get_body_composition_measurements", fetch)

    with pytest.raises(RenphoAPIError, match="Malformed device metadata"):
        client.get_all_measurements(profile_user_id="123", strict=True)
    assert post.call_count == 2
    fetch.assert_not_called()


def test_api_rejection_is_not_retried(client, monkeypatch):
    post = Mock(return_value={"code": 403, "msg": "Unauthorized"})
    monkeypatch.setattr(client, "_post", post)
    with pytest.raises(RenphoAPIError, match="Unauthorized"):
        client.get_device_info()
    assert post.call_count == 1


def test_http_error_keeps_existing_request_fallback(client, monkeypatch):
    metadata = {"scale": []}
    post = Mock(side_effect=[requests.HTTPError("server error"), _response(metadata)])
    monkeypatch.setattr(client, "_post", post)
    assert client.get_device_info() == metadata
    assert post.call_count == 2
