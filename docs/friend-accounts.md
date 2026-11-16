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
