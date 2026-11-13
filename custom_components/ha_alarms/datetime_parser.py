"""Unified natural-language datetime parser for ha_alarms intent handlers.

Converts the raw string values of the {time} and {date} slots produced by HA's
sentence engine into a tz-aware Python datetime. This is the single parser used
by all intent handlers — there is no second inline parser in the handlers.

Languages: English (default) and German.  Every public function takes an
optional ``lang`` ("en" / "de", region suffixes such as "de-DE" are accepted;
anything unknown falls back to English).  The German forms are listed at the
end of this docstring.

Supported input forms (English):

  Absolute time:
    "7:30 AM", "7:30 PM", "7:30", "7 AM", "7am", "19:30"

  Relative time:
    "in 30 minutes", "in an hour", "in 2 hours", "in 90 minutes"
    These return a datetime offset from now; the date slot is ignored.

  Special words:
    "noon" (12:00), "midnight" (0:00)

  Bare hour without AM/PM:
    Raises ParseAmbiguousError with a speakable message so the intent handler
    can ask the user to clarify rather than silently guessing.

  Date:
    "today", "tomorrow"
    Weekday names ("monday" … "sunday") → next occurrence, never today.

Supported input forms (German, ``lang="de"``):

  Absolute time (24 h clock; hours 1-12 are taken at face value — say
  "19 Uhr" or "sieben Uhr abends" for the evening):
    "7 Uhr", "7:30", "7.30 Uhr", "7 Uhr 30", "19:45", "sieben Uhr dreißig",
    "sieben Uhr fünfundvierzig", "um acht"

  Colloquial clock:
    "halb acht" (7:30), "viertel nach sieben" (7:15), "viertel vor acht" (7:45),
    "viertel acht" (7:15), "dreiviertel acht" (7:45), "fünf nach sieben",
    "zehn vor acht", "fünf vor halb acht" (7:25), "fünf nach halb acht" (7:35)

  Day period words (disambiguate 12-hour values):
    morgens / früh / vormittags, mittags, nachmittags / abends, nachts

  Special words:
    "Mittag" (12:00), "Mitternacht" (0:00)

  Relative time:
    "in 30 Minuten", "in einer Stunde", "in zwei Stunden", "in anderthalb
    Stunden", "in einer halben Stunde", "in einer Viertelstunde",
    "in einer Stunde und 15 Minuten"

  Date:
    "heute", "morgen", "übermorgen", weekday names (Montag … Sonntag, with an
    optional "am"/"nächsten"/"kommenden"), optionally followed by a day period
    ("heute Abend", "morgen früh").  Weekdays → next occurrence, never today.

Public API:
    parse_datetime(time_text, date_text=None, now=None, lang="en") -> datetime
    parse_date(date_text, now=None, lang="en") -> date
    parse_minutes(text, lang="en") -> int | None
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timedelta
from typing import Optional

try:
    from homeassistant.util import dt as dt_util
    _HAS_HA = True
except ImportError:
    _HAS_HA = False


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class ParseError(Exception):
    """Raised when a time or date string cannot be parsed."""


class ParseAmbiguousError(ParseError):
    """Raised when a bare hour has no AM/PM indicator.

    str(exc) is a user-facing string suitable for TTS, e.g.
    "Did you mean 6 AM or 6 PM?"
    """


# ---------------------------------------------------------------------------
# Internal constants
# ---------------------------------------------------------------------------

_DAYS: dict[str, int] = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}

# Word → integer mapping used for both relative time and bare-hour parsing.
_WORD_TO_NUM: dict[str, int] = {
    "a": 1, "an": 1,
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40,
    "fifty": 50, "sixty": 60, "ninety": 90,
}

_WORD_NUM_PAT = "|".join(sorted(_WORD_TO_NUM, key=len, reverse=True))  # longest first

# "in 30 minutes", "in two hours", "30 minutes", "an hour", "two hours"
# "in" is optional — slot captures "30 minutes" when sentence has "remind me in {time}"
_RELATIVE_RE = re.compile(
    rf"\b(?:in\s+)?(?P<qty>{_WORD_NUM_PAT}|\d+)\s+(?P<unit>minutes?|hours?)\b",
    re.IGNORECASE,
)

# Matches "7", "7:30", "7 AM", "7:30 AM", "19:30", "7am", etc.
_TIME_RE = re.compile(
    r"^(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\s*(?P<ampm>am|pm)?\s*\.?$",
    re.IGNORECASE,
)

# Matches "Saturday at 10am", "monday 7:30 PM", etc. — day name embedded in
# the time slot because the sentence matched "{time}" without a {date} slot.
_DAY_EMBEDDED_RE = re.compile(
    r"^(?P<day>monday|tuesday|wednesday|thursday|friday|saturday|sunday)"
    r"\s+(?:at\s+)?(?P<time>.+)$",
    re.IGNORECASE,
)

# Normalisation patterns for faster-whisper STT variants.
# Applied in order before the absolute-time regex match.
_NORM_AMPM_DOTS = re.compile(                                    # a.m./p.m. → am/pm
    r"\b([ap])\s*\.\s*m\.{0,2}",
    re.IGNORECASE,
)
_NORM_DOT_SEP   = re.compile(r"^(\d{1,2})\.(\d{2})")            # 8.15 → 8:15
_NORM_SPACE_SEP = re.compile(r"^(\d{1,2})\s+(\d{2})(?=\s|$)")  # 8 15 → 8:15

# Word → integer for word-based time expressions (hours and minute-tens).
_WORD_HOUR_MAP: dict[str, int] = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12,
}
_WORD_MIN_TENS: dict[str, int] = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
}
_WORD_MIN_ONES: dict[str, int] = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19,
}

_WORD_HOUR_PAT = "|".join(sorted(_WORD_HOUR_MAP, key=len, reverse=True))
_WORD_MIN_TENS_PAT = "|".join(sorted(_WORD_MIN_TENS, key=len, reverse=True))
_WORD_MIN_ONES_PAT = "|".join(sorted(_WORD_MIN_ONES, key=len, reverse=True))

# Matches "eight thirty PM", "six forty-five am", "seven oh five AM"
_WORD_TIME_RE = re.compile(
    rf"^(?P<hour>{_WORD_HOUR_PAT})"
    rf"\s+"
    rf"(?P<minutes>oh\s+\d{{1,2}}|oh\s+(?:{_WORD_MIN_ONES_PAT})|"
    rf"(?:{_WORD_MIN_TENS_PAT})(?:\s+(?:{_WORD_MIN_ONES_PAT})|\s+\d{{1,2}}|-(?:{_WORD_MIN_ONES_PAT})|-\d{{1,2}})?|"
    rf"\d{{1,2}})"
    rf"(?:\s*(?P<ampm>am|pm|a\.m\.?\.?|p\.m\.?\.?))?$",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalise_word_time(s: str) -> str | None:
    """Normalise word-based time expressions like "eight thirty PM".

    Returns the normalised string (e.g. "8:30 PM") or None if no match.
    """
    m = _WORD_TIME_RE.match(s.strip())
    if not m:
        return None

    hour = _WORD_HOUR_MAP[m.group("hour").lower()]
    minutes_raw = m.group("minutes").strip().lower()
    ampm_raw = (m.group("ampm") or "").strip().lower()

    # Normalise ampm: "p.m." / "p.m" → "pm", "a.m." / "a.m" → "am"
    ampm = re.sub(r'\.', '', ampm_raw)  # strip all dots

    # Parse minutes portion
    if minutes_raw.startswith("oh"):
        # "oh five" → 5, "oh 5" → 5
        rest = minutes_raw[2:].strip().lstrip('-')
        try:
            minute = int(rest)
        except ValueError:
            minute = _WORD_MIN_ONES.get(rest, 0)
    else:
        # Try digit-only first
        try:
            minute = int(minutes_raw)
        except ValueError:
            # Word-based minutes: "thirty", "forty five", "forty-five"
            # Split on space or hyphen
            parts = re.split(r'[\s\-]+', minutes_raw)
            tens_word = parts[0]
            tens = _WORD_MIN_TENS.get(tens_word, 0)
            ones = 0
            if len(parts) > 1:
                ones_word = parts[1]
                try:
                    ones = int(ones_word)
                except ValueError:
                    ones = _WORD_MIN_ONES.get(ones_word, 0)
            minute = tens + ones

    result = f"{hour}:{minute:02d}"
    if ampm:
        result += f" {ampm}"
    return result


def _normalise_time_str(s: str) -> str:
    """Normalise faster-whisper STT time variants to standard H:MM am/pm form.

    Applied transformations (in order):
      0. Word-based time expressions: "eight thirty PM" → "8:30 PM"
      1. Spaced AM/PM letters: "7:30 a m" → "7:30 am", "7:30 p m" → "7:30 pm"
      2. Concatenated 3-digit time: "645 AM" → "6:45 AM"
      3. ``a.m.`` / ``p.m.``  →  ``am`` / ``pm``
         Must run before dot-separator step so the period in "p.m." is not
         mistaken for a decimal separator.
      4. Period-as-separator: ``8.15pm``  →  ``8:15pm``
         Only applied when a 1–2 digit hour is followed by exactly 2 digit
         minutes, guarding against unrelated decimal values.
      5. Space-separated digits: ``8 15 pm``  →  ``8:15 pm``
         Matches H MM at the start of the string, optionally followed by
         a space + am/pm suffix, so "8 15 pm" → "8:15 pm" but plain words
         like "in 30 minutes" are never reached (relative RE fires first).
    """
    # Step 0: word-based time expressions
    word_result = _normalise_word_time(s)
    if word_result is not None:
        s = word_result

    # Step 1: spaced AM/PM letters: "a m" → "am", "p m" → "pm"
    s = re.sub(r'\ba\s+m\b', 'am', s, flags=re.IGNORECASE)
    s = re.sub(r'\bp\s+m\b', 'pm', s, flags=re.IGNORECASE)

    # Step 2: concatenated 3-digit time: "645 AM" → "6:45 AM", "645am" → "6:45am"
    s = re.sub(r'^([1-9])(\d{2})(\s|(?=[a-zA-Z])|$)', r'\1:\2\3', s)

    # Steps 3-5: existing normalisers
    s = _NORM_AMPM_DOTS.sub(r"\1m", s)   # a.m. / p.m. → am / pm
    s = _NORM_DOT_SEP.sub(r"\1:\2", s)   # 8.15 → 8:15
    s = _NORM_SPACE_SEP.sub(r"\1:\2", s) # 8 15 → 8:15
    # Strip any trailing punctuation left behind by a.m.. → am. etc.
    return s.strip().rstrip('.')


def _current_now(now: Optional[datetime]) -> datetime:
    """Return the effective 'now', tz-aware in HA's local timezone."""
    if now is not None:
        return now
    if _HAS_HA:
        return dt_util.now()
    from datetime import timezone
    return datetime.now(timezone.utc).astimezone()


