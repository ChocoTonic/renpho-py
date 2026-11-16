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


def token_time_response(data):
    return {"code": 101, "msg": "success", "data": encrypt_request(data)["encryptData"]}


def test_refresh_adopts_and_persists_before_next_request(tmp_path):
    path = tmp_path / "phone.json"
    path.write_text(json.dumps(SESSION))
    path.chmod(0o644)
    client = RenphoClient.from_session_file(path)
    response = token_time_response({"token": "replacement-secret", "userId": "123",
                                    "issAt": 1800000000000, "expAt": 1807776000000})
    with patch.object(client._transport, "post", side_effect=[response, {"code": 101}]) as post:
        info = client.refresh_session()
        client._post("read-endpoint", {})
    assert post.call_args_list[0].args[0] == ENDPOINTS["token_time"]
    assert post.call_args_list[0].kwargs["headers"]["token"] == SESSION["token"]
    assert post.call_args_list[1].kwargs["headers"]["token"] == "replacement-secret"
    assert info == {"issued_at": 1800000000, "expires_at": 1807776000,
                    "token_replaced": True}
    assert "replacement-secret" not in repr(info)
    saved = json.loads(path.read_text())
    assert saved['token'] == "replacement-secret"
    assert "password" not in saved
    assert path.stat().st_mode & 0o777 == 0o600
    restored = RenphoClient.from_session_file(path)
    assert restored.token == client.token
    assert restored.token_expires_at == 1807776000
    with pytest.raises(RenphoSessionError):
        restored.login()


@pytest.mark.parametrize('token', [None, '', '   ', SESSION['token']])
def test_refresh_without_replacement_keeps_current_token(token):
    client = RenphoClient.from_session(SESSION)
    with patch.object(client._transport, "post", return_value=token_time_response(
        {"token": token, "expAt": 1807776000000}
    )):
        result = client.refresh_session()
    assert result['token_replaced'] is False
    assert client.token == SESSION['token']
    assert client.token_expires_at == 1807776000


@pytest.mark.parametrize('data', [[], None, {"token": []},
    {"token": "new", "userId": "456"}, {"token": "new", "expAt": True},
    {"token": "new", "expAt": float('inf')}, {"token": "new", "expAt": -1}])
def test_invalid_renewal_does_not_mutate_existing_session(data, tmp_path):
    path = tmp_path / 'phone.json'
    path.write_text(json.dumps(SESSION))
    client = RenphoClient.from_session_file(path)
    with patch.object(client._transport, 'post', return_value=token_time_response(data)):
        with pytest.raises(RenphoSessionError):
            client.refresh_session()
    assert client.token == SESSION['token']
    assert json.loads(path.read_text()) == SESSION


def test_refresh_rejection_never_logs_in():
    client = RenphoClient.from_session(SESSION)
    with patch.object(client._transport, 'post', return_value={"code": 403}) as post:
        with pytest.raises(RenphoSessionError):
            client.refresh_session()
    assert post.call_count == 1
    assert post.call_args.args[0] == ENDPOINTS['token_time']


def test_failed_persistence_retains_replacement_in_memory_and_old_file(tmp_path):
    path = tmp_path / 'phone.json'
    path.write_text(json.dumps(SESSION))
    client = RenphoClient.from_session_file(path)
    with patch.object(client._transport, 'post', return_value=token_time_response(
        {"token": "new-secret"}
    )), patch('renpho.session.os.replace', side_effect=OSError('disk error')):
        with pytest.raises(RenphoSessionError, match='updated in memory') as exc:
            client.refresh_session()
    assert 'new-secret' not in str(exc.value)
    assert client.token == 'new-secret'
    assert json.loads(path.read_text()) == SESSION
    assert list(tmp_path.iterdir()) == [path]
    client.save_session()
    assert json.loads(path.read_text())['token'] == 'new-secret'


def test_refresh_requires_current_session_even_for_password_client():
    client = RenphoClient('owner@example.com', 'password')
    with patch.object(client._transport, 'post') as post:
        with pytest.raises(RenphoSessionError):
            client.refresh_session()
    post.assert_not_called()


def test_expiry_is_decoded_without_network_or_signature_verification():
    import base64
    payload = base64.urlsafe_b64encode(json.dumps({'exp': 1807776000}).encode()).decode()
    client = RenphoClient.from_session({**SESSION, 'token': 'header.' + payload + '.signature'})
    with patch.object(client._transport, 'post') as post:
        assert client.token_expires_at == 1807776000
    post.assert_not_called()


@pytest.mark.parametrize('token', ['opaque', 'header.invalid.signature', 'a.W10.b'])
def test_opaque_or_malformed_token_has_unknown_local_expiry(token):
    assert RenphoClient.from_session({**SESSION, 'token': token}).token_expires_at is None


def test_password_login_clears_previous_session_expiry():
    import base64
    payload = base64.urlsafe_b64encode(json.dumps({'exp': 1807776000}).encode()).decode()
    replacement = 'header.' + payload + '.signature'
    client = RenphoClient('owner@example.com', 'password')
    client.token, client.user_id = 'old-token', '123'
    login_data = encrypt_request({'login': {'token': replacement, 'id': '123'}})
    with patch.object(client._transport, 'post', side_effect=[
        token_time_response({'expAt': 2000000000000}),
        {'code': 101, 'msg': 'success', 'data': login_data['encryptData']},
    ]):
        client.refresh_session()
        assert client.token_expires_at == 2000000000
        client.login()
        assert client.token_expires_at == 1807776000
