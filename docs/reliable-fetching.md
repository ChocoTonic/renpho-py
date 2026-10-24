# Reliable measurement fetching

`RenphoClient(email, password, timeout=(10.0, 30.0))` bounds connection and read
waits in seconds. Pass a different scalar or `(connect, read)` tuple to configure
requests. Transport errors propagate to the caller, which can preserve its last
successful cache rather than overwrite it with incomplete results.

Both measurement pagination methods reject nonpositive page sizes and raise
`RenphoAPIError` when a page repeats only previously seen rows. A known-count
legacy fetch also raises if the server ends pagination before the advertised
count. These checks prevent silent truncation and endless repeated-page loops;
they do not establish completeness when the server supplies no reliable count.

API errors preserve the server's `message` when its `msg` field is absent or empty.
