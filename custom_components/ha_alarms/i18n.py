"""Spoken-text localisation for ha_alarms (English and German).

No Home Assistant dependency, so it can be unit-tested stand-alone.

Everything the integration *says* — intent responses, the TTS announcement
when an alarm rings, the "when" text on the dashboard sensors — comes from
here.  Adding a language means adding one entry to ``_STRINGS`` and handling
it in the few helper functions below.

Language codes are normalised with :func:`normalize_lang`: ``"de-DE"`` and
``"DE"`` both become ``"de"``; anything unsupported falls back to ``"en"``.
"""

from __future__ import annotations

from datetime import datetime, timedelta

DEFAULT_LANG = "en"
SUPPORTED_LANGS = ("en", "de")


def normalize_lang(lang: str | None) -> str:
    """Return a supported language code for *lang* (fallback: English)."""
    if not lang:
        return DEFAULT_LANG
    base = str(lang).replace("_", "-").split("-")[0].strip().lower()
    return base if base in SUPPORTED_LANGS else DEFAULT_LANG


# ---------------------------------------------------------------------------
# Static strings
# ---------------------------------------------------------------------------

_STRINGS: dict[str, dict[str, str]] = {
    "en": {
        # default labels (used when the user does not name an alarm)
        "default_alarm_label": "Alarm",
        "default_reminder_label": "Reminder",
        # nouns
        "alarm": "alarm",
        "reminder": "reminder",
        "alarms": "alarms",
        "reminders": "reminders",
        # set
        "alarm_set": "Alarm set for {when}.",
        "alarm_set_daily": "Daily alarm set for {when}.",
        "alarm_set_weekdays": "Weekdays alarm set for {when}.",
        "alarm_set_weekends": "Weekends alarm set for {when}.",
        "reminder_set": "Reminder set for {when}: {label}.",
        "ask_reminder_label": "Sorry, what should I remind you about?",
        "time_missing": "Sorry, I didn't catch the time.",
        "time_unparsed": "Sorry, I didn't understand that time.",
        # stop / cancel
        "alarm_stopped": "Alarm stopped.",
        "reminder_stopped": "Reminder stopped.",
        "no_alarm_found": "No alarm found.",
        "no_reminder_found": "No reminder found.",
        "item_cancelled": "{label} for {when} cancelled.",
        "reminder_cancelled": "Reminder '{label}' cancelled.",
        "no_alarm_matching": "No alarm matching '{query}' found.",
        "no_reminder_matching": "No reminder matching '{query}' found.",
        "none_to_cancel_alarms": "No alarms to cancel.",
        "none_to_cancel_reminders": "No reminders to cancel.",
        "all_cancelled_alarms": "All alarms cancelled.",
        "all_cancelled_reminders": "All reminders cancelled.",
        # snooze
        "snoozed": "Snoozed for {minutes} minutes.",
        "nothing_ringing_alarm": "There's no alarm currently ringing.",
        "nothing_ringing_reminder": "There's no reminder currently ringing.",
        # ring-time announcements
        "ring_reminder": "Reminder: {label}.",
        "ring_reminder_nolabel": "Reminder.",
        "ring_alarm_time": "Alarm: {label}. It's {time}.",
        "ring_alarm_time_nolabel": "Alarm. It's {time}.",
        "ring_alarm": "Alarm: {label}.",
        "ring_alarm_nolabel": "Alarm.",
        # sensor "when" text
        "when_missed": "missed ({time})",
        "when_seconds": "in {n}s",
        "when_minutes": "in {n}m",
        "when_hm": "in {h}h {m}m ({base})",
        "when_today": "today at {time}",
        "when_tomorrow": "tomorrow at {time}",
        "when_weekday": "{weekday} at {time}",
        "when_unknown": "unknown",
        # services (errors)
        "service_parse_error": "Could not parse time: {detail}",
    },
    "de": {
        "default_alarm_label": "Wecker",
        "default_reminder_label": "Erinnerung",
        "alarm": "Wecker",
        "reminder": "Erinnerung",
        "alarms": "Wecker",
        "reminders": "Erinnerungen",
        "alarm_set": "Wecker gestellt: {when}.",
        "alarm_set_daily": "Täglicher Wecker gestellt: {when}.",
        "alarm_set_weekdays": "Wecker für Werktage gestellt: {when}.",
        "alarm_set_weekends": "Wecker fürs Wochenende gestellt: {when}.",
        "reminder_set": "Erinnerung gestellt: {when}, {label}.",
        "ask_reminder_label": "Entschuldigung, woran soll ich dich erinnern?",
        "time_missing": "Entschuldigung, die Uhrzeit habe ich nicht verstanden.",
        "time_unparsed": "Entschuldigung, diese Uhrzeit habe ich nicht verstanden.",
        "alarm_stopped": "Wecker gestoppt.",
        "reminder_stopped": "Erinnerung gestoppt.",
        "no_alarm_found": "Ich habe keinen Wecker gefunden.",
        "no_reminder_found": "Ich habe keine Erinnerung gefunden.",
        "item_cancelled": "{label}, {when}, gelöscht.",
        "reminder_cancelled": "Erinnerung {label} gelöscht.",
        "no_alarm_matching": "Ich habe keinen Wecker zu {query} gefunden.",
        "no_reminder_matching": "Ich habe keine Erinnerung zu {query} gefunden.",
        "none_to_cancel_alarms": "Es gibt keine Wecker zu löschen.",
        "none_to_cancel_reminders": "Es gibt keine Erinnerungen zu löschen.",
        "all_cancelled_alarms": "Alle Wecker gelöscht.",
        "all_cancelled_reminders": "Alle Erinnerungen gelöscht.",
        "snoozed": "Noch {minutes} Minuten.",
        "nothing_ringing_alarm": "Es klingelt gerade kein Wecker.",
        "nothing_ringing_reminder": "Es läuft gerade keine Erinnerung.",
        "ring_reminder": "Erinnerung: {label}.",
        "ring_reminder_nolabel": "Erinnerung.",
        "ring_alarm_time": "Wecker: {label}. Es ist {time}.",
        "ring_alarm_time_nolabel": "Wecker. Es ist {time}.",
        "ring_alarm": "Wecker: {label}.",
        "ring_alarm_nolabel": "Wecker.",
        "when_missed": "verpasst ({time})",
        "when_seconds": "in {n} s",
        "when_minutes": "in {n} Min.",
        "when_hm": "in {h} Std. {m} Min. ({base})",
        "when_today": "heute um {time}",
        "when_tomorrow": "morgen um {time}",
        "when_weekday": "{weekday} um {time}",
        "when_unknown": "unbekannt",
        "service_parse_error": "Uhrzeit konnte nicht gelesen werden: {detail}",
    },
}

