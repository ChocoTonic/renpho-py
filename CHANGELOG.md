# Changelog

All notable changes to `renpho-py` are documented here. This project follows
[Semantic Versioning](https://semver.org/): breaking changes to the public API
bump the major version only.

## [1.1.0] — 2026-07-03

Hardening of the multi-account feature (plan P1 + P2 in
[docs/multi-account.md](docs/multi-account.md)). All additive — the public API
remains a superset of 1.0.0.

### Added
- **Concurrent shard discovery.** `discover_user_tables(user_id, max_workers=N)`
  and `get_all_measurements(extra_user_ids=..., max_workers=N)` can probe the 16
  shards in parallel (each worker uses its own session, so it's thread-safe).
  Defaults to `max_workers=1` (serial, unchanged).
- **Discovery caching.** `discover_user_tables` now caches results per user ID on
  the client instance. Pass `refresh=True` to re-probe; new `clear_table_cache()`
  method to reset.

### Changed
- **Probe failures are isolated.** A transport error while probing one shard —
  or while fetching one extra account in `get_all_measurements` — is now logged
  (in debug mode) and skipped, instead of aborting the whole call and discarding
  data already fetched.
- **`discover_user_tables` logs in if needed.** It now calls `login()` when no
  token is set, matching `get_all_measurements`.
- **Tighter typing.** `extra_user_ids: list[str] | None`; new `UserId = int | str`
  alias applied to the multi-account methods.

### Deferred (with rationale, see docs/multi-account.md §5)
- Reusing the probe's first page to skip a refetch — dropped: probes use
  `pageSize=1`, so they can't seed a `pageSize=50` fetch. No real saving.
- Weight-only secondary accounts — needs unverifiable assumptions about the
  basic-measurements endpoint for non-logged-in users; left as a documented gap.
- Composite dedup for `id`-less records — would change default behavior; kept
  opt-in-only for a future minor.

## [1.0.0] — 2026-07-03

First release of `renpho-py`, an independently maintained continuation of the
abandoned [`renpho-api`](https://github.com/danvaneijck/renpho-api). Behavioral
parity with the last `renpho-api` state plus the multi-account feature below.

The public API is unchanged from `renpho-api`, so migration is a one-line swap:

```bash
pip uninstall renpho-api && pip install renpho-py
```

Imports are identical (`from renpho import RenphoClient`).

### Added
- **Multiple Renpho accounts on one email.** `get_all_measurements()` now
  accepts `extra_user_ids: list[str] | None`. For each extra user ID it probes
  all 16 sharded measurement tables, fetches matching records, and dedupes the
  combined timeline by record `id`.
- New `RenphoClient.discover_user_tables(user_id)` — probes
  `measurements_info_0`..`measurements_info_F` and returns the tables that hold
  data for a given user ID (needed because the server only reports the
  logged-in user's table via `device/count`).
- `MEASUREMENT_TABLE_NAMES` constant and a `body_composition_scale_count`
  endpoint entry.
- Tests covering `discover_user_tables` and the `extra_user_ids` path.
- `py.typed` marker (PEP 561) so downstream users get the bundled type hints.
- `LICENSE` and `NOTICE` files (MIT, preserving original attribution).

### Changed
- `get_all_measurements()` return value is now deduped by record `id`
  (records without an `id` are always kept, so nothing is silently dropped).

### Notes
- Public API is a superset of `renpho-api`; no removals, no signature breaks.
