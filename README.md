# Personal Data Analytics Platform

Upload datasets, clean them, explore statistics, visualize insights, detect
anomalies, and generate reports — through an interactive Streamlit dashboard.

## Phase 1: structure and environment setup (this delivery)

- Full modular layout: `core/`, `database/`, `ui/`, `utils/`, `tests/`, `data/`
- `config.py`: single source of truth for paths, limits, and flags
  (override with `PDA_MAX_UPLOAD_MB` / `PDA_LOG_LEVEL`)
- `utils/logger.py`: loguru console + rotating file logging under `data/logs/`
- `app.py`: environment/status page that really probes package imports and
  storage writability — the foundation the Phase 5 dashboard builds on
- `tests/test_config.py`: configuration tests (plain asserts, pytest-ready)

Two justified additions to the spec's tree: `data/logs/` (log file sink needs
a home) and `xlrd` + `pyarrow` in requirements (required for the `.xls` and
`.parquet` formats the spec lists).

## Setup

```bash
cd personal_data_analytics
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Requires Python 3.11+.

## Run

```bash
streamlit run app.py
```

## Test

```bash
pytest -q
# without pytest installed, the Phase 1 tests also run standalone:
python3 -c "
import tests.test_config as t
for name in dir(t):
    if name.startswith('test_'):
        getattr(t, name)()
print('Phase 1 config tests passed')
"
```

## Run

```bash
# Dashboard
streamlit run app.py

# Backend API
uvicorn api.main:app
```

## Test

```bash
pytest -q
ruff check .
```

## Roadmap

1. ✅ Structure and environment setup
2. ✅ Data import and validation (`core/data_loader.py`, `utils/validators.py`)
3. ✅ Data cleaning engine (`core/data_cleaner.py` — preview-before-apply, never mutates originals)
4. ✅ Statistical analysis and EDA (`core/statistics.py`, `core/analyzer.py`)
5. ✅ Interactive dashboard and visualization (`app.py`, `ui/pages/`, `core/visualization.py`)
6. ✅ Machine learning and anomaly detection (`core/ml_engine.py`)
7. ✅ Database integration (SQLite + SQLAlchemy: `database/`)
8. ✅ Report generation (PDF, Excel, CSV, HTML: `core/report_generator.py`)
9. ✅ Testing, optimization, final integration (`tests/`, `pyproject.toml`)

API templates live in `core/templates/` (Jinja2 HTML report). The FastAPI
backend lives in `api/` (added because the original structure predates the
FastAPI requirement).
