"""Tests for datetime_parser.py — no Home Assistant dependency required.

Run with:  python -m pytest tests/test_datetime_parser.py -v
           (or just: pytest)
"""

import importlib.util
import os
import sys
from datetime import datetime, timedelta, timezone

# Import datetime_parser directly from its file so pytest does not trigger
# custom_components/ha_alarms/__init__.py (which requires voluptuous / HA).
_MODULE_PATH = os.path.join(
    os.path.dirname(__file__),
    "..",
    "custom_components",
    "ha_alarms",
    "datetime_parser.py",
)
_spec = importlib.util.spec_from_file_location("datetime_parser", _MODULE_PATH)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

ParseAmbiguousError = _mod.ParseAmbiguousError
ParseError = _mod.ParseError
_normalise_time_str = _mod._normalise_time_str
parse_datetime = _mod.parse_datetime
parse_date = _mod.parse_date
parse_minutes = _mod.parse_minutes

# ---------------------------------------------------------------------------
# Fixed reference: Wednesday 2026-03-25 14:00:00 UTC
# Using 14:00 so AM times (e.g. 8:15 AM) are always "already past" → tomorrow,
# and PM times (8:15 PM = 20:15) are still future → today.
# ---------------------------------------------------------------------------
_REF = datetime(2026, 3, 25, 14, 0, 0, tzinfo=timezone.utc)


def dt(h: int, mi: int, days_ahead: int = 0) -> datetime:
    """Build a UTC datetime at h:mi on the reference date + days_ahead."""
    return _REF.replace(hour=h, minute=mi, second=0, microsecond=0) + timedelta(
        days=days_ahead
    )


# ===========================================================================
# _normalise_time_str — unit tests for the normaliser in isolation
# ===========================================================================

class TestNormaliseTimeStr:
    def test_standard_colon_unchanged(self):
        assert _normalise_time_str("7:30 PM") == "7:30 PM"

    def test_standard_no_space_unchanged(self):
        assert _normalise_time_str("7:30pm") == "7:30pm"

    def test_dot_separator(self):
        assert _normalise_time_str("8.15pm") == "8:15pm"

    def test_dot_separator_with_space_ampm(self):
        assert _normalise_time_str("8.15 pm") == "8:15 pm"

    def test_dot_separator_uppercase_ampm(self):
        assert _normalise_time_str("8.15 PM") == "8:15 PM"

    def test_space_separated_digits(self):
        assert _normalise_time_str("8 15 pm") == "8:15 pm"

    def test_space_separated_digits_no_ampm(self):
        assert _normalise_time_str("8 15") == "8:15"

    def test_dotted_pm(self):
        assert _normalise_time_str("8:15 p.m.").lower() == "8:15 pm"

    def test_dotted_am(self):
        assert _normalise_time_str("8:15 a.m.").lower() == "8:15 am"

    def test_dotted_ampm_uppercase(self):
        assert _normalise_time_str("8:15 P.M.").lower() == "8:15 pm"

    def test_dot_sep_and_dotted_ampm(self):
        # "8.15 p.m." → "8:15 pm"
        assert _normalise_time_str("8.15 p.m.").lower() == "8:15 pm"

    def test_space_sep_and_dotted_ampm(self):
        # "8 15 p.m." → "8:15 pm"
        assert _normalise_time_str("8 15 p.m.").lower() == "8:15 pm"

    def test_noon_unchanged(self):
        assert _normalise_time_str("noon") == "noon"

    def test_midnight_unchanged(self):
        assert _normalise_time_str("midnight") == "midnight"

    def test_24h_unchanged(self):
        assert _normalise_time_str("19:30") == "19:30"


# ===========================================================================
# parse_datetime — faster-whisper variant formats (the core regression suite)
# ===========================================================================