def _next_weekday(now: datetime, target_weekday: int) -> datetime:
    """Return the next occurrence of target_weekday, never today."""
    days_ahead = (target_weekday - now.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return now + timedelta(days=days_ahead)


# ---------------------------------------------------------------------------
# Language helpers
# ---------------------------------------------------------------------------

def _lang_code(lang: Optional[str]) -> str:
    """Return "de" or "en" for any language tag (unknown → "en")."""
    if not lang:
        return "en"
    base = str(lang).replace("_", "-").split("-")[0].strip().lower()
    return base if base in ("en", "de") else "en"


# ---------------------------------------------------------------------------
# German
# ---------------------------------------------------------------------------

_DE_UNITS: dict[str, int] = {
    "null": 0, "ein": 1, "eins": 1, "eine": 1, "einen": 1, "einer": 1,
    "zwei": 2, "zwo": 2, "drei": 3, "vier": 4, "funf": 5, "sechs": 6,
    "sieben": 7, "acht": 8, "neun": 9, "zehn": 10, "elf": 11, "zwolf": 12,
    "dreizehn": 13, "vierzehn": 14, "funfzehn": 15, "sechzehn": 16,
    "siebzehn": 17, "achtzehn": 18, "neunzehn": 19,
}
_DE_TENS: dict[str, int] = {
    "zwanzig": 20, "dreissig": 30, "vierzig": 40, "funfzig": 50,
    "sechzig": 60, "siebzig": 70, "achtzig": 80, "neunzig": 90,
}

_DE_DAYS: dict[str, int] = {
    "montag": 0, "dienstag": 1, "mittwoch": 2, "donnerstag": 3,
    "freitag": 4, "samstag": 5, "sonnabend": 5, "sonntag": 6,
}
_DE_DATE_WORDS = "heute|morgen|ubermorgen|" + "|".join(_DE_DAYS)
_DE_DATE_FILLERS = {"am", "fur", "den", "dem", "diesen", "nachsten", "kommenden", "um"}

# Day-period words → canonical period.  A bare "morgen" is the date
# "tomorrow", so only "morgens" / "am morgen" count as a period.
_DE_PERIODS: dict[str, str] = {
    "morgens": "morning", "fruh": "morning", "vormittags": "morning",
    "vormittag": "morning",
    "mittags": "noon", "mittag": "noon",
    "nachmittags": "afternoon", "nachmittag": "afternoon",
    "abends": "evening", "abend": "evening",
    "nachts": "night", "nacht": "night",
}
_DE_PERIOD_WORDS = "|".join(sorted(_DE_PERIODS, key=len, reverse=True))
_DE_PERIOD_RE = re.compile(
    rf"\b(?:(?:am|in der|in)\s+)?(?P<p>{_DE_PERIOD_WORDS}|(?<=am\s)morgen)\b"
)

# "morgen früh um 7", "am Montag 7:30", "heute Abend um acht", "morgen Mittag"
_DE_DATE_PREFIX_RE = re.compile(
    rf"^(?P<date>(?:(?:am|fur|den|diesen|nachsten|kommenden)\s+)*"
    rf"(?:{_DE_DATE_WORDS})(?:\s+(?:{_DE_PERIOD_WORDS}))?)"
    rf"(?:\s+(?:(?:um|gegen)\s+)?(?P<time>.+))?$"
)


def _de_fold(text: str) -> str:
    """Lower-case, strip umlauts/ß and collapse whitespace.

    "Fünf nach Zwölf" → "funf nach zwolf", "dreißig" → "dreissig".  STT output
    sometimes spells umlauts out ("fuenf"); those variants are folded too.
    """
    s = text.lower().replace("ß", "ss")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    for src, dst in (("fuenf", "funf"), ("zwoelf", "zwolf"),
                     ("uebermorgen", "ubermorgen"), ("frueh", "fruh"),
                     ("naechsten", "nachsten")):
        s = s.replace(src, dst)
    return re.sub(r"\s+", " ", s).strip(" .,!?")


def _de_num(token: str) -> Optional[int]:
    """0–99 as digits or German number word ("fünfundvierzig"); else None."""
    token = token.strip()
    if token.isdigit():
        return int(token)
    if token in _DE_UNITS:
        return _DE_UNITS[token]
    if token in _DE_TENS:
        return _DE_TENS[token]
    # "einundzwanzig" … "neunundneunzig"
    idx = token.find("und")
    while idx != -1:
        ones, tens = token[:idx], token[idx + 3:]
        if ones in _DE_UNITS and 1 <= _DE_UNITS[ones] <= 9 and tens in _DE_TENS:
            return _DE_TENS[tens] + _DE_UNITS[ones]
        idx = token.find("und", idx + 1)
    return None


def _de_extract_period(text: str) -> tuple[str, Optional[str]]:
    """Remove day-period words from *text*; return (remaining, period|None)."""
    found: list[str] = []

    def _sub(m: re.Match) -> str:
        p = m.group("p")
        found.append(_DE_PERIODS.get(p, "morning"))   # "morgen" after "am" → morning
        return " "

    out = _DE_PERIOD_RE.sub(_sub, text)
    return re.sub(r"\s+", " ", out).strip(), (found[0] if found else None)


def _de_apply_period(hour: int, minute: int, period: Optional[str]) -> tuple[int, int]:
    """Resolve a 1–12 hour with a day-period word to the 24 h clock."""
    if period is None or hour > 12:
        return hour, minute
    if period == "noon":
        if hour == 0:
            hour = 12
        elif 1 <= hour <= 4:
            hour += 12
    elif period in ("afternoon", "evening"):
        if hour == 0:
            hour = 12
        elif 1 <= hour <= 11:
            hour += 12
    elif period == "night":
        if hour == 12:
            hour = 0
        elif 6 <= hour <= 11:
            hour += 12
    # "morning": unchanged
    return hour, minute


def _parse_clock_de(txt: str) -> tuple[int, int]:
    """Parse an already folded German clock expression into (hour, minute).

    Raises ParseError if it cannot be understood.  Hours are returned as
    spoken (0–24 → 0–23); day periods are applied by the caller.
    """
    original = txt
    txt = re.sub(r"\b(?:genau|punkt|ziemlich|ungefahr|ca|circa|etwa|bitte|kurz)\b", " ", txt)
    txt = re.sub(r"^\s*(?:um|gegen)\s+", "", txt)
    txt = txt.replace("uhr", " ")
    txt = re.sub(r"\bdrei\s+viertel\b", "dreiviertel", txt)
    txt = re.sub(r"\s+", " ", txt).strip(" .,")
    if not txt:
        raise ParseError(f"Cannot parse time: {original!r}")

    def _finish(h: int, m: int) -> tuple[int, int]:
        if h == 24 and m == 0:
            h = 0
        if not (0 <= h <= 23 and 0 <= m <= 59):
            raise ParseError(f"Time out of range: {original!r}")
        return h, m

    def _hour_token(tok: str) -> int:
        n = _de_num(tok)
        if n is None or not (0 <= n <= 24):
            raise ParseError(f"Cannot parse time: {original!r}")
        return n

    def _from_total(base_hour: int, delta: int) -> tuple[int, int]:
        """base_hour is the spoken hour; delta is minutes relative to it.

        "halb eins" is 12:30 in 12 h speech, not 0:30, so an hour of 1 that
        goes below the hour is shown as 12:xx.
        """
        total = base_hour * 60 + delta
        if base_hour == 1 and delta < 0:
            total += 12 * 60
        total %= 24 * 60
        return divmod(total, 60)

    m = re.fullmatch(r"(\d{1,2})[:.](\d{2})", txt)
    if m:
        return _finish(int(m.group(1)), int(m.group(2)))
    m = re.fullmatch(r"(\d{1,2}) (\d{1,2})", txt)
    if m:
        return _finish(int(m.group(1)), int(m.group(2)))
    m = re.fullmatch(r"\d{1,2}", txt)
    if m:
        return _finish(int(txt), 0)

    toks = txt.split(" ")

    # halb acht → 7:30
    if len(toks) == 2 and toks[0] == "halb":
        return _finish(*_from_total(_hour_token(toks[1]), -30))

    # dreiviertel acht → 7:45, viertel acht → 7:15
    if len(toks) == 2 and toks[0] == "dreiviertel":
        return _finish(*_from_total(_hour_token(toks[1]), -15))
    if len(toks) == 2 and toks[0] == "viertel":
        return _finish(*_from_total(_hour_token(toks[1]), -45))

    # viertel nach/vor X, N nach/vor X, N nach/vor halb X
    m = re.fullmatch(r"(?P<n>.+?) (?P<dir>nach|vor) (?:(?P<half>halb) )?(?P<h>\S+)", txt)
    if m:
        n_txt = m.group("n")
        if n_txt == "viertel":
            n = 15
        elif n_txt == "dreiviertel":
            n = 45
        else:
            n = _de_num(n_txt)
        if n is None or not (0 < n < 60):
            raise ParseError(f"Cannot parse time: {original!r}")
        offset = -30 if m.group("half") else 0
        delta = offset + (n if m.group("dir") == "nach" else -n)
        return _finish(*_from_total(_hour_token(m.group("h")), delta))

    # "sieben dreissig", "sieben null funf", "sieben" (hour [+ minutes])
    hour = _hour_token(toks[0])
    rest = toks[1:]
    if not rest:
        return _finish(hour, 0)
    if rest[0] == "null" and len(rest) == 2:
        minute = _de_num(rest[1])
    elif len(rest) == 1:
        minute = _de_num(rest[0])
    else:
        minute = None
    if minute is None:
        raise ParseError(f"Cannot parse time: {original!r}")
    return _finish(hour, minute)


def _parse_relative_de(txt: str) -> Optional[timedelta]:
    """Parse "in 30 Minuten", "in einer halben Stunde" …; None if not relative."""
    if not re.search(r"stunde|minute|\bstd\b|\bmin\b", txt):
        return None
    t = re.sub(r"^in\s+", "", txt)
    minutes = 0
    matched = False

    def _take(pattern: str, value) -> None:
        nonlocal t

        def _sub(m: re.Match) -> str:
            nonlocal minutes, matched
            matched = True
            minutes += value(m) if callable(value) else value
            return " "

        t = re.sub(pattern, _sub, t)

    art = r"(?:(?:eine|einer|ein)\s+)?"
    _take(r"\banderthalb\s+stunden?\b", 90)
    _take(r"\b(\w+?)einhalb\s+stunden?\b",
          lambda m: (_de_num(m.group(1)) or 0) * 60 + 30)
    _take(rf"{art}\bdreiviertel\s*stunden?\b", 45)
    _take(rf"{art}\bviertel\s*stunden?\b", 15)
    _take(rf"{art}\bhalben?\s+stunden?\b", 30)
    _take(rf"{art}\bhalbe\s+stunden?\b", 30)

    def _pair(m: re.Match) -> int:
        n = _de_num(m.group("q"))
        if n is None:
            raise ParseError(f"Cannot parse time: {txt!r}")
        return n * 60 if m.group("u").startswith(("stunde", "std")) else n

    _take(r"\b(?P<q>\d+|\w+?)\s*(?P<u>stunden?|std\.?|minuten?|min\.?)(?!\w)", _pair)

    if not matched or minutes <= 0:
        return None
    return timedelta(minutes=minutes)


def _parse_date_de(date_text: str, now: datetime) -> tuple:
    """Return (date, period|None) for a German date phrase."""
    txt = _de_fold(date_text)
    # "morgen" is a date here, not a day period, so only strip unambiguous
    # period words and keep the first date token.
    period = None
    words = []
    for tok in txt.split(" "):
        if tok in _DE_DATE_FILLERS:
            continue
        if tok in _DE_PERIODS and tok not in ("morgen",):
            period = period or _DE_PERIODS[tok]
            continue
        words.append(tok)
    if len(words) != 1:
        raise ParseError(f"Cannot parse date: {date_text!r}")
    word = words[0]
    if word == "heute":
        return now.date(), period
    if word == "morgen":
        return (now + timedelta(days=1)).date(), period
    if word == "ubermorgen":
        return (now + timedelta(days=2)).date(), period
    if word in _DE_DAYS:
        return _next_weekday(now, _DE_DAYS[word]).date(), period
    raise ParseError(f"Cannot parse date: {date_text!r}")


def _parse_datetime_de(time_text: str, date_text: Optional[str], now: datetime) -> datetime:
    """German counterpart of parse_datetime (see module docstring)."""
    txt = _de_fold(time_text)

    # Relative time ("in 30 Minuten") — date slot is ignored.
    delta = _parse_relative_de(txt)
    if delta is not None:
        return now + delta

    # Date embedded in the time slot ("morgen um 7 Uhr", "am Montag 7:30").
    if date_text is None:
        dm = _DE_DATE_PREFIX_RE.match(txt)
        if dm:
            date_text = dm.group("date")
            txt = dm.group("time") or ""
            delta = _parse_relative_de(txt)
            if delta is not None:
                return now + delta

    txt, period = _de_extract_period(txt)
    if period is None and date_text is not None:
        # Period attached to the date ("heute Abend um 8", "morgen Mittag").
        period = _parse_date_de(date_text, now)[1]

    if txt == "mitternacht":
        hour, minute = 0, 0
    elif not txt and period == "noon":
        hour, minute = 12, 0
    elif not txt:
        # "morgen" with a day period only ("heute Abend") or nothing usable.
        raise ParseError(f"Cannot parse time: {time_text!r}")
    else:
        hour, minute = _parse_clock_de(txt)
        hour, minute = _de_apply_period(hour, minute, period)

    if date_text is not None:
        target, _ = _parse_date_de(date_text, now)
        return now.replace(
            year=target.year, month=target.month, day=target.day,
            hour=hour, minute=minute, second=0, microsecond=0,
        )

    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(days=1)
    return candidate


def parse_minutes(text: Optional[str], lang: Optional[str] = None) -> Optional[int]:
    """Parse a spoken minute count ("5", "five", "fünf", "zehn Minuten").

    Returns None if *text* is empty or not a number.
    """
    if not text:
        return None
    lang = _lang_code(lang)
    if lang == "de":
        tok = _de_fold(text).split(" ")[0]
        return _de_num(tok)
    tok = text.strip().lower().split(" ")[0].rstrip(".")
    if tok.isdigit():
        return int(tok)
    return _WORD_TO_NUM.get(tok)



# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_datetime(
    time_text: str,
    date_text: Optional[str] = None,
    now: Optional[datetime] = None,
    lang: Optional[str] = None,
) -> datetime:
    """Parse a spoken time and optional spoken date into a tz-aware datetime.

    Parameters
    ----------
    time_text:
        Spoken time string: "7:30 AM", "in 30 minutes", "noon", etc.
    date_text:
        Optional spoken date string: "today", "tomorrow", "monday", etc.
        Ignored for relative time expressions.
        When None with an absolute time, the nearest future occurrence is used
        (today if the time is still in the future, otherwise tomorrow).
    now:
        Override the current time. Accepts any tz-aware datetime. Intended for
        unit tests.
    lang:
        "en" (default) or "de".  Selects the language of ``time_text`` and
        ``date_text``.

    Returns
    -------
    datetime
        Tz-aware datetime in HA's local timezone (or the system local timezone
        when running outside of HA).

    Raises
    ------
    ParseAmbiguousError
        For bare hours without AM/PM (e.g. "6"). The exception message is
        suitable for TTS: "Did you mean 6 AM or 6 PM?"
    ParseError
        For any other unparseable input.
    """
    _now = _current_now(now)
    time_text = time_text.strip()

    if _lang_code(lang) == "de":
        return _parse_datetime_de(time_text, date_text, _now)

    # -----------------------------------------------------------------------
    # Relative time — must be checked before absolute so "in an hour" doesn't
    # fall through to the absolute parser.
    # -----------------------------------------------------------------------
    m = _RELATIVE_RE.search(time_text)
    if m:
        qty_raw = m.group("qty").lower()
        qty = _WORD_TO_NUM.get(qty_raw) or int(qty_raw)
        unit = m.group("unit").lower()
        delta = timedelta(hours=qty) if unit.startswith("hour") else timedelta(minutes=qty)
        return _now + delta

    # -----------------------------------------------------------------------
    # Embedded day name: "Saturday at 10am", "monday 7:30 PM"
    # Occurs when the sentence matched a single {time} wildcard and the user
    # said "{day} at {time}".  Extract the day into date_text and recurse.
    # -----------------------------------------------------------------------
    if date_text is None:
        dm = _DAY_EMBEDDED_RE.match(time_text)
        if dm:
            return parse_datetime(
                dm.group("time").strip(),
                dm.group("day"),
                now=now,
            )

    # -----------------------------------------------------------------------
    # Word-number bare-hour: "nine" → "9", "seven" → "7"
    # Normalise before the special-word check so bare word hours reach the
    # ambiguity check ("Did you mean 9 AM or 9 PM?") instead of ParseError.
    # -----------------------------------------------------------------------
    _lower_check = time_text.lower().strip()
    if _lower_check in _WORD_TO_NUM and 1 <= _WORD_TO_NUM[_lower_check] <= 12:
        time_text = str(_WORD_TO_NUM[_lower_check])

    # -----------------------------------------------------------------------
    # Pre-normalisation ambiguity checks for spoken 12-hour forms.
    # These forms are inherently 12-hour and ambiguous without AM/PM.
    # -----------------------------------------------------------------------

    # Concatenated 3-digit: "645" (no AM/PM) — ambiguous spoken hour.
    _stripped = time_text.strip()
    if re.match(r'^[1-9]\d{2}$', _stripped):
        _h = int(_stripped[0])
        raise ParseAmbiguousError(f"Did you mean {_h} AM or {_h} PM?")

    # Word-based time without AM/PM: "nine thirty" — ambiguous.
    _wt_check = _WORD_TIME_RE.match(_stripped)
    if _wt_check and not (_wt_check.group("ampm") or "").strip():
        _wh = _WORD_HOUR_MAP[_wt_check.group("hour").lower()]
        raise ParseAmbiguousError(f"Did you mean {_wh} AM or {_wh} PM?")

    # -----------------------------------------------------------------------
    # STT normalisation — convert faster-whisper variants to standard form.
    # "8.15pm" → "8:15pm", "8 15 p.m." → "8:15 pm", etc.
    # Run after relative/word-number checks so those paths are unaffected.
    # -----------------------------------------------------------------------
    time_text = _normalise_time_str(time_text)

    # -----------------------------------------------------------------------
    # Special words
    # -----------------------------------------------------------------------
    lower = time_text.lower()
    if lower == "noon":
        hour, minute = 12, 0
    elif lower == "midnight":
        hour, minute = 0, 0
    else:
        # -------------------------------------------------------------------
        # Absolute time
        # -------------------------------------------------------------------
        tm = _TIME_RE.match(time_text)
        if not tm:
            raise ParseError(f"Cannot parse time: {time_text!r}")

        hour = int(tm.group("hour"))
        minute = int(tm.group("minute") or 0)
        ampm = (tm.group("ampm") or "").lower()
        has_minutes = tm.group("minute") is not None

        if ampm == "am":
            if hour == 12:
                hour = 0  # 12:xx AM → 00:xx
        elif ampm == "pm":
            if hour != 12:
                hour += 12  # 1–11 PM → 13–23
        else:
            # No AM/PM indicator.
            if not has_minutes and 1 <= hour <= 12:
                # Bare hour, genuinely ambiguous.
                raise ParseAmbiguousError(f"Did you mean {hour} AM or {hour} PM?")
            # HH:MM without AM/PM → treat as 24-hour clock.
            # Hours 0 and 13–23 are unambiguous; hours 1–12 with minutes
            # are interpreted at face value (e.g. "7:30" → 07:30).

        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ParseError(f"Time out of range: {time_text!r}")

    # -----------------------------------------------------------------------
    # Date
    # -----------------------------------------------------------------------
    if date_text is not None:
        target = _parse_date(date_text.strip(), _now)
        return _now.replace(
            year=target.year,
            month=target.month,
            day=target.day,
            hour=hour,
            minute=minute,
            second=0,
            microsecond=0,
        )

    # No explicit date: use today unless the time has already passed.
    candidate = _now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= _now:
        candidate += timedelta(days=1)
    return candidate


