"""Run backend tests against disposable application data, never user databases.

Usage: python scripts/check_backend.py [pytest arguments]
Live provider tests have a separate, explicitly free-only runner.
"""
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch


def main():
    import pytest

    backend = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="carole-tests-") as directory:
        root = Path(directory)
        environment = {
            "CAROLE_HOME_DIR": str(root / ".carole"),
            "DATABASE_URL": f"sqlite+aiosqlite:///{(root / 'test.db').as_posix()}",
            "WORKSPACE_ROOT": str(root / "workspace"),
            "JWT_SECRET": "disposable-test-secret-not-used-in-production",
            "ENV": "test", "ENVIRONMENT": "test", "FORCE_DB_RECREATE": "false",
            "PYTHON_DOTENV_DISABLED": "1", "ENABLE_OPENLLMETRY": "false",
            "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
            "BROWSER_USE_CONFIG_DIR": str(root / "browser-use"),
            "ANONYMIZED_TELEMETRY": "false", "BROWSER_USE_CLOUD_SYNC": "false",
        }
        for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "OPENROUTER_API_KEY",
                    "GOOGLE_API_KEY", "GEMINI_API_KEY", "NVIDIA_API_KEY", "TAVILY_API_KEY"):
            environment[key] = ""
        (root / "workspace").mkdir()
        sys.path.insert(0, str(backend))
        os.chdir(backend)
        with patch.dict(os.environ, environment), patch.object(Path, "home", return_value=root):
            return pytest.main(["-c", str(backend / "pytest.ini"),
                                "--basetemp", str(root / "pytest"), *sys.argv[1:]])


if __name__ == "__main__":
    raise SystemExit(main())
