# Operations: the machines, the final runner, the swarm

For the lead (and Claude). Agents don't need this file; they follow `AGENTS.md`.

## The machines
| Machine | Where | Role | Login (from the laptop) |
|---|---|---|---|
| `loud-rain-laughs-fin-03` (Verda, 4 vCPU, 16 GB, €0.055/h) | Helsinki, ~25 ms from Bahn's server | **The final runner, and nothing else** | `ssh -i ~/.ssh/verda_spread root@95.133.252.120` |
| `spread-swarm` (Google Cloud e2-standard-4, ~$0.14/h, hackathon project `junction26hel-7477`) | Stockholm, ~8 ms | **The swarm**: Gemini agents and their evaluations | `ssh -i ~/.ssh/verda_spread ops@34.51.182.19` |
| the laptop | the venue | the lead's checkout; the first Gemini wave ran here | — |

Everything runs as the user `lab` (`sudo -u lab -H bash -l`). Both machines were set up with
`scripts/vm-push.sh <user@host> final|swarm`, which installs uv, the repo (through a deploy key with write
access to this repository only), the `.env`, and, on the swarm host, Node and the Gemini CLI.

Notes: Verda drops new SSH connections that come in quick bursts (wait ~30 s and retry); its minimal image has
no SFTP, so copy files with `ssh host 'cat > file' < file`. The Google account is deleted the day after the
hackathon; nothing on `spread-swarm` survives that, so everything lives in git.

## Practice is slow on the server's side, not ours
A practice `advance` takes the shared server ~70 ms to simulate, from anywhere (laptop, Helsinki or
Stockholm all give ~50–60 s per level-8 week at ~650 requests). Throughput comes from parallel worlds: the
team may hold 8. `SPREAD_SLOTS` sets each machine's share (swarm host 7, laptop 6 by default; across
machines the server's 409 makes the harness wait). The team's practice limit (263 requests/s at 00:15 on
Saturday, shared by all our machines) is not the bottleneck.

## The final runner (Verda)
- A systemd service, `spread-final`, runs `uv run lab final` in `/home/lab/spread-final` (a clean clone of
  `main`). It waits for a final, plays it, exits when it ends, restarts after 5 s, and waits for the next.
  So it plays **both test finals (Sat 14:00, 20:00) and the final (Sun 08:00)** without anyone touching it,
  and it rejoins by itself after a crash or a server restart.
- Before every start it pulls `main`, so it always plays the current champion. To pin what it plays (do this
  on Sunday morning once the champion is final): `touch /home/lab/spread-final/.freeze`; remove the file to
  unpin.
- Watch it: `systemctl status spread-final`, `tail -f /home/lab/spread-final/runs/final.log` (the desk's
  day lines) and `runs/final-service.log` (everything). Restart it after promoting a new champion if no final
  is running: `systemctl restart spread-final`.
- **Never run `lab final` anywhere else.** Two desks on one final world would quote and post against each
  other.
- During a test final or the final the team's practice limit drops to 20 requests/s: pause the swarm.

## Since Sat 01:00 (see docs/HANDOFF.md)
- Quiet hours pause practice during the finals; `~/.spread-lab/pause` pauses it by hand.
- The final runner restarts itself on a new main while no final is set (`.freeze` pins it).
- `uv run lab board --auto --yes` plays what is left of the current ranking round.

## The swarm (Stockholm)
- Start one agent per idea (a worktree and branch per agent, a turn cap per agent):
  `cd ~/spread && git pull && TURNS=120 setsid nohup bash scripts/swarm.sh <slug> gemini-3.1-pro-preview experiments/prompts/gemini-<slug>.md >/dev/null 2>&1 &`
- Logs: `~/spread/runs/swarm/<slug>.jsonl` (stream-json: tool calls, messages, and at the end the token
  stats). Results: the agent pushes `exp/gemini-<slug>` with code and an experiment note.
- Budget: the Google project warns against "thousands of requests". Wave 1 used ~40 model turns per
  agent; keep waves to 3–4 agents.

## Promoting a champion
**Since Sat 07:15: `scripts/promote.sh <branch> [-s key=value ...]` on the swarm host** does all of it with gates: it
merges the branch onto origin/main in a fresh worktree, refuses files outside the policy, runs dev, holdout and a
restart, checks them with `scripts/promote_gate.py` against the champion, promotes, logs to
`experiments/PROMOTIONS.md` and pushes main fast-forward. `DRY=1` checks without pushing; it refuses after Sun 06:00
Helsinki. The steps below are what it does by hand.
1. The candidate's branch must be SAFE on dev with a clear gain (t ≥ 2), and SAFE on holdout.
2. Merge it into `main`, bake its flags into the `Params` defaults (or keep them in `champion.json`), and
   `uv run lab promote <dev run folder>` then `uv run lab promote <holdout run folder>`; commit `champion/`.
3. Push `main`. The final runner picks it up at its next start.

## The night run (`scripts/night.sh`, on the swarm host)
One detached process for HOURS (default 8). It runs Gemini workers from a queue (`experiments/prompts/night/*.md`,
3 at a time, 150 turns each), refills the queue with a Gemini lead tick (`experiments/prompts/_night-lead.md`) when
it runs dry, runs the sweep track (`experiments/night/sweeps.txt` on dev, then the lead's additions), plays the
ranking rounds with the champion (`NIGHT_BOARD=1`), and every 20 minutes force-pushes run summaries, sweep tables,
worker reports and `STATUS.md` to the branch `night/<date>`, which a cloud session can read in the morning.
- Start: `cd ~/spread && HOURS=8 setsid nohup bash scripts/night.sh > runs/night.out 2>&1 < /dev/null &`
- Watch: `tail -f runs/night/night.txt`, `python3 scripts/night_status.py`. Stop: `touch runs/night/stop`.
- Add work live: a prompt file in `runs/night/queue/`, a line in `runs/night/sweeps-extra.txt`.
- If workers die within 3 minutes three times in a row, it switches to `FALLBACK_MODEL` (gemini-3.1-pro-preview).
