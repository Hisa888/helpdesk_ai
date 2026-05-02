from __future__ import annotations

from helpdesk_app.modules.clarification_state import ensure_clarification_state, is_clarification_pending
from helpdesk_app.modules.voice_input_panel import render_voice_input_widget


def ensure_chat_session_state(st) -> None:
    ensure_clarification_state(st)
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
    pending_q = str(st.session_state.get("pending_q", "") or "").strip()

    clarification_mode = is_clarification_pending(st)
    current_placeholder = "追加情報を入力してください" if clarification_mode else placeholder

    # Streamlit の st.chat_input は画面下部の固定入力欄です。
    # 通常質問用/追加情報用で key を切り替えると、環境によっては
    # 「アプリ」→追加質問→「インストール」Enter の追加入力を取りこぼすことがあります。
    # placeholder だけを切り替え、key は常に固定して安定させます。
    input_key = "main_chat_input"

    st.markdown('<div id="query-input-anchor"></div>', unsafe_allow_html=True)
    render_voice_input_widget(st, auto_submit=False)
    user_q = st.chat_input(current_placeholder, key=input_key)

    if pending_q:
        st.session_state.pending_q = ""
        return pending_q, True

    return str(user_q or "").strip(), False


def append_user_message(*, st, user_q: str) -> None:
    st.session_state.messages.append({"role": "user", "content": user_q})
