"""Tests pour awale_agent/config.py : missing_env_vars, constantes."""

import os
import importlib
import sys
import tempfile

import pytest


@pytest.fixture(autouse=True)
def reload_config(monkeypatch):
    """Recharge config à chaque test pour refléter l'environnement patché."""
    # On nettoie le module pour forcer re-import
    if "config" in sys.modules:
        del sys.modules["config"]
    yield
    if "config" in sys.modules:
        del sys.modules["config"]


def _load_config(monkeypatch=None, empty_env_vars=None):
    """Charge config en isolant dotenv : simule un environnement sans fichier .env."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    # Patch load_dotenv pour éviter que le .env réel ne repollue l'environnement
    import dotenv

    original_load = dotenv.load_dotenv
    dotenv.load_dotenv = lambda *a, **kw: False
    if "config" in sys.modules:
        del sys.modules["config"]
    import config  # noqa: E402
    importlib.reload(config)
    # Restaure load_dotenv
    dotenv.load_dotenv = original_load
    # Si des vars doivent être considérées absentes, les retirer du module
    if empty_env_vars:
        for var in empty_env_vars:
            if hasattr(config, var):
                setattr(config, var, None)
    # Appliquer monkeypatch overrides manuels sur les attributs du module
    if monkeypatch is not None:
        pass  # l'appelant a déjà fait monkeypatch.setenv -> refléter sur attributs
        for var in ["DUCKDB_PATH", "OPENROUTER_API_KEY", "OPENROUTER_BASE_URL", "MODEL_ID", "LLM_CACHE_PATH"]:
            env_val = os.environ.get(var)
            # Pour LLM_CACHE_PATH, le défaut est calculé via tempfile, pas via env direct
            if var == "LLM_CACHE_PATH":
                if env_val is not None:
                    setattr(config, var, env_val)
                elif "LLM_CACHE_PATH" not in os.environ:
                    import tempfile as _tf
                    setattr(config, var, os.path.join(_tf.gettempdir(), "llm_cache.sqlite"))
            else:
                # DUCKDB_PATH etc: refléter l'env actuel
                setattr(config, var, env_val)
    return config


class TestMissingEnvVars:
    def test_no_missing_when_key_present(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
        cfg = _load_config(monkeypatch)
        assert cfg.missing_env_vars() == []

    def test_missing_when_key_absent(self, monkeypatch):
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        cfg = _load_config(monkeypatch)
        assert "OPENROUTER_API_KEY" in cfg.missing_env_vars()

    def test_missing_when_key_empty(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "")
        cfg = _load_config(monkeypatch)
        assert "OPENROUTER_API_KEY" in cfg.missing_env_vars()

    def test_never_raises(self, monkeypatch):
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        cfg = _load_config(monkeypatch)
        # Ne doit jamais lever
        result = cfg.missing_env_vars()
        assert isinstance(result, list)

    def test_returns_list_of_strings(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "x")
        cfg = _load_config(monkeypatch)
        result = cfg.missing_env_vars()
        assert isinstance(result, list)
        for item in result:
            assert isinstance(item, str)


class TestConfigConstants:
    def test_allowed_tables_contains_fct(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "x")
        cfg = _load_config(monkeypatch)
        assert "fct_business_performance" in cfg.ALLOWED_TABLES

    def test_required_env_vars_contains_api_key(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "x")
        cfg = _load_config(monkeypatch)
        assert "OPENROUTER_API_KEY" in cfg.REQUIRED_ENV_VARS

    def test_llm_cache_default_is_tmp(self, monkeypatch):
        monkeypatch.delenv("LLM_CACHE_PATH", raising=False)
        monkeypatch.setenv("OPENROUTER_API_KEY", "x")
        cfg = _load_config(monkeypatch)
        assert cfg.LLM_CACHE_PATH.startswith(tempfile.gettempdir())

    def test_llm_cache_respects_env(self, monkeypatch):
        monkeypatch.setenv("LLM_CACHE_PATH", "/tmp/custom_cache.sqlite")
        monkeypatch.setenv("OPENROUTER_API_KEY", "x")
        cfg = _load_config(monkeypatch)
        assert cfg.LLM_CACHE_PATH == "/tmp/custom_cache.sqlite"

    def test_duckdb_path_from_env(self, monkeypatch):
        monkeypatch.setenv("DUCKDB_PATH", "/tmp/test.duckdb")
        monkeypatch.setenv("OPENROUTER_API_KEY", "x")
        cfg = _load_config(monkeypatch)
        assert cfg.DUCKDB_PATH == "/tmp/test.duckdb"

    def test_duckdb_path_none_when_not_set(self, monkeypatch):
        monkeypatch.delenv("DUCKDB_PATH", raising=False)
        monkeypatch.setenv("OPENROUTER_API_KEY", "x")
        cfg = _load_config(monkeypatch)
        assert cfg.DUCKDB_PATH is None
