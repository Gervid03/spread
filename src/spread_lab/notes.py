"""Reading dealer notes (Finnish, Swedish, English).

The v0 window reader is the kit starter's, kept as the default (`v2=False`) so its behaviour is a known
quantity. With `v2=True` (`notes_v2`), the reader parses pickup/delivery opening hours, relative days
("tomorrow", "huomenna", "ylihuomenna"), weekday names (2..6 days after arrival), Finnish/Swedish hours
in words (working hours 9..17 and "puoli X" / "halv X"), self-corrections and denials, and flags notes
with an unplaced time as `unsure`.
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


# --- v2 reader -------------------------------------------------------------------------------------
_TRANSLIT = str.maketrans({"ä": "a", "ö": "o", "å": "a", "–": "-", "—": "-"})

_KEYWORDS = (
    # Days
    "tanaan", "huomenna", "ylihuomenna", "idag", "morgon", "imorgon", "overmorgon", "today", "tomorrow",
    "maanantai", "maanantaina", "tiistai", "tiistaina", "keskiviikko", "keskiviikkona",
    "torstai", "torstaina", "perjantai", "perjantaina", "lauantai", "lauantaina", "sunnuntai", "sunnuntaina",
    "mandag", "tisdag", "onsdag", "torsdag", "fredag", "lordag", "sondag",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    # Number words
    "puoli", "puolta", "yhteen", "yhdelta", "yhdesta", "yhden", "yhta", "kahteen", "kahdelta", "kahdesta", "kahden", "kahta",
    "kolmeen", "kolmelta", "kolmesta", "kolmen", "kolmea", "neljaan", "neljalta", "neljasta", "neljan", "neljaa",
    "viiteen", "viidelta", "viidesta", "viiden", "viitta", "kuuteen", "kuudelta", "kuudesta", "kuuden", "kuutta",
    "seitsemaan", "seitsemalta", "seitsemasta", "seitseman", "seitsemaa", "kahdeksaan", "kahdeksalta", "kahdeksasta", "kahdeksan", "kahdeksaa",
    "yhdeksaan", "yhdeksalta", "yhdeksasta", "yhdeksan", "yhdeksaa", "kymmeneen", "kymmenelta", "kymmenesta", "kymmenen", "kymmenta",
    "yhteentoista", "yhdeltatoista", "yhdentoista", "yhtatoista", "kahteentoista", "kahdeltatoista", "kahdentoista", "kahtatoista",
    "halv", "klockan", "kello",
    # Corrections / denials
    "korjaus", "eikun", "correction", "sorry", "rattelse", "inte",
    # Pickup / ready / release
    "nouto", "noudettavissa", "noutaa", "haettava", "haettavissa", "hakea", "valmis", "valmiina", "valmistuu",
    "aikaisintaan", "alkaen", "jalkeen", "ennen", "mennessa", "viimeistaan", "asti",
    "luovutus", "luovutetaan", "luovutuksia", "maksettu", "maksu", "maksun", "maksaa", "nakyy", "ostaja", "rahoitus", "vahvistuu",
    "liike", "auki", "aukioloajat", "sulkee", "kiinni", "arkisin", "arkipaivisin", "ketaan",
    "pickup", "collect", "ready", "earliest", "before", "after", "until", "close", "closes", "opening", "weekdays",
    "released", "payment", "clears", "buyer", "workshop",
    "hamtas", "hamtning", "tidigast", "framat", "klar", "forran", "lamnas", "betalning", "oppet", "stanger", "vardagar",
    # Delivery
    "toimitus", "toimitukset", "toimitusosoite", "perilla", "perille", "vastaanotto", "vastaanottava", "vastaanotetaan", "kohde", "kohteen",
    "deliver", "delivery", "destination", "arrive", "arrival", "receiving", "latest", "nobody",
    "leverans", "leverera", "framme", "senast", "mottagning", "mottagaren", "ingen",
    # Private / harmless
    "myyja", "omistaja", "kotona", "paikalla", "seller", "agaren", "hemma",
    "soita", "sita", "saapumista", "tuntia", "asiakkaalle", "pihalla", "plats",
    # Flags
    "manuaali", "manuaalivaihteinen", "manuaalivaihteet", "manuaalikortin", "kasivaihteinen", "kasivaihteet",
    "automaatti", "automaattivaihteinen", "manuell", "manuellt", "manual", "automatic", "licence", "license",
    "kilvet", "kilpia", "kilveton", "koekilvet", "siirtokilvet", "rekkareita", "rekisterikilvet", "rekisterista", "poistettu", "puuttuu", "irrotettu",
    "skyltar", "provskyltar", "plates", "unregistered",
    "kesarenkaat", "kesarenkailla", "kesarengasta", "talvirenkaita", "vaihdettu", "sommardack", "sommardacken",
    "takakontissa", "tavaratilassa", "kontissa", "kyydissa", "mukaan", "mukana", "bakluckan", "bagaget",
)


def _build_typo_map() -> dict[str, str]:
    m: dict[str, str] = {}
    kw_set = set(_KEYWORDS)
    for kw in _KEYWORDS:
        if len(kw) < 5:
            continue
        for i in range(len(kw) - 1):
            v = kw[:i] + kw[i + 1] + kw[i] + kw[i + 2:]
            if v not in kw_set:
                m[v] = kw
        for i in range(len(kw)):
            v = kw[:i] + kw[i + 1:]
            if len(v) >= 4 and v not in kw_set:
                m[v] = kw
        for i in range(len(kw)):
            v = kw[:i] + kw[i] + kw[i:]
            if v not in kw_set:
                m[v] = kw
    return m


_TYPO_MAP = _build_typo_map()
_WORD_RE = re.compile(r"[a-z]+")


def normalize_text(text: str) -> str:
    s = text.lower().translate(_TRANSLIT)
    return _WORD_RE.sub(lambda m: _TYPO_MAP.get(m.group(0), m.group(0)), s)


_WORD_HOURS: list[tuple[str, int]] = [
    (r"(?:yhteentoista|yhdeltatoista|yhdestatoista|yhdentoista|yhtatoista|yksitoista|elva)", 11),
    (r"(?:kahteentoista|kahdeltatoista|kahdestatoista|kahdentoista|kahtatoista|kaksitoista|tolv)", 12),
    (r"(?:kymmeneen|kymmenelta|kymmenesta|kymmenen|kymmenta|tio)", 10),
    (r"(?:yhdeksaan|yhdeksalta|yhdeksasta|yhdeksan|yhdeksaa|nio)", 9),
    (r"(?:kahdeksaan|kahdeksalta|kahdeksasta|kahdeksan|kahdeksaa|atta)", 8),
    (r"(?:seitsemaan|seitsemalta|seitsemasta|seitseman|seitsemaa|sju)", 7),
    (r"(?:kuuteen|kuudelta|kuudesta|kuuden|kuutta|sex)", 6),
    (r"(?:viiteen|viidelta|viidesta|viiden|viitta|fem)", 5),
    (r"(?:neljaan|neljalta|neljasta|neljan|neljaa|fyra)", 4),
    (r"(?:kolmeen|kolmelta|kolmesta|kolmen|kolmea|tre)", 3),
    (r"(?:kahteen|kahdelta|kahdesta|kahden|kahta|tva)", 2),
    (r"(?:yhteen|yhdelta|yhdesta|yhden|yhta|ett)", 1),
]


def _replace_word_hours(s: str) -> str:
    for pat_str, h in _WORD_HOURS:
        work_h = h + 12 if 1 <= h <= 7 else h
        half_pat = re.compile(r"\b(?:puoli|puolta|halv)\s+" + pat_str + r"\b")
        full_pat = re.compile(r"\b" + pat_str + r"\b")
        s = half_pat.sub(f"klo {work_h - 1}:30", s)
        s = full_pat.sub(f"klo {work_h}:00", s)
    return s


_WEEKDAYS: list[tuple[re.Pattern[str], int]] = [
    (re.compile(r"\b(?:maanantaina|maanantai|mandag|monday|mon|man|ma)\b"), 0),
    (re.compile(r"\b(?:tiistaina|tiistai|tisdag|tuesday|tues|tue|tis|ti)\b"), 1),
    (re.compile(r"\b(?:keskiviikkona|keskiviikko|onsdag|wednesday|wed|ons|ke)\b"), 2),
    (re.compile(r"\b(?:torstaina|torstai|torsdag|thursday|thurs|thur|thu|tors|tor|to)\b"), 3),
    (re.compile(r"\b(?:perjantaina|perjantai|fredag|friday|fri|fre|pe)\b"), 4),
    (re.compile(r"\b(?:lauantaina|lauantai|lordag|saturday|sat|lor|la)\b"), 5),
    (re.compile(r"\b(?:sunnuntaina|sunnuntai|sondag|sunday|sun|son|su)\b"), 6),
]

_DAY_AFTER_TOMORROW = re.compile(r"\b(?:ylihuomenna|i\s+overmorgon|overmorgon|the\s+day\s+after\s+tomorrow|day\s+after\s+tomorrow)\b")
_TOMORROW = re.compile(r"\b(?:huomenna|i\s+morgon|imorgon|tomorrow|tmrw|tmw)\b")
_TODAY = re.compile(r"\b(?:tanaan|idag|today)\b")


def _extract_day(s: str, arr_day: int) -> Optional[int]:
    if _DAY_AFTER_TOMORROW.search(s):
        return arr_day + 2
    if _TOMORROW.search(s):
        return arr_day + 1
    if _TODAY.search(s):
        return arr_day
    for pat, wd in _WEEKDAYS:
        if pat.search(s):
            return arr_day + ((wd - arr_day - 2) % 7) + 2
    return None


def _to_min(h_str: str, m_str: Optional[str], ampm: Optional[str]) -> Optional[int]:
    h = int(h_str)
    m = int(m_str) if m_str else 0
    if ampm:
        ap = ampm.lower()
        if ap == "pm" and h < 12:
            h += 12
        elif ap == "am" and h == 12:
            h = 0
    if h > 24 or m > 59 or (h == 24 and m > 0):
        return None
    return h * HOUR + m


_RANGE_AMPM_RE = re.compile(
    r"\b(\d{1,2})(?:[.:](\d{2}))?\s*(am|pm)?\s*-\s*(\d{1,2})(?:[.:](\d{2}))?\s*(am|pm)?(?!\d|[.:]\d)\b"
)
_RANGE_FI_RE = re.compile(r"\b(\d{1,2}):sta\s+(\d{1,2}):[ea]+n\b")

_CLOCK_RE = re.compile(
    r"(?:klo|kl\.?|klockan|kello)\s*(\d{2})(\d{2})\b"
    r"|(?:klo|kl\.?|klockan|kello)\s*(\d{1,2})(?:[.:](\d{2}))?\s*(am|pm)?(?!\d|[.:]\d)\b"
    r"|\b(\d{1,2})[.:](\d{2})\s*(am|pm)?\b"
    r"|\b(\d{1,2})\s*(am|pm)\b"
    r"|\b(?:fore|till|senast|tidigast|ennen|asti|jalkeen|alkaen|by|before|until|after|from)\s+(\d{1,2})(?!\d|[.:]\d)\b"
    r"|\b(\d{1,2})\s+(?:mennessa|alkaen|jalkeen|asti|perilla|valmis|latest)\b"
)


def _extract_time(s: str) -> Optional[int]:
    for m in _CLOCK_RE.finditer(s):
        if m.group(1) is not None:
            res = _to_min(m.group(1), m.group(2), None)
        elif m.group(3) is not None:
            res = _to_min(m.group(3), m.group(4), m.group(5))
        elif m.group(6) is not None:
            res = _to_min(m.group(6), m.group(7), m.group(8))
        elif m.group(9) is not None:
            res = _to_min(m.group(9), None, m.group(10))
        elif m.group(11) is not None:
            res = _to_min(m.group(11), None, None)
        else:
            res = _to_min(m.group(12), None, None)
        if res is not None:
            return res
    m_bare = re.search(r"\b(\d{1,2})(?!\d|[.:]\d)\b", s)
    if m_bare:
        h = int(m_bare.group(1))
        if 6 <= h <= 23:
            return h * HOUR
    return None


def _extract_range(s: str) -> Optional[tuple[int, int]]:
    for m in _RANGE_AMPM_RE.finditer(s):
        o = _to_min(m.group(1), m.group(2), m.group(3))
        c = _to_min(m.group(4), m.group(5), m.group(6))
        if o is not None and c is not None and 5 * HOUR <= o < c <= 23 * HOUR:
            return o, c
    m2 = _RANGE_FI_RE.search(s)
    if m2:
        o, c = int(m2.group(1)) * HOUR, int(m2.group(2)) * HOUR
        if 5 * HOUR <= o < c <= 23 * HOUR:
            return o, c
    return None


class ParsedNote(NamedTuple):
    ready_at: Optional[int] = None
    released_at: Optional[int] = None
    pickup_opens: Optional[int] = None
    pickup_closes: Optional[int] = None
    delivery_opens: Optional[int] = None
    delivery_closes: Optional[int] = None
    note_deadline: Optional[int] = None
    manual: bool = False
    plates: bool = False
    summer_tyres: bool = False
    unsure: bool = False

    @property
    def has_info(self) -> bool:
        return any((
            self.ready_at is not None,
            self.released_at is not None,
            self.pickup_opens is not None,
            self.pickup_closes is not None,
            self.delivery_opens is not None,
            self.delivery_closes is not None,
            self.note_deadline is not None,
            self.manual,
            self.plates,
            self.summer_tyres,
        ))


_DENY_PAREN_RE = re.compile(r"\(\s*(?:not|inte|ei)\b[^)]*\)")
_DENY_TAIL_RE = re.compile(
    r",\s*(?:ei(?!\s*(?:kun\b|ennen\b|enaa\b|ketaan\b|automaat|manuaal|kilp|rekkar|talvirenk|erityis))"
    r"|inte(?!\s*(?:fore\b|klar\b|manuell))"
    r"|not(?!\s*(?:before\b|ready\b|a\s+manual\b)))\s+[^.!?;]+"
)
_MERGE_CORR_RE = re.compile(r"[.!?]+\s*(?=(?:korjaus|correction|rattelse)\b)")
_CORR_SPLIT_RE = re.compile(r"(?:,\s*)?\b(?:ei\s+kun|eikun|sorry,\s*i\s*mean|korjaus:|correction:|rattelse:)\s*")
_CALL_AHEAD_RE = re.compile(
    r"\b(?:soita|ilmoita|call|ring)\b[^.!?/]*?\b(?:ennen\s+(?:perilla\s+oloa|saapumista|noutoa|kuin\s+tulet)|before\s+(?:arrival|you\s+arrive|pickup)|innan(?:\s+hamtning)?)"
)
_PRIVATE_SLOT_RE = re.compile(r"\b(?:myyja|omistaja|seller|agaren)\s+(?:kotona|paikalla|home|hemma)\b")

_DELIV_CONTEXT_RE = re.compile(
    r"\b(?:toimitusosoite|toimitukset|toimitus|vastaanottava|vastaanotetaan|vastaanotto|kohde|kohteen|perilla|perille"
    r"|destination|receiving|deliver|delivery|arrive|arrival|mottagaren|mottagning|framme|leverans|leverera)\b"
)
_DEADLINE_RE = re.compile(
    r"\b(?:perilla|perille|toimitus|destination|arrive|arrival|deliver|framme)\b.*"
    r"\b(?:viim|viimeistaan|mennessa|by|latest|no\s+later\s+than|senast)\b"
    r"|\b(?:viim|viimeistaan|mennessa|by|latest|no\s+later\s+than|senast)\b.*"
    r"\b(?:perilla|perille|toimitus|destination|arrive|arrival|deliver|framme)\b"
    r"|\b(?:customer\s+picks\s+it\s+up|asiakas\s+noutaa)\b"
)
_RELEASE_RE = re.compile(
    r"\b(?:maksettu|maksun\s+jalkeen|ostaja\s+maksaa|maksu\s+nakyy|rahoitus\s+vahvistuu"
    r"|after\s+payment|buyer\s+pays|payment\s+clears|efter\s+betalning)\b"
)
_READY_RE = re.compile(
    r"\b(?:voi\s+noutaa|noudettavissa\s+aikaisintaan"
    r"|valmis|valmiina|valmistuu|huolto\s+kesken|odottaa\s+osia|pesu\s+kesken|saa\s+hakea\s+vasta"
    r"|ready\s+for\s+pickup|ready\b|not\s+ready|in\s+the\s+workshop|earliest\s+pickup"
    r"|kan\s+hamtas\s+tidigast|kan\s+hamtas\s+(?:i\s+morgon|imorgon|idag|pa\s+\w+|kl)|klar\s+forst|inte\s+klar\s+forran)\b"
)
_PICKUP_CLOSES_RE = re.compile(
    r"\b(?:nouto\s+ennen|haettava\s+ennen|pitaa\s+hakea\s+ennen|liike\s+(?:kiinni|sulkee|menee\s+kiinni)"
    r"|taalla\s+ei\s+ketaan|ei\s+enaa\s+luovutuksia|auki\s+vain"
    r"|collect\s+before|pick\s*up\s+(?:by|before|no\s+later\s+than)|we\s+close\s+at"
    r"|hamtas\s+fore|vi\s+stanger)\b"
)
_DELIV_CLOSES_RE = re.compile(
    r"\b(?:vastaanotetaan\s+.*?\s+asti|vastaanotto\s+.*?\s+asti|(?:vastaanottava\s+liike|toimitusosoite|kohde)\s+(?:sulkee|menee\s+kiinni|kiinni)"
    r"|perilla\s+ei\s+ketaan"
    r"|receiving\s+until|receiving\s+shop\s+closes|destination\s+closes|nobody\s+at\s+the\s+destination\s+after"
    r"|mottagning\s+till|mottagaren\s+stanger|ingen\s+hos\s+mottagaren\s+efter)\b"
)

_NOT_MANUAL_RE = re.compile(r"\b(?:not\s+(?:a\s+)?|no\s+|ei\s+|inte\s+)(?:manuaal\w*|kasivaiht\w*|manuell\w*|manual)\b")
_MANUAL_V2_RE = re.compile(r"\b(?:manuaal\w*|kasivaiht\w*|manuell\w*|manual|stick\s*shift|clutch|kytkin\w*)\b")
_PLATES_V2_RE = re.compile(
    r"\b(?:ei\s+kilp\w*|ilman\s+kilp\w*|kilveton|kilpia\s+ei|siirtokil[pv]\w*|koekil[pv]\w*|ei\s+rekkar\w*"
    r"|kilvet\s+(?:poistettu|puuttuu|irrotettu)|rekisterikilvet\s+(?:poistettu|puuttuu|irrotettu)|poistettu\s+rekisterista"
    r"|inga\s+skyltar|utan\s+skyltar|saknar\s+skyltar|provskylt\w*|avstalld|avregistrerad"
    r"|no\s+(?:license\s+|licence\s+|number\s+|registration\s+)?plates"
    r"|without\s+(?:license\s+|licence\s+|number\s+)?plates"
    r"|plates?\s+(?:are\s+)?(?:missing|removed)"
    r"|(?:needs?|bring)\s+(?:transfer\s+|trade\s+)?plates"
    r"|unregistered)\b"
)
_SUMMER_ON_RE = re.compile(
    r"\b(?:kesarenkaat\s+alla|viela\s+kesarenka\w*|ei\s+talvirenk\w*|talvirenkaita\s+ei\s+viela"
    r"|sommardack\s+pa|fortfarande\s+sommardack|inga\s+vinterdack"
    r"|summer\s+t[yi]res?\s+on|still\s+on\s+summer\s+t[yi]res?|no\s+winters?)\b"
)


def parse_note_v2(note: Optional[Note], arrived_at: int = 0) -> ParsedNote:
    if not note or not note.get("text"):
        return ParsedNote()
    raw = note["text"]
    norm = normalize_text(raw)
    norm = _DENY_PAREN_RE.sub(" ", norm)
    norm = _MERGE_CORR_RE.sub(", korjaus: ", norm)
    norm = _CALL_AHEAD_RE.sub(" ", norm)
    norm = _replace_word_hours(norm)

    norm_no_neg_man = _NOT_MANUAL_RE.sub(" ", norm)
    manual = bool(_MANUAL_V2_RE.search(norm_no_neg_man))
    plates = bool(_PLATES_V2_RE.search(norm))
    summer_tyres = bool(_SUMMER_ON_RE.search(norm))

    arr_day = arrived_at // DAY
    ready_at: Optional[int] = None
    released_at: Optional[int] = None
    pickup_opens: Optional[int] = None
    pickup_closes: Optional[int] = None
    delivery_opens: Optional[int] = None
    delivery_closes: Optional[int] = None
    note_deadline: Optional[int] = None
    unsure = False

    s_clean = re.sub(r"\b(viim|n|oik|kl|t|ma|ti|ke|to|pe|la|su)\.", r"\1", norm)
    clauses = re.split(r"\.(?!\d)\s*|[!?/\x0a]+", s_clean)

    for clause in clauses:
        c = clause.strip(" ,.")
        if not c:
            continue
        c = _DENY_TAIL_RE.sub("", c)

        if _PRIVATE_SLOT_RE.search(c):
            continue

        corr_parts = _CORR_SPLIT_RE.split(c, maxsplit=1)
        main_part = corr_parts[0]
        corr_part = corr_parts[1] if len(corr_parts) > 1 else None

        rng = _extract_range(main_part)
        if rng is not None:
            o, cl = rng
            if _DELIV_CONTEXT_RE.search(main_part):
                delivery_opens, delivery_closes = o, cl
            else:
                pickup_opens, pickup_closes = o, cl
            main_part_no_rng = _RANGE_AMPM_RE.sub(" ", main_part)
            main_part_no_rng = _RANGE_FI_RE.sub(" ", main_part_no_rng)
            if not (_DEADLINE_RE.search(main_part_no_rng) or _READY_RE.search(main_part_no_rng) or _RELEASE_RE.search(main_part_no_rng)):
                continue
            main_part = main_part_no_rng

        def resolve_dt(default_day: int) -> tuple[int, Optional[int]]:
            d1 = _extract_day(main_part, arr_day)
            t1 = _extract_time(main_part)
            if corr_part is not None:
                d2 = _extract_day(corr_part, arr_day)
                t2 = _extract_time(corr_part)
                if d2 is not None:
                    d1 = d2
                if t2 is not None:
                    t1 = t2
            return (d1 if d1 is not None else default_day), t1

        if _RELEASE_RE.search(main_part):
            d, t = resolve_dt(arr_day)
            if t is not None:
                released_at = d * DAY + t
            else:
                unsure = True
            continue

        if _DEADLINE_RE.search(main_part):
            d, t = resolve_dt(arr_day)
            if t is not None:
                note_deadline = d * DAY + t
            else:
                unsure = True
            continue

        if _DELIV_CLOSES_RE.search(main_part):
            _, t = resolve_dt(arr_day)
            if t is not None:
                delivery_closes = t
            else:
                unsure = True
            continue

        if _PICKUP_CLOSES_RE.search(main_part):
            _, t = resolve_dt(arr_day)
            if t is not None:
                pickup_closes = t
            else:
                unsure = True
            continue

        if _READY_RE.search(main_part):
            if re.search(r"\b(?:heti|waiting|right\s+away|now|pihalla|noudettavaksi|direkt|bilen\s+star\s+klar)\b", main_part) and _extract_time(main_part) is None:
                continue
            d, t = resolve_dt(arr_day)
            if t is not None:
                ready_at = d * DAY + t
            else:
                unsure = True
            continue

        harmless = re.sub(r"\b\d{4,6}\b", " ", main_part)
        harmless = re.sub(r"\b[24]\s*(?:rengasta|sarjaa|kesarengasta)\b", " ", harmless)
        harmless = re.sub(r"\b(?:10|15|20|30)\s*min\b", " ", harmless)
        harmless = re.sub(r"\b\d+\s*tkm\b", " ", harmless)
        harmless = re.sub(r"\b(?:ruudussa|bay|plats)\s*\d+\b", " ", harmless)
        if _extract_time(harmless) is not None or _extract_range(harmless) is not None:
            unsure = True

    return ParsedNote(
        ready_at=ready_at,
        released_at=released_at,
        pickup_opens=pickup_opens,
        pickup_closes=pickup_closes,
        delivery_opens=delivery_opens,
        delivery_closes=delivery_closes,
        note_deadline=note_deadline,
        manual=manual,
        plates=plates,
        summer_tyres=summer_tyres,
        unsure=unsure,
    )


def shift_business_days(deadline: int, extra_days: int) -> int:
    """When a car is ready `extra_days` later than the request says, its deadline moves by the same business days."""
    if extra_days <= 0:
        return deadline
    d = deadline // DAY
    tod = deadline % DAY
    for _ in range(extra_days):
        d += 1
        while d in (5, 6):
            d += 1
    d = min(d, 7)
    return d * DAY + tod


def window_from_note(
    note: Optional[Note],
    window: TimeWindow,
    stop: str,
    *,
    v2: bool = False,
    arrived_at: Optional[int] = None,
    private_address: bool = False,
    stated_hours: Optional[dict] = None,
) -> TimeWindow:
    """Narrows a stop's window by clock times in the note."""
    if not note:
        return window
    if v2:
        pn = parse_note_v2(note, arrived_at if arrived_at is not None else window["from"])
        start, end = window["from"], window["to"]
        if stop == "pickup":
            if not private_address:
                if pn.ready_at is not None:
                    start = max(start, pn.ready_at)
                if pn.released_at is not None:
                    start = max(start, pn.released_at)
                p_opens = pn.pickup_opens if (pn.pickup_opens is not None and (not stated_hours or pn.pickup_opens > stated_hours["opens"])) else None
                p_closes = pn.pickup_closes if (pn.pickup_closes is not None and (not stated_hours or pn.pickup_closes < stated_hours["closes"])) else None
                if p_opens is not None:
                    start = max(start, start // DAY * DAY + p_opens)
                if p_closes is not None:
                    if start % DAY > p_closes:
                        next_d = shift_business_days(start, 1) // DAY
                        open_m = pn.pickup_opens if pn.pickup_opens is not None else (stated_hours["opens"] if stated_hours else 8 * HOUR)
                        start = next_d * DAY + open_m
                    end_cand = min(end, start // DAY * DAY + p_closes)
                    if end_cand >= start:
                        end = end_cand
                end = max(end, start)
            return {"from": start, "to": end}
        if stop == "delivery":
            if not private_address:
                d_opens = pn.delivery_opens if (pn.delivery_opens is not None and (not stated_hours or pn.delivery_opens > stated_hours["opens"])) else None
                d_closes = pn.delivery_closes if (pn.delivery_closes is not None and (not stated_hours or pn.delivery_closes < stated_hours["closes"])) else None
                if d_opens is not None:
                    start = max(start, start // DAY * DAY + d_opens)
                if pn.note_deadline is not None:
                    end = min(end, pn.note_deadline)
                if d_closes is not None:
                    end = min(end, end // DAY * DAY + d_closes)
            return {"from": start, "to": end}
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


# --- flags (ours) ----------------------------------------------------------------------------------
MANUAL = re.compile(r"manuaali|käsivaiht|manuell|\bmanual\b|stick ?shift|\bclutch\b|kytkin", re.IGNORECASE)
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


def note_flags(note: Optional[Note], *, v2: bool = False) -> NoteFlags:
    if not note:
        return NoteFlags()
    if v2:
        pn = parse_note_v2(note, 0)
        return NoteFlags(manual=pn.manual, plates=pn.plates, summer_tyres=pn.summer_tyres)
    text = note["text"]
    return NoteFlags(manual=bool(MANUAL.search(text)), plates=bool(NO_PLATES.search(text)), summer_tyres=bool(SUMMER.search(text)))
