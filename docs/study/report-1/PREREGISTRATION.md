# AI Coding MPG Report No. 1: pre-registration (DRAFT, frozen before the main run)

Written and committed **before any paid run** (git history shows the date). Nothing below changes after the first study run. Deviations, if any, are reported as deviations.

## Question
On real commits from popular open-source repos, judged by each repo's own tests, which agent setups solve as much for less?

## Setups (each run starts from a fresh, empty config in aimpg's sandbox)
- **Baseline:** plain Claude Code on Claude Sonnet 5.5 (`plain`).
- **Challengers:**
  - Claude Code on Claude Haiku 5.5 (`haiku`);
  - Claude Code on Claude Opus 5.5 (`opus`);
  - OpenAI Codex CLI on gpt-6.1-sol (`codex:gpt-6.1-sol`);
  - Claude Code on Sonnet 5.5 with RTK (`rtk`), installed with `rtk init --global --auto-patch --no-trust-filters`, latest RTK release at run time.
- **RTK setup review:** RTK's maintainers were asked to review this setup on 2026-10-11 (https://github.com/rtk-ai/rtk/discussions/4511). Any change they ask for before the main run is adopted and reported. If they haven't replied by 2026-10-18, the setup above is used.
- **Versions recorded per run:** the versions of every tool and model.

## Repos and commits (chosen by rule, not by hand)
- **Repo rule:**
  - Python with `uv.lock` and pytest, or JS/TS with `package-lock.json` and vitest/jest;
  - at least 1,000 stars; a permissive license; tests that run offline;
  - no vendor of a tested setup.
- **Repos:** the 8 in `plan.json`.
- **Replacement:** a repo with fewer than 5 qualifying commits after the free pre-check is replaced by the next reserve, in the listed order.
- **Commit rule:**
  - authored on or after **2026-07-01**, after every tested model's training cutoff (Claude models: June 2026; gpt-6.1-sol: April 2026);
  - single parent;
  - changes both tests and code;
  - message of at least 6 words;
  - its tests **fail on the parent and pass on the commit, twice each**.
- **Selection:** the **first 7** qualifying commits per repo, oldest first, by any author. Each repo's full candidate list and its SHA-256 are published.
- **Task:** the commit message, plus the names the hidden tests import (`hint` mode). The commit's tests stay hidden and decide the outcome. Agents' edits to tests are undone before judging.
- **Repeats:** 3 per commit and setup.

## Primary comparisons (5, Holm-corrected at α = 0.05)
1. Haiku 5.5 vs Sonnet 5.5: cost per solved task.
2. Opus 5.5 vs Sonnet 5.5: cost per solved task.
3. Codex (gpt-6.1-sol) vs Claude Code (Sonnet 5.5): cost per solved task.
4. RTK vs plain, both on Sonnet 5.5: **tokens per attempted task**, the unit RTK advertises.
5. Fresh session vs continued session for the next task: cost per attempted task.
   - Pairs: 2 per repo, the 1st and 2nd and then the 3rd and 4th selected commits.
   - Task 1 is run once.
   - Task 2 is run in the same session after the code is reset to its starting point, and in a new session told only task 1's subject.

## Metrics reported for every comparison
- **Solve rate,** with 95% Wilson intervals, overall and per repo.
- **Cost per attempted task:** every run counts, failures included.
- **Cost per solved task,** and its challenger/baseline ratio, with a 95% interval from a bootstrap over repos and then commits.
- **Tokens per attempted task,** and its ratio.
- **The number of repos where the challenger came out cheaper.**
- **Dollars:** list prices (Anthropic and OpenAI pricing pages), applied to the tokens each run used.
- **Energy:** a secondary estimate with ranges, never a headline.

## Headline rule
A finding is stated as a result only if both:
- its Holm-adjusted p is below 0.05, **and**
- its direction holds in at least 5 of 6 or more repos.

Everything else is reported as "not shown", with its interval.

## Exclusions and stopping
- **Harness errors:** a run that fails for aimpg's own reasons is retried once. If it fails again, that commit is excluded for **every** setup and listed.
- **Account errors** (credit or key problems) are redone and never counted against a setup.
- **RTK runs** where RTK never fired (by RTK's own count) are included in the results, and their number is reported.
- **Budget:** the total cap is **$250**. If it's reached, everything finished is reported and marked incomplete. No result is rerun because of its outcome.

## Pilot
1 repo × 2 commits × 1 repeat, all setups, to check the harness and measure cost and variance. Pilot runs are **not** part of the results and are published separately.

## Disclosure
- aimpg is built by one developer using Claude Code (Anthropic).
- The author pays for all runs, has no affiliation with any vendor tested, and receives nothing from them.
- Every raw record, the selection lists and the analysis code are published, so anyone can rerun any commit with `aimpg verify --rerun`.

## Changes before the freeze (no paid run has happened yet)
- **2026-10-11, harness:**
  - **Dependency groups:** installs use only dependency groups named like dev/test/testing, because installing every group pulled in docs tooling.
  - **Git dependencies:** the install phase may also reach github.com and codeload.github.com, for dependencies a lockfile pins to a commit. The agent phase is unchanged.
  - **macOS cache file:** the sandbox allows the xcrun cache file macOS's git and clang need.
  - **Early give-up:** a repo whose first 5 candidates all fail to install is given up early.
  - **Selection restart:** the commit selection was restarted from scratch after these changes.
- **2026-10-11, repos:** pydantic now builds its Rust core from source inside the repo, so its commits can't be installed offline. By the replacement rule it is replaced by the first reserve, litestar.
