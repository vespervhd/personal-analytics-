"""Alert rules on the live source: threshold checks on numeric columns.

A project connected to a live CSV can define rules such as "alert when the
largest value of ``price`` goes above 100". Rules are evaluated whenever a
live refresh fetches *changed* data (scheduled or manual); an unchanged
refresh never re-triggers, so a steady value does not spam events.

Observed value semantics (documented in the UI): for an "above" rule the
observed value is the column maximum; for a "below" rule it is the column
minimum. The comparison is strict: a value exactly equal to the threshold
does not trigger.

Storage: rules, triggered events, and the last-seen marker live inside the
project's ``live_source.json`` record (``alert_rules``, ``alert_events``,
``alerts_last_seen_at``), written atomically (tmp + replace), fail-soft.

Notifications: events are always recorded in-app. When a Telegram bot
token and chat id are configured (``ANALYTICS_TG_BOT_TOKEN`` /
``ANALYTICS_TG_CHAT_ID`` in ``config.SETTINGS``), new events are also
forwarded to Telegram; without them, alerting stays in-app only. The
token is never logged or shown anywhere.
"""

from __future__ import annotations

import json
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from config import SETTINGS
from utils.logger import get_logger

log = get_logger("alerts")

_LIVE_FILE = "live_source.json"

#: Telegram Bot API base URL.
_TG_API = "https://api.telegram.org"

#: Supported rule conditions.
CONDITIONS = ("above", "below")

#: How many triggered events are kept (newest first).
MAX_EVENTS = 50


class AlertError(ValueError):
    """Raised when an alert rule is invalid."""


def evaluate_rule(df: pd.DataFrame, rule: dict) -> dict | None:
    """Check one rule against a DataFrame.

    Returns an event dict (without the timestamp) when the rule triggers,
    else None. Never raises: a missing or non-numeric column simply does
    not trigger.
    """
    try:
        column = rule.get("column")
        condition = rule.get("condition")
        threshold = rule.get("threshold")
        if column not in df.columns or condition not in CONDITIONS:
            return None
        numeric = pd.to_numeric(df[column], errors="coerce").dropna()
        if numeric.empty:
            return None
        if condition == "above":
            observed = float(numeric.max())
            triggered = observed > float(threshold)
        else:
            observed = float(numeric.min())
            triggered = observed < float(threshold)
        if not triggered:
            return None
        return {
            "rule_id": rule.get("id"),
            "column": column,
            "condition": condition,
            "threshold": float(threshold),
            "value": observed,
        }
    except Exception as exc:
        log.warning("Alert evaluation failed for {}: {}", rule, exc)
        return None


def evaluate_rules(df: pd.DataFrame, rules: list[dict]) -> list[dict]:
    """Evaluate every rule; return the triggered events (no timestamps)."""
    events = []
    for rule in rules or []:
        event = evaluate_rule(df, rule)
        if event is not None:
            events.append(event)
    return events


def _record_path(directory: Path | None) -> Path | None:
    if directory is None:
        return None
    return Path(directory) / _LIVE_FILE


def _read_record(directory: Path | None) -> dict | None:
    path = _record_path(directory)
    if path is None or not path.exists():
        return None
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning("Failed to read live source for alerts: {}", exc)
        return None
    return record if isinstance(record, dict) else None


def _write_record(directory: Path | None, record: dict) -> bool:
    path = _record_path(directory)
    if path is None:
        return False
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
    except Exception as exc:
        log.warning("Failed to write alert rules: {}", exc)
        return False
    return True


def load_alert_rules(directory: Path | None) -> list[dict]:
    """Return the project's alert rules (empty list when none)."""
    record = _read_record(directory)
    if record is None:
        return []
    rules = record.get("alert_rules")
    return list(rules) if isinstance(rules, list) else []


def load_alert_events(directory: Path | None) -> list[dict]:
    """Return triggered alert events, newest first."""
    record = _read_record(directory)
    if record is None:
        return []
    events = record.get("alert_events")
    return list(events) if isinstance(events, list) else []


