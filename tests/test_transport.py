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
        "https://example.test/some/endpoint", json={"a": 1}, headers={"h": "v"}
    )
    fake_resp.raise_for_status.assert_called_once()
    assert result == {"ok": True}


def test_post_uses_own_session_by_default():
    transport = Transport("https://example.test")
    transport.session = MagicMock()
    transport.session.post.return_value.json.return_value = {}

    transport.post("e", {})

    assert transport.session.post.called
