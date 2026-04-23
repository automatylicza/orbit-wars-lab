"""Agent HTTP server — launched IN a subprocess by the coordinator.

Invocation: `python -m orbit_wars_app.agent_serve --agent-dir <path>`

Protocol:
- On stdout line: {"status": "ready", "url": "http://127.0.0.1:<port>"}
- On POST /act payload {action: "act", configuration: {...}, state: {observation: {...}}}
  returns {action: <agent_output>}.

1:1 compatible with kaggle-environments UrlAgent (agent.py).
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import socket
import sys
from pathlib import Path
from typing import Callable, Optional


def load_agent(agent_dir: str) -> Optional[Callable]:
    """Import agent_dir/main.py, return last callable in its namespace.

    Mirrors kaggle-environments agent.py:40-65 behavior.
    """
    main_py = Path(agent_dir) / "main.py"
    if not main_py.is_file():
        raise FileNotFoundError(f"main.py not found in {agent_dir}")
    spec = importlib.util.spec_from_file_location("bot_main", main_py)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    # Append agent_dir to sys.path (to parity with kaggle-envs agent.py:53
    # — installed packages take priority over local helpers.py).
    agent_dir_str = str(agent_dir)
    sys.path.append(agent_dir_str)
    try:
        spec.loader.exec_module(mod)
    finally:
        # Remove the first occurrence (append added it at the end)
        try:
            sys.path.remove(agent_dir_str)
        except ValueError:
            pass
    # Per kaggle-envs agent.py:64: take the last callable from namespace,
    # WITHOUT filtering classes/builtins (agent may be a class with __call__ or a factory).
    callables = [v for v in vars(mod).values() if callable(v)]
    return callables[-1] if callables else None


def _find_free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _make_app(agent_fn: Callable):
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse
    from starlette.requests import Request

    app = FastAPI()

    # Cache co_argcount once (avoid hasattr per-request)
    argcount = _count_args(agent_fn)

    # NOTE: We avoid `from __future__ import annotations` interplay with
    # FastAPI's get_type_hints() by using add_route instead of decorator,
    # so the Request type annotation resolves correctly at runtime.
    async def _act_handler(request: Request) -> JSONResponse:
        try:
            payload = await request.json()
            obs = payload["state"]["observation"]
            cfg = payload.get("configuration", {})
            args = [obs, cfg][:argcount] if argcount >= 1 else []
            action = agent_fn(*args)
            return JSONResponse({"action": action})
        except Exception as e:
            # Mirror kaggle-envs UrlAgent: return BaseException:: form
            return JSONResponse({"action": f"BaseException::{type(e).__name__}: {e}"})

    async def _health_handler(request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    # UrlAgent (refs/engine/core/kaggle_environments/agent.py:91) POSTs to the
    # base URL (self.raw), not /act. Register the act handler on both root and
    # /act — root for Kaggle-faithful UrlAgent, /act as explicit alias for
    # manual testing and documentation.
    app.add_route("/", _act_handler, methods=["POST"])
    app.add_route("/act", _act_handler, methods=["POST"])
    app.add_route("/health", _health_handler, methods=["GET"])

    return app


def _count_args(fn: Callable) -> int:
    if hasattr(fn, "__code__") and hasattr(fn.__code__, "co_argcount"):
        return int(fn.__code__.co_argcount)
    return 2  # default assumption: agent(obs, cfg)


def main() -> None:
    import uvicorn

    parser = argparse.ArgumentParser()
    parser.add_argument("--agent-dir", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    try:
        agent_fn = load_agent(args.agent_dir)
    except Exception as e:
        print(json.dumps({"status": "error", "reason": f"load failed: {e}"}), flush=True)
        sys.exit(1)
    if agent_fn is None:
        print(json.dumps({"status": "error", "reason": "no callable in main.py"}), flush=True)
        sys.exit(1)

    port = _find_free_port()
    url = f"http://{args.host}:{port}"
    print(json.dumps({"status": "ready", "url": url}), flush=True)

    app = _make_app(agent_fn)
    uvicorn.run(app, host=args.host, port=port, log_level="error")


if __name__ == "__main__":
    main()
