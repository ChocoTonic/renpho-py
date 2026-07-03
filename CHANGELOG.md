# Changelog

All notable changes to `renpho-py` are documented here. This project follows
[Semantic Versioning](https://semver.org/): breaking changes to the public API
bump the major version only.

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
