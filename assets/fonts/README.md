# Bundled Vazirmatn fonts

These files ship in the repo so Persian rendering never depends on
Google Fonts or a system font package. They are binary and are NOT
committed through the GitHub connector (it only pushes UTF-8 text);
they are fetched at deploy time — see the deploy commands in the
goal notes. Verify with `sha256sum` after fetching.

- `Vazirmatn-Regular.ttf` (weight 400) and `Vazirmatn-Bold.ttf`
  (weight 700), static instances from Vazirmatn v33.003:
  - https://cdn.jsdelivr.net/gh/rastikerdar/vazirmatn@v33.003/fonts/ttf/Vazirmatn-Regular.ttf
  - https://cdn.jsdelivr.net/gh/rastikerdar/vazirmatn@v33.003/fonts/ttf/Vazirmatn-Bold.ttf
  - Used by matplotlib (`core.persian_text.ensure_matplotlib_persian`)
    and as the PDF fallback (`core.report_generator.find_arabic_font`).
  - sha256 (v33.003):
    - Regular: b69fd4c680b8f3f225feabcc655a2c585d97627b8f5f5c0f9985e894069f3a56
    - Bold: f635fdbea28f265de395ba83b4b1570dcf2f58d13c65469e61903b1c2d2ae723

- `vazirmatn-arabic.woff2` and `vazirmatn-latin.woff2`, variable-font
  subsets (weight 100..900) from Google Fonts v16, byte-identical to:
  - https://fonts.gstatic.com/s/vazirmatn/v16/Dxxo8j6PP2D_kU2muijlGMWWMmk.woff2
  - https://fonts.gstatic.com/s/vazirmatn/v16/Dxxo8j6PP2D_kU2muijlHcWW.woff2
  - Embedded as base64 `@font-face` by
    `core.persian_text.font_face_css` for the web UI and HTML reports.
  - sha256 (v16):
    - Arabic: 84a382e46c30fb4f73d0e3800c16d0af15888e2731e57fa5f93e2c29a2c6a957
    - Latin: d29c041cd4294af893cf3c01dfab6d47202c667ab55d702f68782599918c651d
