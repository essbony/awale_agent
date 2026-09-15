
import os
import tempfile
from dotenv import load_dotenv

load_dotenv()

DUCKDB_PATH = os.environ.get("DUCKDB_PATH", "my_db.duckdb")

OPENROUTER_BASE_URL = os.environ.get("OPENROUTER_BASE_URL")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
MODEL_ID = os.environ.get("MODEL_ID")


# Rediriger vers /tmp/ si on est sur Streamlit Cloud ou en lecture seule, sinon garder le chemin local
default_cache = os.path.join(tempfile.gettempdir(), "llm_cache.sqlite")
LLM_CACHE_PATH = os.environ.get("LLM_CACHE_PATH", default_cache)

# Table réellement construite dans le projet (mart unique regroupant
# ventes, dépenses marketing et sentiment).
ALLOWED_TABLES = [
    "fct_business_performance",
]

REQUIRED_ENV_VARS = ["OPENROUTER_API_KEY"]


def missing_env_vars() -> list[str]:
    """Retourne la liste des variables d'environnement requises absentes.
    Ne lève jamais d'exception — laisse l'appelant (UI) décider comment
    afficher l'erreur."""
    return [v for v in REQUIRED_ENV_VARS if not os.environ.get(v)]
    