_WEEKDAYS: dict[str, tuple[str, ...]] = {
    "en": ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"),
    "de": ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"),
}


def t(lang: str | None, key: str, **kwargs: object) -> str:
    """Return the string *key* in *lang*, formatted with *kwargs*."""
    lang = normalize_lang(lang)
    template = _STRINGS[lang].get(key) or _STRINGS[DEFAULT_LANG][key]
    return template.format(**kwargs) if kwargs else template


def default_label(lang: str | None, item_type: str) -> str:
    """Default spoken label for an unnamed alarm/reminder."""
    return t(lang, "default_alarm_label" if item_type == "alarm" else "default_reminder_label")


def is_default_label(label: str, item_type: str) -> bool:
    """True if *label* is the default label in any supported language."""
    wanted = "default_alarm_label" if item_type == "alarm" else "default_reminder_label"
    low = (label or "").strip().lower()
    return any(low == _STRINGS[lang][wanted].lower() for lang in SUPPORTED_LANGS)


def weekday_name(lang: str | None, weekday: int) -> str:
    """Localised weekday name for ``datetime.weekday()`` (0 = Monday)."""
    return _WEEKDAYS[normalize_lang(lang)][weekday]


# ---------------------------------------------------------------------------
# Times
# ---------------------------------------------------------------------------

def clock(dt: datetime, lang: str | None = None) -> str:
    """Spoken clock time: ``7:30 AM`` (en) or ``7:30 Uhr`` (de)."""
    if normalize_lang(lang) == "de":
        return f"{dt.hour}:{dt.minute:02d} Uhr"
    hour12 = dt.hour % 12 or 12
    return f"{hour12}:{dt.minute:02d} {'AM' if dt.hour < 12 else 'PM'}"


def when(dt: datetime, now: datetime, lang: str | None = None) -> str:
    """Natural spoken date+time.

    en: "7:30 AM", "7:30 AM tomorrow", "7:30 AM on Monday"
    de: "heute um 7:30 Uhr", "morgen um 7:30 Uhr", "am Montag um 7:30 Uhr"
    """
    lang = normalize_lang(lang)
    time_str = clock(dt, lang)
    if lang == "de":
        if dt.date() == now.date():
            return f"heute um {time_str}"
        if dt.date() == (now + timedelta(days=1)).date():
            return f"morgen um {time_str}"
        return f"am {weekday_name(lang, dt.weekday())} um {time_str}"
    if dt.date() == now.date():
        return time_str
    if dt.date() == (now + timedelta(days=1)).date():
        return f"{time_str} tomorrow"
    return f"{time_str} on {weekday_name(lang, dt.weekday())}"


