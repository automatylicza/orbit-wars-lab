"""Spawn agent subprocess, handshake via stdout JSON, manage lifecycle."""
from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class AgentHandle:
    agent_id: str
    url: str
    proc: subprocess.Popen
    stdout_lines: list[str] = field(default_factory=list)
    stderr_lines: list[str] = field(default_factory=list)


def _wait_for_port(url: str, deadline: float, interval: float = 0.05) -> None:
    """Probe TCP connection until port accepts or deadline passes."""
    # Parse host:port from url (e.g. "http://127.0.0.1:12345")
    parts = url.rsplit(":", 1)
    host = parts[0].removeprefix("http://").removeprefix("https://")
    port = int(parts[1].split("/")[0])
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.1):
                return
        except OSError:
            time.sleep(interval)
    raise TimeoutError(f"Port {port} did not accept connections before deadline")


def spawn_agent(
    agent_dir: Path | str,
    agent_id: str,
    startup_timeout: float = 10.0,
) -> AgentHandle:
    """Fork agent subprocess. Wait for 'ready' on stdout. Return handle.

    Raises:
        RuntimeError: if subprocess exits before 'ready' (import error, etc.)
        TimeoutError: if no 'ready' within startup_timeout.
    """
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "orbit_wars_app.agent_serve",
            "--agent-dir",
            str(agent_dir),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    deadline = time.monotonic() + startup_timeout

    while time.monotonic() < deadline:
        line = proc.stdout.readline() if proc.stdout else ""
        if not line:
            if proc.poll() is not None:
                stderr = proc.stderr.read() if proc.stderr else ""
                raise RuntimeError(
                    f"Agent {agent_id!r} subprocess exited (code {proc.returncode}); "
                    f"stderr:\n{stderr}"
                )
            time.sleep(0.05)
            continue
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        status = msg.get("status")
        if status == "ready":
            url = msg["url"]
            # agent_serve.py prints 'ready' before uvicorn.run() binds the socket.
            # Probe TCP until the port accepts connections (remaining deadline).
            try:
                _wait_for_port(url, deadline)
            except TimeoutError:
                # Port never opened — kill subprocess so we don't leak it
                proc.kill()
                try:
                    proc.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    pass
                raise
            return AgentHandle(agent_id=agent_id, url=url, proc=proc)
        if status == "error":
            proc.kill()
            raise RuntimeError(f"Agent {agent_id!r} reported error: {msg.get('reason')}")

    proc.kill()
    raise TimeoutError(
        f"Agent {agent_id!r} did not emit 'ready' within {startup_timeout}s"
    )


def shutdown(handle: AgentHandle, grace: float = 2.0) -> None:
    """Terminate subprocess gracefully, force-kill after grace.

    Drains stdout/stderr pipes into handle buffers for post-mortem logging.
    Task 9 (match runner) should persist these BEFORE the handle goes out of
    scope if the stderr log is needed on disk.
    """
    if handle.proc.poll() is not None:
        return
    handle.proc.terminate()
    try:
        handle.proc.wait(timeout=grace)
    except subprocess.TimeoutExpired:
        handle.proc.kill()
        try:
            handle.proc.wait(timeout=1.0)
        except subprocess.TimeoutExpired:
            # Zombie we couldn't reap — OS will clean up eventually.
            # Don't block the match loop; proceed to drain what we can.
            pass

    # Drain pipes. Process is dead so reads return EOF quickly; guard against
    # unexpected pipe errors so one bad subprocess can't abort the tournament.
    try:
        if handle.proc.stdout:
            handle.stdout_lines.extend(handle.proc.stdout)
        if handle.proc.stderr:
            handle.stderr_lines.extend(handle.proc.stderr)
    except (OSError, ValueError):
        pass
