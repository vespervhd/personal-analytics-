"""Tests for the Persian/English string dictionary (ui/i18n.py).

No network is required: the RTL helper only builds a string, and the
bundled font is embedded as a data URI, never fetched.
"""

from ui.i18n import STRINGS, rtl_style, t


def test_parity_fa_en():
    assert set(STRINGS["fa"]) == set(STRINGS["en"])
    assert STRINGS["fa"] and STRINGS["en"]


def test_t_non_empty_both_languages():
    for key in STRINGS["fa"]:
        assert t(key, lang="fa").strip(), f"empty fa string for {key}"
        assert t(key, lang="en").strip(), f"empty en string for {key}"


def test_t_falls_back_to_english_then_key():
    # A key present only in English still resolves for Persian.
    STRINGS["en"]["_test_only_en"] = "English only"
    try:
        assert t("_test_only_en", lang="fa") == "English only"
    finally:
        del STRINGS["en"]["_test_only_en"]
    assert t("no_such_key_at_all", lang="fa") == "no_such_key_at_all"
    assert t("no_such_key_at_all", lang="en") == "no_such_key_at_all"


def test_rtl_style_persian():
    css = rtl_style("fa")
    assert "direction: rtl" in css
    assert "Vazirmatn" in css
    # The font is embedded, not fetched: @font-face with data URIs, and
    # no Google Fonts dependency (unreachable on slow/filtered links).
    assert "@font-face" in css
    assert "data:font/woff2;base64," in css
    assert "fonts.googleapis.com" not in css
    assert "fonts.gstatic.com" not in css


def test_rtl_style_english_is_empty():
    assert rtl_style("en") == ""


def test_templates_use_latin_digits_only():
    # Rendered template placeholders must not introduce Persian digits.
    persian_digits = set("۰۱۲۳۴۵۶۷۸۹")
    for lang in ("fa", "en"):
        for key, value in STRINGS[lang].items():
            assert not (set(value) & persian_digits), f"{lang}:{key} has Persian digits"
