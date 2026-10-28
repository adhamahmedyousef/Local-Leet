# Chrome setup

Extract the latest release, then open `chrome://extensions` → **Developer mode** → **Load unpacked**.
Choose the extracted folder containing `manifest.json`. Keep that folder in place.

Local Rank appears beside the contest Global Ranking. Click it for the country and date.
A `*` means the profile's global rank differs from the snapshot. Unknown countries show `—`.
The separate sidebar rank is unchanged. English leetcode.com layout is supported; localized
leetcode.cn layouts have not been verified.

Version 0.2.0 needs `storage`, `alarms`, and access to `adhamahmedyousef.github.io` for verified
data updates, plus content-script access to LeetCode. It does not read credentials or submissions.
No usernames are sent to the update server. Future data updates apply without a page reload.
Code updates still require a new extension version; this does not fetch or execute remote code.

To rebuild from source, run `python scripts/build-extension.py --from-release`. To collect a fresh
local baseline instead, run `python -m localleet.collect`, `python -m localleet.build`, and
`python -m localleet.verify --live` before building without `--from-release`.

Built By [VoidHub](https://voidhub.co).
