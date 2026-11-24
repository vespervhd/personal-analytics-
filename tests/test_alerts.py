"""Tests for core/alerts.py and its live-refresh wiring.

The HTTP server is local (an ephemeral port on 127.0.0.1), so no test
depends on the internet.
"""

import functools
import http.server
import json
import threading
import urllib.error
from types import SimpleNamespace

import pandas as pd
import pytest

import core.alerts as alerts_mod
import core.live_source as live
from core.alerts import (
    AlertError,
    add_alert_rule,
    delete_alert_rule,
    evaluate_rule,
    evaluate_rules,
    format_alert_message,
    load_alert_events,
    load_alert_rules,
    mark_alerts_seen,
    notify_alert_events,
    record_alert_events,
    send_telegram_message,
    telegram_configured,
    unseen_alert_count,
)
from core.live_source import refresh_live_source, save_live_source


class _Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):  # keep test output quiet
        pass


@pytest.fixture()
def csv_server(tmp_path):
    """Serve tmp_path over HTTP on an ephemeral local port."""
    handler = functools.partial(_Handler, directory=str(tmp_path))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


@pytest.fixture(autouse=True)
def _shutdown_scheduler():
    yield
    live.shutdown_scheduler()


def _df() -> pd.DataFrame:
    return pd.DataFrame({"price": [10.0, 20.0, 30.0], "name": ["a", "b", "c"]})


def test_above_triggers_only_strictly_over() -> None:
    df = _df()
    assert evaluate_rule(df, {"id": "r1", "column": "price", "condition": "above", "threshold": 25.0})["value"] == 30.0
    # Boundary: max equals the threshold, so no trigger.
    assert evaluate_rule(df, {"id": "r1", "column": "price", "condition": "above", "threshold": 30.0}) is None
    assert evaluate_rule(df, {"id": "r1", "column": "price", "condition": "above", "threshold": 31.0}) is None


def test_below_triggers_only_strictly_under() -> None:
    df = _df()
    assert evaluate_rule(df, {"id": "r1", "column": "price", "condition": "below", "threshold": 15.0})["value"] == 10.0
    # Boundary: min equals the threshold, so no trigger.
    assert evaluate_rule(df, {"id": "r1", "column": "price", "condition": "below", "threshold": 10.0}) is None
    assert evaluate_rule(df, {"id": "r1", "column": "price", "condition": "below", "threshold": 5.0}) is None


def test_evaluate_ignores_missing_or_non_numeric_columns() -> None:
    df = _df()
    assert evaluate_rule(df, {"id": "r1", "column": "nope", "condition": "above", "threshold": 1.0}) is None
    assert evaluate_rule(df, {"id": "r1", "column": "name", "condition": "above", "threshold": 1.0}) is None
    assert evaluate_rule(df, {"id": "r1", "column": "price", "condition": "sideways", "threshold": 1.0}) is None
    assert evaluate_rules(df, []) == []


def test_rule_persistence_round_trip(tmp_path) -> None:
    directory = tmp_path / "proj"
    assert save_live_source(directory, "https://example.com/d.csv", 60, name="d.csv")
    rule = add_alert_rule(directory, "price", "above", 25.0)
    assert rule["column"] == "price" and rule["threshold"] == 25.0
    rules = load_alert_rules(directory)
    assert len(rules) == 1 and rules[0]["id"] == rule["id"]
    assert delete_alert_rule(directory, rule["id"]) is True
    assert load_alert_rules(directory) == []
    assert delete_alert_rule(directory, rule["id"]) is False
    assert load_alert_rules(tmp_path / "missing") == []


def test_add_rule_validation(tmp_path) -> None:
    directory = tmp_path / "proj"
    with pytest.raises(AlertError):
        add_alert_rule(directory, "price", "above", 1.0)  # no live source
    save_live_source(directory, "https://example.com/d.csv", 60, name="d.csv")
    with pytest.raises(AlertError):
        add_alert_rule(directory, "", "above", 1.0)
    with pytest.raises(AlertError):
        add_alert_rule(directory, "price", "sideways", 1.0)
    with pytest.raises(AlertError):
        add_alert_rule(directory, "price", "above", "not-a-number")


def test_events_and_seen_marker(tmp_path) -> None:
    directory = tmp_path / "proj"
    save_live_source(directory, "https://example.com/d.csv", 60, name="d.csv")
    assert unseen_alert_count(directory) == 0
    assert record_alert_events(directory, [{"rule_id": "r1", "column": "price", "condition": "above", "threshold": 5.0, "value": 9.0}]) is True
    events = load_alert_events(directory)
    assert len(events) == 1 and events[0]["value"] == 9.0 and events[0]["at"]
    assert unseen_alert_count(directory) == 1
    assert mark_alerts_seen(directory) is True
    assert unseen_alert_count(directory) == 0


