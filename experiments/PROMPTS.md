# Prompts for the swarm

Copy-paste starters for the lead. Each agent gets its own git worktree and one idea.

## Starting an agent (Codex, Gemini or Claude)
```sh
# from the main checkout; one worktree and branch per agent and idea
git worktree add ../spread-<slug> -b exp/<agent>-<slug>
cd ../spread-<slug> && uv sync
# Codex needs network for the harness:  codex --sandbox danger-full-access   (or workspace-write with network access on)
# Gemini CLI reads GEMINI.md, which imports AGENTS.md; Codex reads AGENTS.md; Claude Code reads CLAUDE.md -> AGENTS.md.
```
If agents run on more than one machine, give each machine its share of the team's 8 practice worlds:
`SPREAD_SLOTS=4` on one, `3` on the other (leave one for the lead).

## The implementer prompt
> You are working on Swarm Dispatch, our entry for Bahn Express's Spread challenge. Read `AGENTS.md`
> completely, then `docs/GAME.md`. Your idea is **#<N> in `experiments/IDEAS.md`: <title>**; mark it
> `taken (<your branch>)` there. Implement it behind new `Params` flags whose defaults reproduce the
> champion exactly (prove it: `uv run lab eval --seeds-from smoke` with no overrides shows Δ = 0.00).
> Iterate on smoke; when it looks good, run the dev set. Write your experiment note from
> `experiments/TEMPLATE.md` with the numbers from the run's `summary.json`, commit code and note on your
> branch, push the branch, and finish with a 3-line report: the flag values, Δmargin ± SE on dev, the
> worst on-time share, and the run folder. Follow the hard rules in AGENTS.md; never run `lab board`,
> `lab final`, `lab promote` or `lab reap --force`.

## The research prompt (no policy change)
> Read `AGENTS.md` and `docs/GAME.md`. Question: **<e.g. at what price ÷ list do our quotes start to lose,
> by option and hour?>** Use reveals of finished practice worlds (`uv run lab reveal <world id>`; the world
> ids are in each run's `results.jsonl`), not new worlds where you can avoid it. Write the answer, with
> numbers and the script that produced them, to `experiments/<date>-<agent>-research-<slug>.md`, and end
> with what it suggests for the desk (which Params, which values).

## The ideation prompt (Fable)
> Read `AGENTS.md`, `docs/GAME.md`, the organisers' `docs/kit/HANDBOOK.md` and `RULES.md`,
> `experiments/IDEAS.md`, every note in `experiments/`, `champion/champion.json`, and
> `src/spread_lab/policy.py`. Our score is the mean margin on 16 level-8 worlds, with every world at least
> 92% on time. Propose the ideas most likely to raise it, ranked by expected gain per hour of agent work.
> For each: the mechanism in the game it exploits (cite the rule or a measurement), the change to the desk
> as `Params` flags with defaults that keep the champion, how to measure it (seed set, which counters), and
> the risk to the on-time share. Rewrite `experiments/IDEAS.md` with them (keep finished items with their
> results). Prefer few, sharp ideas the jury can follow: elegant, clear, creative, robust.
