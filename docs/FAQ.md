# FAQ

**Who makes aimpg? Is it sponsored?**
aimpg is one developer's free, open-source project. It's built with Claude Code (Anthropic's coding agent), and Claude Code logs are its best-supported input. The author pays for every test run, has no affiliation with any vendor whose tools it tests, and receives nothing from them. Codex, Cursor and any agent CLI are supported, and every study includes non-Anthropic setups.

**Your sample is tiny.**
The early results came from one repo and 10–40 runs, and we label them that way. That's why Report No. 1 is a [pre-registered study](study/report-1/PREREGISTRATION.md): 8 public repos, commits chosen by a fixed rule, 3 repeats, Holm correction, and a finding only counts if it holds in at least 5 of 6 repos. All raw records are published.

**Aren't the energy numbers just guesses?**
They're estimates with stated assumption ranges, not measurements. Model sizes and data-centre details aren't public, so every figure is a low–high range. Each assumption is sourced in [`aimpg/factors.json`](../aimpg/factors.json). As a sanity check, a chat-sized prompt on a mid-size model comes out at 0.017–0.34 Wh, which brackets Google's disclosed 0.24 Wh per median Gemini prompt. That's one external figure, not proof for every model. We never headline energy, and we only rank energy within the same model.

**I'm on a subscription. Why does it show dollars?**
Dollars are what the same tokens would cost at the API's list prices. That's a consistent way to compare setups, not your bill. A subscription costs less. Token counts and rate-limit share are shown too.

**Aren't these tasks too easy, because the agent sees the tests?**
By default the agent doesn't see the tests. It gets the commit message plus the names the hidden tests import, and the commit's own tests judge the result. Any edits the agent makes to tests are undone before judging. A "tests shown" mode exists, is easier, and is labeled when used.

**Couldn't the model have memorized these commits?**
Studies only use commits made after every tested model's training cutoff (Claude: June 2026; gpt-6.1-sol: April 2026). Each commit's tests also have to fail on the code before it and pass on the commit, twice each.

**Why not just look at my bill?**
A bill tells you the total. aimpg tells you what each change that shipped and lasted cost, which habits drove it, and whether a cheaper model or a token-saver actually saves money on your code, judged by your tests.

**"Just /clear more." Do I need a tool for that?**
Maybe not. aimpg tells you how much of your agents' tokens were conversation carried over from before your last commit (57% for the author). It doesn't claim clearing saves all of that: a fresh session has to rebuild some context. Report No. 1 includes an experiment that measures the real difference on real commits.

**Is it safe to run?**
`report`, `live`, `sci` and `defaults` only read local logs and git. Replays run agents in a sandbox: Seatbelt on macOS, bubblewrap on Linux. The sandbox hides your home folder, temp folders and other users' files, and only reaches the model's API through an allowlisting proxy. A pre-launch security review found and fixed three high-severity issues (in 0.6.1), each with a regression test. `--rerun` of someone else's record shows every command, hook and prompt it would run, and asks first.

**What leaves my machine?**
Nothing, unless you choose:
- `aimpg notes push` shares per-commit cost numbers in your git repo.
- `aimpg submit` publishes a stripped copy of a `verify` result on the public scoreboard, after showing you the exact file.

Prompts, code, diffs, commit messages and API keys are never sent.

**Windows?**
`report` and the team commands should work, but they're untested there. Replays and `verify` need macOS or Linux.

**What about RTK?**
On the author's repo, RTK showed no reliable energy saving, but that's one repo and RTK advertises *token* savings. In Report No. 1 RTK is judged on tokens per task, its own claim. We asked its maintainers to review our setup before running it ([discussion](https://github.com/rtk-ai/rtk/discussions/4511)), and we'll publish their response next to the results.

**How do I check a result myself?**
- `aimpg verify --check record.json` recomputes any record's verdict and checks it's consistent (free). It can't prove the runs happened.
- `aimpg verify --rerun record.json --repo <clone>` reruns a public record on your own machine.

Only results someone else has reproduced reach the scoreboard's headline.

**Can a vendor game the scoreboard?**
Not easily:
- Self-reported results never make the headline.
- One account counts for at most 3 repos per claim.
- A number needs at least 5 repos and 3 people.
- A vendor's own claims count only once someone unconnected reproduces them.

See the [challenge rules](https://github.com/kumarganduri/aimpg-scoreboard/blob/main/CHALLENGE.md).