def test_refresh_triggers_once_and_not_on_unchanged(csv_server, tmp_path) -> None:
    (tmp_path / "data.csv").write_text("price\n10\n20\n", encoding="utf-8")
    directory = tmp_path / "proj"
    url = f"{csv_server}/data.csv"
    save_live_source(directory, url, 60, name="data.csv")
    add_alert_rule(directory, "price", "above", 15.0)

    first = refresh_live_source(directory)
    assert first is not None and first["changed"] is True
    events = load_alert_events(directory)
    assert len(events) == 1
    assert events[0]["column"] == "price" and events[0]["value"] == 20.0

    # Unchanged refresh: same data, no new event.
    second = refresh_live_source(directory)
    assert second is not None and second["changed"] is False
    assert len(load_alert_events(directory)) == 1

    # Changed data that still triggers: one more event.
    (tmp_path / "data.csv").write_text("price\n10\n40\n", encoding="utf-8")
    third = refresh_live_source(directory)
    assert third is not None and third["changed"] is True
    events = load_alert_events(directory)
    assert len(events) == 2 and events[0]["value"] == 40.0


# ---------------------------------------------------------------------------
# Telegram forwarding (fake transport — never hits the real network)
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, body: bytes = b'{"ok": true}'):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self) -> bytes:
        return self._body


class _FakeUrlopen:
    def __init__(self, body: bytes = b'{"ok": true}', error=None):
        self.requests = []
        self.body = body
        self.error = error

    def __call__(self, request, timeout=None):
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return _FakeResponse(self.body)


def _tg_settings(monkeypatch, token="TESTTOKEN", chat_id="12345"):
    monkeypatch.setattr(
        alerts_mod,
        "SETTINGS",
        SimpleNamespace(
            telegram_bot_token=token,
            telegram_chat_id=chat_id,
            telegram_configured=bool(token and chat_id),
        ),
    )


def _event() -> dict:
    return {
        "rule_id": "r1",
        "column": "price",
        "condition": "above",
        "threshold": 15.0,
        "value": 20.0,
    }


def test_send_telegram_not_configured(monkeypatch) -> None:
    _tg_settings(monkeypatch, token="", chat_id="")
    assert telegram_configured() is False
    fake = _FakeUrlopen()
    assert send_telegram_message("hi", _urlopen=fake) is False
    assert fake.requests == []


def test_send_telegram_posts_to_bot_api(monkeypatch) -> None:
    _tg_settings(monkeypatch)
    fake = _FakeUrlopen()
    assert send_telegram_message("hello", _urlopen=fake) is True
    assert len(fake.requests) == 1
    request = fake.requests[0]
    assert request.full_url == "https://api.telegram.org/botTESTTOKEN/sendMessage"
    assert request.get_method() == "POST"
    assert json.loads(request.data.decode("utf-8")) == {
        "chat_id": "12345",
        "text": "hello",
    }
    assert request.get_header("Content-type") == "application/json"


def test_send_telegram_api_not_ok(monkeypatch) -> None:
    _tg_settings(monkeypatch)
    fake = _FakeUrlopen(body=b'{"ok": false, "description": "bad"}')
    assert send_telegram_message("hi", _urlopen=fake) is False


def test_send_telegram_network_error_is_false(monkeypatch) -> None:
    _tg_settings(monkeypatch)
    fake = _FakeUrlopen(error=urllib.error.URLError("boom"))
    assert send_telegram_message("hi", _urlopen=fake) is False


def test_notify_alert_events_sends_one_message(monkeypatch) -> None:
    _tg_settings(monkeypatch)
    fake = _FakeUrlopen()
    # notify_alert_events uses the module's default transport, so patch
    # urllib.request.urlopen itself for this test.
    monkeypatch.setattr("urllib.request.urlopen", fake)
    assert notify_alert_events([_event()]) == 1
    assert len(fake.requests) == 1
    text = json.loads(fake.requests[0].data.decode("utf-8"))["text"]
    assert "price" in text and "20.0" in text and "15.0" in text


def test_notify_alert_events_unconfigured(monkeypatch) -> None:
    _tg_settings(monkeypatch, token="", chat_id="")
    fake = _FakeUrlopen()
    monkeypatch.setattr("urllib.request.urlopen", fake)
    assert notify_alert_events([_event()]) == 0
    assert fake.requests == []


def test_notify_alert_events_no_events(monkeypatch) -> None:
    _tg_settings(monkeypatch)
    fake = _FakeUrlopen()
    monkeypatch.setattr("urllib.request.urlopen", fake)
    assert notify_alert_events([]) == 0
    assert fake.requests == []


def test_format_alert_message_both_conditions() -> None:
    text = format_alert_message(
        [
            _event(),
            {
                "rule_id": "r2",
                "column": "stock",
                "condition": "below",
                "threshold": 5.0,
                "value": 2.0,
            },
        ]
    )
    assert "بالاتر از" in text and "پایین‌تر از" in text
    assert "stock" in text and "2.0" in text
