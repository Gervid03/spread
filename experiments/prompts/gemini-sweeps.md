The Tier 0 sweeps S1-S6 of experiments/IDEAS.md. They need no code: run commands and write up results.
Skip protocol steps 1-2 (there is no code to check).
- Run each sweep on smoke exactly as the table writes it, adding `--name s<N>` (S5 is a single eval).
- For each sweep whose best combination is SAFE and beats the champion on smoke, run that one combination
  on dev: `uv run lab eval -s key=value ... --name s<N>-dev`. At most 6 dev runs in all: pick by promise.
- Then combine every setting that helped on dev into one dev run (for example S1's radius with S3's fee).
- Write one note, experiments/<YYYYMMDD-HHMM>-gemini-tier0-sweeps.md: per sweep a table (setting, smoke mean
  margin, paired delta, worst on-time, SAFE), the dev confirmations, and a one-line verdict. Commit, push.
