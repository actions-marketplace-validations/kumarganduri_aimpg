# Launch posts: AI Coding MPG Report No. 1

**Link targets**
- Report page: https://kumarganduri.github.io/aimpg-scoreboard/report-1/
- Tool: https://github.com/kumarganduri/aimpg
- 5-minute guide: https://kumarganduri.github.io/aimpg-scoreboard/start/

**Rules for every post**
- Lead with one finding.
- Say "not shown" as plainly as "found".
- Never put RTK in a title.
- Disclose that it's built with Claude Code.
- Never ask anyone to upvote.

**Facts to use** (all from the report):
- 984 runs, 8 open-source repos, 56 commits, 3 repeats each, $121 at published prices. Pre-registered and frozen before the main run (after a $1.79 pilot), with all raw data public.
- **Deviation found in review:** 10 of the 56 commits were written before the 2026-07-01 cutoff but committed after it (all 7 homebridge, 3 click). Without them every result keeps its direction and finding status (Haiku −82%, Opus +176%, fresh session +11%).
- **Haiku 5.5 vs Sonnet 5.5 in Claude Code:** about 6× cheaper per solved task (−83%, 95% interval −86% to −80%); solved 49% vs 51%; cheaper in 8 of 8 repos.
- **Opus 5.5:** solved more (61% vs 51%) but cost 2.6× more per solved task; more expensive in 8 of 8 repos.
- **A fresh session for the next task** (with a one-line summary) cost 13% more than continuing, despite 16% fewer tokens, in 8 of 8 repos. Cache writes cost more than cache reads.
- **Not shown:** Codex (gpt-6.1-sol) vs Claude Code on cost per solved task (+9%, −23% to +41%); a popular token-saving tool on tokens (+1%, −6% to +9%).
- **Side finding:** Claude Code 2.1.287 displays Haiku 5.5 runs at about 27× the price Anthropic actually bills.

---

## Hacker News (Tue–Thu, 8–10am US Eastern)

**Title options (pick one):**
1. `Show HN: AI Coding MPG – 984 reruns of real commits, cost per solved task by model`
2. `Haiku solved nearly as many real coding tasks as Sonnet for a sixth of the cost`, linking to the report page (a blog-style submission)
3. `Show HN: aimpg – what your AI coding agent costs per change that ships`

**First comment (post right after submitting):**

> I built aimpg ("miles per gallon for AI coding") because I couldn't tell what my Claude Code work cost per change that actually shipped, or whether "saves 60% of tokens" claims hold on real code.
>
> To test that properly I pre-registered a study: 8 open-source repos (litestar, starlette, click, pyinfra, axios, lint-staged, recharts, homebridge), the first 7 commits committed after the models' training cutoff whose tests fail before the change and pass after, each redone 3 times by 5 setups in a sandbox, and judged by the repo's own hidden tests. 984 runs, $121.
>
> What held up, in all 8 repos:
> - Haiku 5.5 cost about 1/6 as much as Sonnet 5.5 per solved task, solving 49% vs 51%.
> - Opus 5.5 solved more (61% vs 51%) but cost 2.6× more per solved task.
> - Starting a fresh session for the next task cost 13% *more* than continuing. Re-reading cached context is cheap; rewriting it into the cache isn't. This contradicted the tip my own tool used to give, so I removed it.
>
> What didn't hold up: Codex vs Claude Code (no clear difference), and a popular token-saver (no token saving shown).
>
> One thing I got wrong: the selection checked the commit date, not the date the code was written, so 10 of the 56 commits were written before the cutoff. Without them every result still holds; both versions are on the page.
>
> Limits: 8 Python/TypeScript repos with good tests; small-to-medium tasks; one config per tool; prices change. I built it with Claude Code and pay for every run myself, with no vendor affiliation. All raw records, the pre-registration and the deviations (two credit run-outs, one misclassified Codex quota error, all fixed before the analysis) are linked on the page. Any result can be rerun with one command.
>
> For your own numbers: `uvx aimpg report` reads your local Claude Code / Codex logs. Nothing leaves your machine. No logs? `uvx aimpg report --demo` shows a sample.

**Replies to have ready:**
- **"n is small":** Agreed it's not huge. That's why it's pre-registered, why a finding needs ≥5 of 6+ repos, and why two of five comparisons are reported as "not shown". Reruns welcome; the command is on the page.
- **"Energy numbers are guesses":** They're estimates with ranges, and none of the findings rely on them. Dollars come from tokens at published prices, and I checked them against my actual bill.
- **"Shill for Anthropic?":** The study made two Anthropic models look expensive or no better, and it tested Codex. I have no affiliation.
- **"Tests-only tasks are easy":** The tests were hidden; the agent saw only the commit message and the names the tests import. Solve rates were around 50%.
- **"Why did the fresh session cost more?":** A new session writes its whole context to the prompt cache again, and cache writes are priced above cache reads. The 16% fewer tokens didn't make up for it.

---

## X / Twitter (thread; attach `aimpg-clip.mp4` to post 1)

1. I reran 56 real commits from 8 open-source repos with 5 AI coding setups, 984 times, and let each repo's own hidden tests judge.
   What does AI coding cost per *solved* task? 🧵 [clip]
