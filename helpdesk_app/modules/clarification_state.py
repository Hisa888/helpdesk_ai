from __future__ import annotations


def ensure_clarification_state(st) -> None:
    defaults = {
        "clarification_pending": False,
        "clarification_original_question": "",
        "clarification_prompt": "",
        "clarification_count": 0,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def start_clarification(*, st, original_question: str, prompt_text: str) -> None:
    ensure_clarification_state(st)
    st.session_state["clarification_pending"] = True
    st.session_state["clarification_original_question"] = str(original_question or "").strip()
    st.session_state["clarification_prompt"] = str(prompt_text or "").strip()
    st.session_state["clarification_count"] = int(st.session_state.get("clarification_count", 0) or 0) + 1


def is_clarification_pending(st) -> bool:
    ensure_clarification_state(st)
    return bool(st.session_state.get("clarification_pending", False))


def get_clarification_original_question(st) -> str:
    ensure_clarification_state(st)
    return str(st.session_state.get("clarification_original_question", "") or "")


def get_clarification_prompt(st) -> str:
    ensure_clarification_state(st)
    return str(st.session_state.get("clarification_prompt", "") or "")


def get_clarification_count(st) -> int:
    ensure_clarification_state(st)
    return int(st.session_state.get("clarification_count", 0) or 0)


def clear_clarification(*, st, reset_count: bool = True) -> None:
    ensure_clarification_state(st)
    st.session_state["clarification_pending"] = False
    st.session_state["clarification_original_question"] = ""
    st.session_state["clarification_prompt"] = ""
    if reset_count:
        st.session_state["clarification_count"] = 0


def consume_clarification_followup(*, st, followup_text: str) -> str:
    ensure_clarification_state(st)
    original = str(st.session_state.get("clarification_original_question", "") or "").strip()
    followup = str(followup_text or "").strip()
    st.session_state["clarification_pending"] = False
    st.session_state["clarification_original_question"] = ""
    st.session_state["clarification_prompt"] = ""
    if not original:
        return followup
    if not followup:
        return original
    # 検索用の結合文。"補足情報" などのラベル語を混ぜると検索ノイズになるため、
    # 「アプリ インストール」のように自然な検索文へ変換する。
    return f"{original} {followup}".strip()
