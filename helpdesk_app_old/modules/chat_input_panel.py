from __future__ import annotations


def ensure_chat_session_state(st) -> None:
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "pending_q" not in st.session_state:
        st.session_state.pending_q = ""
    if "used_hits" not in st.session_state:
        st.session_state.used_hits = []
    if "pending_nohit_active" not in st.session_state:
        st.session_state.pending_nohit_active = False
    if "pending_nohit" not in st.session_state:
        st.session_state.pending_nohit = {}


def render_chat_input(st, *, placeholder: str = "情シス問い合わせを入力してください"):
    chat_typed = st.chat_input(placeholder)
    pending_q = st.session_state.get("pending_q", "")
    user_q = chat_typed or pending_q
    used_pending = (not chat_typed) and bool(pending_q)
    if user_q:
        st.session_state.pending_q = ""
    return user_q, used_pending


def append_user_message(*, st, user_q: str) -> None:
    st.session_state.messages.append({"role": "user", "content": user_q})
    with st.chat_message("user"):
        st.markdown(user_q)
