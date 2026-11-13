"""Check the custom sentence files against hassil (Home Assistant's sentence engine).

Skipped automatically when hassil / PyYAML are not installed.
For every utterance: it must match the expected intent, and the captured slots
must be parseable by datetime_parser in the matching language.
"""

import importlib.util
import os
from datetime import datetime, timezone

import pytest

yaml = pytest.importorskip("yaml")
hassil = pytest.importorskip("hassil")

_ROOT = os.path.join(os.path.dirname(__file__), "..")
_spec = importlib.util.spec_from_file_location(
    "datetime_parser", os.path.join(_ROOT, "custom_components", "ha_alarms", "datetime_parser.py")
)
dp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dp)

_REF = datetime(2026, 3, 25, 14, 0, tzinfo=timezone.utc)  # Wednesday


def _load(lang):
    path = os.path.join(_ROOT, "config", "custom_sentences", lang, "ha_alarms.yaml")
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    assert data["language"] == lang
    return hassil.Intents.from_dict(data)


def _recognize(intents, text):
    res = hassil.recognize_best(text, intents)
    if res is None:
        return None, {}
    return res.intent.name, {k: v.value for k, v in res.entities.items()}


def test_intent_names_match_between_languages():
    def names(lang):
        with open(os.path.join(_ROOT, "config", "custom_sentences", lang, "ha_alarms.yaml"),
                  encoding="utf-8") as fh:
            return set(yaml.safe_load(fh)["intents"])
    assert names("de") == names("en")


# (utterance, expected intent, expected slots (case-insensitive subset))
DE_CASES = [
    ("Stell einen Wecker auf 7 Uhr 30", "HaAlarmsSetAlarm", {"time": "7 Uhr 30"}),
    ("Stell einen Wecker für halb acht", "HaAlarmsSetAlarm", {"time": "halb acht"}),
    ("Stelle mir einen Wecker um 6:45", "HaAlarmsSetAlarm", {"time": "6:45"}),
    ("Stell einen Wecker in 30 Minuten", "HaAlarmsSetAlarm", {"time": "30 Minuten"}),
    ("Weck mich um 7 Uhr", "HaAlarmsSetAlarm", {"time": "7 Uhr"}),
    ("Weck mich morgen um viertel nach sieben", "HaAlarmsSetAlarm", {}),
    ("Weck mich in einer Stunde", "HaAlarmsSetAlarm", {"time": "einer Stunde"}),
    ("Weck mich täglich um 6 Uhr", "HaAlarmsSetAlarm", {"repeat": "daily", "time": "6 Uhr"}),
    ("Weck mich jeden Tag um halb sieben", "HaAlarmsSetAlarm", {"repeat": "daily"}),
    ("Stell einen Wecker für 7 Uhr werktags", "HaAlarmsSetAlarm", {"repeat": "weekdays", "time": "7 Uhr"}),
    ("Weck mich montags bis freitags um 6 Uhr 15", "HaAlarmsSetAlarm", {"repeat": "weekdays"}),
    ("Weck mich am Wochenende um 9 Uhr", "HaAlarmsSetAlarm", {"repeat": "weekends"}),
    ("Erinnere mich um 18 Uhr an Mama anrufen", "HaAlarmsSetReminder", {"time": "18 Uhr", "label": "Mama anrufen"}),
    ("Erinnere mich morgen um 9 Uhr an den Zahnarzt", "HaAlarmsSetReminder", {"date": "morgen", "label": "den Zahnarzt"}),
    ("Erinnere mich in 30 Minuten an die Wäsche", "HaAlarmsSetReminder", {"time": "30 Minuten"}),
    ("Erinnere mich an den Zahnarzt um 15 Uhr", "HaAlarmsSetReminder", {"time": "15 Uhr"}),
    ("Lösche den Wochenende Wecker", "HaAlarmsCancelAlarm", {"label": "Wochenende"}),
    ("Lösche den Wecker für 7 Uhr", "HaAlarmsCancelAlarm", {"label": "7 Uhr"}),
    ("Lösche die Erinnerung an Mama anrufen", "HaAlarmsCancelReminder", {"label": "Mama anrufen"}),
    ("Stoppe den Wecker", "HaAlarmsStopAlarm", {}),
    ("Wecker aus", "HaAlarmsStopAlarm", {}),
    ("Beende die Erinnerung", "HaAlarmsStopReminder", {}),
    ("Snooze", "HaAlarmsSnoozeAlarm", {}),
    ("Schlummern für 10 Minuten", "HaAlarmsSnoozeAlarm", {"minutes": "10"}),
    ("Gib mir noch 5 Minuten", "HaAlarmsSnoozeAlarm", {"minutes": "5"}),
    ("Schlummere die Erinnerung für 10 Minuten", "HaAlarmsSnoozeReminder", {"minutes": "10"}),
    ("Welche Wecker habe ich", "HaAlarmsListAlarms", {}),
    ("Wann klingelt mein Wecker", "HaAlarmsListAlarms", {}),
    ("Welche Erinnerungen habe ich gestellt", "HaAlarmsListReminders", {}),
    ("Lösche alle Wecker", "HaAlarmsCancelAllAlarms", {}),
    ("Lösche alle meine Erinnerungen", "HaAlarmsCancelAllReminders", {}),
    # Built-in HA intents must not be shadowed.
    ("Wie spät ist es", None, {}),
]

EN_CASES = [
    ("Set an alarm for 7 AM", "HaAlarmsSetAlarm", {"time": "7 AM"}),
    ("Wake me up every day at 6 AM", "HaAlarmsSetAlarm", {"repeat": "daily"}),
    ("Remind me to call Mom at 6 PM", "HaAlarmsSetReminder", {"label": "call Mom"}),
    ("What time is it", None, {}),
]


@pytest.mark.parametrize("lang, cases", [("de", DE_CASES), ("en", EN_CASES)])
def test_utterances(lang, cases):
    intents = _load(lang)
    for text, intent, slots in cases:
        got_intent, got_slots = _recognize(intents, text)
        assert got_intent == intent, text
        for key, value in slots.items():
            assert got_slots.get(key, "").lower() == value.lower(), (text, key, got_slots)


@pytest.mark.parametrize("text", [
    "Stell einen Wecker auf 7 Uhr 30",
    "Stell einen Wecker für halb acht",
    "Stell einen Wecker für morgen um 7 Uhr",
    "Weck mich morgen früh um sieben",
    "Weck mich heute Abend um halb neun",
    "Weck mich in einer halben Stunde",
    "Weck mich am Montag um viertel vor sieben",
    "Erinnere mich in 30 Minuten an die Wäsche",
])
def test_german_slots_feed_the_parser(text):
    """End to end: sentence → slots → datetime, with no exceptions."""
    intents = _load("de")
    intent, slots = _recognize(intents, text)
    assert intent in ("HaAlarmsSetAlarm", "HaAlarmsSetReminder")
    when = dp.parse_datetime(slots["time"], slots.get("date"), now=_REF, lang="de")
    assert when > _REF
