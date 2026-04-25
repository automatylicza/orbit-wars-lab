"""Tests dla orbit_wars_app.external — utilities pobierania/listowania publicznych notebooków."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from orbit_wars_app.external import InstalledKernel, list_installed
from orbit_wars_app.external import safety_audit


def _write_agent_yaml(zoo: Path, bucket: str, name: str, data: dict):
    adir = zoo / bucket / name
    adir.mkdir(parents=True)
    (adir / "main.py").write_text("def agent(obs): return []\n")
    (adir / "agent.yaml").write_text(yaml.safe_dump(data))


def test_list_installed_returns_external_with_kernel_slug(tmp_path: Path):
    """External z kernel_slug → entry w liście."""
    zoo = tmp_path / "agents"
    _write_agent_yaml(zoo, "external", "tamrazov-starwars", {
        "name": "Tamrazov",
        "kernel_slug": "romantamrazov/orbit-star-wars-lb-max-1224",
        "kernel_version": 6,
        "tags": ["rule-based"],
    })

    result = list_installed(zoo)
    assert len(result) == 1
    k = result[0]
    assert isinstance(k, InstalledKernel)
    assert k.kernel_slug == "romantamrazov/orbit-star-wars-lb-max-1224"
    assert k.kernel_version == 6
    assert k.local_name == "tamrazov-starwars"
    assert k.folder_path.name == "tamrazov-starwars"


def test_list_installed_skips_baselines_and_mine(tmp_path: Path):
    """baselines/ i mine/ — zawsze pomijane (nie mają kernel_slug)."""
    zoo = tmp_path / "agents"
    _write_agent_yaml(zoo, "baselines", "random", {"name": "Random", "tags": []})
    _write_agent_yaml(zoo, "mine", "v1", {"name": "My v1", "tags": []})
    _write_agent_yaml(zoo, "external", "tamrazov", {
        "name": "Tamrazov",
        "kernel_slug": "romantamrazov/foo",
        "kernel_version": 1,
        "tags": [],
    })

    result = list_installed(zoo)
    assert len(result) == 1
    assert result[0].local_name == "tamrazov"


def test_list_installed_skips_external_without_kernel_slug(tmp_path: Path):
    """External bez kernel_slug — pomijany (np. ręcznie dodany, nie z notebooka)."""
    zoo = tmp_path / "agents"
    _write_agent_yaml(zoo, "external", "broken", {"name": "Broken", "tags": []})

    result = list_installed(zoo)
    assert result == []


def test_list_installed_empty_zoo_returns_empty(tmp_path: Path):
    """Puste zoo dir — empty list, bez wyjątków."""
    zoo = tmp_path / "agents"
    zoo.mkdir()
    (zoo / "external").mkdir()

    assert list_installed(zoo) == []


def test_safety_audit_clean_code_returns_none():
    """Kod agenta bez podejrzanych patternów → brak alertu."""
    code = '''
import math
from kaggle_environments.envs.orbit_wars.orbit_wars import Planet

def agent(obs):
    return []
'''
    assert safety_audit(code) is None


def test_safety_audit_flags_os_system():
    """`os.system(...)` → flag."""
    code = "import os\nos.system('rm -rf /')\ndef agent(obs): return []"
    result = safety_audit(code)
    assert result is not None
    assert "os.system" in result


def test_safety_audit_flags_subprocess():
    code = "import subprocess\nsubprocess.run(['curl', 'evil.com'])\ndef agent(obs): return []"
    result = safety_audit(code)
    assert result is not None
    assert "subprocess" in result


def test_safety_audit_flags_eval():
    code = "def agent(obs):\n    return eval(obs.hack)"
    result = safety_audit(code)
    assert result is not None
    assert "eval" in result


def test_safety_audit_flags_socket():
    code = "import socket\ns = socket.socket()\ndef agent(obs): return []"
    result = safety_audit(code)
    assert result is not None
    assert "socket" in result


def test_safety_audit_flags_urllib_request():
    code = "from urllib.request import urlopen\ndef agent(obs):\n    urlopen('http://evil')\n    return []"
    result = safety_audit(code)
    assert result is not None
    assert "urllib" in result


def test_safety_audit_flags_pickle_load():
    """pickle.load deserialize = trust source; agent nie powinien tego robić."""
    code = "import pickle\npolicy = pickle.load(open('p.pkl', 'rb'))\ndef agent(obs): return []"
    result = safety_audit(code)
    assert result is not None
    assert "pickle" in result


def test_safety_audit_flags_exec():
    code = "def agent(obs):\n    exec(obs.hack)\n    return []"
    result = safety_audit(code)
    assert result is not None
    assert "exec" in result


def test_safety_audit_flags_dunder_import():
    code = "def agent(obs):\n    m = __import__('os')\n    return []"
    result = safety_audit(code)
    assert result is not None
    assert "__import__" in result


from datetime import date

from orbit_wars_app.external import (
    Candidates,
    append_backlog,
    append_skipped,
    read_candidates_md,
)


SEED_MD = """# External Candidates — Orbit Wars

