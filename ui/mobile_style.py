"""Phone-first layout tweaks for the dashboard (item 8).

A single global CSS module, injected once from ``app.py``. It only
touches presentation: no strings, no widgets, no session state, so it
cannot disturb navigation (``nav_pending``), i18n, or workspaces.

What it does, all inside media queries so desktop is untouched:

* Narrows page padding and shrinks headings on phone screens.
* Lets Streamlit column rows wrap (metric rows, button rows) instead
  of squeezing every column into a 390px viewport, and makes buttons
  fill their column with a 44px minimum touch height.
* Keeps dataframes/charts inside the viewport: the table itself gets
  an internal horizontal scroll, the page never gains one.
* Keeps the sidebar usable on phones: the collapsed-sidebar control
  is a larger tap target, and an expanded sidebar is capped at 88vw
  so it never pushes the page off-screen.
* Sets form fields to 16px text, which stops iOS Safari auto-zooming
  into inputs on focus.

Breakpoints: 640px covers phones in general; 390px tightens the
smallest phones further. Desktop (>= 641px) gets no rule at all.
"""

from __future__ import annotations

#: Raw CSS, kept separate from the ``<style>`` wrapper so tests can
#: inspect the rules without parsing HTML.
MOBILE_CSS = """
/* ---- Phone layout (<= 640px) ------------------------------------ */
@media (max-width: 640px) {
  /* Page chrome: less padding, never wider than the viewport. */
  [data-testid="stAppViewContainer"] {
    overflow-x: clip;
  }
  .block-container {
    padding: 1rem 0.75rem 2rem 0.75rem !important;
    max-width: 100vw !important;
  }
  /* Vertical stacks and element wrappers must be allowed to shrink
     below their content width, or a wide table/chart forces the page
     wider than the screen. */
  [data-testid="stVerticalBlock"],
  [data-testid="stHorizontalBlock"],
  .element-container {
    min-width: 0;
    max-width: 100%;
  }
  /* Headings wrap instead of overflowing on narrow screens. */
  h1, h2, h3 {
    overflow-wrap: anywhere;
  }
  h1 {
    font-size: 1.5rem !important;
  }
  h2 {
    font-size: 1.25rem !important;
  }
  /* Column rows wrap: a row of metrics or buttons becomes two-per-row
     (or one-per-row for wide content) instead of five squeezed columns.
     A 160px basis fits two columns across a 390px screen with gaps. */
  [data-testid="stHorizontalBlock"] {
    flex-wrap: wrap;
  }
  [data-testid="stHorizontalBlock"] > [data-testid="column"] {
    flex: 1 1 160px !important;
    min-width: 0 !important;
  }
  /* Metrics: values must wrap, not clip, once columns narrow. */
  [data-testid="stMetric"] {
    min-width: 0;
  }
  [data-testid="stMetricValue"] {
    font-size: 1.25rem !important;
    overflow-wrap: anywhere;
  }
  [data-testid="stMetricLabel"] {
    overflow-wrap: anywhere;
  }
  /* Buttons fill their column and meet a 44px touch target. */
  .stButton > button,
  .stDownloadButton > button,
  .stFormSubmitButton > button {
    width: 100%;
    min-height: 44px;
    white-space: normal;
    height: auto;
    padding-top: 0.6rem;
    padding-bottom: 0.6rem;
  }
  /* Sidebar on phones: a bigger collapsed-control tap target, a 44px
     collapse button (Streamlit 1.66 renders it 28px by default), and an
     expanded sidebar capped at 88vw so it cannot push content away.
     Note: the sidebar marks its state with data-collapsed, not
     aria-expanded — the latter selector silently matches nothing. */
  /* Streamlit 1.66 names the expand control stExpandSidebarButton
     (older versions used collapsedControl — both are covered). */
  [data-testid="collapsedControl"],
  [data-testid="stExpandSidebarButton"] {
    padding: 0.75rem !important;
    min-width: 44px !important;
    min-height: 44px !important;
  }
  [data-testid="collapsedControl"] button {
    min-width: 44px;
    min-height: 44px;
  }
  [data-testid="stSidebar"] button[aria-label="Collapse sidebar"] {
    min-width: 44px !important;
    min-height: 44px !important;
  }
  [data-testid="stSidebar"][data-collapsed="false"] {
    min-width: min(21rem, 88vw) !important;
    max-width: 88vw !important;
  }
  [data-testid="stSidebar"] .stButton > button {
    width: 100%;
  }
  /* Tables: the dataframe scrolls internally; the page must not. */
  [data-testid="stDataFrame"] {
    max-width: 100%;
    overflow-x: auto;
  }
  /* Charts resize with their container instead of overflowing it. */
  .js-plotly-plot, .plotly {
    max-width: 100%;
  }
  /* Form fields: 16px text stops iOS auto-zoom on focus, and controls
     get a comfortable touch height. */
  .stApp input, .stApp textarea, .stApp select {
    font-size: 16px !important;
  }
  [data-testid="stFileUploaderDropzone"] {
    padding: 1rem 0.75rem;
    max-width: 100%;
  }
  /* Expander headers and tab buttons are tap targets too. */
  [data-testid="stExpander"] summary {
    min-height: 44px;
  }
  [data-testid="stTabs"] button {
    min-height: 44px;
  }
  /* Long code/paths in captions and markdown wrap instead of
     stretching the page (e.g. upload paths in the sidebar). */
  .stApp code, .stApp p {
    overflow-wrap: anywhere;
  }
}

/* ---- Smallest phones (<= 390px) ---------------------------------- */
@media (max-width: 390px) {
  .block-container {
    padding: 0.75rem 0.5rem 2rem 0.5rem !important;
  }
  h1 {
    font-size: 1.35rem !important;
  }
  /* Column rows keep the 160px wrap basis from the 640px query: two
     columns still fit across 390px, and buttons stay full-column-width
     and tappable. Only the sidebar grows to fill the small screen. */
  [data-testid="stSidebar"][data-collapsed="false"] {
    min-width: 88vw !important;
  }
}
"""


def mobile_style() -> str:
    """Return the mobile CSS wrapped for ``st.markdown(..., unsafe_allow_html=True)``."""
    return f"<style>\n{MOBILE_CSS.strip()}\n</style>"
