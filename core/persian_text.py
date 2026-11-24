"""Persian text and font helpers shared by charts, PDF and web UI.

Single home for everything Persian-font so no surface depends on
Google Fonts or on a system font package:

* :func:`reshape_persian` — reshape + reorder for renderers with no
  shaping engine (matplotlib, ReportLab). Browsers shape natively,
  so Plotly and the Streamlit UI never get reshaped text.
* Bundled Vazirmatn files under ``assets/fonts/`` — a TTF pair for
  matplotlib/ReportLab and woff2 subsets for the web UI.
* :func:`font_face_css` — ``@font-face`` block with base64 data URIs,
  so the dashboard renders Vazirmatn even when Google Fonts is
  unreachable (slow or filtered connection).
* :func:`ensure_matplotlib_persian` — register the bundled TTFs with
  matplotlib and switch its default family to Vazirmatn.
"""

from __future__ import annotations

import base64
from functools import lru_cache
from pathlib import Path

from utils.logger import get_logger

log = get_logger("persian_text")

#: Bundled Vazirmatn files (copied into the repo so the app never
#: depends on a font download or a system font package).
_ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
TTF_REGULAR = _ASSETS_DIR / "Vazirmatn-Regular.ttf"
TTF_BOLD = _ASSETS_DIR / "Vazirmatn-Bold.ttf"
WOFF2_ARABIC = _ASSETS_DIR / "vazirmatn-arabic.woff2"
WOFF2_LATIN = _ASSETS_DIR / "vazirmatn-latin.woff2"

#: Arabic-script ranges (base letters, supplements, presentation forms).
_ARABIC_RANGES = (
    (0x0600, 0x06FF),
    (0x0750, 0x077F),
    (0x08A0, 0x08FF),
    (0xFB50, 0xFDFF),
    (0xFE70, 0xFEFF),
)


def is_arabic_char(char: str) -> bool:
    """Return True when ``char`` is in an Arabic-script range."""
    code = ord(char)
    return any(start <= code <= end for start, end in _ARABIC_RANGES)


# Short alias used inside this module.
_is_arabic_char = is_arabic_char


def contains_arabic(text: str) -> bool:
    """Return True when ``text`` holds any Arabic-script character."""
    return any(_is_arabic_char(char) for char in text)


def reshape_persian(text: str) -> str:
    """Reshape + reorder Persian text into visual order for dumb renderers.

    ``arabic_reshaper`` joins letters into their presentation forms and
    ``python-bidi`` reorders the line so a left-to-right renderer (PDF,
    matplotlib) draws it correctly. Non-Arabic text passes through
    unchanged apart from the bidi pass, which leaves pure Latin order
    intact.
    """
    import arabic_reshaper
    from bidi.algorithm import get_display

    return get_display(arabic_reshaper.reshape(text))


def bundled_font_pair() -> tuple[str, str] | None:
    """Return the bundled (regular, bold) Vazirmatn TTF paths, if present."""
    if TTF_REGULAR.is_file() and TTF_BOLD.is_file():
        return str(TTF_REGULAR), str(TTF_BOLD)
    if TTF_REGULAR.is_file():
        return str(TTF_REGULAR), str(TTF_REGULAR)
    return None


def _data_uri(path: Path) -> str:
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:font/woff2;base64,{encoded}"