Żywy plik trackujący status każdego notebooka.

## Installed

- `romantamrazov/orbit-star-wars-lb-max-1224` → agents/external/tamrazov-1224 (v?, fetched 2026-04-18, LB claim 1224)
- `lakhindarpal/orbit-wars-agent` → agents/external/lakhindar-pal (v2, fetched 2026-04-18)

## Skipped (reviewed, pomijamy w rekomendacjach)

- `bovard/getting-started` — 2026-04-21: "Official Kaggle tutorial, kod = Nearest Planet Sniper (mamy w baselines)"

## Backlog (rozważ później)

- `debugendless/orbit-wars-sun-dodging-baseline` — 2026-04-21: "pure sun-dodge compact 115 LOC"
"""


def test_read_candidates_md_parses_sections(tmp_path: Path):
    """3 sekcje → odpowiednie listy slugów."""
    md = tmp_path / "external-candidates.md"
    md.write_text(SEED_MD)

    c = read_candidates_md(md)
    assert isinstance(c, Candidates)
    assert "romantamrazov/orbit-star-wars-lb-max-1224" in c.installed
    assert "lakhindarpal/orbit-wars-agent" in c.installed
    assert len(c.installed) == 2
    assert "bovard/getting-started" in c.skipped
    assert "debugendless/orbit-wars-sun-dodging-baseline" in c.backlog


def test_read_candidates_md_missing_file_returns_empty(tmp_path: Path):
    md = tmp_path / "external-candidates.md"
    c = read_candidates_md(md)
    assert c.installed == set()
    assert c.skipped == set()
    assert c.backlog == set()


def test_append_skipped_creates_new_entry(tmp_path: Path):
    """append_skipped dodaje wpis w sekcji Skipped."""
    md = tmp_path / "external-candidates.md"
    md.write_text(SEED_MD)

    append_skipped(md, "foo/bar-slug", "test reason")
    content = md.read_text()
    assert "foo/bar-slug" in content
    assert "test reason" in content

    # Re-read — slug trafia do skipped set
    c = read_candidates_md(md)
    assert "foo/bar-slug" in c.skipped


def test_append_skipped_idempotent(tmp_path: Path):
    """Dwukrotne append tego samego slug → nie dublujemy."""
    md = tmp_path / "external-candidates.md"
    md.write_text(SEED_MD)

    append_skipped(md, "foo/bar-slug", "first")
    append_skipped(md, "foo/bar-slug", "second — powinno być ignore")
    content = md.read_text()
    assert content.count("foo/bar-slug") == 1
    assert "first" in content
    assert "second" not in content  # drugie append nie zaktualizowało


def test_append_backlog_creates_new_entry(tmp_path: Path):
    md = tmp_path / "external-candidates.md"
    md.write_text(SEED_MD)

    append_backlog(md, "baz/qux", "może kiedyś")
    c = read_candidates_md(md)
    assert "baz/qux" in c.backlog


def test_append_skipped_raises_when_section_missing(tmp_path: Path):
    """Plik bez ## Skipped header → ValueError (nie silent orphan)."""
    md = tmp_path / "external-candidates.md"
    md.write_text("# Test\n\n## Installed\n\n- `foo/a`\n")

    with pytest.raises(ValueError, match="## Skipped"):
        append_skipped(md, "baz/new", "should fail — no Skipped section")


