# Chrome Web Store draft

Name: Local-Leet++
Short description: See country contest ranks on LeetCode profiles, beside the global ranking.
Category: determine from available dashboard categories before submitting.
Language: English

Description:
See a LeetCode user's country contest rank alongside their global ranking. Visit your profile or another user's profile to see their local rank and the number of ranked accounts declaring that country.

Ranking data is refreshed daily when collection succeeds. The extension checks for updates automatically and keeps a bundled snapshot for offline use. Ranks are based on public contest ranking data and declared countries; they may be incomplete or out of date.

Built by VoidHub: https://voidhub.co

Single purpose: Display country contest ranks on LeetCode profiles.

Permission justifications:
- storage: Save update metadata and cached ranking data for fast lookups and offline fallback.
- alarms: Schedule checks for new ranking snapshots.
- LeetCode and LeetCode China: Read the profile identity and display local ranks alongside global ranks.
- adhamahmedyousef.github.io: Retrieve the ranking snapshot metadata and data shards.
- Remote code: No. Remote resources are data, not executable code.

Privacy: Profile identity is read and processed locally; remote shard requests reveal a shard identifier and network metadata to GitHub Pages. Review the dashboard's exact data category definitions and verified privacy policy URL before submitting.

Privacy policy URL: https://github.com/adhamahmedyousef/Local-Leet/blob/main/PRIVACY.md

Support URL: https://github.com/adhamahmedyousef/Local-Leet/issues

Reviewer notes: No login is required. Open https://leetcode.com/u/Adham0X1Star/ and find Local Rank beside Global Ranking. The popup shows the snapshot and offers Check for updates. GitHub Pages requests download only metadata and gzip-compressed JSON records; all executable logic is bundled. No remote JS, WASM, interpreter, or executable archive is downloaded.

Data disclosures: The extension processes public profile usernames/slugs, profile region, and the displayed global ranking locally. It does not transmit usernames or a browsing-history log to the developer. GitHub Pages receives network metadata and the requested hash-prefix shard path. Do not claim completely anonymous networking or zero data access. Select dashboard categories only after checking their exact definitions against these practices.

Final upload files:
- dist/local-leet-0.2.8.zip
- store-preparation/screenshot-1280x800.png (original user screenshot in a 1280x800 presentation)
- dist/local-leet-0.2.8/icons/128.png

Before Submit for review: check verified contact email, trader declaration, category, privacy disclosures and Limited Use certifications. Review the displayed listing. This preparation does not constitute a submission or approval by Google.
