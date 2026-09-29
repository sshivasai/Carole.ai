"""Build the web UI and stage all non-Python resources for a wheel."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
WEB_TARGET = ROOT / "backend" / "carole_ai" / "web"
RESOURCE_TARGET = ROOT / "backend" / "carole_ai" / "resources"


def _copy_tree(source: Path, target: Path, keep: set[str] | None = None) -> None:
    keep = keep or set()
    target.mkdir(parents=True, exist_ok=True)
    for child in target.iterdir():
        if child.name in keep:
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()
    shutil.copytree(
        source,
        target,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
    )


def main() -> None:
    npm = shutil.which("npm")
    if not npm:
        raise SystemExit("Node.js/npm is required to create a Carole.ai release")

    subprocess.run([npm, "ci"], cwd=FRONTEND, check=True)
    next_cache = FRONTEND / ".next"
    if next_cache.exists():
        shutil.rmtree(next_cache)
    subprocess.run([npm, "run", "build"], cwd=FRONTEND, check=True)

    exported = FRONTEND / "out"
    if not (exported / "index.html").is_file():
        raise SystemExit("Next.js did not create frontend/out/index.html")

    _copy_tree(exported, WEB_TARGET, keep={"__init__.py"})

    RESOURCE_TARGET.mkdir(parents=True, exist_ok=True)
    oauth_client = RESOURCE_TARGET / "google_oauth_client.json"
    if not oauth_client.is_file():
        raise SystemExit(
            "Missing backend/carole_ai/resources/google_oauth_client.json; "
            "a Desktop OAuth client is required for the built-in Google connection"
        )
    shutil.copy2(ROOT / "backend" / "alembic.ini", RESOURCE_TARGET / "alembic.ini")
    _copy_tree(ROOT / "backend" / "alembic", RESOURCE_TARGET / "alembic")

    web_size = sum(path.stat().st_size for path in WEB_TARGET.rglob("*") if path.is_file())
    print(f"Staged frontend and migrations ({web_size / 1024 / 1024:.1f} MiB web assets)")


if __name__ == "__main__":
    main()
