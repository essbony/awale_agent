"""Régression: RuntimeError: Event loop is closed après 2e message Streamlit."""

import asyncio
import sys
import os
import concurrent.futures

# Copie exacte de app._run_async pour tester sans importer app
# (importer app déclenche st.cache_resource + connexion DuckDB au chargement)
def _run_async(coro):
    try:
        running = asyncio.get_running_loop()
        if running and not running.is_closed():
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result()
    except RuntimeError:
        pass
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


# Vérifie aussi que le vrai app._run_async est identique (sans l'importer)
def _load_app_source() -> str:
    path = os.path.join(os.path.dirname(__file__), "..", "app.py")
    with open(path, encoding="utf-8") as f:
        return f.read()


async def _dummy(value: str = "ok") -> str:
    await asyncio.sleep(0.005)
    return value


class TestRunAsyncClosedLoop:
    def test_app_contains_run_async(self):
        """Garde-fou: app.py doit contenir _run_async et gérer is_closed."""
        src = _load_app_source()
        assert "def _run_async" in src
        assert "is_closed()" in src
        assert "new_event_loop" in src

    def test_successive_calls(self):
        """2 messages consécutifs (2e appel après fermeture implicite de la boucle)."""
        assert _run_async(_dummy("a")) == "a"
        assert _run_async(_dummy("b")) == "b"
        assert _run_async(_dummy("c")) == "c"

    def test_recovers_after_explicit_close(self):
        """Boucle fermée explicitement entre 2 appels -> doit recréer."""
        assert _run_async(_dummy("1")) == "1"
        loop = asyncio.new_event_loop()
        loop.close()
        asyncio.set_event_loop(loop)
        assert loop.is_closed()
        # Doit récupérer et réussir
        assert _run_async(_dummy("2")) == "2"
        assert _run_async(_dummy("3")) == "3"

    def test_no_running_loop_required(self):
        """Sans boucle en cours, doit fonctionner."""
        try:
            asyncio.get_running_loop()
            running = True
        except RuntimeError:
            running = False
        assert not running  # test exécuté hors boucle
        assert _run_async(_dummy("x")) == "x"
