"""Tests for renpho.transport.Transport."""

from unittest.mock import MagicMock

from renpho.transport import Transport


def test_post_builds_url_passes_headers_and_returns_json():
    transport = Transport("https://example.test")
    fake_resp = MagicMock()
    fake_resp.json.return_value = {"ok": True}
    fake_session = MagicMock()
    fake_session.post.return_value = fake_resp

    result = transport.post(
        "some/endpoint", {"a": 1}, headers={"h": "v"}, session=fake_session
    )

    fake_session.post.assert_called_once_with(
        "https://example.test/some/endpoint", json={"a": 1}, headers={"h": "v"},
        timeout=(10.0, 30.0),
    )
    fake_resp.raise_for_status.assert_called_once()
    assert result == {"ok": True}


def test_post_uses_own_session_by_default():
    transport = Transport("https://example.test")
    transport.session = MagicMock()
    transport.session.post.return_value.json.return_value = {}

    transport.post("e", {})

    assert transport.session.post.called


def test_custom_timeout_is_applied_and_timeout_propagates():
    import pytest
    import requests

    transport = Transport(timeout=(2.0, 5.0))
    transport.session = MagicMock()
    transport.session.post.side_effect = requests.exceptions.ReadTimeout("timed out")
    with pytest.raises(requests.exceptions.ReadTimeout):
        transport.post("e", {})
    assert transport.session.post.call_args.kwargs["timeout"] == (2.0, 5.0)