2. Haiku 5.5 vs Sonnet 5.5 (Claude Code): about 6× cheaper per solved task, solving 49% vs 51%. Cheaper in 8 of 8 repos.
3. Opus 5.5 solved more (61% vs 51%) but cost 2.6× more per solved task. Worth it when you need the extra solves; expensive as a default.
4. "Start a fresh session after each commit"? It cost 13% MORE for the next task, despite 16% fewer tokens. Re-reading cached context is cheap; rebuilding it isn't. My own tool said otherwise, so I fixed the tool.
5. Not shown: Codex vs Claude Code (about even), and a popular token-saver (no token saving). Reported as plainly as the wins.
6. Pre-registered before the main run, all 984 raw records public, deviations listed (including one I found after: 10 commits were older than the cutoff; results hold without them), and any result can be rerun with one command: [report link]
7. For your own numbers from your Claude Code / Codex logs (nothing leaves your machine): `uvx aimpg report` (no logs? `uvx aimpg report --demo`). Post your receipt with #AIcodingMPG · github.com/kumarganduri/aimpg
8. What should Report No. 2 test? Suggest a setup or a vendor claim to check: [Report No. 2 thread link]

---

## LinkedIn (engineering leaders)

> **What does your team's AI coding actually cost per change that ships?**
>
> Most teams see a monthly AI bill and a commit count, but not the cost per change that ships, or whether the model they default to is the right one.
>
> I ran a pre-registered study: 56 real commits from 8 open-source projects, redone 984 times by 5 AI coding setups, judged by each project's own hidden tests.
>
> **For teams it suggests three things:**
> 1. **Default model:** Haiku 5.5 solved about as many tasks as Sonnet 5.5 for about a sixth of the cost per solved task. Opus 5.5 solved more but cost 2.6× more per solved task. "Which model by default" is a real budget lever, and it's measurable on your own code.
> 2. **Session habits:** "start fresh to save tokens" backfired. It cost 13% more for the next task.
> 3. **Vendor claims:** a popular token-saving tool showed no saving. Check claims on your own commits before rolling them out.
>
> aimpg is free and open source. It can post each PR's AI cost as a comment, report the team's weekly cost per working change, and set a team's default model from evidence on your own repo. Metadata only, and never per person.
>
> Full report and raw data: [report link]
> (Disclosure: built with Claude Code; no vendor affiliation; I paid for every run.)

---

## Reddit (one per day; flair each post as the subreddit's rules ask)

**r/ClaudeAI, day 1.** Title: `I reran 56 real commits with Haiku 5.5, Sonnet 5.5 and Opus 5.5 in Claude Code (984 runs). Cost per solved task results`
> Body: Haiku/Sonnet/Opus numbers, the fresh-session finding, and Claude Code's 27× Haiku cost display vs the actual bill (worth knowing if you budget from it). Method in 3 lines, then the report link and `uvx aimpg report`. Disclosure at the end.

**r/ChatGPTCoding, day 2.** Title: `Codex (gpt-6.1-sol) vs Claude Code on 56 real commits judged by hidden tests: about even on cost per solved task`
> Body: Codex solved 57% vs 51%; cost per solved task +9% (−23% to +41%), not a clear difference; more tokens per attempt (+61%). Report link. Invite reruns with other models.

**r/programming, day 3–4** (only as a methodology write-up). Title: `Pre-registering a benchmark of AI coding agents on real commits: what broke, what we fixed, what held up`
> Body: the harness problems (localhost test servers, git-derived versions, coverage thresholds, a misread quota error) and how pre-registration kept us honest. Results are secondary. Report link.

---

## Newsletters and communities (the week after)
- **Pragmatic Engineer** (tip line): "Pre-registered study, 984 reruns of real commits: Haiku 5.5 about 6× cheaper per solved task than Sonnet 5.5 with a similar solve rate; 'start a fresh session' cost 13% more. Raw data public." Link.
- **TLDR:** submit the report link with a one-line summary.
- **Green Software Foundation:** "aimpg produces SCI for AI (Consumer) figures for coding agents from real usage logs, and the report measures cost and energy per solved task. Happy to contribute it as a reference implementation." Link.
- **Claude Code Discord** (#showcase): the receipt card + `uvx aimpg report` + the report link, asking for feedback.

---

## Before launch: right of reply to RTK (post 3–4 days before, in discussion #4511)
> Following up on the setup question above: the pre-registered study has run. With the setup described above (RTK 0.51.0, `rtk init --global --auto-patch --no-trust-filters`), RTK fired in 163 of 168 runs. Tokens per attempt were +1% (95% interval −6% to +9%) compared with plain Claude Code on the same tasks, so no token saving was shown on these repos. Raw records: [link to data]. If you think the setup or the measurement is unfair, reply here before [launch date] and we'll publish your response next to the results, or rerun with a setup you recommend.

---

## Launch day: "What should Report No. 2 test?" (open right after the report goes live)
Discussions are off on the aimpg repo, so either turn them on (Settings → Features → Discussions; an "Ideas" category) or open this as a pinned issue. Then link it from the report page ("Next report") and the README.

**Title:** What should AI Coding MPG Report No. 2 test?

> Report No. 1 compared Claude Code on Haiku/Sonnet/Opus 5.5, Codex and one token-saving tool on 56 real commits ([report](https://kumarganduri.github.io/aimpg-scoreboard/report-1/)).
>
> Report No. 2 will test what you ask for. Reply with one suggestion per comment and 👍 the ones you want; the top suggestions go into the next pre-registration. Good suggestions name:
> - the setup (agent, model, tool, prompt or setting), and
> - the claim to check ("saves 60% of tokens", "solves more", "cheaper per task"), with a link if a vendor makes it.
>
> Vendors are welcome to suggest their own product's setup; it's tested the same way, and you get to review the setup before any run, as RTK was offered.
>
> Want a result sooner? Run it on your own repo with `aimpg verify` and submit it to the [scoreboard](https://kumarganduri.github.io/aimpg-scoreboard/).
