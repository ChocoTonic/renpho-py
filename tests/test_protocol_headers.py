"""Protocol metadata must be sent independently of session authentication."""

from unittest.mock import patch, sentinel

import pytest

from renpho.client import RenphoClient
from renpho.constants import APP_VERSION, PLATFORM
from renpho.crypto import encrypt_request


@pytest.mark.parametrize("authenticated", [False, True])
def test_protocol_headers_and_transport_arguments(authenticated):
    client = RenphoClient("test@example.invalid", "password")
    client.token = "session-token"
    client.user_id = 123
    body = {"encryptData": "payload"}
    with patch.object(client._transport, "post", return_value={"code": 0}) as post:
        result = client._post("endpoint", body, auth=authenticated, session=sentinel.session)
    expected = {"appVersion": APP_VERSION, "platform": PLATFORM}
    if authenticated:
        expected.update(token="session-token", userId="123")
    post.assert_called_once_with("endpoint", body, headers=expected, session=sentinel.session)
    assert result == {"code": 0}


def test_login_omits_existing_session_and_retains_encrypted_payload():
    client = RenphoClient("test@example.invalid", "password")
    client.token = "stale-token"
    client.user_id = 456
    response = {
        "code": 0,
        "data": encrypt_request({"login": {"id": 123, "token": "new-token"}})["encryptData"],
    }
    with patch.object(client._transport, "post", return_value=response) as post:
        client.login()
    post.assert_called_once()
    assert post.call_args.kwargs["headers"] == {
        "appVersion": APP_VERSION, "platform": PLATFORM,
    }
    assert set(post.call_args.args[1]) == {"encryptData"}
    assert "password" not in str(post.call_args.kwargs)
    assert client.token == "new-token"
    assert client.user_id == 123
