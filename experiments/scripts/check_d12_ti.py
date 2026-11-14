"""Check notes on all 2-leg trade-ins on dev-12 tape."""
from __future__ import annotations

import json
from spread_lab.env import lab_home
from spread_lab.notes import note_flags, parse_note_v2


def main() -> None:
    tape = json.loads((lab_home() / "tas" / "dev-12" / "tape.json").read_text())
    for r in tape["requests"]:
        if len(r["legs"]) == 2 and r.get("note"):
            pn = parse_note_v2(r["note"], r["arrivedAt"])
            fl = note_flags(r["note"], v2=True)
            print(r["id"], r["legs"][0]["pickup"]["placeId"], "->", r["legs"][0]["delivery"]["placeId"], "note=", r["note"]["text"], "pn=", pn, "fl=", fl)


if __name__ == "__main__":
    main()
