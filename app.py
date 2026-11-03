
import asyncio
import uuid
import streamlit as st

import config
from agent import build_agent, check_grounding, stream_agent_response

st.set_page_config(page_title="Agent données Awalé", page_icon="🤖")

# Gestion propre des secrets manquants : évite un crash brutal avec
# traceback Python visible par l'utilisateur final.
_missing = config.missing_env_vars()
if _missing:
    st.error(
        f"Configuration manquante : {', '.join(_missing)}. "
        "Vérifie les secrets/variables d'environnement du déploiement."
    )
    st.stop()

# UUID de session : identifie la conversation pour la mémoire de l'agent
# (thread_id du checkpointer LangGraph dans agent.py).
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

st.title("🤖 Agent d'analyse — données Awalé Boissons")
st.caption(f"Session : `{st.session_state.session_id}`")


def _run_async(coro):
    """Exécute une coroutine en gérant le cas 'Event loop is closed' de Streamlit.

    `asyncio.run()` crée/ferme une boucle à chaque appel. Au 2e message,
    `asyncio.get_event_loop()` peut retourner la boucle fermée par l'appel
    précédent, d'où `RuntimeError: Event loop is closed`.
    On détecte ce cas et on recrée une boucle neuve. Si une boucle tourne
    déjà, on exécute dans un thread séparé.
    """
    try:
        running = asyncio.get_running_loop()
        if running and not running.is_closed():
            import concurrent.futures

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


@st.cache_resource
def get_cached_agent():
    return build_agent()


agent = get_cached_agent()

# --------------------------------------------------------------------------
# Avatar animé (pastille qui pulse pendant la réflexion, via CSS)
# --------------------------------------------------------------------------

THINKING_HTML = """
<style>
@keyframes pulse-avatar {
  0%, 100% { transform: scale(1); opacity: 1; }
  50% { transform: scale(1.15); opacity: 0.6; }
}
.thinking-avatar {
  display: inline-block;
  font-size: 20px;
  animation: pulse-avatar 1s ease-in-out infinite;
}
</style>
<span class="thinking-avatar">🤖</span> <i>L'agent réfléchit et interroge les données...</i>
"""

# --------------------------------------------------------------------------
# Interface chat
# --------------------------------------------------------------------------

if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    avatar = "🤖" if msg["role"] == "assistant" else None
    with st.chat_message(msg["role"], avatar=avatar):
        st.markdown(msg["content"])

if question := st.chat_input("Pose une question sur les données Awalé..."):
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant", avatar="🤖"):
        thinking_placeholder = st.empty()
        thinking_placeholder.markdown(THINKING_HTML, unsafe_allow_html=True)
        response_placeholder = st.empty()

        async def consume_stream():
            accumulated = ""
            tool_outputs: list[str] = []
            async for ev in stream_agent_response(agent, question, st.session_state.session_id):
                if ev.type == "token":
                    accumulated += ev.content
                    response_placeholder.markdown(accumulated + "▌")
                elif ev.type == "tool_result":
                    tool_outputs.append(ev.content)
                elif ev.type == "final":
                    accumulated = ev.content
                    tool_outputs = ev.tool_outputs
                    response_placeholder.markdown(accumulated)
            return accumulated, tool_outputs

        try:
            final_answer, tool_outputs = _run_async(consume_stream())
            thinking_placeholder.empty()

            if not check_grounding(final_answer, tool_outputs):
                st.warning(
                    "⚠️ Certains chiffres de cette réponse n'ont pas pu être "
                    "confirmés dans les résultats de requête exécutés. "
                    "À vérifier avant utilisation.",
                    icon="⚠️",
                )

            with st.expander("Voir les étapes de l'agent (anonymisées)"):
                for i, output in enumerate(tool_outputs, start=1):
                    st.text(f"Résultat requête {i} :\n{output}")

            st.session_state.messages.append({"role": "assistant", "content": final_answer})
        except Exception as e:
            thinking_placeholder.empty()
            error_msg = f"Erreur : {e}"
            st.error(error_msg)
            st.session_state.messages.append({"role": "assistant", "content": error_msg})
