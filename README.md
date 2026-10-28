# Local Leet

Your country contest rank beside LeetCode's Global Ranking.

Built By [VoidHub](https://voidhub.co).

## Install

1. Download and extract the ZIP from [Releases](https://github.com/adhamahmedyousef/Local-Leet/releases/latest).
2. Open `chrome://extensions`, enable **Developer mode**, choose **Load unpacked** and select the extracted folder.
3. Open a LeetCode profile. Click **Local Rank** for its country and snapshot date.

Moving from 0.1.0 requires loading 0.2.0 once. Future **data** updates need no reload or reinstall.

## Updates

Ranking data refreshes every **two days** through GitHub Actions and Pages. Chrome checks hourly
and updates open profiles automatically. Cached data and a bundled snapshot work offline.
Countries must be declared by users; unknown countries display `—`. Ranks describe dated data,
not guaranteed live standings. [Data details](docs/data.md).

## Development

```sh
npm ci
npm test
python -m unittest discover -s tests -q
python scripts/build-extension.py --from-release
python scripts/verify-extension.py
```

Source, tests and workflows only; datasets and builds stay out of Git. [Setup](docs/extension.md).

## License

Source-available, not an unrestricted open-source license. Rights are reserved to VoidHub.
Reuse or redistribution requires written permission; attribution alone is insufficient.
Pull requests are welcome. Read [LICENSE](LICENSE) and [CONTRIBUTING](CONTRIBUTING.md).
