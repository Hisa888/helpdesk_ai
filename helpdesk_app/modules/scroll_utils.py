from __future__ import annotations


def ensure_scroll_state(st) -> None:
    if "scroll_to_answer" not in st.session_state:
        st.session_state.scroll_to_answer = True
    if "focus_chat_input_pending" not in st.session_state:
        st.session_state.focus_chat_input_pending = True


def request_scroll_to_answer(st) -> None:
    st.session_state["scroll_to_answer"] = True
    st.session_state["focus_chat_input_pending"] = True


def render_scroll_to_latest_answer(components, *, delay_ms: int = 80) -> None:
    components.html(
        f"""
        <script>
        const focusChatInput = () => {{
          const doc = window.parent.document;
          const anchor = doc.getElementById('query-input-anchor');
          if (anchor) {{
            anchor.scrollIntoView({{ behavior: 'auto', block: 'center' }});
          }}

          const candidates = [
            'div[data-testid="stChatInput"] textarea',
            'div[data-testid="stChatInput"] input',
            'textarea[aria-label]',
            'input[aria-label="情シス問い合わせを入力してください"]',
            'input[aria-label="追加情報を入力してください"]'
          ];

          let el = null;
          for (const selector of candidates) {{
            el = doc.querySelector(selector);
            if (el) break;
          }}
          if (el) {{
            el.focus({{ preventScroll: true }});
            try {{
              const len = el.value ? el.value.length : 0;
              if (typeof el.setSelectionRange === 'function') {{
                el.setSelectionRange(len, len);
              }}
            }} catch (e) {{}}
          }}
        }};
        setTimeout(focusChatInput, {delay_ms});
        setTimeout(focusChatInput, {delay_ms + 250});
        </script>
        """,
        height=0,
    )


def maybe_scroll_to_latest_answer(*, st, components) -> None:
    should_focus = bool(st.session_state.get("scroll_to_answer", False) or st.session_state.get("focus_chat_input_pending", False))
    if should_focus:
        render_scroll_to_latest_answer(components)
    st.session_state["scroll_to_answer"] = False
    st.session_state["focus_chat_input_pending"] = False
