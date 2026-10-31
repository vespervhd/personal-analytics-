"""Tests for the phone-first CSS module (ui/mobile_style.py).

Static checks only: the rules are plain CSS strings, so asserting on
their contents is the honest unit test. The real layout proof is the
Playwright viewport check (390px) run against the live app.
"""

from ui.mobile_style import MOBILE_CSS, mobile_style


def test_mobile_style_wraps_css_for_streamlit_injection():
    html = mobile_style()
    assert html.startswith("<style>")
    assert html.endswith("</style>")
    assert MOBILE_CSS.strip() in html


def test_phone_and_small_phone_breakpoints_present():
    assert "@media (max-width: 640px)" in MOBILE_CSS
    assert "@media (max-width: 390px)" in MOBILE_CSS


def test_tables_scroll_internally_not_the_page():
    assert '[data-testid="stDataFrame"]' in MOBILE_CSS
    assert "overflow-x: auto" in MOBILE_CSS
    assert '[data-testid="stAppViewContainer"]' in MOBILE_CSS
    assert "overflow-x: clip" in MOBILE_CSS


def test_columns_wrap_and_metrics_do_not_squeeze():
    assert '[data-testid="stHorizontalBlock"]' in MOBILE_CSS
    assert "flex-wrap: wrap" in MOBILE_CSS
    assert '[data-testid="stMetricValue"]' in MOBILE_CSS


def test_buttons_have_touch_height_and_sidebar_is_capped():
    assert ".stButton > button" in MOBILE_CSS
    assert "min-height: 44px" in MOBILE_CSS
    assert '[data-testid="stSidebar"]' in MOBILE_CSS
    assert "88vw" in MOBILE_CSS
    # Sidebar state is data-collapsed in Streamlit 1.66, not aria-expanded.
    assert '[data-testid="stSidebar"][data-collapsed="false"]' in MOBILE_CSS
    assert 'button[aria-label="Collapse sidebar"]' in MOBILE_CSS
    assert '[data-testid="stExpandSidebarButton"]' in MOBILE_CSS


def test_no_desktop_rules_outside_media_queries():
    # Everything before the first @media must be comments/blank lines:
    # desktop (>= 641px) gets no rule at all.
    head = MOBILE_CSS.split("@media")[0]
    rules = [line for line in head.splitlines() if line.strip() and not line.strip().startswith("/*") and not line.strip().startswith("*")]
    assert rules == []


def test_no_new_user_visible_strings():
    # CSS-only work: no Persian/English labels may sneak in here.
    assert "مجموعه" not in MOBILE_CSS
    assert "dataset" not in MOBILE_CSS.lower()
