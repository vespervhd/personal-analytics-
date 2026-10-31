"""Central logging setup (loguru).

One console sink for the operator and one rotating file sink under
``data/logs/`` for later inspection. Call :func:`get_logger` from any
module; setup runs exactly once.
"""

from __future__ import annotations

import sys

from loguru import logger

from config import SETTINGS

_LOG_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{extra[module]}</cyan> | {message}"
)

_configured = False


def _add_sinks(level: str) -> None:
    logger.add(sys.stderr, level=level, format=_LOG_FORMAT)
    SETTINGS.ensure_directories()
    logger.add(
        SETTINGS.logs_dir / "app.log",
        level=level,
        format=_LOG_FORMAT,
        rotation="10 MB",
        retention="7 days",
        encoding="utf-8",
    )


def setup_logging(level: str | None = None) -> None:
    """Configure loguru sinks once. Safe to call repeatedly."""
    global _configured
    if _configured:
        return
    _add_sinks((level or SETTINGS.log_level).upper())
    _configured = True


def set_log_level(level: str) -> None:
    """Reconfigure logging at a new level at runtime (Settings page)."""
    global _configured
    logger.remove()
    _add_sinks(level.upper())
    _configured = True


def get_logger(module: str):
    """Return a logger bound to ``module`` (appears in every log line)."""
    setup_logging()
    return logger.bind(module=module)
