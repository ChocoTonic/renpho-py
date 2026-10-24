from unittest.mock import patch

import pytest

from renpho.client import RenphoAPIError, RenphoClient, _check_response
from renpho.crypto import encrypt_request


class TestPaginationProgress:
    @pytest.mark.parametrize("method", ["get_measurements", "get_body_composition_measurements"])
    def test_repeated_page_raises_instead_of_looping(self, method):
        client = RenphoClient("a@b.com", "p")
        rows = [{"id": 1, "weight": 70}, {"id": 2, "weight": 71}]
        response = {"code": 101, "data": encrypt_request(rows)["encryptData"]}
        with (
            patch.object(client, "_post", return_value=response) as post,
            pytest.raises(RenphoAPIError, match="made no progress"),
        ):
            getattr(client, method)("measurements_info_1", 1, page_size=2)
        assert post.call_count == 2

    def test_reordered_previous_rows_are_still_no_progress(self):
        client = RenphoClient("a@b.com", "p")
        rows = [{"id": 1, "weight": 70}, {"id": 2, "weight": 71}]
        responses = [
            {"code": 101, "data": encrypt_request(page)["encryptData"]}
            for page in [rows, list(reversed(rows))]
        ]
        with (
            patch.object(client, "_post", side_effect=responses),
            pytest.raises(RenphoAPIError, match="made no progress"),
        ):
            client.get_body_composition_measurements("measurements_info_1", 1, page_size=2)

    @pytest.mark.parametrize("data", [None, encrypt_request([])["encryptData"]])
    def test_known_count_empty_page_reports_incomplete_fetch(self, data):
        client = RenphoClient("a@b.com", "p")
        with (
            patch.object(client, "_post", return_value={"code": 101, "data": data}) as post,
            pytest.raises(RenphoAPIError, match="advertised record count"),
        ):
            client.get_measurements("measurements_info_1", 1, total_count=10)
        assert post.call_count == 1

    @pytest.mark.parametrize("method", ["get_measurements", "get_body_composition_measurements"])
    def test_invalid_page_size_is_rejected_before_network_request(self, method):
        client = RenphoClient("a@b.com", "p")
        with patch.object(client, "_post") as post, pytest.raises(ValueError):
            getattr(client, method)("measurements_info_1", 1, page_size=0)
        post.assert_not_called()

    def test_client_exposes_transport_timeout(self):
        client = RenphoClient("a@b.com", "p", timeout=(2.0, 5.0))
        assert client._transport.timeout == (2.0, 5.0)


@pytest.mark.parametrize("msg", [None, ""])
def test_server_message_fallback(msg):
    with pytest.raises(RenphoAPIError, match="Decryption failed"):
        _check_response({"code": -114, "msg": msg, "message": "Decryption failed"})
