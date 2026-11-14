## Your task: c5, an LLM supervisor that sets tomorrow's dials each evening (the user's idea, the jury's "creative")

The user's question (14 Nov): can an LLM watch the week and adjust the system the way a dispatcher would, so it copes
with a world unlike our practice worlds? Per request it is too slow (a request has 4.5 real seconds in the final), so
it runs once a world-day, in the evening, and moves a few dials inside fixed limits. A formula arm runs beside it, so
the jury gets "with and without, on the same weeks".

Implement `src/spread_lab/supervisor.py` and flags in policy.py, off by default:
- `supervisor: str = ""` ("" = off, "llm", or "rule"). At 20:00 on Mon–Thu (world time), build a small JSON of the
  day: requests, quotes, wins and the win rate by pool (capital, ring, other) and option; late orders and warnings;
  drops; unbooked orders now; the projected on-time share; the five biggest dealers' trust counts; and today's dials.
- "llm": send it with a short system prompt (the rules in ten lines, the dials and their limits, "answer only JSON") to
  `gemini-4-argon` through the Gemini API (`GEMINI_API_KEY` from the environment; standard library `urllib`, no new
  packages), temperature 0, a 20-second timeout. It answers `{"price_target_win": x, "min_supply": n, "fee_open": f,
  "why": "..."}`. Clamp to the limits: `price_target_win` 0.35–0.45, `min_supply` 18–30, `fee_open` 0.75–1.00. On any
  error, timeout or bad JSON, keep today's dials and count it.
- "rule": the same dials from a formula: if the projected share is ≥ 0.96 and the unbooked backlog is low, loosen
  one step (win +0.02, min_supply −2); if ≤ 0.93 or the backlog is high, tighten one step; else keep.
- Replay for paired tests: cache each answer in `runs/supervisor/<world seed>-<day>.json` and reuse it when it exists,
  so a rerun of the same seed plays the same dials. In live mode (`lab final`) make the call in a thread, so quoting
  never waits for it; the dials change when it answers.
- Counters: calls, answers used, fallbacks, the dials per day, and the "why" lines (into the note, a few examples).

Protocol: noop on smoke; then "rule" and "llm" on 8 dev worlds each (the LLM arm costs ~32 calls). The 16 only for an
arm with Δ > 0. Report the worst world first, then margin against the champion, and for "llm" whether its choices
differ from the rule's and when. Even a null result is useful to the jury if it is measured: write it up either way.
