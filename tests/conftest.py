import sys
import os
from unittest.mock import MagicMock

# Compat : agent.py importe ischema_names depuis duckdb_engine.datatypes
# qui n'existe plus dans les versions récentes (déplacé sur Dialect).
# On injecte un shim avant tout import d'agent.
try:
    from duckdb_engine.datatypes import ischema_names  # noqa: F401
except ImportError:
    import duckdb_engine.datatypes as _dt
    from duckdb_engine import Dialect as _Dialect
    _dt.ischema_names = _Dialect.ischema_names  # type: ignore[attr-defined]
    sys.modules["duckdb_engine.datatypes"] = _dt

# Ensure OPENROUTER_API_KEY existe pour les imports au chargement
os.environ.setdefault("OPENROUTER_API_KEY", "test-key-for-pytest")

# Ensure project root and sub-packages are importable
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Standalone: awale_agent files are at project root
for p in [
    PROJECT_ROOT,
    os.path.join(PROJECT_ROOT, "awale_agent"),
    os.path.join(PROJECT_ROOT, "prompts"),
    os.path.join(PROJECT_ROOT, "awale-ai"),
    os.path.dirname(os.path.abspath(__file__)),
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
]:
    if p not in sys.path:
        sys.path.insert(0, p)
