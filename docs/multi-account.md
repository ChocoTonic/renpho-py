# Multi-account support — analysis & forward plan

Status of the feature that never made it into upstream `renpho-api` (the
`Handle-multiple-Renpho-accounts-by-user-ID` branch): **landed in `renpho-py`
1.0.0** with the test coverage it lacked upstream, and **hardened in 1.1.0**
(robustness + caching + concurrency + typing — see §5). This document is the
design analysis and the roadmap, all delivered without breaking the public
contract.

Code: `renpho/client.py` — `discover_user_tables()` (L281) and
`get_all_measurements(extra_user_ids=...)` (L312).
Tests: `tests/test_client.py` — `TestDiscoverUserTables`,
`TestGetAllMeasurementsMultiAccount`.

---

## 1. The problem it solves

Some users have **two Renpho accounts under the same email** — typically an
orphan account created by the Google-SSO migration, or a re-registration. Each
account has its own user ID and its own measurement rows, and the default login
only surfaces the account you authenticate as. The goal: pull a **single,
combined, de-duplicated timeline** across all of a person's accounts for one
physical scale.

Renpho exposes no "list all accounts for this email" endpoint — it treats
same-email accounts as fully independent. So the design works around two facts:

1. A logged-in user *can* read measurement rows belonging to other linked user
   IDs (the API authorizes by token, then filters by the `userIds` in the body).
2. Body-composition scales **shard** measurements across 16 tables,
   `measurements_info_0` … `measurements_info_F`
   (`constants.py: MEASUREMENT_TABLE_NAMES`). `device/count` only reports the
   shard for the *logged-in* user, so another account's shard must be found by
   probing.

## 2. How it works

**`discover_user_tables(user_id)`** — iterates all 16 shard names and issues a
minimal probe (`pageNum=1, pageSize=1`) per shard against the
body-composition endpoint. Any shard that decrypts to at least one record is
collected and returned. This is the "which tables hold this stranger's data"
step.

**`get_all_measurements(extra_user_ids=None)`** — unchanged for the default
(single-account) case. When `extra_user_ids` is supplied it:
1. fetches the primary account's data as before,
2. for each extra user ID, discovers its shards and pulls the
   body-composition rows,
3. **dedupes the merged list by record `id`** (records with no `id` are always
   kept, so nothing is silently dropped),
4. sorts newest-first by `timeStamp`.

## 3. Contract assessment

- **Backward compatible.** `extra_user_ids` defaults to `None`; the extra-account
  loop and discovery are skipped entirely on the default path (verified by
  `test_no_extra_ids_is_backward_compatible`, which asserts `discover_user_tables`
  is never called).
- **Behavioral delta for existing callers:** results are now dedup-filtered by
  `id`. In practice single-account data has no duplicate `id`s, so this is a
  no-op; `id`-less records pass through untouched.
- **Additive surface:** one new public method + one new keyword arg + one new
  constant. No removals, no signature breaks.

## 4. Known limitations & weaknesses

Ranked by user impact. None are release-blockers; they are the backlog.

| # | Issue | Where | Impact |
| --- | --- | --- | --- |
| L1 | **16 serial probes per extra user, every call, no caching.** `discover_user_tables` fires 16 sequential HTTP round-trips; re-running `get_all_measurements` re-probes from scratch. | `client.py:296-303` | Latency: ~16× a single request per extra account, repeated on every call. |
| L2 | **Discovered shard is re-fetched from page 1.** After a probe confirms a shard, `get_body_composition_measurements` re-requests page 1 (re-reading the row the probe already saw). | `client.py:361-365` | Minor redundant request per shard. |
| L3 | **Extra accounts only use the body-composition endpoint.** Discovery and fetch both go through `queryBodyCompositionMeasureData`; a weight-only (non-impedance) secondary account may not be discovered or fetched, unlike the primary path which falls back to `get_measurements`. | `client.py:303,364` | Weight-only secondary accounts unsupported. |
| L4 | **No error isolation in the probe loop.** A transport error mid-probe raises and aborts the whole `get_all_measurements` — including discarding the primary account's already-fetched rows. | `client.py:303` | One flaky request loses the entire result. |
| L5 | **Dedup keys on `id` only.** If the same physical weigh-in exists under two accounts with different `id`s (or `id` is absent), it survives as a duplicate. | `client.py:367-376` | Rare double-counting. |
| L6 | **Loose typing.** `extra_user_ids: list \| None` and the pervasive untyped `user_id` weaken the value of shipping `py.typed`. | `client.py:312` | No type-checker help for callers. |
| L7 | **`discover_user_tables` assumes an active token.** Standalone use without a prior `login()` sends unauthenticated probes. | `client.py:281` | Foot-gun for direct callers. |

