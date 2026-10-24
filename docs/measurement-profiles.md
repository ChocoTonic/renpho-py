# Account identity and measurement profiles

Password login and measurement profiles are distinct. The authenticated account
can expose measurements for multiple people; never infer a person's identity
from the account email alone.

```python
from renpho import RenphoClient

client = RenphoClient(email, password)
client.login(expected_user_id=known_account_id)
profiles = client.get_measurement_profiles()
records = client.get_all_measurements(profile_user_id=selected_profile_id, strict=True)
```

`expected_user_id` is optional and accepts an integer or string. A successful
login to another account raises `RenphoAPIError` and clears the session.
`get_measurement_profiles()` lists the owner and IDs advertised by device metadata
without downloading history. Profiles absent from metadata can still be selected
explicitly; collection then discovers their measurement tables.

`profile_user_id` selects one person and ignores `extra_user_ids`. Every returned
row must identify that person through `bUserId`, or through legacy `userId` when
`bUserId` is absent. Foreign and unidentified rows are excluded. Empty profile
results raise in strict mode. The legacy endpoint is tried when the body
composition endpoint returns no rows.

Without a selected profile, the existing merged-account behavior remains the
default. `strict=True` raises on failed extra-account discovery or collection and
on empty configured extra accounts. Strict discovery bypasses cached results and
raises when endpoint failures leave the presence of data uncertain. Successful
probes can establish presence even if another endpoint failed. This is a failure
detection mechanism, not proof that every cloud measurement exists.

Renpho uses 24 decimal-suffixed tables (`measurements_info_0` through
`measurements_info_23`). Discovery tries the normal `user_id % 24` table first,
then scans the others if it is empty. Returned rows deduplicate by `(table, id)`;
IDs from different tables must not suppress each other.

Keep the last successful application cache when strict collection raises. Switch
to these optional arguments before replacing a local dependency with a remote
pin. Roll back by restoring the previous dependency pin and lockfile together.