class TestFasterWhisperFormats:
    """These formats were produced by faster-whisper and previously failed."""

    def test_dot_separator_pm(self):
        # "8.15pm" → 20:15 today (still future at 14:00)
        result = parse_datetime("8.15pm", now=_REF)
        assert result == dt(20, 15)

    def test_dot_separator_am(self):
        # "8.15am" → 08:15 tomorrow (already past at 14:00)
        result = parse_datetime("8.15am", now=_REF)
        assert result == dt(8, 15, days_ahead=1)

    def test_dot_separator_space_pm(self):
        # "8.15 pm"
        result = parse_datetime("8.15 pm", now=_REF)
        assert result == dt(20, 15)

    def test_space_separated_pm(self):
        # "8 15 pm"
        result = parse_datetime("8 15 pm", now=_REF)
        assert result == dt(20, 15)

    def test_space_separated_am(self):
        # "8 15 am" → tomorrow (past at 14:00)
        result = parse_datetime("8 15 am", now=_REF)
        assert result == dt(8, 15, days_ahead=1)

    def test_dotted_pm_suffix(self):
        # "8:15 p.m."
        result = parse_datetime("8:15 p.m.", now=_REF)
        assert result == dt(20, 15)

    def test_dotted_am_suffix(self):
        # "8:15 a.m." → tomorrow (past at 14:00)
        result = parse_datetime("8:15 a.m.", now=_REF)
        assert result == dt(8, 15, days_ahead=1)

    def test_dot_sep_and_dotted_pm(self):
        # "8.15 p.m."
        result = parse_datetime("8.15 p.m.", now=_REF)
        assert result == dt(20, 15)

    def test_space_sep_and_dotted_pm(self):
        # "8 15 p.m."
        result = parse_datetime("8 15 p.m.", now=_REF)
        assert result == dt(20, 15)

    def test_space_sep_and_dotted_am(self):
        # "8 15 a.m." → tomorrow
        result = parse_datetime("8 15 a.m.", now=_REF)
        assert result == dt(8, 15, days_ahead=1)

    def test_uppercase_dotted_pm(self):
        # "8:15 P.M."
        result = parse_datetime("8:15 P.M.", now=_REF)
        assert result == dt(20, 15)

    def test_two_digit_hour_dot_sep(self):
        # "10.30 pm"
        result = parse_datetime("10.30 pm", now=_REF)
        assert result == dt(22, 30)

    def test_zero_minutes_dot_sep(self):
        # "9.00 pm"
        result = parse_datetime("9.00 pm", now=_REF)
        assert result == dt(21, 0)

    def test_space_sep_zero_minutes(self):
        # "9 00 pm"
        result = parse_datetime("9 00 pm", now=_REF)
        assert result == dt(21, 0)


# ===========================================================================
# parse_datetime — existing standard formats must still work (regression)
# ===========================================================================

class TestStandardFormats:
    def test_colon_am(self):
        # 9:00 AM is before the 14:00 reference → advances to tomorrow
        assert parse_datetime("9:00 AM", now=_REF) == dt(9, 0, days_ahead=1)

    def test_colon_pm(self):
        assert parse_datetime("7:30 PM", now=_REF) == dt(19, 30)

    def test_no_space_am(self):
        assert parse_datetime("7am", now=_REF) == dt(7, 0, days_ahead=1)

    def test_no_space_pm(self):
        assert parse_datetime("7pm", now=_REF) == dt(19, 0)

    def test_24h(self):
        assert parse_datetime("19:30", now=_REF) == dt(19, 30)

    def test_noon(self):
        # noon is before the 14:00 reference → advances to tomorrow
        assert parse_datetime("noon", now=_REF) == dt(12, 0, days_ahead=1)

    def test_midnight(self):
        # midnight is past 14:00 → tomorrow
        assert parse_datetime("midnight", now=_REF) == dt(0, 0, days_ahead=1)

    def test_relative_minutes(self):
        assert parse_datetime("in 30 minutes", now=_REF) == _REF + timedelta(minutes=30)

    def test_relative_hours(self):
        assert parse_datetime("in 2 hours", now=_REF) == _REF + timedelta(hours=2)

    def test_bare_hour_ambiguous(self):
        import pytest
        with pytest.raises(ParseAmbiguousError):
            parse_datetime("7", now=_REF)

    def test_garbage_raises(self):
        import pytest
        with pytest.raises(ParseError):
            parse_datetime("purple monkey", now=_REF)


# ===========================================================================
# TestWhisperLocalVariants — new Whisper STT output variations
# ===========================================================================

# Use midnight as reference so all times today are in the future.
_REF_MIDNIGHT = datetime(2026, 4, 20, 0, 0, 0, tzinfo=timezone.utc)


def dt2(h: int, mi: int, days_ahead: int = 0) -> datetime:
    """Build a UTC datetime at h:mi on 2026-04-20 + days_ahead."""
    return _REF_MIDNIGHT.replace(hour=h, minute=mi, second=0, microsecond=0) + timedelta(
        days=days_ahead
    )


