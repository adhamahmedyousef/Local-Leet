# Security

Report security issues privately through https://voidhub.co. Do not include secrets in issues.

Data updates are HTTPS JSON/gzip from the project's fixed GitHub Pages origin. They never contain
executable code. Metadata and shards are bounded, validated and checked against SHA-256 hashes.
Failed downloads retain the last valid data or the bundled fallback.

Only the main-branch publishing workflow can deploy. Pull requests receive no publishing tokens.
The isolated keepalive job has Actions write permission only to renew the refresh workflow;
it checks out no code and has no repository-content or Pages write permission.
GitHub scheduling and LeetCode availability can delay updates; the extension shows snapshot dates.

Built By [VoidHub](https://voidhub.co).