def test_append_backlog_raises_when_section_missing(tmp_path: Path):
    md = tmp_path / "external-candidates.md"
    md.write_text("# Test\n\n## Installed\n\n- `foo/a`\n")

    with pytest.raises(ValueError, match="## Backlog"):
        append_backlog(md, "baz/new", "no Backlog section")


def test_append_skipped_handles_missing_trailing_newline(tmp_path: Path):
    """Section header na ostatniej linii bez \\n → entry wstawiony poprawnie."""
    md = tmp_path / "external-candidates.md"
    # UWAGA: no trailing newline after ## Skipped
    md.write_text("# Test\n\n## Skipped")

    append_skipped(md, "foo/bar", "test reason")

    # Entry MUSI być na nowej linii, nie glued to header
    content = md.read_text()
    assert "## Skipped" in content
    assert "foo/bar" in content
    # Re-read parses it correctly
    c = read_candidates_md(md)
    assert "foo/bar" in c.skipped


# -----------------------------------------------------------------------------
# Task 8: fetch_notebook() — pull via kaggle CLI + stub agent.yaml
# -----------------------------------------------------------------------------
from orbit_wars_app.external import FetchResult, fetch_notebook


def _fake_ipynb(kernel_code: str) -> str:
    """Produce .ipynb content with given code in one cell."""
    nb = {
        "cells": [
            {"cell_type": "markdown", "source": ["# Hello"]},
            {"cell_type": "code", "source": [kernel_code]},
        ],
        "metadata": {},
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    return json.dumps(nb)


def test_fetch_notebook_happy_path(tmp_path: Path, monkeypatch):
    """Pobierz czysty kod → folder z main.py + agent.yaml (disabled: false)."""
    zoo = tmp_path / "agents"
    zoo.mkdir()

    # Fake kaggle CLI: zapisze notebook.ipynb do target dir
    def fake_run(cmd, *args, **kwargs):
        # cmd = ['kaggle', 'kernels', 'pull', slug, '-p', tmpdir]
        tmpdir = Path(cmd[-1])
        (tmpdir / "orbit-star-wars-lb-max-1224.ipynb").write_text(
            _fake_ipynb("def agent(obs):\n    return []\n")
        )
        return MagicMock(returncode=0, stdout="", stderr="")

    with patch("orbit_wars_app.external.subprocess.run", side_effect=fake_run), \
         patch("orbit_wars_app.external._kaggle_get_notebook_info",
               return_value={"version_number": 6, "license": "Apache 2.0"}):
        result = fetch_notebook(
            kernel_slug="romantamrazov/orbit-star-wars-lb-max-1224",
            target_name="tamrazov-starwars",
            zoo_dir=zoo,
        )

    assert isinstance(result, FetchResult)
    assert result.success is True
    assert result.folder_path.name == "tamrazov-starwars"

    # agent.yaml + main.py utworzone
    main_py = result.folder_path / "main.py"
    assert main_py.is_file()
    assert "def agent" in main_py.read_text()

    yaml_path = result.folder_path / "agent.yaml"
    assert yaml_path.is_file()
    data = yaml.safe_load(yaml_path.read_text())
    assert data["kernel_slug"] == "romantamrazov/orbit-star-wars-lb-max-1224"
    assert data["kernel_version"] == 6
    assert data["license"] == "Apache 2.0"
    assert data["disabled"] is False


def test_fetch_notebook_suspicious_code_marks_disabled(tmp_path: Path, monkeypatch):
    """Suspicious pattern → disabled: true + last_error."""
    zoo = tmp_path / "agents"
    zoo.mkdir()

    malicious = "import os\nos.system('evil')\ndef agent(obs): return []"

    def fake_run(cmd, *args, **kwargs):
        tmpdir = Path(cmd[-1])
        (tmpdir / "evil.ipynb").write_text(_fake_ipynb(malicious))
        return MagicMock(returncode=0, stdout="", stderr="")

    with patch("orbit_wars_app.external.subprocess.run", side_effect=fake_run), \
         patch("orbit_wars_app.external._kaggle_get_notebook_info",
               return_value={"version_number": 1, "license": "Apache 2.0"}):
        result = fetch_notebook(
            kernel_slug="evil/notebook",
            target_name="evil",
            zoo_dir=zoo,
        )

    assert result.success is True
    assert result.safety_alert is not None
    assert "os.system" in result.safety_alert

    data = yaml.safe_load((result.folder_path / "agent.yaml").read_text())
    assert data["disabled"] is True
    assert "suspicious pattern" in data.get("last_error", "")


def test_fetch_notebook_refresh_overwrites(tmp_path: Path):
    """refresh=True nadpisuje istniejący folder."""
    # zoo = agents/; external/ jest subdir ustalaną przez fetch_notebook
    zoo = tmp_path / "agents"
    external = zoo / "external"
    external.mkdir(parents=True)
    existing = external / "tamrazov-starwars"
    existing.mkdir()
    (existing / "main.py").write_text("OLD CODE")
    (existing / "agent.yaml").write_text(yaml.safe_dump({
        "name": "Old",
        "kernel_slug": "romantamrazov/orbit-star-wars-lb-max-1224",
        "kernel_version": 3,
        "tags": ["rule-based"],
    }))

    def fake_run(cmd, *args, **kwargs):
        tmpdir = Path(cmd[-1])
        (tmpdir / "new.ipynb").write_text(_fake_ipynb("NEW CODE\ndef agent(obs): return []"))
        return MagicMock(returncode=0, stdout="", stderr="")

    with patch("orbit_wars_app.external.subprocess.run", side_effect=fake_run), \
         patch("orbit_wars_app.external._kaggle_get_notebook_info",
               return_value={"version_number": 6, "license": "Apache 2.0"}):
        result = fetch_notebook(
            kernel_slug="romantamrazov/orbit-star-wars-lb-max-1224",
            target_name="tamrazov-starwars",
            zoo_dir=zoo,
            refresh=True,
        )

    assert result.success is True
    main_py_content = (result.folder_path / "main.py").read_text()
    assert "NEW CODE" in main_py_content
    assert "OLD CODE" not in main_py_content

    data = yaml.safe_load((result.folder_path / "agent.yaml").read_text())
    assert data["kernel_version"] == 6  # zaktualizowane
    # Zachowane pola z starego yaml (tags, name) nie są nadpisywane przez stub


def test_fetch_notebook_exists_without_refresh_errors(tmp_path: Path):
    """Folder już istnieje, refresh=False → FetchResult(success=False)."""
    zoo = tmp_path / "agents"
    external = zoo / "external"
    external.mkdir(parents=True)
    existing = external / "tamrazov-starwars"
    existing.mkdir()
    (existing / "main.py").write_text("pass")

    result = fetch_notebook(
        kernel_slug="romantamrazov/orbit-star-wars-lb-max-1224",
        target_name="tamrazov-starwars",
        zoo_dir=zoo,
        refresh=False,
    )
    assert result.success is False
    assert "already exists" in result.error or "exists" in result.error.lower()


def test_fetch_notebook_kaggle_cli_failure(tmp_path: Path):
    """kaggle CLI returns non-zero → FetchResult(success=False)."""
    zoo = tmp_path / "agents"
    zoo.mkdir()

    def fake_run(cmd, *args, **kwargs):
        return MagicMock(returncode=1, stdout="", stderr="404 Not Found")

    with patch("orbit_wars_app.external.subprocess.run", side_effect=fake_run), \
         patch("orbit_wars_app.external._kaggle_get_notebook_info",
               return_value={"version_number": 1, "license": "Apache 2.0"}):
        result = fetch_notebook(
            kernel_slug="nonexistent/notebook",
            target_name="nonexistent",
            zoo_dir=zoo,
        )

    assert result.success is False
    assert "404" in result.error or "CLI" in result.error


# -----------------------------------------------------------------------------
# Task 9: check_updates() — porównaj lokalne kernel_version z Kaggle
# -----------------------------------------------------------------------------
from orbit_wars_app.external import UpdateAvailable, check_updates


def test_check_updates_returns_available_when_remote_newer(tmp_path: Path):
    """Local v2 → remote v6 → UpdateAvailable w returnie."""
    zoo = tmp_path / "agents"
    _write_agent_yaml(zoo, "external", "tamrazov-starwars", {
        "name": "Tamrazov",
        "kernel_slug": "romantamrazov/orbit-star-wars-lb-max-1224",
        "kernel_version": 2,
        "tags": ["rule-based"],
    })

    with patch("orbit_wars_app.external._kaggle_get_notebook_info",
               return_value={"version_number": 6, "license": "Apache 2.0"}):
        result = check_updates(zoo)

    assert len(result) == 1
    upd = result[0]
    assert isinstance(upd, UpdateAvailable)
    assert upd.kernel_slug == "romantamrazov/orbit-star-wars-lb-max-1224"
    assert upd.local_version == 2
    assert upd.remote_version == 6
    assert upd.local_name == "tamrazov-starwars"


def test_check_updates_empty_when_all_current(tmp_path: Path):
    zoo = tmp_path / "agents"
    _write_agent_yaml(zoo, "external", "foo", {
        "name": "Foo",
        "kernel_slug": "foo/bar",
        "kernel_version": 3,
        "tags": [],
    })

    with patch("orbit_wars_app.external._kaggle_get_notebook_info",
               return_value={"version_number": 3, "license": "Apache 2.0"}):
        result = check_updates(zoo)
    assert result == []


def test_check_updates_ignores_failed_api_lookups(tmp_path: Path):
    """Jeden agent się nie sprawdza (API fail) → nie psuje całości."""
    zoo = tmp_path / "agents"
    _write_agent_yaml(zoo, "external", "good", {
        "kernel_slug": "a/b", "kernel_version": 1, "tags": [],
    })
    _write_agent_yaml(zoo, "external", "bad", {
        "kernel_slug": "x/y", "kernel_version": 1, "tags": [],
    })

    def side_effect(slug):
        if slug == "a/b":
            return {"version_number": 2, "license": "Apache 2.0"}
        raise RuntimeError("API down")

    with patch("orbit_wars_app.external._kaggle_get_notebook_info", side_effect=side_effect):
        result = check_updates(zoo)

    assert len(result) == 1
    assert result[0].kernel_slug == "a/b"


def test_kaggle_get_notebook_info_reraises_filenotfounderror_as_runtimeerror(tmp_path: Path):
    """Missing kaggle binary → FileNotFoundError → RuntimeError (for loop guard)."""
    from orbit_wars_app.external import _kaggle_get_notebook_info

    with patch("orbit_wars_app.external.subprocess.run",
               side_effect=FileNotFoundError(2, "No such file or directory: 'kaggle'")):
        with pytest.raises(RuntimeError, match="kaggle CLI binary not available"):
            _kaggle_get_notebook_info("foo/bar")


def test_check_updates_robust_to_missing_kaggle_binary(tmp_path: Path):
    """Missing kaggle binary → wszystkie lookups failują, ale check_updates nie crashuje → empty list."""
    zoo = tmp_path / "agents"
    _write_agent_yaml(zoo, "external", "foo", {
        "kernel_slug": "a/b", "kernel_version": 1, "tags": [],
    })
    _write_agent_yaml(zoo, "external", "bar", {
        "kernel_slug": "x/y", "kernel_version": 1, "tags": [],
    })

    with patch("orbit_wars_app.external.subprocess.run",
               side_effect=FileNotFoundError(2, "No such file")):
        result = check_updates(zoo)

    # Wszystkie API calls failują → empty list, nie raise
    assert result == []
