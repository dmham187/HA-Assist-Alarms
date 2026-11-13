"""Tests for i18n.py — no Home Assistant dependency required."""

import importlib.util
import os
from datetime import datetime, timezone

import pytest

_PATH = os.path.join(os.path.dirname(__file__), "..", "custom_components", "ha_alarms", "i18n.py")
_spec = importlib.util.spec_from_file_location("i18n", _PATH)
i18n = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(i18n)

# Wednesday 2026-03-25 09:00 UTC
NOW = datetime(2026, 3, 25, 9, 0, tzinfo=timezone.utc)


def at(day_offset: int, h: int, m: int) -> datetime:
    return NOW.replace(day=25 + day_offset, hour=h, minute=m)


@pytest.mark.parametrize("raw, expected", [
    ("de", "de"), ("de-DE", "de"), ("de_AT", "de"), ("DE", "de"),
    ("en", "en"), ("en-US", "en"), ("fr", "en"), ("", "en"), (None, "en"),
])
def test_normalize_lang(raw, expected):
    assert i18n.normalize_lang(raw) == expected


def test_every_key_exists_in_every_language():
    en, de = i18n._STRINGS["en"], i18n._STRINGS["de"]
    assert set(en) == set(de)


def test_placeholders_match_between_languages():
    import string
    fmt = string.Formatter()
    for key, en_text in i18n._STRINGS["en"].items():
        en_fields = {f for _, f, _, _ in fmt.parse(en_text) if f}
        de_fields = {f for _, f, _, _ in fmt.parse(i18n._STRINGS["de"][key]) if f}
        assert en_fields == de_fields, key


class TestClockAndWhen:
    def test_english_unchanged(self):
        assert i18n.clock(at(0, 7, 30), "en") == "7:30 AM"
        assert i18n.clock(at(0, 19, 5), "en") == "7:05 PM"
        assert i18n.clock(at(0, 0, 0), "en") == "12:00 AM"
        assert i18n.clock(at(0, 12, 15), "en") == "12:15 PM"
        assert i18n.when(at(0, 7, 30), NOW, "en") == "7:30 AM"
        assert i18n.when(at(1, 7, 30), NOW, "en") == "7:30 AM tomorrow"
        assert i18n.when(at(5, 7, 30), NOW, "en") == "7:30 AM on Monday"

    def test_german(self):
        assert i18n.clock(at(0, 7, 30), "de") == "7:30 Uhr"
        assert i18n.clock(at(0, 19, 5), "de") == "19:05 Uhr"
        assert i18n.when(at(0, 7, 30), NOW, "de") == "heute um 7:30 Uhr"
        assert i18n.when(at(1, 7, 30), NOW, "de") == "morgen um 7:30 Uhr"
        assert i18n.when(at(5, 7, 30), NOW, "de") == "am Montag um 7:30 Uhr"

    def test_weekday_names_do_not_depend_on_locale(self):
        assert i18n.weekday_name("de", 2) == "Mittwoch"
        assert i18n.weekday_name("en", 2) == "Wednesday"


class TestHumanWhen:
    def test_english(self):
        assert i18n.human_when(at(0, 8, 0).replace(hour=9, minute=0, second=30), NOW, "en") == "in 30s"
        assert i18n.human_when(at(0, 9, 45), NOW, "en") == "in 45m"
        assert i18n.human_when(at(0, 11, 30), NOW, "en") == "in 2h 30m (today at 11:30 AM)"
        assert i18n.human_when(at(1, 7, 0), NOW, "en") == "tomorrow at 7:00 AM"
        assert i18n.human_when(at(0, 8, 0), NOW, "en") == "missed (8:00 AM)"

    def test_german(self):
        assert i18n.human_when(at(0, 9, 45), NOW, "de") == "in 45 Min."
        assert i18n.human_when(at(0, 11, 30), NOW, "de") == "in 2 Std. 30 Min. (heute um 11:30 Uhr)"
        assert i18n.human_when(at(1, 7, 0), NOW, "de") == "morgen um 7:00 Uhr"
        assert i18n.human_when(at(5, 7, 0), NOW, "de") == "Montag um 7:00 Uhr"
        assert i18n.human_when(at(0, 8, 0), NOW, "de") == "verpasst (8:00 Uhr)"


class TestListMessage:
    def test_english_matches_original_wording(self):
        lm = i18n.list_message
        assert lm("en", "alarm", []) == "You have no alarms set."
        assert lm("en", "alarm", ["7:30 AM"]) == "You have one alarm set: 7:30 AM."
        assert lm("en", "alarm", ["a", "b"]) == "You have two alarms set: a and b."
        assert lm("en", "alarm", ["a", "b", "c"]) == "You have three alarms set: a, b, and c."
        assert lm("en", "alarm", list("abcd")) == "You have four alarms set: a, b, and c and one more."
        assert lm("en", "reminder", list("abcde")) == "You have five reminders set: a, b, and c and two more."
        assert lm("en", "reminder", []) == "You have no reminders set."
        assert lm("en", "reminder", ["x"]) == "You have one reminder set: x."

    def test_german_alarms(self):
        lm = i18n.list_message
        assert lm("de", "alarm", []) == "Du hast keine Wecker gestellt."
        assert lm("de", "alarm", ["a"]) == "Du hast einen Wecker gestellt: a."
        assert lm("de", "alarm", ["a", "b"]) == "Du hast zwei Wecker gestellt: a und b."
        assert lm("de", "alarm", ["a", "b", "c"]) == "Du hast drei Wecker gestellt: a, b und c."
        assert lm("de", "alarm", list("abcd")) == "Du hast vier Wecker gestellt: a, b, c und einen weiteren."
        assert lm("de", "alarm", list("abcde")) == "Du hast fünf Wecker gestellt: a, b, c und zwei weitere."
        assert lm("de", "alarm", list("abcdefg")).startswith("Du hast 7 Wecker gestellt")

    def test_german_reminders_use_feminine_forms(self):
        lm = i18n.list_message
        assert lm("de", "reminder", []) == "Du hast keine Erinnerungen gestellt."
        assert lm("de", "reminder", ["x"]) == "Du hast eine Erinnerung gestellt: x."
        assert lm("de", "reminder", list("abcd")) == "Du hast vier Erinnerungen gestellt: a, b, c und eine weitere."

    def test_reminder_entry(self):
        assert i18n.reminder_entry("call Mom", "7:30 AM", "en") == "call Mom at 7:30 AM"
        assert i18n.reminder_entry("Mama anrufen", "morgen um 7:30 Uhr", "de") == "Mama anrufen, morgen um 7:30 Uhr"


class TestLabels:
    def test_default_labels(self):
        assert i18n.default_label("en", "alarm") == "Alarm"
        assert i18n.default_label("de", "alarm") == "Wecker"
        assert i18n.default_label("de", "reminder") == "Erinnerung"

    def test_is_default_label_any_language(self):
        assert i18n.is_default_label("Alarm", "alarm")
        assert i18n.is_default_label("wecker", "alarm")
        assert not i18n.is_default_label("Wecker", "reminder")
        assert not i18n.is_default_label("Zahnarzt", "reminder")


def test_unknown_key_falls_back_to_english_text():
    # A key that exists only in English must not raise for German.
    i18n._STRINGS["en"]["_tmp"] = "x {a}"
    try:
        assert i18n.t("de", "_tmp", a=1) == "x 1"
    finally:
        del i18n._STRINGS["en"]["_tmp"]
