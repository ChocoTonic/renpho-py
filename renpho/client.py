"""Renpho API client for fetching scale measurements."""

import json
from concurrent.futures import ThreadPoolExecutor

import requests

from .constants import (
    APP_VERSION,
    BODY_WEIGHT_SCALES,
    ENDPOINTS,
    MEASUREMENT_TABLE_NAMES,
    MEASUREMENT_TABLE_SHARDS,
    PLATFORM,
)
from .crypto import (
    decrypt_response,
    encrypt_empty_bytes,
    encrypt_empty_object,
    encrypt_request,
)
from .exceptions import RenphoAPIError
from .exceptions import check_response as _check_response
from .transport import Transport

# A Renpho user ID is sometimes an int (login response) and sometimes a
# stringified int (measurement queries); accept either.
UserId = int | str

__all__ = ["RenphoClient", "RenphoAPIError"]


class RenphoClient:
    """Client for the Renpho cloud API.

    Example::

        client = RenphoClient("user@example.com", "password")
        client.login()
        measurements = client.get_all_measurements()
        for m in measurements:
            print(m["weight"], m.get("bodyfat"))
    """

    def __init__(
        self,
        email: str,
        password: str,
        *,
        debug: bool = False,
        timeout: float | tuple[float, float] = (10.0, 30.0),
    ):
        self.email = email
        self.password = password
        self.debug = debug
        self.token: str | None = None
        self.user_id: int | str | None = None
        self.user_info: dict | None = None
        self._transport = Transport(debug=debug, timeout=timeout)
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
        """Assemble auth headers and delegate the request to the transport.

        ``session`` lets callers supply their own :class:`requests.Session`
        (used for concurrent shard probing, where sharing one session across
        threads would be unsafe). Defaults to the transport's own session.
        """
        # Protocol headers are required even before login. Without them the
        # server rejects the encrypted payload with code -114.
        headers: dict[str, str] = {"appVersion": APP_VERSION, "platform": PLATFORM}
        if auth and self.token:
            headers["token"] = self.token
            headers["userId"] = str(self.user_id)

        return self._transport.post(endpoint, body, headers=headers, session=session)

    # ----- public API -----

    def login(self, *, expected_user_id: UserId | None = None) -> dict:
        """Authenticate and store the session token.

        Returns the full decrypted login response (includes user profile).

        Args:
            expected_user_id: Require the authenticated principal to match the
                known app account. This catches credentials for a different
                account before an unrelated measurement timeline is fetched.

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

        if expected_user_id is not None and str(self.user_id) != str(expected_user_id):
            self.token = None
            self.user_id = None
            self.user_info = None
            raise RenphoAPIError(
                "Login account mismatch", None,
                "Password login authenticated a different account from the "
                "expected app account. Verify the configured email against "
                "the account signed into the Renpho app and use credentials "
                "belonging to that account.",
            )

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
        self,
        table_name: str,
        user_id,
        total_count: int | None = None,
        *,
        page_size: int = 50,
    ) -> list[dict]:
        """Fetch measurements from a specific scale table with pagination.

        Args:
            table_name: Dynamic table name from :meth:`get_device_info`.
            user_id: The user ID to query for.
            total_count: Total records available (from device info). If omitted,
                paginate until the server returns a short page.
            page_size: Records per page (default 50).

        Returns:
            List of measurement dicts.
        """
        if page_size <= 0:
            raise ValueError("page_size must be positive")
        all_measurements: list[dict] = []
        seen_records: set[str] = set()
        page = 1

        while total_count is None or len(all_measurements) < total_count:
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
                if total_count is not None:
                    raise RenphoAPIError(
                        f"Measurements page {page}", None,
                        "Pagination ended before the advertised record count was reached",
                    )
                break

            page_data = decrypt_response(result["data"])

            if self.debug:
                if isinstance(page_data, list):
                    print(f"  Got {len(page_data)} records")
                else:
                    print(f"  Response type: {type(page_data)}")

            records = self._extract_records(page_data)
            if not records:
                if total_count is not None:
                    raise RenphoAPIError(
                        f"Measurements page {page}", None,
                        "Pagination ended before the advertised record count was reached",
                    )
                break

            self._check_page_progress(records, seen_records, f"Measurements page {page}")
            all_measurements.extend(records)
            if total_count is None and len(records) < page_size:
                break
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
        if page_size <= 0:
            raise ValueError("page_size must be positive")
        all_measurements: list[dict] = []
        seen_records: set[str] = set()
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

            self._check_page_progress(records, seen_records, f"Measurements page {page}")
            all_measurements.extend(records)
            if len(records) < page_size:
                break
            page += 1

        return all_measurements


    def _shard_has_data(
        self,
        user_id: UserId,
        table: str,
        *,
        session: requests.Session | None = None,
        strict: bool = False,
    ) -> bool:
        """Return True if ``table`` holds at least one record for ``user_id``.

        By default failed endpoint requests are skipped. Strict probes raise
        when failures leave the presence of data uncertain. Either endpoint
        returning records is enough to establish that the shard has data.
        """
        encrypted_body = encrypt_request({
            "pageNum": 1,
            "pageSize": 1,
            "userIds": [str(user_id)],
            "tableName": table,
        })
        failures: list[Exception] = []
        for endpoint in ("body_composition_measurements", "measurements"):
            try:
                result = self._post(
                    ENDPOINTS[endpoint], encrypted_body, session=session
                )
                _check_response(result, f"Shard discovery via {endpoint}")
                if result.get("data") and self._extract_records(
                    decrypt_response(result["data"])
                ):
                    return True
            except (requests.exceptions.RequestException, RenphoAPIError) as error:
                failures.append(error)
                if self.debug:
                    print(f"  Probe of {table} via {endpoint} failed: {error}")
        if strict and failures:
            raise RenphoAPIError(
                "Shard discovery", None,
                f"Could not establish whether {table} contains data; "
                f"{len(failures)} endpoint request(s) failed",
            ) from failures[0]
        return False


    def discover_user_tables(
        self,
        user_id: UserId,
        *,
        refresh: bool = False,
        max_workers: int = 1,
        strict: bool = False,
    ) -> list[str]:
        """Probe all measurement tables for a given user_id and return the ones with data.

        Body composition scales shard measurements across 24 decimal tables
        (``measurements_info_0`` through ``measurements_info_23``). The server
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
            strict: Re-probe and raise if a failed request could hide data.
                Failed discoveries are never cached in this mode.

        Returns:
            List of table names (in canonical shard order) that contain at
            least one record for ``user_id``.
        """
        if not self.token:
            self.login()

        key = str(user_id)
        if not refresh and not strict and key in self._table_cache:
            return list(self._table_cache[key])

        def has_data(table: str) -> bool:
            if strict:
                return self._shard_has_data(user_id, table, strict=True)
            return self._shard_has_data(user_id, table)

        candidates = list(MEASUREMENT_TABLE_NAMES)
        expected = self.measurement_table_for(user_id)
        if expected in candidates:
            candidates.remove(expected)
            if has_data(expected):
                found = [expected]
                self._table_cache[key] = found
                return list(found)

        if max_workers and max_workers > 1:
            found = self._discover_concurrent(
                user_id, max_workers, candidates, strict=strict
            )
        else:
            found = [t for t in candidates if has_data(t)]

        self._table_cache[key] = found
        return list(found)


    def _discover_concurrent(
        self, user_id: UserId, max_workers: int, tables: list[str], *, strict: bool = False
    ) -> list[str]:
        """Probe all shards concurrently, one dedicated session per worker."""

        def probe(table: str) -> tuple[str, bool]:
            session = requests.Session()
            try:
                return table, self._shard_has_data(
                    user_id, table, session=session, strict=strict
                )
            finally:
                session.close()

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            has_data = dict(executor.map(probe, tables))

        # Preserve canonical shard order regardless of completion order.
        return [table for table in tables if has_data.get(table)]


    def clear_table_cache(self) -> None:
        """Clear cached shard-discovery results (see :meth:`discover_user_tables`)."""
        self._table_cache.clear()

    def get_all_measurements(
        self,
        extra_user_ids: list[str] | None = None,
        *,
        max_workers: int = 1,
        strict: bool = False,
        profile_user_id: str | None = None,
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
            profile_user_id: Fetch only this measurement profile, ignoring extra
                accounts. Verify bUserId (or legacy userId) on every record.
            strict: Require every configured extra account to return records.
                Raise on failed probes, fetches, or an empty extra account
                rather than returning a silently incomplete timeline.

        Returns:
            List of measurement dicts sorted by timestamp (newest first),
            deduped by record ``id``.
        """
        if not self.token:
            self.login()

        device_info = self.get_device_info()
        scales = device_info.get("scale", [])

        if profile_user_id is not None:
            selected = str(profile_user_id)
            profile_tables = {
                scale["tableName"] for scale in scales
                if scale.get("tableName")
                and selected in {str(uid) for uid in scale.get("userIds", [])}
            }
            if not profile_tables:
                profile_tables = set(self.discover_user_tables(
                    selected, max_workers=max_workers, strict=strict
                ))
            records = {}
            for table in sorted(profile_tables):
                rows = self.get_body_composition_measurements(table, selected)
                if not rows:
                    rows = self.get_measurements(table, selected)
                for row in rows:
                    owner = row.get("bUserId") or row.get("userId")
                    if str(owner) == selected:
                        key = (table, row.get("id", (row.get("timeStamp"), row.get("weight"))))
                        records[key] = row
            if strict and not records:
                raise RenphoAPIError(
                    "Profile measurements", None,
                    f"Selected measurement profile {selected} returned no identifiable records.",
                )
            return sorted(
                records.values(), key=lambda row: row.get("timeStamp", 0) or 0, reverse=True
            )

        all_measurements: list[dict] = []
        seen: set[tuple[str, object]] = set()

        def collect(table: str, records: list[dict]) -> None:
            for record in records:
                record_id = record.get("id")
                key = (table, record_id)
                if record_id is not None and key in seen:
                    continue
                if record_id is not None:
                    seen.add(key)
                all_measurements.append(record)
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

            collect(table_name, measurements)

        for extra_uid in extra_user_ids or []:
            try:
                discovery_options = {"strict": True} if strict else {}
                tables = self.discover_user_tables(
                    extra_uid, max_workers=max_workers, **discovery_options
                )
                if strict and not tables:
                    raise RenphoAPIError(
                        "Extra-account measurements", None,
                        "A configured extra account returned no measurements across "
                        "the 24 known shards. Verify its current account ID and "
                        "cloud sync in the Renpho app; empty responses do not "
                        "confirm that the account has no weigh-ins.",
                    )
                extra_count = 0
                for table in tables:
                    measurements = self.get_body_composition_measurements(
                        table, extra_uid
                    )
                    if not measurements:
                        measurements = self.get_measurements(table, extra_uid)
                    extra_count += len(measurements)
                    collect(table, measurements)
                if strict and not extra_count:
                    raise RenphoAPIError(
                        "Extra-account measurements", None,
                        "A configured extra account became empty after discovery; "
                        "retry the fetch before accepting a partial timeline.",
                    )
            except (requests.exceptions.RequestException, RenphoAPIError) as e:
                if strict:
                    raise
                if self.debug:
                    print(f"  Failed to fetch extra user {extra_uid}: {e}")
                continue

        all_measurements.sort(
            key=lambda m: m.get("timeStamp", 0) or 0,
            reverse=True,
        )
        return all_measurements


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

    @staticmethod
    def _check_page_progress(
        records: list[dict], seen_records: set[str], context: str
    ) -> None:
        """Stop pagination if the server returns only previously seen rows."""
        fingerprints = {json.dumps(row, sort_keys=True) for row in records}
        if fingerprints.issubset(seen_records):
            raise RenphoAPIError(
                context, None,
                "Measurement pagination made no progress; the server repeated earlier records",
            )
        seen_records.update(fingerprints)

    @staticmethod
    def measurement_table_for(user_id: UserId) -> str | None:
        """Return the normal shard for ``user_id`` (``user_id % 24``)."""
        try:
            return f"measurements_info_{int(user_id) % MEASUREMENT_TABLE_SHARDS}"
        except (TypeError, ValueError):
            return None

    def get_measurement_profiles(self) -> list[dict]:
        """List selectable measurement profiles without downloading history."""
        if not self.token:
            self.login()
        ids = {str(self.user_id)}
        for scale in self.get_device_info().get("scale", []):
            ids.update(str(uid) for uid in scale.get("userIds", []) if uid)
        return [
            {"user_id": uid, "is_account_owner": uid == str(self.user_id)}
            for uid in sorted(ids)
        ]



