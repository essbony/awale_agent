
import re
from dataclasses import dataclass, field
from typing import AsyncIterator

from langchain_core.globals import set_llm_cache
from langchain_community.cache import SQLiteCache
from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits.sql.toolkit import SQLDatabaseToolkit
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import HumanMessage

import config
from prompts import SYSTEM_PROMPT

# --------------------------------------------------------------------------
# Anonymisation
# --------------------------------------------------------------------------

# Détecte les numéros ivoiriens : locaux (10 chiffres commençant par 0) ou
# internationaux (+225/00225 suivi de 10 chiffres). L'ancre "commence par 0
# ou +225" évite de confondre un gros montant FCFA avec un téléphone.
PHONE_PATTERN = re.compile(
    r"(?:\+225|00225)[\s.-]?(?:\d[\s.-]?){9}\d|0(?:[\s.-]?\d){9}"
)


def anonymize(text: str) -> str:
    def mask(match: re.Match) -> str:
        raw = match.group(0)
        digits = re.sub(r"\D", "", raw)
        if len(digits) < 8:
            return raw
        return digits[:2] + "*" * (len(digits) - 4) + digits[-2:]

    return PHONE_PATTERN.sub(mask, text)


# --------------------------------------------------------------------------
# Guardrail : vérifie que les nombres cités viennent d'un résultat réel
# --------------------------------------------------------------------------

NUMBER_PATTERN = re.compile(r"\d[\d\s]*(?:[.,]\d+)?")


def extract_numbers(text: str) -> set[str]:
    return {n.replace(" ", "").replace(",", ".") for n in NUMBER_PATTERN.findall(text)}


def check_grounding(final_answer: str, tool_outputs: list[str]) -> bool:
    """True si tous les nombres significatifs (3+ chiffres) de la réponse
    apparaissent dans au moins un résultat d'outil exécuté."""
    answer_numbers = {n for n in extract_numbers(final_answer) if len(n.replace(".", "")) >= 3}
    if not answer_numbers:
        return True

    all_tool_text = " ".join(tool_outputs)
    tool_numbers = extract_numbers(all_tool_text)
    return len(answer_numbers - tool_numbers) == 0


# --------------------------------------------------------------------------
# Construction de l'agent
# --------------------------------------------------------------------------

def build_agent():
    """Construit et retourne l'agent LangGraph compilé. Pas de mise en
    cache ici — c'est à la couche interface de décider (ex: st.cache_resource
    côté Streamlit) puisque le mécanisme de cache dépend du framework."""
    set_llm_cache(SQLiteCache(database_path=config.LLM_CACHE_PATH))

    # Connexion en LECTURE SEULE : empêche tout DROP/DELETE/UPDATE/INSERT.
    # include_tables restreint l'agent à fct_business_performance.
    db = SQLDatabase.from_uri(
        f"duckdb:///{config.DUCKDB_PATH}",
        include_tables=config.ALLOWED_TABLES,
        engine_args={"connect_args": {"read_only": True}},
    )
    llm = ChatOpenAI(
        model=config.MODEL_ID,
        base_url=config.OPENROUTER_BASE_URL,
        api_key=config.OPENROUTER_API_KEY,
        temperature=0,
        max_tokens=512,
        streaming=True,
    )
    toolkit = SQLDatabaseToolkit(db=db, llm=llm)
    tools = toolkit.get_tools()
    memory = MemorySaver()
    return create_react_agent(llm, tools, prompt=SYSTEM_PROMPT, checkpointer=memory)


# --------------------------------------------------------------------------
# Streaming — événements génériques, indépendants de toute UI
# --------------------------------------------------------------------------

@dataclass
class StreamEvent:
    type: str  # "token" | "tool_result" | "final"
    content: str = ""
    tool_outputs: list[str] = field(default_factory=list)


async def stream_agent_response(
    agent, question: str, thread_id: str
) -> AsyncIterator[StreamEvent]:
    """Générateur asynchrone : yield un StreamEvent par token généré et par
    résultat d'outil, puis un dernier événement "final" avec la réponse
    complète (anonymisée) et tous les résultats d'outils accumulés.

    La couche interface (Streamlit, CLI, etc.) consomme ce générateur et
    décide comment afficher chaque événement — aucune dépendance UI ici.
    """
    agent_config = {"configurable": {"thread_id": thread_id}}
    accumulated = ""
    tool_outputs: list[str] = []

    async for event in agent.astream_events(
        {"messages": [HumanMessage(content=question)]}, config=agent_config, version="v2"
    ):
        kind = event["event"]

        if kind == "on_chat_model_stream":
            chunk = event["data"]["chunk"]
            token = getattr(chunk, "content", "") or ""
            if token:
                accumulated += token
                yield StreamEvent(type="token", content=anonymize(token))

        elif kind == "on_tool_end":
            output = str(event["data"].get("output", ""))
            tool_outputs.append(output)
            yield StreamEvent(type="tool_result", content=anonymize(output))

    # Filet de sécurité : si le streaming n'a rien produit (fournisseur qui
    # ne supporte pas le streaming token par token), on refait un appel
    # classique non streamé pour ne pas laisser l'utilisateur sans réponse.
    if not accumulated.strip():
        fallback = await agent.ainvoke(
            {"messages": [HumanMessage(content=question)]}, config=agent_config
        )
        accumulated = fallback["messages"][-1].content

    yield StreamEvent(
        type="final", content=anonymize(accumulated), tool_outputs=tool_outputs
    )