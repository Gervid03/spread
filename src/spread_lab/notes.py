"""Reading dealer notes (Finnish, Swedish, English).

The window reader is the kit starter's, kept as it is so its behaviour is a known quantity. The flag
readers (manual gearbox, plates, summer tyres) are ours: they let a post fix the cause *before* a
failed visit instead of after one. The reveal (`lab reveal`) shows what each won note really meant,
so any reader here can be measured: `lab notes-check <run dir>`.
"""
from __future__ import annotations

import re
from typing import NamedTuple, Optional

from spread.types import Note, TimeWindow

HOUR, DAY = 60, 24 * 60

# --- the starter's window reader ------------------------------------------------------------------
# "Not before", "at the earliest" and a ready time all mean from then on; read them before BEFORE.
# re.ASCII makes \b and \d mean what they mean in JavaScript, so both starters read a note alike.
AFTER = re.compile(r"jälkeen|alkaen|aikaisintaan|\bafter\b|\bfrom\b|earliest|not before|ei ennen|valmis|\bready\b|efter|tidigast|inte före|klar", re.ASCII)
BEFORE = re.compile(r"ennen|mennessä|viim|\bbefore\b|\bby\b|latest|före|senast", re.ASCII)
DELIVERY = re.compile(r"toimit|perillä|perille|vastaanot|kohde|deliver|arrive|destination|receiv|leverera|leverans|framme|mottag", re.ASCII)
CLOCK = re.compile(r"(?:klo|kl\.?)\s*(\d{1,2})(?:[.:](\d{2}))?|\b(\d{1,2})[.:](\d{2})\b", re.ASCII)
# Opening hours as a range: "9-16", "klo 9.00-14.30", "kl 10-14".
RANGE = re.compile(r"\b(\d{1,2})(?:[.:](\d{2}))?\s*[-–]\s*(\d{1,2})(?:[.:](\d{2}))?\b", re.ASCII)


def window_from_note(note: Optional[Note], window: TimeWindow, stop: str) -> TimeWindow:
    """Narrows a stop's window by clock times in the note, found by keywords: "nouto ennen 15.30",
    "klo 12 jälkeen", "deliver by 19:00", "efter kl. 12", "aikaisintaan klo 13.30", "not before
    16:00", and opening hours as a range, "arkisin 9-16". The time is on the window's own day."""
    if not note:
        return window
    text = note["text"].lower()
    if bool(DELIVERY.search(text)) != (stop == "delivery"):
        return window

    def minutes(hour: int, minute: int) -> Optional[int]:
        return None if hour > 24 or minute > 59 else hour * HOUR + minute

    start, end = window["from"], window["to"]
    for match in RANGE.finditer(text):
        opens, closes = minutes(int(match[1]), int(match[2] or 0)), minutes(int(match[3]), int(match[4] or 0))
        if opens is None or closes is None or opens >= closes:
            continue
        start = max(start, start // DAY * DAY + opens)
        end = min(end, end // DAY * DAY + closes)
    text = RANGE.sub(" ", text)
    for match in CLOCK.finditer(text):
        m = minutes(int(match[1] or match[3]), int(match[2] or match[4] or 0))
        if m is None:
            continue
        time = window["from"] // DAY * DAY + m
        around = text[max(0, match.start() - 16): match.end() + 16]
        if AFTER.search(around):
            start = max(start, time)
        elif BEFORE.search(around):
            end = min(end, time)
    return {"from": start, "to": end} if start <= end else window


# --- our flag readers -----------------------------------------------------------------------------
MANUAL = re.compile(r"manuaali|käsivaiht|manuell|\bmanual\b|stick ?shift|\bclutch\b|kytkin", re.IGNORECASE)
# Plates: a negation or a transfer-plate word. "Kilvet autossa" (plates in the car) must not fire.
NO_PLATES = re.compile(
    r"ei kilp|ilman kilp|kilvet[oö]n|kilpiä ei|siirtokilp|koekilp|"
    r"inga skyltar|utan skyltar|saknar skyltar|provskylt|"
    r"no (?:license |licence |number |registration )?plates|without (?:license |licence |number )?plates|"
    r"plates? (?:are )?missing|needs? (?:transfer |trade )?plates|unregistered",
    re.IGNORECASE)
SUMMER = re.compile(r"kesärenka|kesäkum|sommardäck|summer tyres?|summer tires?", re.IGNORECASE)


class NoteFlags(NamedTuple):
    manual: bool = False
    plates: bool = False
    summer_tyres: bool = False


def note_flags(note: Optional[Note]) -> NoteFlags:
    if not note:
        return NoteFlags()
    text = note["text"]
    return NoteFlags(manual=bool(MANUAL.search(text)), plates=bool(NO_PLATES.search(text)), summer_tyres=bool(SUMMER.search(text)))
