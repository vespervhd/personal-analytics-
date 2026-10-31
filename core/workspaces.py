"""Per-visitor workspaces and multiple projects.

Item 5 (public version) problem: ``data/persisted/`` used to be one
server-global directory, so one visitor's dataset was restored for the
next visitor. Item 7 adds multiple named projects per visitor.

Design (exactly as specified):

* A workspace token comes from the ``?ws=`` URL query parameter. Only
  tokens matching ``^[A-Za-z0-9-]{8,64}$`` are accepted (a uuid4 hex
  token passes); anything else — including path traversal such as
  ``../`` — is rejected and a fresh token is generated instead. The
  token is never used raw as a filesystem path without validation.
* On-disk layout under ``data/persisted/``::

      <token>/projects.json
      <token>/<project_id>/working.parquet
      <token>/<project_id>/original.parquet
      <token>/<project_id>/manifest.json

  The per-project files are exactly the set ``core.persistence`` already
  writes; callers pass ``directory=project_dir(...)`` so end-of-run
  saves and delete-clears touch only the active project.
* ``projects.json`` is a list of ``{id, name, created_at, updated_at}``
  dicts. Every function here fails soft (logs, returns a falsy value)
  like ``core.persistence`` — a projects-file problem must never break
  the UI.
* Legacy migration: if top-level ``working.parquet`` / ``manifest.json``
  files exist directly under ``data/persisted/`` AND no subdirectory
  exists there yet, the legacy state is moved into the first token's
  first project (project name from the manifest's ``df_name``, else a
  default) and the legacy files are removed. This happens exactly once
  because the move deletes the legacy files. Honest limitation: a
  token-less legacy state cannot be attributed to anyone, so the first
  visitor after deploy (in practice the owner, who restarts the app
  first) adopts it; after adoption no later visitor can inherit it.
"""

from __future__ import annotations

import json
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.persistence import persisted_dir
from utils.logger import get_logger

log = get_logger("workspaces")

#: Strict token shape: uuid hex passes; slashes, dots and other path
#: characters are rejected, so a token can never escape its directory.
TOKEN_RE = re.compile(r"^[A-Za-z0-9-]{8,64}$")

#: Project ids are uuid4 hex strings, so they match TOKEN_RE too.
_PROJECTS_FILE = "projects.json"
_DEFAULT_PROJECT_NAME = "Untitled project"

_LEGACY_FILES = ("working.parquet", "original.parquet", "manifest.json")


def is_valid_token(token: str | None) -> bool:
    """Return True only for tokens safe to use as a directory name."""
    return isinstance(token, str) and TOKEN_RE.match(token) is not None


def new_token() -> str:
    """Generate a fresh workspace token (uuid4 hex, 32 chars)."""
    return uuid.uuid4().hex


def resolve_token(raw: str | None) -> str:
    """Return ``raw`` when it is a valid token, else a fresh token.

    Idempotent: calling this again with an already-valid token returns
    the same token, so a rerun caused by writing the token into the URL
    query params is harmless.
    """
    if is_valid_token(raw):
        return raw
    return new_token()


def token_dir(token: str) -> Path | None:
    """Return ``data/persisted/<token>``, or None for an invalid token."""
    if not is_valid_token(token):
        log.warning("Refused invalid workspace token")
        return None
    return persisted_dir() / token


def project_dir(token: str, project_id: str) -> Path | None:
    """Return the directory for one project, or None for bad input."""
    base = token_dir(token)
    if base is None or not is_valid_token(project_id):
        return None
    return base / project_id


def _projects_path(token: str) -> Path | None:
    base = token_dir(token)
    return base / _PROJECTS_FILE if base is not None else None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_projects(token: str) -> list[dict[str, Any]]:
    """Return the token's project list (empty list on any problem)."""
    path = _projects_path(token)
    if path is None or not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning("Failed to read projects list: {}", exc)
        return []
    if not isinstance(data, list):
        return []
    projects = [p for p in data if isinstance(p, dict) and is_valid_token(str(p.get("id", "")))]
    return projects


def _write_projects(token: str, projects: list[dict[str, Any]]) -> bool:
    path = _projects_path(token)
    if path is None:
        return False
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(projects, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        log.warning("Failed to write projects list: {}", exc)
        return False
    return True


def create_project(token: str, name: str | None) -> dict[str, Any] | None:
    """Create a project entry and return it, or None on bad input/error."""
    if token_dir(token) is None:
        return None
    clean = (name or "").strip()
    project = {
        "id": uuid.uuid4().hex,
        "name": clean or _DEFAULT_PROJECT_NAME,
        "created_at": _now(),
        "updated_at": _now(),
    }
    projects = load_projects(token)
    projects.append(project)
    if not _write_projects(token, projects):
        return None
    return project


def ensure_default_project(token: str, name: str | None = None) -> dict[str, Any] | None:
    """Return the first project, creating a default one when none exist."""
    projects = load_projects(token)
    if projects:
        return projects[0]
    return create_project(token, name)


def touch_project(token: str, project_id: str) -> bool:
    """Refresh a project's ``updated_at``. Returns False when not found."""
    projects = load_projects(token)
    for project in projects:
        if project.get("id") == project_id:
            project["updated_at"] = _now()
            return _write_projects(token, projects)
    return False


def delete_project(token: str, project_id: str) -> bool:
    """Remove a project entry and its directory. Never raises.

    Returns True when the entry is gone (including when it never
    existed); False only when the entry or directory could not be
    removed.
    """
    directory = project_dir(token, project_id)
    if directory is None:
        return False
    projects = load_projects(token)
    remaining = [p for p in projects if p.get("id") != project_id]
    if len(remaining) == len(projects) and not directory.exists():
        return True
    try:
        if directory.exists():
            shutil.rmtree(directory)
    except Exception as exc:
        log.warning("Failed to delete project directory: {}", exc)
        return False
    if len(remaining) != len(projects) and not _write_projects(token, remaining):
        return False
    return True


def has_legacy_state(base: Path | None = None) -> bool:
    """Return True when top-level legacy persisted files exist."""
    root = Path(base) if base is not None else persisted_dir()
    return (root / "working.parquet").exists() and (root / "manifest.json").exists()


def migrate_legacy_state(token: str, base: Path | None = None) -> dict[str, Any] | None:
    """Adopt a legacy top-level persisted state into this token's project.

    Runs only when legacy files exist AND ``data/persisted/`` has no
    subdirectories yet. Returns the created project, or None when there
    is nothing to migrate (or migration failed). Because the legacy
    files are moved away, a second call is a no-op: adoption happens
    exactly once.
    """
    root = Path(base) if base is not None else persisted_dir()
    if not has_legacy_state(root):
        return None
    try:
        has_subdirs = any(child.is_dir() for child in root.iterdir())
    except OSError as exc:
        log.warning("Legacy migration check failed: {}", exc)
        return None
    if has_subdirs:
        return None
    manifest_name = ""
    try:
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        manifest_name = str(manifest.get("df_name") or "")
    except Exception as exc:
        log.warning("Legacy manifest unreadable, using default project name: {}", exc)
    project = create_project(token, manifest_name or None)
    if project is None:
        return None
    directory = project_dir(token, project["id"])
    if directory is None:
        return None
    try:
        directory.mkdir(parents=True, exist_ok=True)
        for filename in _LEGACY_FILES:
            source = root / filename
            if source.exists():
                shutil.move(str(source), str(directory / filename))
    except Exception as exc:
        log.warning("Legacy migration failed: {}", exc)
        return None
    log.info("Adopted legacy persisted state into project {}", project["id"])
    return project
