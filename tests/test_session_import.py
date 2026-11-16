"""Imported phone sessions must never create a competing login."""
import json
from unittest.mock import patch

import pytest
import requests

from renpho import RenphoClient, RenphoSessionError
from renpho.constants import ENDPOINTS
from renpho.crypto import encrypt_request

SESSION = {"token": "test-phone-token", "user_id": "123", "email": "owner@example.com"}


def test_file_import_reads_with_original_token_without_login(tmp_path):
    path = tmp_path / "session.json"
    path.write_text(json.dumps(SESSION))
    client = RenphoClient.from_session_file(path, expected_user_id=123)
    encrypted = encrypt_request([{"id": "row", "bUserId": "123", "weight": 70}])
    results = [
        {"code": 101, "msg": "success", "data": encrypted["encryptData"]},
        {"code": 101, "msg": "success", "data": encrypt_request([])["encryptData"]},
    ]
    with patch.object(client._transport, "post", side_effect=results) as post:
        rows = client.get_body_composition_measurements("measurements_info_0", 123)
    assert len(rows) == 1
    assert client.password == ""
    for call in post.call_args_list:
        assert call.args[0] != ENDPOINTS["login"]
        assert call.kwargs["headers"]["token"] == SESSION["token"]
        assert call.kwargs["headers"]["userId"] == "123"


@pytest.mark.parametrize("operation", ["login", "get_all_measurements"])
def test_no_explicit_or_implicit_login_after_token_is_missing(operation):
    client = RenphoClient.from_session(SESSION)
    client.token = None
    with patch.object(client._transport, "post") as post:
        with pytest.raises(RenphoSessionError):
            getattr(client, operation)()
    post.assert_not_called()


@pytest.mark.parametrize("code", [401, "401", 403, "403"])
def test_rejected_session_is_not_renewed_or_swallowed_by_collection(code):
    client = RenphoClient.from_session(SESSION)
    with patch.object(client._transport, "post", return_value={"code": code}) as post:
        with pytest.raises(RenphoSessionError):
            client.discover_user_tables("456")
    assert post.call_count == 1
    assert post.call_args.args[0] != ENDPOINTS["login"]


def test_http_rejection_does_not_retry_or_leak_token():
    client = RenphoClient.from_session(SESSION)
    response = requests.Response()
    response.status_code = 403
    error = requests.HTTPError("sensitive response", response=response)
    with patch.object(client._transport, "post", side_effect=error) as post:
        with pytest.raises(RenphoSessionError) as exc:
            client.get_device_info()
    assert post.call_count == 1
    assert SESSION["token"] not in str(exc.value)
    assert "sensitive response" not in str(exc.value)


@pytest.mark.parametrize("data", [None, [], {}, {"token": "", "user_id": "123"},
    {"token": "x", "user_id": True}, {"token": "x", "user_id": ""},
    {"token": "x", "user_id": "wrong"}, {"token": "x", "user_id": 123, "email": []}])
def test_invalid_import_fails_before_network(data):
    with patch("renpho.transport.requests.Session.post") as post:
        with pytest.raises(ValueError):
            RenphoClient.from_session(data)
    post.assert_not_called()


def test_wrong_expected_principal_is_rejected():
    with pytest.raises(ValueError, match="expected_user_id"):
        RenphoClient.from_session(SESSION, expected_user_id="456")


def test_bad_json_error_does_not_echo_contents(tmp_path):
    path = tmp_path / "session.json"
    path.write_text('test-phone-token-not-json')
    with pytest.raises(ValueError, match="cannot read session JSON") as exc:
        RenphoClient.from_session_file(path)
    assert 'test-phone-token' not in str(exc.value)