class TestWhisperLocalVariants:
    """Whisper STT output variations added in session 3."""

    # --- Concatenated 3-digit times ---

    def test_645_AM_upper(self):
        assert parse_datetime("645 AM", now=_REF_MIDNIGHT) == dt2(6, 45)

    def test_645_am_lower(self):
        assert parse_datetime("645 am", now=_REF_MIDNIGHT) == dt2(6, 45)

    def test_645_Am_mixed(self):
        assert parse_datetime("645 Am", now=_REF_MIDNIGHT) == dt2(6, 45)

    def test_645am_no_space(self):
        assert parse_datetime("645am", now=_REF_MIDNIGHT) == dt2(6, 45)

    def test_645_bare_ambiguous(self):
        import pytest
        with pytest.raises(ParseAmbiguousError):
            parse_datetime("645", now=_REF_MIDNIGHT)

    # --- Space-separated (regression guards) ---

    def test_6_45_AM_space_sep(self):
        assert parse_datetime("6 45 AM", now=_REF_MIDNIGHT) == dt2(6, 45)

    def test_6_45_am_space_sep(self):
        assert parse_datetime("6 45 am", now=_REF_MIDNIGHT) == dt2(6, 45)

    # --- Spaced AM/PM letters ---

    def test_spaced_am_letters(self):
        # "7:30 a m" → normalises to "7:30 am" → 07:30
        assert parse_datetime("7:30 a m", now=_REF_MIDNIGHT) == dt2(7, 30)

    def test_spaced_pm_letters(self):
        # "7:30 p m" → normalises to "7:30 pm" → 19:30
        assert parse_datetime("7:30 p m", now=_REF_MIDNIGHT) == dt2(19, 30)

    # --- Capitalisation variants (regression guards) ---

    def test_7_30_Am_mixed(self):
        assert parse_datetime("7:30 Am", now=_REF_MIDNIGHT) == dt2(7, 30)

    def test_7_30_aM_mixed(self):
        assert parse_datetime("7:30 aM", now=_REF_MIDNIGHT) == dt2(7, 30)

    # --- Word-based time expressions ---

    def test_eight_thirty_PM(self):
        assert parse_datetime("eight thirty PM", now=_REF_MIDNIGHT) == dt2(20, 30)

    def test_eight_thirty_pm_dotted(self):
        # "eight thirty p.m" — Whisper sometimes drops trailing dot
        assert parse_datetime("eight thirty p.m", now=_REF_MIDNIGHT) == dt2(20, 30)

    def test_eight_thirty_am(self):
        assert parse_datetime("eight thirty am", now=_REF_MIDNIGHT) == dt2(8, 30)

    def test_six_forty_five_am_spaced(self):
        assert parse_datetime("six forty five am", now=_REF_MIDNIGHT) == dt2(6, 45)

    def test_six_forty_five_am_hyphen(self):
        assert parse_datetime("six forty-five am", now=_REF_MIDNIGHT) == dt2(6, 45)

    def test_seven_oh_five_AM(self):
        assert parse_datetime("seven oh five AM", now=_REF_MIDNIGHT) == dt2(7, 5)

    def test_nine_thirty_bare_ambiguous(self):
        import pytest
        with pytest.raises(ParseAmbiguousError):
            parse_datetime("nine thirty", now=_REF_MIDNIGHT)


class TestTrailingPeriodVariants:
    """Community-reported bug: Whisper outputs 'a.m.' with trailing sentence
    period, producing '6 a.m..' which previously failed to parse."""

    def test_standard_am_dot(self):
        # "6 a.m." — standard form, should already work
        result = parse_datetime("6 a.m.", now=_REF_MIDNIGHT)
        assert result == dt2(6, 0)

    def test_double_trailing_period(self):
        # "6 a.m.." — sentence-ending period after a.m. — the reported bug
        result = parse_datetime("6 a.m..", now=_REF_MIDNIGHT)
        assert result == dt2(6, 0)

    def test_am_dot_with_date(self):
        # "set alarm for 6 a.m. tomorrow" — time slot as extracted by sentence engine
        result = parse_datetime("6 a.m.", date_text="tomorrow", now=_REF_MIDNIGHT)
        assert result == dt2(6, 0) + timedelta(days=1)

    def test_pm_dot_variant(self):
        # "wake me at 6 p.m." — PM form, time slot as extracted
        result = parse_datetime("6 p.m.", now=_REF_MIDNIGHT)
        assert result == dt2(18, 0)

    def test_colon_pm_trailing_sentence_period(self):
        # "Set alarm for 3:00 PM." — sentence-ending period after colon-format time
        result = parse_datetime("3:00 PM.", now=_REF_MIDNIGHT)
        assert result == dt2(15, 0)