@lru_cache(maxsize=1)
def font_face_css() -> str:
    """Return ``@font-face`` rules for the bundled Vazirmatn woff2 files.

    The files are the variable font (weight 100..900), split into an
    Arabic subset and a Latin subset, so one rule per subset covers
    every weight. Embedded as data URIs: no network request, no
    Google Fonts dependency, works offline and behind filters.
    """
    if not (WOFF2_ARABIC.is_file() and WOFF2_LATIN.is_file()):
        log.warning("Bundled Vazirmatn woff2 files missing; web UI falls back to system fonts.")
        return ""
    arabic_range = (
        "U+0600-06FF, U+0750-077F, U+0870-0891, U+0897-08E1, U+08E3-08FF, "
        "U+200C-200E, U+2010-2011, U+204F, U+2E41, U+FB50-FDFF, U+FE70-FE74, "
        "U+FE76-FEFC"
    )
    latin_range = (
        "U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, "
        "U+02DC, U+2000-206F, U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215, "
        "U+FEFF, U+FFFD"
    )
    return (
        "@font-face {\n"
        "  font-family: 'Vazirmatn';\n"
        "  font-style: normal;\n"
        "  font-weight: 100 900;\n"
        "  font-display: swap;\n"
        f"  src: url({_data_uri(WOFF2_ARABIC)}) format('woff2');\n"
        f"  unicode-range: {arabic_range};\n"
        "}\n"
        "@font-face {\n"
        "  font-family: 'Vazirmatn';\n"
        "  font-style: normal;\n"
        "  font-weight: 100 900;\n"
        "  font-display: swap;\n"
        f"  src: url({_data_uri(WOFF2_LATIN)}) format('woff2');\n"
        f"  unicode-range: {latin_range};\n"
        "}"
    )


_MPL_READY = False


def ensure_matplotlib_persian() -> str | None:
    """Register bundled Vazirmatn with matplotlib; return its family name.

    Idempotent: registration and the rcParams switch happen once per
    process. Returns ``"Vazirmatn"`` on success, ``None`` when the
    bundled files are missing (callers keep matplotlib's defaults and
    still reshape text, which is better than raw Persian).
    """
    global _MPL_READY
    if _MPL_READY:
        return "Vazirmatn"
    pair = bundled_font_pair()
    if pair is None:
        log.warning("Bundled Vazirmatn TTFs missing; matplotlib keeps its default font.")
        return None
    try:
        import matplotlib
        from matplotlib import font_manager

        for path in pair:
            font_manager.fontManager.addfont(path)
        matplotlib.rcParams["font.family"] = "Vazirmatn"
        matplotlib.rcParams["axes.unicode_minus"] = False
    except Exception as exc:  # pragma: no cover - defensive; font files ship with the repo
        log.warning("Could not register Vazirmatn with matplotlib: {}", exc)
        return None
    _MPL_READY = True
    return "Vazirmatn"


def localize_matplotlib_texts(fig) -> None:
    """Reshape every Persian text object inside a matplotlib figure.

    Walks all :class:`matplotlib.text.Text` artists (titles, axis
    labels, tick labels, annotations) and rewrites Persian ones into
    visual order. Pure-Persian texts also switch to the Vazirmatn
    family (registered first by :func:`ensure_matplotlib_persian`);
    mixed Latin/Persian texts keep the figure's default font, which
    covers Latin plus every common reshaped Persian form. Latin-only
    texts are untouched.

    Tick labels need special handling: matplotlib regenerates them
    from the axis formatter on every draw, so merely rewriting the
    Text objects is undone by the next draw. They are therefore
    pinned first — read in logical order, reshaped, and installed
    explicitly (``set_ticks`` + ``set_ticklabels``), which survives
    later draws — and skipped by the general walk afterwards, so
    they are never reshaped twice.
    """
    from matplotlib.text import Text

    family = ensure_matplotlib_persian()
    try:
        fig.canvas.draw()
    except Exception:  # pragma: no cover - Agg figures always draw
        pass
    pinned: set[int] = set()
    for ax in fig.get_axes():
        for axis in (ax.xaxis, ax.yaxis):
            labels = axis.get_ticklabels()
            texts = [label.get_text() for label in labels]
            if texts and any(contains_arabic(text) for text in texts):
                axis.set_ticks(axis.get_ticklocs())
                axis.set_ticklabels([reshape_persian(text) for text in texts])
                pinned.update(id(label) for label in axis.get_ticklabels())
    for obj in fig.findobj(lambda item: isinstance(item, Text)):
        if id(obj) in pinned:
            continue
        text = obj.get_text()
        if text and contains_arabic(text):
            obj.set_text(reshape_persian(text))
            if family and not any("A" <= c <= "z" for c in text):
                obj.set_fontfamily(family)
