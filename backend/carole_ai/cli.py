"""Command-line entry point for the packaged Carole.ai application."""

from __future__ import annotations

import argparse
import os
import socket
import threading
import time
import webbrowser
from pathlib import Path

from carole_ai import __version__


def _open_when_ready(host: str, port: int) -> None:
    connect_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((connect_host, port), timeout=0.5):
                webbrowser.open(f"http://{connect_host}:{port}")
                return
        except OSError:
            time.sleep(0.2)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="caroleai",
        description="Run the Carole.ai backend and web application.",
    )
    parser.add_argument("--host", default=os.getenv("HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8000")))
    parser.add_argument("--data-dir", type=Path, help="Persistent Carole.ai data directory")
    parser.add_argument("--no-browser", action="store_true", help="Do not open the web UI")
    parser.add_argument("--version", action="version", version=f"Carole.ai {__version__}")
    return parser


def main() -> None:
    args = _parser().parse_args()
    if args.data_dir:
        os.environ["CAROLE_HOME_DIR"] = str(args.data_dir.expanduser().resolve())

    # Google Desktop OAuth must return to the same local Carole.ai instance,
    # including when the user selects a non-default port.
    connect_host = "127.0.0.1" if args.host in {"0.0.0.0", "::"} else args.host
    local_url = f"http://{connect_host}:{args.port}"
    os.environ.setdefault(
        "GOOGLE_REDIRECT_URI", f"{local_url}/api/auth/google/callback"
    )
    os.environ.setdefault("FRONTEND_URL", local_url)

    if not args.no_browser:
        threading.Thread(
            target=_open_when_ready,
            args=(args.host, args.port),
            daemon=True,
        ).start()

    import uvicorn

    # OAuth callback query strings contain short-lived authorization codes.
    # Keep application diagnostics, but do not write request URLs to access logs.
    uvicorn.run("main:app", host=args.host, port=args.port, reload=False, access_log=False)


if __name__ == "__main__":
    main()