# ===========================================================================
# German (lang="de")
# _REF is Wednesday 14:00 UTC: morning times roll over to tomorrow, evening
# times stay today.
# ===========================================================================

import pytest


def de(time_text, date_text=None):
    return parse_datetime(time_text, date_text, now=_REF, lang="de")


class TestGermanAbsoluteTime:
    @pytest.mark.parametrize("text, expected", [
        ("7 Uhr", dt(7, 0, 1)),
        ("7:30", dt(7, 30, 1)),
        ("7.30 Uhr", dt(7, 30, 1)),
        ("7 Uhr 30", dt(7, 30, 1)),
        ("07:05", dt(7, 5, 1)),
        ("19:45", dt(19, 45)),
        ("19 Uhr", dt(19, 0)),
        ("um acht", dt(8, 0, 1)),
        ("sieben Uhr", dt(7, 0, 1)),
        ("sieben Uhr dreißig", dt(7, 30, 1)),
        ("sieben Uhr dreissig", dt(7, 30, 1)),
        ("sieben Uhr fünfundvierzig", dt(7, 45, 1)),
        ("sieben Uhr fuenfzehn", dt(7, 15, 1)),
        ("sieben Uhr null fünf", dt(7, 5, 1)),
        ("null Uhr dreißig", dt(0, 30, 1)),
        ("achtzehn Uhr", dt(18, 0)),
    ])
    def test_forms(self, text, expected):
        assert de(text) == expected

    def test_bare_hour_is_face_value_not_ambiguous(self):
        # Unlike English there is no "AM or PM?" question: "um sieben" = 07:00.
        assert de("sieben") == dt(7, 0, 1)

    @pytest.mark.parametrize("text", ["25 Uhr", "7 Uhr 61", "lila Affe", ""])
    def test_invalid(self, text):
        with pytest.raises(ParseError):
            de(text)


class TestGermanColloquialClock:
    @pytest.mark.parametrize("text, expected", [
        ("halb acht", dt(7, 30, 1)),
        ("halb sieben", dt(6, 30, 1)),
        ("halb zwölf", dt(11, 30, 1)),
        ("halb eins", dt(12, 30, 1)),          # 12:30, not 00:30
        ("viertel nach sieben", dt(7, 15, 1)),
        ("viertel vor acht", dt(7, 45, 1)),
        ("viertel acht", dt(7, 15, 1)),
        ("dreiviertel acht", dt(7, 45, 1)),
        ("drei viertel acht", dt(7, 45, 1)),
        ("fünf nach sieben", dt(7, 5, 1)),
        ("zehn vor acht", dt(7, 50, 1)),
        ("zwanzig nach acht", dt(8, 20, 1)),
        ("fünf vor halb acht", dt(7, 25, 1)),
        ("fünf nach halb acht", dt(7, 35, 1)),
        ("zehn nach sieben", dt(7, 10, 1)),
    ])
    def test_forms(self, text, expected):
        assert de(text) == expected


class TestGermanDayPeriod:
    @pytest.mark.parametrize("text, expected", [
        ("sieben Uhr abends", dt(19, 0)),
        ("halb acht abends", dt(19, 30)),
        ("acht Uhr morgens", dt(8, 0, 1)),
        ("sieben Uhr früh", dt(7, 0, 1)),
        ("fünf Uhr nachmittags", dt(17, 0)),
        ("ein Uhr mittags", dt(13, 0, 1)),
        ("zwölf Uhr mittags", dt(12, 0, 1)),
        ("zwölf Uhr nachts", dt(0, 0, 1)),
        ("elf Uhr nachts", dt(23, 0)),
        ("drei Uhr nachts", dt(3, 0, 1)),
        ("halb eins mittags", dt(12, 30, 1)),
        ("Mittag", dt(12, 0, 1)),
        ("Mittags", dt(12, 0, 1)),
        ("Mitternacht", dt(0, 0, 1)),
    ])
    def test_forms(self, text, expected):
        assert de(text) == expected

    def test_24h_hours_ignore_period(self):
        assert de("19 Uhr abends") == dt(19, 0)


