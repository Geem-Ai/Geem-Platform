"""Every ``python -m`` entrypoint must be able to configure its own mappers.

Querying one mapped class configures the whole registry, so a module that
imports a subset dies on the first query with an unresolved relationship name
(for example ``Workspace`` referring to ``'User'``). The API service never hits
this because it imports :mod:`app.db.models`, and neither does the test suite,
because ``conftest`` imports it too — which is exactly why this check runs each
entrypoint in a fresh interpreter instead of in-process.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

API_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = API_ROOT / "app"
MAIN_GUARD = 'if __name__ == "__main__":'

PROBE = (
    "import importlib, sys\n"
    "from sqlalchemy.orm import configure_mappers\n"
    "importlib.import_module(sys.argv[1])\n"
    "configure_mappers()\n"
)


def standalone_entrypoints() -> list[str]:
    modules = []
    for path in sorted(APP_ROOT.rglob("*.py")):
        if MAIN_GUARD not in path.read_text(encoding="utf-8"):
            continue
        parts = path.relative_to(API_ROOT).with_suffix("").parts
        modules.append(".".join(parts))
    return modules


def test_entrypoint_discovery_finds_known_modules() -> None:
    modules = standalone_entrypoints()
    assert "app.apps_catalog.reconcile_mcp" in modules
    assert "app.apps_catalog.seed" in modules
    assert "app.billing.seed" in modules


@pytest.mark.parametrize("module", standalone_entrypoints())
def test_entrypoint_configures_mappers_in_a_fresh_interpreter(module: str) -> None:
    result = subprocess.run(
        [sys.executable, "-c", PROBE, module],
        cwd=API_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, (
        f"{module} cannot configure the mapper registry from its own imports; "
        f"import app.db.models in it.\n{result.stderr[-2000:]}"
    )