def human_when(scheduled_at: datetime, now: datetime, lang: str | None = None) -> str:
    """Compact relative text for the dashboard sensors."""
    delta = scheduled_at - now
    total_seconds = int(delta.total_seconds())

    if total_seconds < 0:
        return t(lang, "when_missed", time=clock(scheduled_at, lang))
    if total_seconds < 60:
        return t(lang, "when_seconds", n=total_seconds)

    minutes = total_seconds // 60
    if minutes < 60:
        return t(lang, "when_minutes", n=minutes)

    hours = minutes // 60
    remaining = minutes % 60
    time_str = clock(scheduled_at, lang)
    if scheduled_at.date() == now.date():
        base = t(lang, "when_today", time=time_str)
    elif scheduled_at.date() == (now + timedelta(days=1)).date():
        base = t(lang, "when_tomorrow", time=time_str)
    else:
        base = t(
            lang, "when_weekday",
            weekday=weekday_name(lang, scheduled_at.weekday()), time=time_str,
        )

    if hours < 24 and remaining:
        return t(lang, "when_hm", h=hours, m=remaining, base=base)
    return base


# ---------------------------------------------------------------------------
# Counts and lists
# ---------------------------------------------------------------------------

_COUNT_EN = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five"}
# German: "Wecker" is masculine ("einen Wecker"), "Erinnerung" feminine.
_COUNT_DE = {2: "zwei", 3: "drei", 4: "vier", 5: "fünf"}


def count_word(n: int, lang: str | None = None, item_type: str = "alarm") -> str:
    """'one'..'five' (en) / 'einen|eine'..'fünf' (de); digits for 6+."""
    if normalize_lang(lang) == "de":
        if n == 1:
            return "einen" if item_type == "alarm" else "eine"
        return _COUNT_DE.get(n, str(n))
    return _COUNT_EN.get(n, str(n))


def _more_word(remaining: int, lang: str, item_type: str) -> str:
    if lang == "de":
        if remaining == 1:
            return "einen weiteren" if item_type == "alarm" else "eine weitere"
        return f"{_COUNT_DE.get(remaining, str(remaining))} weitere"
    return f"{_COUNT_EN.get(remaining, str(remaining))} more"


def list_message(lang: str | None, item_type: str, entries: list[str]) -> str:
    """Spoken summary of the scheduled alarms/reminders.

    *entries* are already-formatted per-item strings (e.g. "7:30 AM").  At most
    three are read out; the rest are summarised as "and N more".
    """
    lang = normalize_lang(lang)
    n = len(entries)
    plural = "alarms" if item_type == "alarm" else "reminders"

    if lang == "de":
        noun_pl = "Wecker" if item_type == "alarm" else "Erinnerungen"
        if n == 0:
            return f"Du hast keine {noun_pl} gestellt."
        if n == 1:
            return f"Du hast {count_word(1, lang, item_type)} {_STRINGS['de'][item_type]} gestellt: {entries[0]}."
        if n == 2:
            return f"Du hast zwei {noun_pl} gestellt: {entries[0]} und {entries[1]}."
        listed = f"{entries[0]}, {entries[1]} und {entries[2]}"
        if n == 3:
            return f"Du hast drei {noun_pl} gestellt: {listed}."
        listed = f"{entries[0]}, {entries[1]}, {entries[2]} und {_more_word(n - 3, lang, item_type)}"
        return f"Du hast {count_word(n, lang, item_type)} {noun_pl} gestellt: {listed}."

    if n == 0:
        return f"You have no {plural} set."
    if n == 1:
        return f"You have one {item_type} set: {entries[0]}."
    if n == 2:
        return f"You have two {plural} set: {entries[0]} and {entries[1]}."
    listed = f"{entries[0]}, {entries[1]}, and {entries[2]}"
    if n == 3:
        return f"You have {count_word(n)} {plural} set: {listed}."
    return f"You have {count_word(n)} {plural} set: {listed} and {_more_word(n - 3, lang, item_type)}."


def reminder_entry(label: str, when_text: str, lang: str | None = None) -> str:
    """One reminder in a list: "call Mom at 7:30 AM" / "Mama anrufen, morgen um 7:30 Uhr"."""
    if normalize_lang(lang) == "de":
        return f"{label}, {when_text}"
    return f"{label} at {when_text}"