def add_alert_rule(
    directory: Path | None, column: str, condition: str, threshold: float
) -> dict:
    """Add a rule and persist it. Raises AlertError on invalid input."""
    if directory is None:
        raise AlertError("No project directory.")
    column = (column or "").strip()
    if not column:
        raise AlertError("A column is required.")
    if condition not in CONDITIONS:
        raise AlertError("Condition must be 'above' or 'below'.")
    try:
        threshold_value = float(threshold)
    except (TypeError, ValueError) as exc:
        raise AlertError("Threshold must be a number.") from exc
    record = _read_record(directory)
    if record is None:
        raise AlertError("No live source is connected for this project.")
    rule = {
        "id": uuid.uuid4().hex[:12],
        "column": column,
        "condition": condition,
        "threshold": threshold_value,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    rules = record.get("alert_rules")
    rules = list(rules) if isinstance(rules, list) else []
    rules.append(rule)
    record["alert_rules"] = rules
    if not _write_record(directory, record):
        raise AlertError("Could not save the alert rule.")
    return rule


def delete_alert_rule(directory: Path | None, rule_id: str) -> bool:
    """Remove a rule by id. Returns True when a rule was removed."""
    record = _read_record(directory)
    if record is None:
        return False
    rules = record.get("alert_rules")
    rules = list(rules) if isinstance(rules, list) else []
    kept = [r for r in rules if r.get("id") != rule_id]
    if len(kept) == len(rules):
        return False
    record["alert_rules"] = kept
    return _write_record(directory, record)


def record_alert_events(directory: Path | None, events: list[dict]) -> bool:
    """Append triggered events (newest first, capped). Fail-soft."""
    if not events:
        return True
    record = _read_record(directory)
    if record is None:
        return False
    now = datetime.now(timezone.utc).isoformat()
    stamped = [{**event, "at": now} for event in events]
    existing = record.get("alert_events")
    existing = list(existing) if isinstance(existing, list) else []
    record["alert_events"] = (stamped + existing)[:MAX_EVENTS]
    return _write_record(directory, record)


def unseen_alert_count(directory: Path | None) -> int:
    """How many triggered events are newer than the last-seen marker."""
    record = _read_record(directory)
    if record is None:
        return 0
    seen_at = record.get("alerts_last_seen_at") or ""
    events = record.get("alert_events")
    if not isinstance(events, list):
        return 0
    return sum(1 for event in events if str(event.get("at", "")) > str(seen_at))


def mark_alerts_seen(directory: Path | None) -> bool:
    """Mark all current events as seen. Fail-soft."""
    record = _read_record(directory)
    if record is None:
        return False
    record["alerts_last_seen_at"] = datetime.now(timezone.utc).isoformat()
    return _write_record(directory, record)


# ---------------------------------------------------------------------------
# Telegram forwarding (stdlib only, fail-soft, token never logged)
# ---------------------------------------------------------------------------


def telegram_configured() -> bool:
    """True when a bot token and a chat id are both configured."""
    return bool(SETTINGS.telegram_configured)


def send_telegram_message(text: str, *, timeout: float = 10.0, _urlopen=None) -> bool:
    """Send one plain message through the configured Telegram bot.

    Returns False when Telegram is not configured or the send fails;
    never raises. The token is never written to logs: error text from
    the HTTP layer can contain the request URL, so only the exception
    type is logged. ``_urlopen`` exists only so tests can inject a fake
    transport — production always uses :func:`urllib.request.urlopen`.
    """
    token = SETTINGS.telegram_bot_token
    chat_id = SETTINGS.telegram_chat_id
    if not token or not chat_id:
        return False
    url = f"{_TG_API}/bot{token}/sendMessage"
    payload = json.dumps({"chat_id": chat_id, "text": text}, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    opener = _urlopen if _urlopen is not None else urllib.request.urlopen
    try:
        with opener(request, timeout=timeout) as response:
            body = response.read()
        result = json.loads(body.decode("utf-8"))
    except Exception as exc:
        # No exception detail: it may contain the request URL (and token).
        log.warning("Telegram send failed: {}", type(exc).__name__)
        return False
    return bool(isinstance(result, dict) and result.get("ok"))


def format_alert_message(events: list[dict], lang: str = "fa") -> str:
    """Render triggered events as one short Telegram message."""
    from ui.i18n import t

    lines = [t("tg_alert_title", lang=lang)]
    for event in events:
        condition = (
            t("alert_condition_above", lang=lang)
            if event.get("condition") == "above"
            else t("alert_condition_below", lang=lang)
        )
        lines.append(
            t("tg_alert_line", lang=lang).format(
                column=event.get("column"),
                cond=condition,
                threshold=event.get("threshold"),
                value=event.get("value"),
            )
        )
    return "\n".join(lines)


def notify_alert_events(events: list[dict], lang: str = "fa") -> int:
    """Forward new alert events to Telegram when configured.

    Returns 1 when a message was sent, 0 otherwise (no events, not
    configured, or the send failed). Fail-soft: a Telegram failure
    never breaks the in-app recording that already happened.
    """
    if not events or not telegram_configured():
        return 0
    try:
        text = format_alert_message(events, lang=lang)
    except Exception as exc:
        log.warning("Telegram alert formatting failed: {}", exc)
        return 0
    return 1 if send_telegram_message(text) else 0
