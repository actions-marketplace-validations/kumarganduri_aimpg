# Launch brief (for review, 2026-10-11)

## The product today (aimpg 0.6.0, free and open source, solo maintainer)
- **What it is:** github.com/kumarganduri/aimpg, PyPI `aimpg`. "Miles per gallon for AI coding": cost and carbon per *working change* (a commit still standing 30 days later).
- **`aimpg report`:** reads Claude Code, Codex and Cursor (export) logs locally and prints energy (kWh range), $ (API-equivalent) and commits; the typical kept commit's cost; and two measured tips. The author's 30 days: $1,284, 353 commits, $2.05 per typical kept commit, "fresh session after each commit would save up to 45%".
- **`aimpg live`:** a Claude Code status line ("task $1.96 · usual $2.05 · 92% of context is from before your last commit") and a note after each commit.
- **`aimpg verify`:** reruns your own past commits in a sandbox (macOS Seatbelt or Linux bubblewrap, network allowlisted to the model API) with a baseline vs a challenger: a token-saver (RTK), a prompt, hooks, another model, Codex, or any agent CLI. Your own tests judge. It writes a recheckable record (`--check`); `--public` records can be `--rerun` by anyone.
- **Public scoreboard** (kumarganduri.github.io/aimpg-scoreboard): records are submitted by PR via `aimpg submit` (stripped; private by default). CI validates. Trust tiers: Reproduced / Self-reported / Disputed. A number shows only with ≥5 repos and ≥3 people. Currently empty.
- **Team:** `aimpg notes push` (git notes, metadata only) plus a GitHub Action: PR cost comments and a weekly rollup (cost per working change, waste ratio; ≥5 people, never per person). `aimpg defaults` writes a replay-proven default model into `.claude/settings.json`. `aimpg sci` produces GSF SCI-for-AI (Consumer) output.
- **5-minute walkthrough:** kumarganduri.github.io/aimpg-scoreboard/start/

## Evidence so far (all on one repo, the author's "Legwork")
- **Model picker (10 commits, task mode "tests shown"):** Sonnet 10/10 at $0.12 per solved task; Opus 10/10 at $0.33; Haiku 8/10 at $0.38. The cheapest model per token was the most expensive per solved task.
- **RTK vs plain Claude Code (20 commits × 2 repeats):** about +10% energy (interval −11%…+35%, not proven); solved 32/40 vs 36/40. RTK advertises 60–90% token savings.
- **Waste:** 45% of the author's AI energy went to re-reading conversation from before the last commit.
- **Energy:** a physics-based model with ranges, calibrated to Google's disclosed 0.24 Wh per median prompt (arXiv 2508.15734). Dollars are within about 7% of Claude Code's own totals.

## Proposed launch (the maintainer's current plan)
- **Lead with findings, not features.** The tool is the instrument.
- **Before launch:**
  1. A launch study on 5–6 popular public OSS repos (models, RTK, terse prompt, Codex) as `--public` rerunnable records, about $100–200.
  2. 2–3 friends independently rerun records, so "Reproduced" exists on day one.
  3. Give the RTK maintainers a right of reply.
  4. A launch page with charts.
  5. A 20-second demo clip.
  6. A security review of what users install.
  7. An FAQ for objections; disclose that it's built with Claude Code but vendor-neutral.
- **Frame:** "AI Coding MPG Index", first edition, quarterly, with open data.
- **Channels:** soft week; then Show HN (finding as title) with X and LinkedIn the same day; Reddit staggered (r/ClaudeAI, r/ChatGPTCoding, r/ExperiencedDevs, r/programming if it's a write-up); then the Green Software Foundation, newsletters (TLDR, Pragmatic Engineer, Latent Space), Lobsters, dev.to.

## Constraints
One maintainer; no budget beyond a few hundred dollars of API credit; must stay credible as a neutral referee; posts go from the maintainer's own accounts.

## Decisions (2026-10-11, after reviews: CEO review, an HN regular, a growth marketer, a skeptic, Codex)

**Study first, launch around early November**, as "AI Coding MPG Report No. 1". Get quiet feedback in the Claude Code and Cursor communities in the meantime.

**Checklist**
- [ ] A. Honesty and safety fixes:
  - the fresh-session tip worded as "carried over", with both energy-range ends;
  - the live "/clear" line reworded;
  - "list-price equivalent" $;
  - the energy model called an "estimate with assumption ranges";
  - Windows stated in the README;
  - stale dates fixed;
  - Action dependencies pinned by SHA;
  - markdown from notes escaped;
  - `/cso` security review.
- [ ] B. Study infrastructure:
  - `--any-author` selection;
  - per-model training cutoffs recorded;
  - hint mode as the primary result;
  - intention-to-treat cost and Wilson intervals;
  - bootstrap on the cost-per-solve ratio, clustered by repo and commit;
  - RTK version and hook-firing count (a run with zero firings is invalid);
  - a hash of the full qualifying-candidate list in each record;
  - the fresh-session chain experiment (continue vs /clear plus a summary over 2–3 consecutive commits).
- [ ] C. Pre-registration committed before any paid run:
  - hypotheses and primary metrics;
  - the repo rule and commit rule;
  - the stopping rule and Holm correction;
  - the RTK config approved by its maintainers;
  - headline only if the direction holds in at least 5 of 6 repos.
- [ ] D. A pilot (about $10) to size n, then the full study: about 55 commits × 3 repeats × (Haiku, Sonnet, Opus, Codex, RTK), plus the fresh-session chains. $80–250, approved by the user in the terminal.
- [ ] E. At least 2–3 reruns by unaffiliated people, so "Reproduced" exists; friends' reruns are labeled as reruns. Get one team quote if possible.
- [ ] F. Assets:
  - the Report No. 1 page on the scoreboard site, with charts and a forest plot;
  - a 20-second clip;
  - `aimpg report --share` card;
  - a "see your own" footer on PR comments;
  - a Marketplace listing;
  - the FAQ, with the Claude Code disclosure;
  - the "Bring Your Claim" challenge with a "Verified by aimpg" badge;
  - per-channel post drafts.
- [ ] G. Launch:
  - Tuesday to Thursday, 8–10am Eastern: Show HN or the study post (finding in the title, RTK never named in a title), plus X and LinkedIn;
  - Reddit staggered;
  - newsletters, then GSF.
  - The user posts from their own accounts.
