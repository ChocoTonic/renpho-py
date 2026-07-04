"""HTTP transport for the Renpho cloud API.

Owns the connection session and the mechanics of issuing a request (URL
building, JSON encoding, status checking). Auth headers are supplied per call
by :class:`~renpho.client.RenphoClient`, which owns the token and user id.
Keeping this separate makes retries/timeouts/rate-limiting a single place to
change and makes the client trivially mockable.
"""

import requests

from .constants import API_BASE_URL


class Transport:
    """Executes POST requests against the Renpho API."""

    def __init__(self, base_url: str = API_BASE_URL, *, debug: bool = False):
        self.base_url = base_url
        self.debug = debug
        self.session = requests.Session()

    def post(
        self,
        endpoint: str,
        body: dict,
        *,
        headers: dict[str, str] | None = None,
        session: requests.Session | None = None,
    ) -> dict:
        """POST ``body`` (already encrypted) to ``endpoint`` and return JSON.

        ``session`` overrides the default session (used for concurrent shard
        probing, where sharing one session across threads would be unsafe).
        """
        url = f"{self.base_url}/{endpoint}"

        if self.debug:
            print(f"  POST {url}")

        resp = (session or self.session).post(url, json=body, headers=headers or {})

        if self.debug:
            print(f"  Status: {resp.status_code}")
            print(f"  Response: {resp.text[:300]}")

        resp.raise_for_status()
        return resp.json()
