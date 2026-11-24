"""Live CSV source: a dataset fed by a URL with periodic refresh.

A project can be connected to a CSV URL instead of a manual upload. The
connection (URL, interval, refresh history) is stored per project in
``live_source.json`` next to the persisted dataset, and a shared
APScheduler background scheduler refreshes it on its own: the fetched
CSV is loaded through the Polars fast path, and when its content changed
the persisted working dataset is replaced (the fetched data becomes both
the working and the original copy, with a fresh cleaning history).

Honest limits, by design:

* The refresh updates the *persisted* dataset. An already-open browser
  session keeps showing its own copy until the user reloads or presses
  the manual refresh button on the Data Import page.
* If the user replaces the dataset in that project (another upload, the
  sample), the refresh job notices the persisted source is no longer
  the live URL and leaves the new dataset alone.
* The scheduler lives in the Streamlit server process; a server restart
  drops the in-memory jobs, and they are re-registered from the stored
  records when the app runs again.
"""

from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from config import SETTINGS
from core.alerts import (
    evaluate_rules,
    load_alert_rules,
    notify_alert_events,
    record_alert_events,
)
from core.data_loader import DataLoadError, load_csv_bytes
from core.persistence import load_state, save_state
from core.workspaces import project_dir
from utils.logger import get_logger

log = get_logger("live_source")

_LIVE_FILE = "live_source.json"
_USER_AGENT = "personal-data-analytics/1.0"

#: Refresh intervals offered in the UI (minutes).
INTERVAL_CHOICES = (15, 30, 60, 360, 1440)
DEFAULT_INTERVAL_MINUTES = 60

_scheduler: BackgroundScheduler | None = None


class LiveSourceError(ValueError):
    """Raised when a live source cannot be connected or refreshed."""


def validate_live_url(url: str) -> str:
    """Return the cleaned URL, or raise LiveSourceError."""
    clean = (url or "").strip()
    if not clean:
        raise LiveSourceError("A URL is required.")
    if not (clean.startswith("http://") or clean.startswith("https://")):
        raise LiveSourceError("The URL must start with http:// or https://.")
    return clean


def _record_path(directory: Path | None) -> Path | None:
    if directory is None:
        return None
    return Path(directory) / _LIVE_FILE


def _write_live_source(directory: Path | None, record: dict) -> bool:
    """Write the live-source record atomically (tmp + replace)."""
    path = _record_path(directory)
    if path is None:
        return False
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
    except Exception as exc:
        log.warning("Failed to write live source: {}", exc)
        return False
    return True


def save_live_source(
    directory: Path | None, url: str, interval_minutes: int, *, name: str = "",
) -> bool:
    """Persist a live-source record for a project. Fail-soft."""
    record = {
        "url": url,
        "interval_minutes": int(interval_minutes),
        "name": name or "",
        "last_refreshed_at": None,
        "last_rows": None,
        "last_hash": None,
        "last_error": None,
    }
    return _write_live_source(directory, record)


def load_live_source(directory: Path | None) -> dict[str, Any] | None:
    """Return the project's live-source record, or None."""
    path = _record_path(directory)
    if path is None or not path.exists():
        return None
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning("Failed to read live source: {}", exc)
        return None
    if not isinstance(record, dict) or not record.get("url"):
        return None
    return record


def clear_live_source(directory: Path | None) -> bool:
    """Remove the project's live-source record. Never raises."""
    path = _record_path(directory)
    if path is None:
        return False
    try:
        path.unlink(missing_ok=True)
    except Exception as exc:
        log.warning("Failed to clear live source: {}", exc)
        return False
    return True


def _update_live_source(directory: Path | None, **fields) -> bool:
    """Merge fields into the stored record (refresh history)."""
    record = load_live_source(directory) or {}
    record.update(fields)
    return _write_live_source(directory, record)


def note_live_refresh(directory: Path | None, digest: str, rows: int) -> bool:
    """Record a successful fetch (used right after connecting)."""
    now = datetime.now(timezone.utc).isoformat()
    return _update_live_source(
        directory,
        last_refreshed_at=now,
        last_rows=rows,
        last_hash=digest,
        last_error=None,
    )


