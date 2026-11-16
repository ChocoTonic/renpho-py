# Importing an existing phone session

`RenphoClient.from_session_file()` uses an existing RENPHO session without
creating a new login. This is intended for testing whether an integration can
share the phone's session instead of repeatedly replacing it.

```python
from renpho import RenphoClient, RenphoSessionError

client = RenphoClient.from_session_file(
    "~/.config/renpho/phone-session.json",
    expected_user_id="YOUR_OWNER_USER_ID",
)
try:
    # Uses the app's getTokenTime operation; adopts and saves a replacement
    # if RENPHO issues one. This never calls password login.
    info = client.refresh_session()
    rows = client.get_all_measurements(
        profile_user_id=client.user_id,
        strict=True,
    )
except RenphoSessionError:
    # Obtain the current phone session. Do not call password login here.
    raise
```

The JSON file contains:

```json
{"token": "EXISTING_RENPHO_TOKEN", "user_id": "123456789", "email": "owner@example.com"}
```

`email` is optional. `expected_user_id` checks the supplied identity before any
network request. The server validates the token; importing it does not verify
its signature, expiry or ownership offline. `RenphoClient.from_session(data)`
accepts the same object directly.

## Renewal and replacement tokens

`refresh_session()` sends the app's encrypted empty-object request to
`RenphoHealth/app/sync/getTokenTime`. RENPHO decides whether renewal is due.
The response may include a nonblank replacement `token`; the client adopts it
for subsequent requests and automatically persists a file-imported session.
An empty, absent or unchanged token leaves the current token in use. A returned
account ID must match the current account. Invalid token or timestamp fields
raise before changing the session.

The result contains `issued_at` and `expires_at` in Unix seconds, plus
`token_replaced`. It never includes the token. Server `issAt` and `expAt`
timestamps are converted from milliseconds. `client.token_expires_at` also
reports expiry from saved metadata or an unverified decoded JWT claim, without
a network request; opaque tokens with no expiry metadata return `None`.

File updates use a temporary mode-0600 file and atomic replacement. If saving
fails after a server replacement, the client keeps the new token in memory
and raises `RenphoSessionError`; retry `client.save_session()` after correcting
the filesystem problem. `save_session(path)` can also establish a save location
for a session imported from an object. Its parent directory must already exist.

Renewal is explicit rather than a hidden side effect of reading measurements.
Call it from the sync job when you want the app's renewal check. It cannot revive
a revoked token, and it never falls back to password login. The server's behavior
when issuing a replacement near expiry is not yet verified against the phone's
old token, so indefinite coexistence remains unproven.

An imported-session client holds no password and rejects explicit or implicit
`login()` calls. A 401/403 session rejection raises `RenphoSessionError` without
retrying login, including during shard discovery or optional account collection.
An unreadable or invalid session file fails rather than falling back to saved
credentials. Measurement reads do not silently request renewal; the explicit
renewal method above handles replacement and persistence. The existing
password-authentication constructor retains its behavior.

This is not a separate read-only authorization grant: the token carries the
phone session's account access. Keep the file outside the repository, restrict
it to its owner (for example, `chmod 600`), and keep tokens out of logs, exports,
issues and pull requests. Use an existing authenticated request to obtain a
RENPHO token; a Google sign-in token is not a replacement.

Session import does not bypass server-side sharing restrictions, resurrect an
expired session, or guarantee concurrent phone/API use. Another login may revoke
the shared token, and app refresh behavior needs live validation. The CLI still
uses password login; use the library entry point above for imported sessions.

## Live verification on 2026-11-16

An existing owner session was captured from authenticated iOS app traffic and
imported without a password. Two full reads returned 185 owner-profile
body-composition records each. Transport instrumentation independently blocked
the login endpoint; neither read attempted login. Between those reads, fresh
authenticated phone requests returned HTTP 200 / API code 101, the device view
remained accessible, and the captured token did not change.

A third full read also returned the same 185 owner records after the Wi-Fi proxy
was restored to Off, certificate trust was disabled, and the capture process was
stopped. Continued interception is therefore unnecessary for the tested reads.
The imported token declares a 90-day lifetime; these claims were decoded for
diagnostics, not verified offline. Revocation can happen earlier.

A subsequent explicit renewal check returned the same expiry without issuing a
replacement, and persisted the current session successfully. Both the current
session and an independent client using the original phone token could still
read device information afterward. No login endpoint was called.

This demonstrates short-term coexistence on one account and app version. Actual
replacement issuance near expiry, reauthentication, overnight use and later app
updates were not tested. No captured credentials or measurement values are
included in this repository.
