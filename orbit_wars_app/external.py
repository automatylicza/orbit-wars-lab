"""Utilities for the conversational workflow of fetching/managing external agents.

Called by Claude in conversation (via `python -c` or import); no user-facing CLI.

Modules:
- list_installed() — what we have locally (scan agents/external/)
- fetch_notebook(kernel_slug, ...) — pull .ipynb from Kaggle, extract main.py, stub agent.yaml
- check_updates() — compare local kernel_version against Kaggle
- read_candidates_md() / append_skipped() / append_backlog() — work with docs/external-candidates.md
- safety_audit(source_code) — regex scan for suspicious import patterns
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Optional

import yaml


# Kaggle CLI binary path. Override via $KAGGLE_CLI env var if your `kaggle`
# shell alias points somewhere else (e.g. a `cd` alias vs the Python script).
KAGGLE_CLI = os.environ.get("KAGGLE_CLI", "kaggle")


def _ensure_kaggle_env() -> None:
    """Bridge KGAT_ tokens from kaggle.json into KAGGLE_API_TOKEN env var.

    The Kaggle CLI 2.x reads new-style access tokens only from the env var,
    not from the legacy `key` field of kaggle.json (which it tries to send
    as Basic auth — Kaggle returns 401 for KGAT_ over Basic). subprocess.run
    inherits os.environ by default, so setting it here lets the CLI succeed.
    Idempotent and a no-op when env is already set or the file is legacy.
    """
    try:
        from . import kaggle_auth
        kaggle_auth.apply_token_to_env()
    except ImportError:
        pass


SUSPICIOUS_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("os.system",      re.compile(r'\bos\.system\b')),
    ("subprocess",     re.compile(r'\bsubprocess\.')),
    ("socket",         re.compile(r'\bsocket\.')),
    ("urllib.request", re.compile(r'\burllib\.request\b')),
    ("requests",       re.compile(r'\brequests\.')),
    ("pickle.load",    re.compile(r'\bpickle\.(load|loads)\b')),
    ("eval",           re.compile(r'\beval\s*\(')),
    ("exec",           re.compile(r'\bexec\s*\(')),
    ("__import__",     re.compile(r'\b__import__\s*\(')),
]


def safety_audit(source_code: str) -> Optional[str]:
    """Scan `source_code` with regexes for suspicious import patterns.

    Returns:
    - None if clean
    - string describing the first pattern that matched, e.g. "suspicious pattern: os.system"

    Does not raise. False positives (e.g. pickle for a trained policy) are OK —
    fetch_notebook will write `disabled: true` + `last_error`, and after manual
    validation the user can remove the disabled flag.
    """
    for name, pattern in SUSPICIOUS_PATTERNS:
        if pattern.search(source_code):
            return f"suspicious pattern: {name}"
    return None


@dataclass(frozen=True)
class InstalledKernel:
    """Description of an installed external agent (fetched from a Kaggle notebook)."""
    kernel_slug: str
    kernel_version: Optional[int]
    local_name: str
    folder_path: Path


def list_installed(zoo_dir: Path) -> list[InstalledKernel]:
    """Scan `zoo_dir/external/*/agent.yaml`, return list of InstalledKernel.

    Skips:
    - folders without `main.py`
    - folders without `agent.yaml`
    - agents without `kernel_slug` in YAML (manually added, not from a notebook)
    """
    external = zoo_dir / "external"
    if not external.is_dir():
        return []

    result: list[InstalledKernel] = []
    for child in sorted(external.iterdir()):
        if not child.is_dir():
            continue
        if not (child / "main.py").is_file():
            continue
        yaml_path = child / "agent.yaml"
        if not yaml_path.is_file():
            continue
        try:
            with yaml_path.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError:
            continue
        if not isinstance(data, dict):
            continue
        slug = data.get("kernel_slug")
        if not slug:
            continue
        kv = data.get("kernel_version")
        try:
            kv_int = int(kv) if kv is not None else None
        except (TypeError, ValueError):
            kv_int = None
        result.append(InstalledKernel(
            kernel_slug=str(slug),
            kernel_version=kv_int,
            local_name=child.name,
            folder_path=child,
        ))
    return result


@dataclass
class Candidates:
    """Snapshot of docs/external-candidates.md contents."""
    installed: set[str]   # kernel_slugs in the Installed section
    skipped: set[str]     # in the Skipped section
    backlog: set[str]     # in the Backlog section


_INSTALLED_HEADER = "## Installed"
_SKIPPED_HEADER = "## Skipped"
_BACKLOG_HEADER = "## Backlog"
# Kernel slug pattern: <owner>/<kernel>. Match anywhere in line (naturally after `- `),
# finds the slug inside backticks: `owner/slug`.
_SLUG_RE = re.compile(r"`([a-z0-9][a-z0-9\-_]*/[a-z0-9][a-z0-9\-_]*)`")


def read_candidates_md(md_path: Path) -> Candidates:
    """Parse docs/external-candidates.md into Installed / Skipped / Backlog sets.

    If the file doesn't exist → empty sets.
    Robustly ignores malformatted lines.
    """
    if not md_path.is_file():
        return Candidates(installed=set(), skipped=set(), backlog=set())

    installed: set[str] = set()
    skipped: set[str] = set()
    backlog: set[str] = set()

    section: str | None = None  # "installed" | "skipped" | "backlog"
    for raw_line in md_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith(_INSTALLED_HEADER):
            section = "installed"
            continue
        if line.startswith(_SKIPPED_HEADER):
            section = "skipped"
            continue
        if line.startswith(_BACKLOG_HEADER):
            section = "backlog"
            continue
        if line.startswith("## "):
            section = None  # entered a different section
            continue
        if section is None:
            continue
        m = _SLUG_RE.search(line)
        if not m:
            continue
        slug = m.group(1)
        if section == "installed":
            installed.add(slug)
        elif section == "skipped":
            skipped.add(slug)
        elif section == "backlog":
            backlog.add(slug)

    return Candidates(installed=installed, skipped=skipped, backlog=backlog)


def _append_to_section(md_path: Path, section_header: str, slug: str, reason: str) -> None:
    r"""Internal helper — append `- \`{slug}\` — {date}: "{reason}"` in the given section.

    If the slug is already present (in any section of the file) — does nothing (idempotent).
    The section must exist in the file.
    """
    content = md_path.read_text(encoding="utf-8") if md_path.is_file() else ""

    # Idempotency: if the slug is already in the file, don't duplicate
    if f"`{slug}`" in content:
        return

    if section_header not in content:
        raise ValueError(
            f"Section {section_header!r} not found in {md_path}. "
            f"File must contain the section header before append."
        )

    today = date.today().isoformat()
    new_entry = f"- `{slug}` — {today}: \"{reason}\"\n"

    # Find section_header and insert after the first empty line following it
    lines = content.splitlines(keepends=True)
    out_lines: list[str] = []
    inserted = False
    in_section = False

    for i, line in enumerate(lines):
        out_lines.append(line)
        if line.strip().startswith(section_header):
            in_section = True
            continue
        if in_section and not inserted:
            # wait for the first empty line OR the next `## ` header
            stripped = line.strip()
            if stripped.startswith("## ") and stripped != section_header:
                # insert before this header
                out_lines.insert(len(out_lines) - 1, new_entry)
                inserted = True
                in_section = False
            elif stripped == "" and i + 1 < len(lines):
                # find the next non-empty line
                next_non_empty = next(
                    (l for l in lines[i + 1:] if l.strip()),
                    None,
                )
                if next_non_empty is None or next_non_empty.strip().startswith("## "):
                    # section empty or another header follows — insert here
                    out_lines.append(new_entry)
                    inserted = True
                    in_section = False

    if not inserted:
        # no good spot found — append at end of section (fallback)
        # Ensure last line ends with a newline before appending
        if out_lines and not out_lines[-1].endswith("\n"):
            out_lines[-1] = out_lines[-1] + "\n"
        out_lines.append(new_entry)

    md_path.write_text("".join(out_lines), encoding="utf-8")


# -----------------------------------------------------------------------------
# fetch_notebook — pull .ipynb from Kaggle + stub agent.yaml
# -----------------------------------------------------------------------------


@dataclass
class FetchResult:
    """Output of fetch_notebook.

    Attributes:
        success: True when the folder was created/overwritten.
        folder_path: where it went (or planned location when success=False).
        error: empty when success=True.
        safety_alert: None = clean code; string = description of matched pattern.
    """
    success: bool
    folder_path: Path
    error: str = ""
    safety_alert: Optional[str] = None


def _kaggle_get_notebook_info(kernel_slug: str) -> dict[str, Any]:
    """Invoke `kaggle kernels status` to retrieve version_number.

    Returns dict {version_number: int, license: str}.
    Raises RuntimeError if the CLI fails — including: binary missing (FileNotFoundError),
    permission denied (PermissionError), or non-zero returncode.

    License — Kaggle CLI `kernels status` does not return it, so default to "Apache 2.0"
    (most common on LB). For an exact value, we'd need `kernels get-metadata`,
    but that's an extra call — leave it for manual verification after fetch.
    """
    _ensure_kaggle_env()
    try:
        result = subprocess.run(
            [KAGGLE_CLI, "kernels", "status", kernel_slug],
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, PermissionError) as e:
        raise RuntimeError(
            f"kaggle CLI binary not available at {KAGGLE_CLI}: {e}"
        ) from e
    if result.returncode != 0:
        raise RuntimeError(f"kaggle kernels status failed: {result.stderr or result.stdout}")

    # Parse versionNumber from output. Output format varies; look for a line with "version"
    version_number: int = 1
    for line in result.stdout.splitlines():
        if "VersionNumber" in line or "version" in line.lower():
            parts = line.split(":")
            if len(parts) >= 2:
                try:
                    version_number = int(parts[-1].strip())
                    break
                except ValueError:
                    pass

    return {
        "version_number": version_number,
        "license": "Apache 2.0",
    }


def _extract_main_py_from_ipynb(ipynb_path: Path) -> str:
    """Parse notebook .ipynb, return concatenation of all code cells.

    Strategy: stitch all code cells together (agents often have helper
    functions spread across several cells). Markdown is skipped.
    """
    with ipynb_path.open("r", encoding="utf-8") as f:
        nb = json.load(f)

    parts: list[str] = []
    for cell in nb.get("cells", []):
        if cell.get("cell_type") != "code":
            continue
        source = cell.get("source", [])
        if isinstance(source, list):
            parts.append("".join(source))
        else:
            parts.append(source)
    return "\n\n".join(parts)


def fetch_notebook(
    kernel_slug: str,
    target_name: str,
    zoo_dir: Path,
    *,
    refresh: bool = False,
) -> FetchResult:
    """Pull `.ipynb` from Kaggle, extract main.py, create folder with stub `agent.yaml`.

    Args:
        kernel_slug: `<owner>/<kernel>`, e.g. "romantamrazov/orbit-star-wars-lb-max-1224"
        target_name: folder name under `agents/external/<target_name>/`
        zoo_dir: path to `agents/` (parent of `external/`)
        refresh: True → overwrite existing folder (preserving name/tags/etc from yaml).

    Returns:
        FetchResult(success=True, folder_path=..., safety_alert=Optional[str])
        FetchResult(success=False, error=...)
    """
    target_dir = zoo_dir / "external" / target_name

    # Existence check: when main.py already exists and refresh=False → error
    if target_dir.is_dir() and (target_dir / "main.py").is_file():
        if not refresh:
            return FetchResult(
                success=False,
                folder_path=target_dir,
                error=f"folder {target_dir} already exists (use refresh=True to overwrite)",
            )

    # Step 1: get notebook info (version, license)
    try:
        info = _kaggle_get_notebook_info(kernel_slug)
    except RuntimeError as e:
        return FetchResult(
            success=False,
            folder_path=target_dir,
            error=f"kaggle CLI info error: {e}",
        )

    # Step 2: pull notebook via kaggle CLI into a temp directory
    _ensure_kaggle_env()
    with tempfile.TemporaryDirectory(prefix="kaggle-pull-") as tmp:
        tmpdir = Path(tmp)
        result = subprocess.run(
            [KAGGLE_CLI, "kernels", "pull", kernel_slug, "-p", str(tmpdir)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return FetchResult(
                success=False,
                folder_path=target_dir,
                error=f"kaggle CLI pull error: {result.stderr or result.stdout}",
            )

        # Find .ipynb in tmpdir (kaggle CLI writes <slug>.ipynb + metadata.json)
        ipynb_files = list(tmpdir.glob("*.ipynb"))
        if not ipynb_files:
            # Fallback: kernel may be a .py script instead of a notebook
            py_files = list(tmpdir.glob("*.py"))
            if not py_files:
                return FetchResult(
                    success=False,
                    folder_path=target_dir,
                    error=f"no .ipynb or .py in tmpdir after pull: {list(tmpdir.iterdir())}",
                )
            main_py_code = py_files[0].read_text(encoding="utf-8")
        else:
            main_py_code = _extract_main_py_from_ipynb(ipynb_files[0])

    # Step 3: safety audit (regex scan for suspicious imports)
    alert = safety_audit(main_py_code)

    # Step 4: create folder + write main.py
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "main.py").write_text(main_py_code, encoding="utf-8")

    # Step 5: stub agent.yaml (preserving existing fields on refresh)
    existing_yaml: dict = {}
    yaml_path = target_dir / "agent.yaml"
    if refresh and yaml_path.is_file():
        try:
            existing_yaml = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            existing_yaml = {}

    stub: dict[str, Any] = {
        "name": existing_yaml.get("name") or target_name.replace("-", " ").title(),
        "description": existing_yaml.get("description") or "TODO: fill after subagent analysis",
        "author": existing_yaml.get("author") or kernel_slug.split("/")[0],
        "kernel_slug": kernel_slug,
        "kernel_version": info["version_number"],
        "date_fetched": date.today().isoformat(),
        "license": info.get("license", "Apache 2.0"),
        "tags": existing_yaml.get("tags") or ["external"],
        "disabled": alert is not None,
    }
    if existing_yaml.get("author_claimed_lb_score") is not None:
        stub["author_claimed_lb_score"] = existing_yaml["author_claimed_lb_score"]
    if alert is not None:
        stub["last_error"] = alert

    yaml_path.write_text(
        yaml.safe_dump(stub, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    return FetchResult(
        success=True,
        folder_path=target_dir,
        safety_alert=alert,
    )


def append_skipped(md_path: Path, kernel_slug: str, reason: str) -> None:
    """Append an entry in the Skipped section. Idempotent."""
    _append_to_section(md_path, _SKIPPED_HEADER, kernel_slug, reason)


def append_backlog(md_path: Path, kernel_slug: str, reason: str) -> None:
    """Append an entry in the Backlog section. Idempotent."""
    _append_to_section(md_path, _BACKLOG_HEADER, kernel_slug, reason)


def append_installed(md_path: Path, kernel_slug: str, local_name: str,
                     kernel_version: int, lb_score: Optional[float] = None) -> None:
    """Append an entry in the Installed section. Idempotent. Format matching seed.

    Usage: called by fetch_notebook() on success.
    """
    today = date.today().isoformat()
    lb_part = f", LB claim {lb_score}" if lb_score is not None else ""
    entry_body = f"→ agents/external/{local_name} (v{kernel_version}, fetched {today}{lb_part})"

    content = md_path.read_text(encoding="utf-8") if md_path.is_file() else ""
    if f"`{kernel_slug}`" in content:
        return  # already present

    if _INSTALLED_HEADER not in content:
        raise ValueError(
            f"Section {_INSTALLED_HEADER!r} not found in {md_path}. "
            f"File must contain the section header before append."
        )

    new_entry = f"- `{kernel_slug}` {entry_body}\n"

    # Use the same logic as _append_to_section, but with a different format:
    lines = content.splitlines(keepends=True)
    out_lines: list[str] = []
    inserted = False
    in_section = False

    for i, line in enumerate(lines):
        out_lines.append(line)
        if line.strip().startswith(_INSTALLED_HEADER):
            in_section = True
            continue
        if in_section and not inserted:
            stripped = line.strip()
            if stripped.startswith("## ") and stripped != _INSTALLED_HEADER:
                out_lines.insert(len(out_lines) - 1, new_entry)
                inserted = True
                in_section = False
            elif stripped == "" and i + 1 < len(lines):
                next_non_empty = next(
                    (l for l in lines[i + 1:] if l.strip()),
                    None,
                )
                if next_non_empty is None or next_non_empty.strip().startswith("## "):
                    out_lines.append(new_entry)
                    inserted = True
                    in_section = False

    if not inserted:
        # no good spot found — append at end of section (fallback)
        # Ensure last line ends with a newline before appending
        if out_lines and not out_lines[-1].endswith("\n"):
            out_lines[-1] = out_lines[-1] + "\n"
        out_lines.append(new_entry)

    md_path.write_text("".join(out_lines), encoding="utf-8")


# -----------------------------------------------------------------------------
# check_updates — compare local kernel_version against Kaggle
# -----------------------------------------------------------------------------


@dataclass
class UpdateAvailable:
    """Notebook has a newer version on Kaggle than locally."""
    kernel_slug: str
    local_version: int
    remote_version: int
    local_name: str
    folder_path: Path


def check_updates(zoo_dir: Path) -> list[UpdateAvailable]:
    """For each installed external: compare kernel_version against Kaggle.

    Agents without local kernel_version (or with non-deterministic API) are skipped.
    Returns only those where remote > local.
    """
    result: list[UpdateAvailable] = []
    for installed in list_installed(zoo_dir):
        if installed.kernel_version is None:
            continue
        try:
            info = _kaggle_get_notebook_info(installed.kernel_slug)
        except RuntimeError:
            continue
        remote_v = info.get("version_number")
        if not isinstance(remote_v, int):
            continue
        if remote_v > installed.kernel_version:
            result.append(UpdateAvailable(
                kernel_slug=installed.kernel_slug,
                local_version=installed.kernel_version,
                remote_version=remote_v,
                local_name=installed.local_name,
                folder_path=installed.folder_path,
            ))
    return result
