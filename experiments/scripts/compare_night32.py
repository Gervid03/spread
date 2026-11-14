import json
import sys
from pathlib import Path
from spread_lab.lab import compare, load_results, summarize


def main() -> None:
    cand_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("runs/20261114-102117-cp-margin-indisc07-fixslot-night32")
    champ_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("/home/lab/spread-wt/n14-06591-final-champion/runs/20261114-073207-fc-v3T-night32")
    cand = load_results(cand_dir)
    champ = load_results(champ_dir)
    print("Champion summary:", json.dumps(summarize(champ), indent=2))
    print("Candidate summary:", json.dumps(summarize(cand), indent=2))
    print("Paired comparison:", json.dumps(compare(cand, champ), indent=2))
    print("Worlds under 92%: candidate=", sum(1 for r in cand if r["on_time"] < 0.92), "champion=", sum(1 for r in champ if r["on_time"] < 0.92))


if __name__ == "__main__":
    main()