## 5. Forward plan

Guiding rule (from `NEW_LIBRARY_PLAN.md`): the public API stays a superset;
improvements are additive and land as `1.x` minors. Each item below is
independently shippable and test-gated.

### P1 — correctness & robustness — ✅ DONE (1.1.0)

- **L4 — isolate probe failures.** ✅ `_shard_has_data` catches
  `requests.exceptions.RequestException` per shard and returns "no data"; the
  extra-account loop in `get_all_measurements` catches per-account and continues.
  One flaky request no longer aborts the merge. (Chose silent-skip + debug log
  over a `strict` flag — simpler, and matches the rest of the client.)
- **L7 — guard token.** ✅ `discover_user_tables` calls `login()` when no token
  is set.
- **Tests:** ✅ `test_probe_failure_is_isolated`, `test_logs_in_when_no_token`,
  `test_extra_account_failure_is_isolated`.

### P2 — performance — ✅ DONE (1.1.0)

- **L1 — cache discovery.** ✅ `self._table_cache` keyed by user ID; `refresh=`
  param + `clear_table_cache()` method.
- **L1 — optional concurrency.** ✅ `max_workers` param on `discover_user_tables`
  (and passed through from `get_all_measurements`); each worker uses its own
  `requests.Session` (Session is not thread-safe), default `max_workers=1`.
- **L2 — reuse the probe result.** ❌ DROPPED. Probes use `pageSize=1`, so the
  probe's single row cannot seed the real `pageSize=50` fetch — there is no page
  to skip. Making probes heavy enough to reuse would defeat the point of a cheap
  probe. No real saving; not worth the coupling.
- **Tests:** ✅ `test_results_are_cached_until_refresh_or_clear`,
  `test_concurrent_matches_serial`.

### P3 — coverage & ergonomics

- **L6 — tighten types.** ✅ DONE (1.1.0) — `extra_user_ids: list[str] | None`,
  new `UserId = int | str` alias on the multi-account methods.
- **L3 — weight-only secondary accounts.** ⏸ DEFERRED. Discovery probes only the
  body-composition endpoint. Supporting weight-only secondary accounts requires
  assuming how `queryAllMeasureDataList` behaves for a *non-logged-in* user ID —
  which can't be verified without a real second weight-only account to test
  against. Left as a documented gap rather than shipping untested guesswork.
- **L5 — stronger dedup.** ⏸ DEFERRED (opt-in only when built). A secondary
  `(timeStamp, weight)` key would change today's default (which always keeps
  `id`-less records), so it must not be the default. Low observed impact; parks
  until someone hits it.

### Explicitly out of scope

- **Auto-discovering the other account's user ID.** Renpho has no endpoint for
  it; the README documents the manual routes (support, app inspection, traffic
  capture). Nothing to build here.

## 6. Test coverage

All in `tests/test_client.py`:

- **Base feature:** `discover_user_tables` (returns only shards with data; empty
  when none), `extra_user_ids` merge + dedup-by-id + newest-first ordering, and
  the backward-compatible default path (discovery never invoked).
- **P1 (1.1.0):** probe-failure isolation, missing-token login, extra-account
  failure isolation.
- **P2 (1.1.0):** cache hit avoids re-probing (+ `refresh`/`clear_table_cache`),
  concurrency returns the same set as serial.

Remaining gaps map to the deferred items (L3 weight-only, L5 composite dedup).

---

*Cross-references:* overall library roadmap and the deferred modular restructure
live in `/Users/asdf/repos/renpho-api-1/NEW_LIBRARY_PLAN.md` (§4). This document
covers only the multi-account feature.
