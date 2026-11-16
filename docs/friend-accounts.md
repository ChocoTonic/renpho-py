# Friend-account reads and household profiles

The friend endpoints let a second account read the daily data that the main
account shares through Renpho Health's friends feature. Logging in as that
second account avoids replacing the main account's phone session.

This is a port of [renpho-api PR #18](https://github.com/danvaneijck/renpho-api/pull/18),
which implements [issue #14](https://github.com/danvaneijck/renpho-api/issues/14).
The underlying protocol is documented in
[renpho-friends](https://github.com/DawidKrynski/renpho-friends).

## Review of the upstream change

The additive client methods fit this library's existing encryption, response
checks and HTTP transport. The required `timeZone` header is a per-request
header, so friend calls can use it without changing other requests. Existing
direct-account reads remain available.

Concrete gaps in the upstream implementation:

- `get_friends()` requests only page 1, silently omitting friends after the first
  50. This port paginates and raises if a full page repeats without progress.
- `time.localtime().tm_gmtoff` is not portable to every supported platform, and
  floor division silently shifts fractional negative offsets to the previous
  hour. This port uses an aware datetime and requires an explicit integer
  `time_zone` when the local offset contains a fractional hour. Friend list and
  summary calls use UTC because they do not group daily trend points.
- The CLI accepts `RENPHO_FRIEND_TIME_ZONE` so fractional-offset hosts can choose
  UTC or another integer offset. It validates the offset before authentication.
- Empty CLI windows exit with status 1 and report that previous exports remain
  unchanged, rather than presenting old files as a successful fresh export.
- The daily merge accepts booleans and nonfinite positive floats as values.
  This port excludes those as well as missing, zero and negative values.
- The PR's validation reports an empty friend list and an API-level error for a
  fabricated friend ID. It explicitly does not verify data from an accepted
  friend. Mocked tests cannot establish server-side sharing or household scope.

The upstream feature and this port request one bounded trend window, with one
call per metric. The CLI does not automatically retrieve all history. Callers
can choose older `end_time` values in Unix seconds. Window width and paging
boundaries need live confirmation; an empty window alone does not establish
that no older data exists.

Daily records merge metrics by `groupDay`. They should not be interpreted as
complete original weigh-ins: individual metric timestamps can differ, and the
merged `timeStamp` comes from the first available metric for that day. One
whole-hour offset applies to each request; historical DST and fractional time
zones cannot be represented exactly by this interface.

## Which identifier is needed?

| Situation | Identifier and access path |
| --- | --- |
| Main account shared with a sync account | Log in as the sync account; discover the main account's `userId` with `get_friends()` and pass it as `friend_id`. |
| Several independently shared accounts | Discover and fetch each friend ID separately; retain the friend ID alongside each result. |
| Multiple measurement profiles accessible under the current account | Use `get_measurement_profiles()` and select with `get_all_measurements(profile_user_id=...)`. |
| Additional known linked account or historical account ID | Existing `extra_user_ids` merges timelines; it does not discover friend relationships or establish which person a profile represents. |
| Household profiles belonging to a friend | Unverified. The known friend payload contains `rhFriendId`, with no separate family/profile selector. |

No arbitrary person's ID is needed. A real accepted friendship between two
test accounts is needed to validate the shared-data path. The friend ID can be
discovered from that relationship rather than obtained by traffic interception.
Any household-member check should use profiles and data the account holder has
agreed to share. Knowing an ID alone does not establish sharing access.

For independent household accounts that can each accept a friendship, a sync
account can fetch them separately. For dependent profiles without their own
login/friend relationship, there is currently no evidence that friending the
owner exposes those profiles. This port does not add a speculative selector or
merge multiple people's data together.

## Is MITM capture necessary?

It is unnecessary for implementing the published friend endpoints: their paths,
payloads, encryption and required headers are already described in the sources.
Ordinary requests from an accepted sync account can validate those operations.

Capture becomes useful if the official app can display a household member's
shared data but the published requests cannot reproduce it. In that case,
observe the request difference when the app switches members: endpoint, IDs,
selectors and headers. Capture only accounts/profiles participating in the test,
and retain redacted fixtures rather than passwords, tokens or health histories.

## Live validation still needed

1. Create or use an email/password sync account, accept its friendship from the
   main account, and verify that the sync account can see data in the app.
   Return the phone to the main account before testing session preservation:
   scripted login as the sync account may replace a phone session on that same
   sync account, which would not test the main account's session.
2. Log in only as the sync account, list friends, and compare one known day's
   weight and composition with the main account's app view. Check a second
   scripted login leaves the main account's phone session active.
3. Compare two weigh-ins on the same day, a day with weight only, and an older
   window to confirm summary semantics and time boundaries.
4. For a household test, record which profiles the app can actually share or
   select, then compare each profile's distinct known measurement. Confirm that
   the friend result belongs to the intended person before scheduling exports.
5. Use app inspection or a targeted capture only if the household case needs a
   request variant beyond the published friend API.

## Official-app observations on 2026-11-16

Google sign-in to the sync account succeeded, and a friend request was sent.
After the account holder accepted it, the main account's Friends screen listed
the sync account. This verifies an accepted relationship in the official app,
not the Python client's accepted-friend response contract.

The friend's submenu offered both **Body Fat Scale** and **Tape Measure**.
Both trend screens offered Week, Month and Year. The scale screen displayed
Weight, BMI, Body Fat and Subcutaneous Fat tabs; the tape screen displayed Neck,
Shoulder, Chest and Waist tabs. Further tabs extended beyond the visible area.
These are visible UI capabilities, not verified API parameters or endpoint paths.
The checked views showed no data for the sync account. After switching back to
the sync account, its Friends screen also listed the main account. The intended
sync-to-main direction was then checked: Weight in Week and Year views, Body
Fat and Subcutaneous Fat in Year view, and Neck in the Tape Measure Week and
Year views all displayed "No data available". The current history calendar was
also empty for the selected date. This verifies navigation in both directions,
not successful retrieval of a populated shared timeline. It does not establish
whether the cause is profile selection, sharing scope, the selected period,
missing cloud records, or another service behavior.

In particular, the app's Tape Measure view means that lack of girth support in
this client must not be described as proof that friend girth sharing is
impossible. Public source inspection or a targeted request comparison is needed
to identify its contract. No household-member selector was visible on the
screens inspected; that is not proof that none exists elsewhere.

A follow-up public-source search found no verified friend tape request or extra
metric mapping. Upstream's [endpoint research](https://github.com/danvaneijck/renpho-api/blob/6df01f7c22bc72bc81bd4281b71382444d189bee/docs/endpoints.md)
reports that friend screens use a React Native bundle downloaded at runtime.
Inspecting that bundle's request builders could avoid interception. Otherwise,
a targeted capture should compare Weight versus Subcutaneous Fat, Week versus
Year, and Scale versus Tape Measure, changing one control at a time. An empty
response can identify a request contract, but cannot validate populated values
or household sharing. Do not infer friend parameters from ordinary measurement
field names, or assume the visible Year label is the literal API enum `YEAR`.

## Direct API validation on 2026-11-16

The PR branch was tested with password authentication as the sync account. Login
succeeded, friend discovery returned the intended main account, and that friend
ID matched the main account's independently configured expected account ID.

With `time_type="MONTH"`, `end_time=0` and an explicit UTC offset of `-8`, all
eight default `trendV2` requests returned success code 101 with decrypted
`{"list": [], "endTime": ...}` responses. This was a genuine empty list in the
known response shape, not data discarded by the normalization helper.
`measure/has` also succeeded with an empty list. The summary endpoint succeeded
and returned the documented summary fields as strings.

A separate password login to the main account matched the expected account ID.
Two minimal page-one baseline queries used that account's advertised table and
requested only the owner ID. The body-composition endpoint returned two recent
owner-profile records; the legacy measurement endpoint returned no rows. Both
returned record ownership IDs matched the requested owner ID.

For this tested account, the friend workaround therefore authenticates and
discovers the right relationship but does **not** retrieve the existing recent
owner measurements. The app's empty friend views agree with the API result.
An alternate target ID or a dependent household profile is not required to
explain this comparison: the requested owner identity was verified directly.

The store difference makes friend coverage of body-composition data, or a
missing source/category request option, a useful hypothesis. It does not prove
that the friend API never supports that store. Inspect the runtime bundle's
request builders or capture the relevant read-screen requests before choosing
new endpoints or discriminator values. No MITM capture was performed.

## Follow-up: account IDs and the actual friend-screen requests

The existing `extra_user_ids` option combines records that the authenticated
account can already read. It does not merge backend identities, link OAuth and
password accounts, or grant friend access. A sync-account request for the known
owner ID and its advertised measurement table returned no rows through either
direct measurement endpoint. The same owner ID returned recent body-composition
records when authenticated as the owner. This comparison does not establish a
duplicate OAuth identity as the cause.

A new owner-profile weigh-in taken after friendship acceptance was confirmed in
the owner's cloud records. The subsequent friend read remained empty, so a
simple exclusion of pre-friendship history does not explain this case.

Static inspection of the server-provided `RenphoHealthFriendRN` panel version
2.0.8 recovered two additional read contracts:

- `RenphoHealth/app/friend/measure/history` receives `rhFriendId`, `startTime`
  and `endTime`, with local-day boundaries expressed as Unix seconds.
- `RenphoHealth/app/friend/measure/trend` receives `rhFriendId`, `timeZone`,
  `param`, `sourceDataType`, `timeType`, `pageNum` and `pageSize: 1000`.
  Its custom-date branch sends both bounds and an empty `timeType`.

Replaying these builders as the sync account returned success code 101 and no
records, both for a recent 30-day range and for the local calendar day containing
the new weigh-in. The normal Weight/Week request also returned an empty list.
In that panel, `sourceDataType` selects `AM`, `PM` or an empty string for all
day; the observed UI exposes no body-composition store option. The inspected
React Native caller and Android 6.17.0 Java/smali region bridge process records
already returned by history, with no additional network request in that path.
The invoked native algorithm library was not audited.

The current iOS 7.11.4 panel (2.2.0) was subsequently decrypted using the panel
extraction implementation statically recovered from Android 7.11.6. The downloaded
Android APK's signature verified and matched the older APK's signing certificate.
ZIP AES authentication passed, and the Hermes bytecode was inspected without
executing the app code. An independent version-98 Hermes bytecode dump confirmed
the Android history builder and its endpoint string boundary.

The current iOS panel's default trend builder matches this library's `trendV2`
payload. Its history builder still uses `measure/history`, with the same three
fields and local-day Unix-second bounds tested above. Its custom-date trend
branch sends `rhFriendId`, `timeZone`, `param`, `sourceDataType`, an empty
`timeType`, `startTime` and `endTime`, without paging keys. Replaying that exact
branch for the weigh-in day and for a recent 30-day range also returned code 101
with an empty `list`. The inspected friend endpoint table exposes no separate
body-composition read or dependent-profile selector. This remains bounded source
evidence, not a comprehensive audit of every native or server path.

No working sync-to-owner retrieval was found in these checks. The verified
alternative is direct owner authentication; it does not satisfy the goal of
reading the data solely as the sync account. A server-side sharing or data-store
coverage problem remains a hypothesis requiring RENPHO's investigation. No
account-linking or sharing settings were changed, and no traffic interception
was used.
