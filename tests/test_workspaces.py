"""Tests for core/workspaces.py (public version + multiple projects).

The real ``data/persisted/`` folder is never touched: ``persisted_dir``
is monkeypatched to a temporary directory for every test.
"""

import pandas as pd
import pandas.testing as tm
import pytest

from core import workspaces
from core.persistence import clear_state, load_state, save_state
from core.workspaces import (
    create_project,
    delete_project,
    ensure_default_project,
    is_valid_token,
    load_projects,
    migrate_legacy_state,
    new_token,
    project_dir,
    resolve_token,
    token_dir,
)


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.setattr(workspaces, "persisted_dir", lambda: tmp_path)
    return tmp_path


def _frame(rows):
    return pd.DataFrame({"name": rows, "age": [30 + i for i in range(len(rows))]})


def test_token_validation_rejects_traversal_and_junk(root):
    assert is_valid_token(new_token())
    assert is_valid_token("a" * 8)
    assert is_valid_token("AbC-123_xyz".replace("_", "-"))  # alnum + hyphen only
    assert not is_valid_token("../evil")
    assert not is_valid_token("..%2Fevil")
    assert not is_valid_token("tok/en")
    assert not is_valid_token("has space")
    assert not is_valid_token("short")
    assert not is_valid_token("")
    assert not is_valid_token(None)
    assert not is_valid_token("x" * 65)
    assert token_dir("../evil") is None
    assert project_dir(new_token(), "../evil") is None
    assert project_dir("../evil", new_token()) is None


def test_resolve_token_is_idempotent_and_replaces_invalid(root):
    valid = new_token()
    assert resolve_token(valid) == valid
    fresh = resolve_token("../evil")
    assert is_valid_token(fresh) and fresh != "../evil"
    assert is_valid_token(resolve_token(None))


def test_project_create_switch_delete_round_trip(root):
    token = new_token()
    project_a = create_project(token, "Alpha")
    project_b = create_project(token, "Beta")
    assert project_a and project_b and project_a["id"] != project_b["id"]
    assert [p["name"] for p in load_projects(token)] == ["Alpha", "Beta"]

    dir_a = project_dir(token, project_a["id"])
    dir_b = project_dir(token, project_b["id"])
    assert save_state(_frame(["Ada"]), _frame(["Ada"]), "a.csv", None, [], directory=dir_a)
    assert save_state(_frame(["Grace", "Linus"]), None, "b.csv", None, [], directory=dir_b)

    # Switching: each project loads back exactly its own dataset.
    restored_a = load_state(directory=dir_a)
    restored_b = load_state(directory=dir_b)
    assert restored_a is not None and restored_b is not None
    tm.assert_frame_equal(restored_a["df"], _frame(["Ada"]))
    tm.assert_frame_equal(restored_b["df"], _frame(["Grace", "Linus"]))

    # Deleting A removes its directory + entry, and leaves B untouched.
    assert delete_project(token, project_a["id"])
    assert not dir_a.exists()
    assert [p["id"] for p in load_projects(token)] == [project_b["id"]]
    assert load_state(directory=dir_b) is not None
    # Deleting a project that never existed is still a success.
    assert delete_project(token, new_token())


def test_end_of_run_save_scopes_to_active_project_only(root):
    token = new_token()
    project_a = create_project(token, "Alpha")
    project_b = create_project(token, "Beta")
    dir_a = project_dir(token, project_a["id"])
    dir_b = project_dir(token, project_b["id"])
    assert save_state(_frame(["Ada"]), None, "a.csv", None, [], directory=dir_a)
    assert load_state(directory=dir_b) is None
    assert not (dir_b / "working.parquet").exists()
    # Clearing the active project must not touch the other one.
    assert save_state(_frame(["Grace"]), None, "b.csv", None, [], directory=dir_b)
    assert clear_state(directory=dir_a)
    assert load_state(directory=dir_a) is None
    assert load_state(directory=dir_b) is not None


def test_ensure_default_project_creates_exactly_one(root):
    token = new_token()
    first = ensure_default_project(token, name="My project")
    second = ensure_default_project(token, name="My project")
    assert first is not None and second is not None
    assert first["id"] == second["id"]
    assert len(load_projects(token)) == 1


def test_migration_adopts_legacy_files_exactly_once(root):
    token = new_token()
    assert save_state(
        _frame(["Ada"]), _frame(["Ada", "Grace"]), "legacy.csv", None,
        [{"operation": "Drop missing values"}], directory=root,
    )
    project = migrate_legacy_state(token, base=root)
    assert project is not None
    assert project["name"] == "legacy.csv"
    # Legacy files are gone from the top level.
    assert not (root / "working.parquet").exists()
    assert not (root / "manifest.json").exists()
    assert not (root / "original.parquet").exists()
    # ...and live inside the new project directory.
    directory = project_dir(token, project["id"])
    restored = load_state(directory=directory)
    assert restored is not None
    tm.assert_frame_equal(restored["df"], _frame(["Ada"]))
    tm.assert_frame_equal(restored["df_original"], _frame(["Ada", "Grace"]))
    assert restored["df_name"] == "legacy.csv"
    # Second call is a no-op: adoption happened exactly once.
    assert migrate_legacy_state(token, base=root) is None
    assert len(load_projects(token)) == 1


def test_migration_skipped_when_token_subdirs_exist(root):
    token = new_token()
    create_project(token, "Existing")
    assert save_state(_frame(["Ada"]), None, "legacy.csv", None, [], directory=root)
    assert migrate_legacy_state(token, base=root) is None
    # Legacy files untouched when a token directory already exists.
    assert (root / "working.parquet").exists()
    assert len(load_projects(token)) == 1


def test_migration_uses_default_name_without_manifest_name(root):
    token = new_token()
    assert save_state(_frame(["Ada"]), None, "", None, [], directory=root)
    project = migrate_legacy_state(token, base=root)
    assert project is not None
    assert project["name"] == "Untitled project"
