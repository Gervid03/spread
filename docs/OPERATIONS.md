# Operations: the machines, the final runner, promoting

## The machines
| Machine | Where | Role | Login |
|---|---|---|---|
| Verda `loud-rain-laughs-fin-03` | Helsinki, ~25 ms from Bahn's server | **The final runner, and nothing else** | `ssh -i ~/.ssh/verda_spread root@95.133.252.120` |
| `spread-swarm` (Google Cloud) | Stockholm, ~8 ms | The practice host: evaluations, experiments, the ranking-round loop | `ssh -i ~/.ssh/verda_spread ops@34.51.182.19` |
| the main PC | — | the lead's checkout (`%USERPROFILE%\spread`) | — |

Everything on the machines runs as the user `lab` (`sudo -u lab -H bash -l`). Verda drops SSH connections that come
in quick bursts (wait ~30 s and retry); it has no SFTP, so copy files with `ssh host 'cat > file' < file`. The
Google account is deleted the day after the hackathon.

## The final runner (Verda)
- A systemd service, `spread-final`, runs `uv run lab final` in `/home/lab/spread-final` (a clean clone of `main`).
  It waits for a final, plays it, exits when it ends, restarts after 5 s and waits for the next; it rejoins by
  itself after a crash or a server restart.
- Before every start it pulls `main`, so it plays the current champion; while no final is set it also exits when
  `src/`, `champion/` or the lock file changed on main. To pin what it plays (Sunday morning, once the champion
  is final): `touch /home/lab/spread-final/.freeze`.
- Watch: `systemctl status spread-final`, `tail -f /home/lab/spread-final/runs/final.log`.
- `/home/lab/final_watch.py` (a separate, read-only process) dumps every event and the score of a final to
  `/home/lab/final-logs/<worldId>/`.
- **Never run `lab final` anywhere else**: two desks on one final world would quote against each other.
- During a final the team's practice limit drops to 20 requests/s; `lab` pauses practice in the quiet hours by
  itself (`QUIET_UTC` in `lab.py`), and `~/.spread-lab/pause` pauses it by hand.

## The practice host
- The root checkout `~/spread` follows main. The ranking-round loop (`lab board --auto --yes` every 30 min, until
  Sun 06:30) runs there in a detached `bash -c while …` and plays each new round with the champion.
- `SPREAD_SLOTS` in `.env` sets how many of the team's 8 practice worlds this machine may hold.

## Promoting a champion
`scripts/promote.sh <branch> [-s key=value ...]` on the practice host, as `lab`: merges the branch onto main in a
fresh worktree, refuses files outside the desk, runs dev, holdout and a restart, checks them with
`scripts/promote_gate.py` against the champion, runs `lab promote`, logs a line in `experiments/PROMOTIONS.md` and
pushes main fast-forward. `DRY=1` checks without pushing. It refuses after Sun 06:00 Helsinki.
