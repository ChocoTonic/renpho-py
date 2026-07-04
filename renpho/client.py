"""Renpho API client for fetching scale measurements."""

import json
import sys
from concurrent.futures import ThreadPoolExecutor

import requests

from .constants import (
    API_BASE_URL,
    APP_VERSION,
    BODY_WEIGHT_SCALES,
    ENDPOINTS,
    MEASUREMENT_TABLE_NAMES,
    PLATFORM,
    SUCCESS_CODES,
)
from .crypto import (
    decrypt_response,
    encrypt_empty_bytes,
    encrypt_empty_object,
    encrypt_request,
)


class RenphoAPIError(Exception):
    """Raised when the Renpho API returns an error response."""

    def __init__(self, context: str, code, msg: str):
        self.context = context
        self.code = code
        self.msg = msg
        super().__init__(f"{context} failed: code={code}, msg={msg}")


def _check_response(result: dict, context: str = "API call") -> None:
    """Raise :class:`RenphoAPIError` if the response indicates failure."""
    code = result.get("code")
    msg = result.get("msg", "")
    if msg.lower() == "success" or code in SUCCESS_CODES:
        return
    raise RenphoAPIError(context, code, msg)


class RenphoClient:
    """Client for the Renpho cloud API.

    Example::

        client = RenphoClient("user@example.com", "password")
        client.login()
        measurements = client.get_all_measurements()
        for m in measurements:
            print(m["weight"], m.get("bodyfat"))
    """

    def __init__(self, email: str, password: str, *, debug: bool = False):
        self.email = email
        self.password = password
        self.debug = debug
        self.token: str | None = None
        self.user_id: int | str | None = None
        self.user_info: dict | None = None
        self._session = requests.Session()
        # Cache of shard-discovery results, keyed by str(user_id).
        self._table_cache: dict[str, list[str]] = {}

    # ----- internal helpers -----

    def _post(
        self,
        endpoint: str,
        body: dict,
        *,
        auth: bool = True,
        session: requests.Session | None = None,
    ) -> dict:
        """Make an encrypted POST request to the Renpho API.

        ``session`` lets callers supply their own :class:`requests.Session`
        (used for concurrent shard probing, where sharing the client's session
        across threads would be unsafe). Defaults to the client's session.
        """
        url = f"{API_BASE_URL}/{endpoint}"
        headers: dict[str, str] = {}
        if auth and self.token:
            headers["token"] = self.token
            headers["userId"] = str(self.user_id)
            headers["appVersion"] = APP_VERSION
            headers["platform"] = PLATFORM

        if self.debug:
            print(f"  POST {url}")
            if auth and self.token:
                print(f"  Headers: token={self.token[:20]}..., userId={self.user_id}")

        resp = (session or self._session).post(url, json=body, headers=headers)

        if self.debug:
            print(f"  Status: {resp.status_code}")
            print(f"  Response: {resp.text[:300]}")

        resp.raise_for_status()
        return resp.json()

    # ----- public API -----

    def login(self) -> dict:
        """Authenticate and store the session token.

        Returns the full decrypted login response (includes user profile).

        Raises:
            RenphoAPIError: If the API rejects the credentials.
            requests.HTTPError: On transport-level failures.
        """
        login_payload = {
            "questionnaire": {},
            "login": {
                "password": self.password,
                "areaCode": "US",
                "appRevision": APP_VERSION,
                "cellphoneType": "PythonScript",
                "systemType": "11",
                "email": self.email,
                "platform": PLATFORM,
            },
            "bindingList": {
                "deviceTypes": BODY_WEIGHT_SCALES,
            },
        }

        encrypted_body = encrypt_request(login_payload)
        result = self._post(ENDPOINTS["login"], encrypted_body, auth=False)
        _check_response(result, "Login")

        user_data = decrypt_response(result["data"])

        if self.debug:
            print(f"  Decrypted login: {json.dumps(user_data, indent=2)[:500]}")

        login_info = user_data.get("login", {})
        self.token = login_info.get("token")
        self.user_id = login_info.get("id")
        self.user_info = login_info

        if not self.token:
            raise RenphoAPIError("Login", None, "No token in login response")

        return user_data

    def get_device_info(self) -> dict:
        """Get device info including scale table names and record counts.

        Returns:
            Decrypted device info dict (contains ``scale`` list among others).

        Raises:
            RenphoAPIError: On API-level failure.
        """
        for attempt, body_fn in enumerate([encrypt_empty_bytes, encrypt_empty_object]):
            encrypted_body = body_fn()
            try:
                result = self._post(ENDPOINTS["device_info"], encrypted_body)
                break
            except requests.exceptions.HTTPError as e:
                if attempt == 0:
                    if self.debug:
                        print(
                            f"  Attempt 1 failed ({e}), retrying with empty object..."
                        )
                    continue
                raise

        _check_response(result, "GetDeviceInfo")
        data = decrypt_response(result["data"])

        if self.debug:
            print(f"  Device info: {json.dumps(data, indent=2)[:500]}")

        return data

    def get_measurements(
        self, table_name: str, user_id, total_count: int, *, page_size: int = 50
    ) -> list[dict]:
        """Fetch measurements from a specific scale table with pagination.

        Args:
            table_name: Dynamic table name from :meth:`get_device_info`.
            user_id: The user ID to query for.
            total_count: Total records available (from device info).
            page_size: Records per page (default 50).

        Returns:
            List of measurement dicts.
        """
        all_measurements: list[dict] = []
        page = 1

        while len(all_measurements) < total_count:
            request_data = {
                "pageNum": page,
                "pageSize": page_size,
                "userIds": [str(user_id)],
                "tableName": table_name,
            }

            if self.debug:
                print(f"  Page {page} (got {len(all_measurements)} so far)...")

            encrypted_body = encrypt_request(request_data)
            result = self._post(ENDPOINTS["measurements"], encrypted_body)
            _check_response(result, f"Measurements page {page}")

            if not result.get("data"):
                break

            page_data = decrypt_response(result["data"])

            if self.debug:
                if isinstance(page_data, list):
                    print(f"  Got {len(page_data)} records")
                else:
                    print(f"  Response type: {type(page_data)}")

            records = self._extract_records(page_data)
            if records is None:
                break

            all_measurements.extend(records)
            page += 1

        return all_measurements

    def get_body_composition_measurements(
        self, table_name: str, user_id, *, page_size: int = 50
    ) -> list[dict]:
        """Fetch body composition measurements using the newer API endpoint.

        Body composition scales (those with impedance sensors) store data under
        ``queryBodyCompositionMeasureData`` rather than ``queryAllMeasureDataList``.
        The server-side count in device info is often reported as 0 for these
        scales even when data exists, so this method paginates until the server
        returns an empty page rather than relying on a total count.

        Args:
            table_name: Dynamic table name from :meth:`get_device_info`.
            user_id: The user ID to query for.
            page_size: Records per page (default 50).

        Returns:
            List of measurement dicts.
        """
        all_measurements: list[dict] = []
        page = 1

        while True:
            request_data = {
                "pageNum": page,
                "pageSize": page_size,
                "userIds": [str(user_id)],
                "tableName": table_name,
            }

            if self.debug:
                print(f"  Page {page} (got {len(all_measurements)} so far)...")

            encrypted_body = encrypt_request(request_data)
            result = self._post(
                ENDPOINTS["body_composition_measurements"], encrypted_body
            )
            _check_response(result, f"BodyCompositionMeasurements page {page}")

            if not result.get("data"):
                break

            page_data = decrypt_response(result["data"])

            if self.debug:
                if isinstance(page_data, list):
                    print(f"  Got {len(page_data)} records")
                else:
                    print(f"  Response type: {type(page_data)}")

            records = self._extract_records(page_data)
            if not records:
                break

            all_measurements.extend(records)
            if len(records) < page_size:
                break
            page += 1

        return all_measurements

    def _shard_has_data(self, user_id, table, *, session=None) -> bool:
        """Return True if ``table`` holds at least one record for ``user_id``.

        A single failed request (transport error) is treated as "no data" so
        one flaky probe cannot abort discovery of the remaining shards.
        """
        try:
            encrypted_body = encrypt_request({
                "pageNum": 1,
                "pageSize": 1,
                "userIds": [str(user_id)],
                "tableName": table,
            })
            result = self._post(
                ENDPOINTS["body_composition_measurements"],
                encrypted_body,
                session=session,
            )
            if not result.get("data"):
                return False
            page_data = decrypt_response(result["data"])
            return bool(self._extract_records(page_data))
        except requests.exceptions.RequestException as e:
            if self.debug:
                print(f"  Probe of {table} for user {user_id} failed: {e}")
            return False

    def discover_user_tables(
        self,
        user_id,
        *,
        refresh: bool = False,
        max_workers: int = 1,
    ) -> list[str]:
        """Probe all measurement tables for a given user_id and return the ones with data.

        Body composition scales shard measurements across 16 tables
        (``measurements_info_0`` through ``measurements_info_F``). The server
        only reports the table for the logged-in user via ``device/count``,
        so for any other linked account this method probes each suffix.

        Results are cached per user ID on the client instance; pass
        ``refresh=True`` to re-probe (or call :meth:`clear_table_cache`). Set
        ``max_workers`` above 1 to probe shards concurrently (each worker uses
        its own session, so this is thread-safe).

        Calls :meth:`login` first if no token is set.

        Args:
            user_id: The user ID to probe for.
            refresh: Ignore any cached result and probe again.
            max_workers: Number of concurrent probe workers (1 = serial).

        Returns:
            List of table names (in canonical shard order) that contain at
            least one record for ``user_id``.
        """
        if not self.token:
            self.login()

        key = str(user_id)
        if not refresh and key in self._table_cache:
            return list(self._table_cache[key])

        if max_workers and max_workers > 1:
            found = self._discover_concurrent(user_id, max_workers)
        else:
            found = [
                table
                for table in MEASUREMENT_TABLE_NAMES
                if self._shard_has_data(user_id, table)
            ]

        self._table_cache[key] = found
        return list(found)

    def _discover_concurrent(self, user_id, max_workers) -> list[str]:
        """Probe all shards concurrently, one dedicated session per worker."""

        def probe(table):
            session = requests.Session()
            try:
                return table, self._shard_has_data(user_id, table, session=session)
            finally:
                session.close()

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            has_data = dict(executor.map(probe, MEASUREMENT_TABLE_NAMES))

        # Preserve canonical shard order regardless of completion order.
        return [table for table in MEASUREMENT_TABLE_NAMES if has_data.get(table)]

    def clear_table_cache(self) -> None:
        """Clear cached shard-discovery results (see :meth:`discover_user_tables`)."""
        self._table_cache.clear()

    def get_all_measurements(
        self,
        extra_user_ids: list | None = None,
        *,
        max_workers: int = 1,
    ) -> list[dict]:
        """High-level helper: fetch device info then pull all measurements.

        Tries the body composition endpoint first (used by impedance scales).
        Falls back to the basic measurements endpoint for weight-only scales.
        The server-side count in device info is unreliable for body composition
        scales (often reports 0), so this method always attempts a fetch.

        Calls :meth:`login` first if no token is set.

        Args:
            extra_user_ids: Additional user IDs to fetch measurements for. The
                Renpho API allows a logged-in user to read measurements belonging
                to other linked accounts (e.g. a separate account from before a
                Google SSO migration). Each id is probed against all known
                measurement tables. Pass these when you have multiple Renpho
                accounts associated with the same physical scale. A failure while
                fetching one extra account is logged (in debug mode) and skipped,
                so it never discards the accounts already fetched.
            max_workers: Concurrency for the per-extra-account shard discovery
                (passed to :meth:`discover_user_tables`; 1 = serial).

        Returns:
            List of measurement dicts sorted by timestamp (newest first),
            deduped by record ``id``.
        """
        if not self.token:
            self.login()

        device_info = self.get_device_info()
        scales = device_info.get("scale", [])

        all_measurements: list[dict] = []
        for scale in scales:
            table_name = scale.get("tableName")
            count = scale.get("count", 0)
            user_ids = scale.get("userIds", [])

            if not table_name:
                continue

            uid = self.user_id
            if user_ids and uid not in user_ids:
                uid = user_ids[0]

            # Try body composition endpoint first; it handles both newer
            # impedance scales and cases where count is incorrectly zero.
            measurements = self.get_body_composition_measurements(table_name, uid)
            if not measurements and count > 0:
                measurements = self.get_measurements(table_name, uid, count)

            all_measurements.extend(measurements)

        for extra_uid in extra_user_ids or []:
            try:
                for table in self.discover_user_tables(
                    extra_uid, max_workers=max_workers
                ):
                    all_measurements.extend(
                        self.get_body_composition_measurements(table, extra_uid)
                    )
            except requests.exceptions.RequestException as e:
                if self.debug:
                    print(f"  Failed to fetch extra user {extra_uid}: {e}")
                continue

        # Dedupe by record id (each measurement is a unique server-side row).
        seen_ids: set = set()
        unique: list[dict] = []
        for m in all_measurements:
            rid = m.get("id")
            if rid is not None and rid in seen_ids:
                continue
            if rid is not None:
                seen_ids.add(rid)
            unique.append(m)

        unique.sort(
            key=lambda m: m.get("timeStamp", 0) or 0,
            reverse=True,
        )
        return unique

    @staticmethod
    def _extract_records(page_data) -> list[dict] | None:
        """Extract measurement records from a page response."""
        if isinstance(page_data, list):
            return page_data if page_data else None

        if isinstance(page_data, dict):
            for key in ("list", "data", "records", "measurements"):
                if key in page_data and isinstance(page_data[key], list):
                    return page_data[key] if page_data[key] else None

            if "weight" in page_data:
                return [page_data]

        return None