def fetch_live_csv(
    url: str, *, timeout: int = 30, max_bytes: int | None = None,
) -> tuple[Any, str, int]:
    """Download a CSV URL and return ``(dataframe, sha256, byte_count)``.

    The download is capped at the app's upload limit, and the CSV is
    parsed through the Polars fast path (``load_csv_bytes``).
    """
    clean = validate_live_url(url)
    limit = max_bytes if max_bytes is not None else SETTINGS.max_upload_bytes
    request = urllib.request.Request(clean, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(limit + 1)
    except urllib.error.URLError as exc:
        raise LiveSourceError(f"Could not download the CSV: {exc}") from exc
    except Exception as exc:
        raise LiveSourceError(f"Could not download the CSV: {exc}") from exc
    if len(raw) > limit:
        raise LiveSourceError(
            f"The CSV is larger than the {limit // (1024 * 1024)} MB limit."
        )
    try:
        df = load_csv_bytes(raw)
    except DataLoadError as exc:
        raise LiveSourceError(str(exc)) from exc
    digest = hashlib.sha256(raw).hexdigest()
    log.info("Fetched live CSV from {} ({} bytes)", clean, len(raw))
    return df, digest, len(raw)


def refresh_live_source(directory: Path | None) -> dict | None:
    """Fetch the project's live source and persist it when it changed.

    Returns a status dict (``changed``, ``rows``, ``refreshed_at``,
    ``error``), or None when no live source is configured. Never raises.
    """
    record = load_live_source(directory)
    if record is None:
        return None
    url = record.get("url")
    try:
        df, digest, _ = fetch_live_csv(url)
    except LiveSourceError as exc:
        _update_live_source(directory, last_error=str(exc))
        log.warning("Live refresh failed for {}: {}", url, exc)
        return {
            "changed": False,
            "rows": record.get("last_rows"),
            "refreshed_at": record.get("last_refreshed_at"),
            "error": str(exc),
        }
    if digest == record.get("last_hash"):
        _update_live_source(directory, last_error=None)
        return {
            "changed": False,
            "rows": len(df),
            "refreshed_at": record.get("last_refreshed_at"),
            "error": None,
        }
    # The dataset on disk is no longer the live one (the user replaced
    # it with an upload or the sample): leave the new dataset alone.
    state = load_state(directory=directory)
    if state is not None and state.get("df_source") not in (None, url):
        log.info(
            "Live refresh skipped: dataset was replaced by {}",
            state.get("df_source"),
        )
        return {
            "changed": False,
            "rows": record.get("last_rows"),
            "refreshed_at": record.get("last_refreshed_at"),
            "error": None,
        }
    name = record.get("name") or (state.get("df_name") if state else "") or url
    save_state(df, df.copy(deep=True), name, url, [], directory=directory)
    now = datetime.now(timezone.utc).isoformat()
    _update_live_source(
        directory,
        last_refreshed_at=now,
        last_rows=len(df),
        last_hash=digest,
        last_error=None,
    )
    # Alert rules are evaluated only on changed data: an unchanged
    # refresh never re-triggers, so a steady value does not spam events.
    events = evaluate_rules(df, load_alert_rules(directory))
    if events:
        record_alert_events(directory, events)
        notify_alert_events(events)
    log.info("Live source refreshed: {} rows from {}", len(df), url)
    return {"changed": True, "rows": len(df), "refreshed_at": now, "error": None}


# ---------------------------------------------------------------------------
# Scheduler (one shared background scheduler for the server process)
# ---------------------------------------------------------------------------


def _job_id(token: str, project_id: str) -> str:
    return f"live-{token}-{project_id}"


def ensure_scheduler() -> BackgroundScheduler:
    """Start the shared background scheduler once (daemon threads)."""
    global _scheduler
    if _scheduler is None or not _scheduler.running:
        _scheduler = BackgroundScheduler(daemon=True)
        _scheduler.start()
        log.info("Live-source scheduler started")
    return _scheduler


def schedule_live_refresh(token: str, project_id: str, interval_minutes: int) -> bool:
    """Schedule periodic refresh for one project (idempotent).

    The job is added only when missing, or rescheduled when the interval
    changed — so a Streamlit rerun never resets the refresh timer.
    """
    try:
        scheduler = ensure_scheduler()
    except Exception as exc:
        log.warning("Could not start live-source scheduler: {}", exc)
        return False
    job_id = _job_id(token, project_id)
    interval = timedelta(minutes=int(interval_minutes))
    existing = scheduler.get_job(job_id)
    if existing is not None:
        trigger = existing.trigger
        if isinstance(trigger, IntervalTrigger) and trigger.interval == interval:
            return True
        try:
            scheduler.reschedule_job(
                job_id, trigger=IntervalTrigger(minutes=int(interval_minutes))
            )
            return True
        except Exception as exc:
            log.warning("Could not reschedule live refresh {}: {}", job_id, exc)
            return False
    directory = project_dir(token, project_id)
    if directory is None:
        return False
    try:
        scheduler.add_job(
            refresh_live_source,
            "interval",
            minutes=int(interval_minutes),
            id=job_id,
            args=[directory],
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
    except Exception as exc:
        log.warning("Could not schedule live refresh {}: {}", job_id, exc)
        return False
    log.info(
        "Scheduled live refresh for project {} every {} minutes",
        project_id, interval_minutes,
    )
    return True


def unschedule_live_refresh(token: str, project_id: str) -> bool:
    """Remove a project's refresh job (no-op when there is none)."""
    if _scheduler is None:
        return True
    try:
        _scheduler.remove_job(_job_id(token, project_id))
    except Exception:
        pass  # job already gone
    return True


def shutdown_scheduler() -> None:
    """Stop the shared scheduler (used by tests)."""
    global _scheduler
    if _scheduler is not None:
        try:
            _scheduler.shutdown(wait=False)
        except Exception:
            pass
        _scheduler = None
