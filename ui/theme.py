"""Light "paper" theme for the analytics dashboard (SAMPLE — unwired).

A single global CSS module, injected once from ``app.py`` next to the
existing ``mobile_style()`` call if the user approves the sample. It only
touches presentation: no strings, no widgets, no session state, so it
cannot disturb navigation, i18n, workspaces, or any of the three new
features (alerts, versions, Google Sheets).

Direction: warm light paper, one restrained teal accent, Vazirmatn
everywhere. No gradients, no purple/blue, no emoji. All text colors meet
WCAG AA against their backgrounds (ink on paper ~14:1, teal #0F766E on
white ~5.0:1, muted #6B6862 on white ~5.2:1).

Tokens (single source of truth, mirrored in
``.streamlit/config.toml.sample``):

* paper background  #F7F6F2   card / sidebar  #FFFFFF
* border            #E6E2DB   ink text        #1F1E1C
* muted text        #6B6862   accent teal     #0F766E
* accent soft tint  #E6F2F0   radius 12px cards / 8px controls
* type: Vazirmatn; H1 22px, H2 17px, body 14px, metric value 26px

Known limit, stated honestly: Streamlit's sidebar navigation is a radio
group and exposes no reliable "active item" class, so the theme cannot
reproduce the highlighted active-nav row shown in the HTML sample. The
real app keeps the radio dot as its active marker; a highlighted nav row
would need a custom nav widget and is out of scope for this sample.
"""

from __future__ import annotations

#: Raw CSS, kept separate from the ``<style>`` wrapper so tests can
#: inspect the rules without parsing HTML.
THEME_CSS = """
/* ---- Paper theme: base ------------------------------------------ */
[data-testid="stAppViewContainer"] {
  background-color: #F7F6F2;
  color: #1F1E1C;
}
.block-container {
  padding: 1.5rem 1.5rem 2rem 1.5rem !important;
  max-width: 72rem;
}
html, body, [data-testid="stAppViewContainer"],
[data-testid="stSidebar"], .stApp input, .stApp textarea,
.stApp select, .stApp button {
  font-family: 'Vazirmatn', Tahoma, sans-serif;
}
h1, h2, h3 {
  color: #1F1E1C;
  letter-spacing: -0.01em;
}
h1 { font-size: 1.375rem !important; font-weight: 700; }
h2 { font-size: 1.0625rem !important; font-weight: 700; }
h3 { font-size: 0.9375rem !important; font-weight: 700; }
p, .stMarkdown { color: #1F1E1C; }
[data-testid="stCaptionContainer"], .stCaption {
  color: #6B6862 !important;
}

/* ---- Sidebar ------------------------------------------------------ */
[data-testid="stSidebar"] {
  background-color: #FFFFFF;
  border-inline-start: 1px solid #E6E2DB;
}
[data-testid="stSidebar"] [data-testid="stWidgetLabel"],
[data-testid="stSidebar"] label {
  color: #6B6862;
  font-size: 0.8rem;
}
[data-testid="stSidebar"] [role="radiogroup"] label {
  color: #1F1E1C;
  font-size: 0.9rem;
  padding: 0.15rem 0;
}

/* ---- Sidebar collapse button ---------------------------------------- */
/* Streamlit draws this as a Material Symbols ligature; when that icon
   font fails to load, the raw "keyboard_double_arrow_left" text shows
   instead of an arrow (seen live). Hide the ligature and draw a plain
   double chevron, so the button never shows raw text on any browser. */
[data-testid="stSidebarCollapseButton"] {
  font-size: 0 !important;
}
[data-testid="stSidebarCollapseButton"]::after {
  content: "«";
  font-size: 1.5rem !important;
  line-height: 1;
  color: #6B6862;
}

/* ---- Metric cards --------------------------------------------------- */
/* Streamlit renders each metric bare; the card chrome comes from here. */
[data-testid="stMetric"] {
  background-color: #FFFFFF;
  border: 1px solid #E6E2DB;
  border-radius: 12px;
  padding: 0.85rem 1rem 0.9rem 1rem;
}
[data-testid="stMetricValue"] {
  color: #1F1E1C !important;
  font-size: 1.625rem !important;
  font-weight: 700;
}
[data-testid="stMetricLabel"] {
  color: #6B6862 !important;
  font-size: 0.78rem !important;
}

/* ---- Buttons ---------------------------------------------------------- */
/* Default buttons stay quiet (white + border); only kind="primary" is
   filled teal, so pages keep their own emphasis. */
.stButton > button, .stDownloadButton > button,
.stFormSubmitButton > button {
  background-color: #FFFFFF;
  color: #1F1E1C;
  border: 1px solid #E6E2DB;
  border-radius: 8px;
}
.stButton > button:hover, .stDownloadButton > button:hover,
.stFormSubmitButton > button:hover {
  border-color: #0F766E;
  color: #0F766E;
}
.stButton > button[kind="primary"],
.stDownloadButton > button[kind="primary"] {
  background-color: #0F766E;
  border-color: #0F766E;
  color: #FFFFFF;
}
.stButton > button[kind="primary"]:hover,
.stDownloadButton > button[kind="primary"]:hover {
  background-color: #0B5E57;
  color: #FFFFFF;
}

/* ---- Tables ----------------------------------------------------------- */
[data-testid="stDataFrame"] {
  border: 1px solid #E6E2DB;
  border-radius: 12px;
  overflow: hidden;
}

/* ---- Inputs ----------------------------------------------------------- */
.stApp input, .stApp textarea, .stApp select {
  border-radius: 8px !important;
}
.stApp input:focus, .stApp textarea:focus, .stApp select:focus {
  border-color: #0F766E !important;
  box-shadow: 0 0 0 1px #0F766E !important;
}

/* ---- Info / alert boxes stay quiet ------------------------------------ */
[data-testid="stAlert"] {
  border-radius: 12px;
}
"""


def theme_style() -> str:
    """Return the paper-theme CSS wrapped for ``st.markdown(..., unsafe_allow_html=True)``.

    Not wired anywhere yet: call from ``app.py`` next to ``mobile_style()``
    only after the user approves the sample.
    """
    return f"<style>\n{THEME_CSS.strip()}\n</style>"