class TestGermanRelative:
    @pytest.mark.parametrize("text, minutes", [
        ("in 30 Minuten", 30),
        ("30 Minuten", 30),
        ("in einer Minute", 1),
        ("in fünf Minuten", 5),
        ("in einer Stunde", 60),
        ("in zwei Stunden", 120),
        ("in 2 Std", 120),
        ("in 90 Minuten", 90),
        ("in anderthalb Stunden", 90),
        ("in einer halben Stunde", 30),
        ("in einer Viertelstunde", 15),
        ("in einer dreiviertel Stunde", 45),
        ("in zweieinhalb Stunden", 150),
        ("in einer Stunde und 15 Minuten", 75),
        ("in 1 Stunde 30 Minuten", 90),
    ])
    def test_forms(self, text, minutes):
        assert de(text) == _REF + timedelta(minutes=minutes)

    def test_date_ignored_for_relative(self):
        assert de("in 30 Minuten", "morgen") == _REF + timedelta(minutes=30)


class TestGermanDates:
    @pytest.mark.parametrize("time_text, date_text, expected", [
        ("9 Uhr", "heute", dt(9, 0)),
        ("9 Uhr", "morgen", dt(9, 0, 1)),
        ("9 Uhr", "übermorgen", dt(9, 0, 2)),
        ("9 Uhr", "uebermorgen", dt(9, 0, 2)),
        ("9 Uhr", "Montag", dt(9, 0, 5)),
        ("9 Uhr", "am Montag", dt(9, 0, 5)),
        ("9 Uhr", "nächsten Freitag", dt(9, 0, 2)),
        ("9 Uhr", "Samstag", dt(9, 0, 3)),
        ("9 Uhr", "Sonnabend", dt(9, 0, 3)),
        ("9 Uhr", "Mittwoch", dt(9, 0, 7)),       # never today
        ("8 Uhr", "heute Abend", dt(20, 0)),
        ("7 Uhr", "morgen früh", dt(7, 0, 1)),
    ])
    def test_explicit_date(self, time_text, date_text, expected):
        assert de(time_text, date_text) == expected

    @pytest.mark.parametrize("text, expected", [
        ("morgen um 7 Uhr", dt(7, 0, 1)),
        ("morgen früh um sieben", dt(7, 0, 1)),
        ("heute Abend um 8", dt(20, 0)),
        ("heute um 18 Uhr", dt(18, 0)),
        ("am Montag um halb acht", dt(7, 30, 5)),
        ("Samstag 10 Uhr", dt(10, 0, 3)),
        ("übermorgen um 6:45", dt(6, 45, 2)),
        ("morgen Mittag", dt(12, 0, 1)),
        ("morgen um 7 Uhr morgens", dt(7, 0, 1)),
        ("morgen in zwei Stunden", _REF + timedelta(hours=2)),
    ])
    def test_date_embedded_in_time_slot(self, text, expected):
        assert de(text) == expected

    def test_bad_date(self):
        with pytest.raises(ParseError):
            de("9 Uhr", "nächste Woche")

    def test_parse_date(self):
        assert parse_date("morgen", now=_REF, lang="de") == (_REF + timedelta(days=1)).date()
        assert parse_date("am Montag", now=_REF, lang="de") == dt(0, 0, 5).date()
        with pytest.raises(ParseError):
            parse_date("blah", now=_REF, lang="de")


class TestLanguageSelection:
    def test_region_suffix_and_case(self):
        assert parse_datetime("halb acht", now=_REF, lang="de-DE") == dt(7, 30, 1)
        assert parse_datetime("halb acht", now=_REF, lang="DE") == dt(7, 30, 1)

    def test_unknown_language_falls_back_to_english(self):
        assert parse_datetime("7:30 PM", now=_REF, lang="fr") == dt(19, 30)

    def test_default_is_english(self):
        assert parse_datetime("7:30 PM", now=_REF) == dt(19, 30)
        with pytest.raises(ParseError):
            parse_datetime("halb acht", now=_REF)   # German is not guessed


class TestParseMinutes:
    @pytest.mark.parametrize("text, lang, expected", [
        ("5", "en", 5), ("five", "en", 5), ("ten", "en", 10), ("10 minutes", "en", 10),
        ("5", "de", 5), ("fünf", "de", 5), ("zehn", "de", 10),
        ("fünfzehn", "de", 15), ("zwanzig Minuten", "de", 20),
        ("fünfundzwanzig", "de", 25), ("eine", "de", 1),
        ("blah", "en", None), ("blah", "de", None), ("", "de", None), (None, "en", None),
    ])
    def test_forms(self, text, lang, expected):
        assert parse_minutes(text, lang) == expected
