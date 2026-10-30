# Local-Leet++ Privacy Policy

Local-Leet++ displays country contest ranks on LeetCode profiles. It reads the username or profile slug and region from a LeetCode profile page and looks up the corresponding public ranking record locally. It also reads the displayed global rank to indicate when a saved local rank may be outdated.

The extension stores update metadata and cached ranking files on the device using Chrome storage and Cache Storage. It includes a bundled ranking snapshot for offline fallback. You can remove this locally stored extension data by removing the extension.

The extension requests ranking metadata and compressed JSON ranking files from GitHub Pages. Requests do not include the profile username, cookies, or referrer. The requested shard identifier is derived from a hash of the username and region; it may reveal which subset of the public ranking dataset is requested. GitHub receives the normal network information needed to serve requests, such as the IP address, and its own privacy practices apply. The extension does not send browsing history or profile usernames to VoidHub servers and contains no analytics or advertising code.

Ranking records are derived from public LeetCode contest rankings and declared profile countries. They may be incomplete or out of date. The dataset is refreshed on a daily schedule when collection and validation succeed.

Permissions: storage stores update state; alarms schedules update checks; access to LeetCode pages enables the profile display; access to GitHub Pages retrieves ranking data.

Built by VoidHub: https://voidhub.co
Contact: use the verified publisher contact email shown on the Chrome Web Store listing.

Last updated: 30 October 2026.

VoidHub uses information accessed by this extension only to provide its stated ranking feature, in accordance with the Chrome Web Store User Data Policy, including its Limited Use requirements. It does not sell this information, use it for advertising, or transfer it for creditworthiness or lending decisions.