def _parse_date(date_text: str, now: datetime):
    """Return a date for a spoken date string (internal helper)."""
    lower = date_text.lower()

    if lower == "today":
        return now.date()
    if lower == "tomorrow":
        return (now + timedelta(days=1)).date()
    if lower in _DAYS:
        return _next_weekday(now, _DAYS[lower]).date()

    raise ParseError(f"Cannot parse date: {date_text!r}")


def parse_date(date_text: str, now: Optional[datetime] = None, lang: Optional[str] = None):
    """Parse a spoken date string into a date object.

    Accepts: "today", "tomorrow", weekday names ("monday" … "sunday");
    in German "heute", "morgen", "übermorgen" and the weekday names.
    Raises ParseError for unrecognised input.
    """
    if _lang_code(lang) == "de":
        return _parse_date_de(date_text.strip(), _current_now(now))[0]
    return _parse_date(date_text.strip(), _current_now(now))


# ---------------------------------------------------------------------------
# Standalone tests (no HA required)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from datetime import timezone

    # Fixed reference point: Wednesday 2026-03-25 08:00:00 UTC+0
    # (chosen so "today" and "tomorrow" have predictable values and
    # relative times don't straddle midnight)
    _REF = datetime(2026, 3, 25, 8, 0, 0, tzinfo=timezone.utc)

    passed = 0
    failed = 0

    def check(label: str, got, expected):
        global passed, failed
        if got == expected:
            print(f"  PASS  {label}")
            passed += 1
        else:
            print(f"  FAIL  {label}")
            print(f"        got:      {got}")
            print(f"        expected: {expected}")
            failed += 1

    def check_raises(label: str, exc_type, fn):
        global passed, failed
        try:
            fn()
            print(f"  FAIL  {label}  (no exception raised)")
            failed += 1
        except exc_type as e:
            print(f"  PASS  {label}  → {e}")
            passed += 1
        except Exception as e:
            print(f"  FAIL  {label}  (wrong exception: {type(e).__name__}: {e})")
            failed += 1

    def dt(y, mo, d, h, mi):
        return datetime(y, mo, d, h, mi, 0, tzinfo=timezone.utc)

    print("=== Absolute time ===")
    check("7:30 AM",  parse_datetime("7:30 AM",  now=_REF), dt(2026, 3, 26,  7, 30))  # 07:30 already past at 08:00
    check("7:30 PM",  parse_datetime("7:30 PM",  now=_REF), dt(2026, 3, 25, 19, 30))
    check("7:30",     parse_datetime("7:30",     now=_REF), dt(2026, 3, 26,  7, 30))  # 07:30 already past at 08:00
    check("7 AM",     parse_datetime("7 AM",     now=_REF), dt(2026, 3, 26,  7,  0))  # 07:00 already passed at ref 08:00
    check("7am",      parse_datetime("7am",      now=_REF), dt(2026, 3, 26,  7,  0))
    check("19:30",    parse_datetime("19:30",    now=_REF), dt(2026, 3, 25, 19, 30))
    check("12:00 AM", parse_datetime("12:00 AM", now=_REF), dt(2026, 3, 26,  0,  0))  # midnight, already past
    check("12:00 PM", parse_datetime("12:00 PM", now=_REF), dt(2026, 3, 25, 12,  0))
    check("9:00 AM",  parse_datetime("9:00 AM",  now=_REF), dt(2026, 3, 25,  9,  0))

    print("\n=== Special words ===")
    check("noon",     parse_datetime("noon",     now=_REF), dt(2026, 3, 25, 12,  0))
    check("midnight", parse_datetime("midnight", now=_REF), dt(2026, 3, 26,  0,  0))  # already past at 08:00

    print("\n=== Relative time ===")
    check("in 30 minutes", parse_datetime("in 30 minutes", now=_REF), _REF + timedelta(minutes=30))
    check("in an hour",    parse_datetime("in an hour",    now=_REF), _REF + timedelta(hours=1))
    check("in a hour",     parse_datetime("in a hour",     now=_REF), _REF + timedelta(hours=1))
    check("in 2 hours",    parse_datetime("in 2 hours",    now=_REF), _REF + timedelta(hours=2))
    check("in 90 minutes", parse_datetime("in 90 minutes", now=_REF), _REF + timedelta(minutes=90))

    print("\n=== Date: explicit ===")
    check("time + today",    parse_datetime("9:00 AM", "today",    now=_REF), dt(2026, 3, 25,  9,  0))
    check("time + tomorrow", parse_datetime("9:00 AM", "tomorrow", now=_REF), dt(2026, 3, 26,  9,  0))
    # Ref is Wednesday (weekday=2). Next Monday = 2026-03-30.
    check("time + monday",   parse_datetime("9:00 AM", "monday",   now=_REF), dt(2026, 3, 30,  9,  0))
    # Next Wednesday = 2026-04-01 (skips today).
    check("time + wednesday",parse_datetime("9:00 AM", "wednesday",now=_REF), dt(2026, 4,  1,  9,  0))
    # Next Saturday = 2026-03-28.
    check("time + saturday", parse_datetime("9:00 AM", "saturday", now=_REF), dt(2026, 3, 28,  9,  0))

    print("\n=== Ambiguous bare hour ===")
    check_raises("bare 6",  ParseAmbiguousError, lambda: parse_datetime("6",  now=_REF))
    check_raises("bare 12", ParseAmbiguousError, lambda: parse_datetime("12", now=_REF))
    check_raises("bare 1",  ParseAmbiguousError, lambda: parse_datetime("1",  now=_REF))

    print("\n=== ParseError ===")
    check_raises("garbage time", ParseError, lambda: parse_datetime("purple monkey", now=_REF))
    check_raises("bad date",     ParseError, lambda: parse_datetime("9:00 AM", "next week", now=_REF))

    print(f"\n{'='*40}")
    print(f"Results: {passed} passed, {failed} failed")
