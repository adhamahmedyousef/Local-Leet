# Data

Ranks use LeetCode's published contest order, counting earlier rows that declare the same country.
Unknown countries remain unknown. A snapshot is not a live ranking or a census of nationalities.
The source's reported participant total may exceed the rows its pages expose; no missing rows
are invented. See the displayed snapshot date before interpreting a rank.

The refresh workflow collects daily. It requests runs at 05:17, 11:17 and 17:17 UTC;
backup triggers skip collection when today's snapshot has already been published.
GitHub scheduling can be delayed or dropped, so these are requested times, not deadlines.
An independent keepalive job preemptively renews this workflow through GitHub's enable API on
every trigger, including skipped backup runs. It uses only the job's short-lived Actions
token, creates no commits and keeps running even if data collection fails. No personal token
or manual inactivity reset is required. This addresses inactivity expiry, not GitHub outages
or an owner deliberately disabling the workflow.
Daily collection starts on 30 October 2026. Manual runs may force a new collection on the same day.

Each run collects a fresh dataset, rejects missing pages, duplicate identities, rank gaps, invalid
ordering and abrupt coverage drops, then independently checks ranks and live source sentinels.
Sampled .com profiles are also checked against their current contest ranks and ratings.
A mismatch blocks publication and retains the previous version. These sampled checks cannot
prove an atomic or globally current snapshot. Only a completed validation deploys. Failure preserves the previous Pages deployment. LeetCode
can block anonymous runner requests; the workflow fails visibly instead of bypassing access controls.

GitHub Pages stores immutable, SHA-256-pinned metadata and gzip shards. The latest and previous
version remain available. Large datasets do not enter Git history. The initial deployment uses
the verified release specified in `bootstrap.json`.

Chrome checks the fixed Pages origin hourly, downloads only needed shards and validates their
size, hash, schema and bounds. It caches eight compressed shards on disk and four parsed shards
in worker memory. An open profile updates through a storage change event, without page reload.
Offline or failed updates use the previous valid version or bundled snapshot. No remote code runs.

Built By [VoidHub](https://voidhub.co).
