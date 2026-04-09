from __future__ import annotations

from typing import Sequence, Tuple

DEFAULT_QUICK_STARTS: Sequence[Tuple[str, str, str]] = (
    ("🔐 パスワードを忘れた", "パスワードを忘れました", "quick_start_password"),
    ("🧩 アカウントがロックされた", "アカウントがロックされました", "quick_start_lock"),
    ("🌐 VPNに接続できない", "VPNに接続できません", "quick_start_vpn"),
)


def ensure_quick_start_session_state(st) -> None:
    if "pending_q" not in st.session_state:
        st.session_state.pending_q = ""


def _render_buttons(st, *, quick_starts: Sequence[Tuple[str, str, str]], key_suffix: str) -> None:
    cols = st.columns(len(quick_starts))
    for col, (label, query, key) in zip(cols, quick_starts):
        if col.button(label, key=f"{key}_{key_suffix}", width="stretch"):
            st.session_state.pending_q = query
            st.session_state["scroll_to_answer"] = True
            st.rerun()


def render_quick_start_hero(st, *, quick_starts: Sequence[Tuple[str, str, str]] = DEFAULT_QUICK_STARTS) -> None:
    st.markdown(
        '<div class="glass-card query-panel"><div class="eyebrow">Quick Start</div><h3>よくある問い合わせをワンクリックで試す</h3><p>デモで見せやすい代表質問を用意しています。クリックするとそのまま送信されます。</p></div>',
        unsafe_allow_html=True,
    )
    st.markdown("### 💡 おすすめ質問（クリックで送信）")
    _render_buttons(st, quick_starts=quick_starts, key_suffix="hero")


def render_quick_start_compact(st, *, quick_starts: Sequence[Tuple[str, str, str]] = DEFAULT_QUICK_STARTS) -> None:
    st.markdown('<div class="eyebrow" style="margin-top:8px;">Quick Start</div>', unsafe_allow_html=True)
    st.caption("よく使う質問をすぐ送信できます")
    _render_buttons(st, quick_starts=quick_starts, key_suffix="compact")
