# Third-party skills

Copied from public repositories listed on [skills.sh](https://skills.sh), pinned to the commit shown.
They were reviewed before adding (no remote downloads, no installers, no data sent to third parties).
To update one, copy the folder again from its repository, review the diff and update the commit here.

| Skill | Source | Commit | Licence | Local changes |
|---|---|---|---|---|
| `frontend-design` | [anthropics/skills](https://github.com/anthropics/skills/tree/main/skills/frontend-design) | `ca45fc4` | Apache-2.0 (`LICENSE.txt`) | none |
| `webapp-testing` | [anthropics/skills](https://github.com/anthropics/skills/tree/main/skills/webapp-testing) | `ca45fc4` | Apache-2.0 (`LICENSE.txt`) | none |
| `web-design-guidelines` | [vercel-labs/agent-skills](https://github.com/vercel-labs/agent-skills/tree/main/skills/web-design-guidelines) + [vercel-labs/web-interface-guidelines](https://github.com/vercel-labs/web-interface-guidelines) | `1a2c79d` + `434b7f9` | MIT (`LICENSE.txt`) | reads the vendored `guidelines.md` instead of fetching it on every run |
| `seo-audit` | [coreyhaines31/marketingskills](https://github.com/coreyhaines31/marketingskills/tree/main/skills/seo-audit) | `88c79f6` | MIT (`LICENSE.txt`) | `evals/` removed |
| `schema` | [coreyhaines31/marketingskills](https://github.com/coreyhaines31/marketingskills/tree/main/skills/schema) | `88c79f6` | MIT (`LICENSE.txt`) | `evals/` removed |
| `analytics` | [coreyhaines31/marketingskills](https://github.com/coreyhaines31/marketingskills/tree/main/skills/analytics) | `96798cf` | MIT (`LICENSE.txt`) | `evals/` removed (skills.sh was not reachable from the session: copied from GitHub) |
| `impeccable` | [pbakaus/impeccable](https://github.com/pbakaus/impeccable) | `5af4319` | Apache-2.0 (`LICENSE`) | `scripts/` not vendored: its launcher downloads and runs a binary, and the live mode can start agents without permission checks. Without it the skill falls back to reading the project context directly |

Project notes for agents:
- `webapp-testing` uses Python Playwright (`pip install playwright && playwright install chromium`); the project's own
  tests use Node Playwright (`npm test`). Either is fine for ad-hoc checks.
- `frontend-design` and `web-design-guidelines` give generic advice: the project rules in `AGENTS.md`
  (pixel art, palette tokens, four languages, no emoji icons) take precedence.
- `impeccable`: the brief wins — pixel art, Press Start 2P/VT323, hard pixel shadows and the museum palette stay even
  where its generic bans would flag them. Used mainly for `distill`, `clarify`, `polish` and `audit`.
- `analytics`: the measurement plan lives in `data/analytics.json`; consent and privacy rules of `AGENTS.md` (rule 14)
  win over its generic advice (no user ids, no Google Signals, no visitor-typed text except catalogue search terms).
- `seo-audit` and `schema` mention related skills from their repository that are not installed here.
