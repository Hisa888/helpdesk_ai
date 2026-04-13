from __future__ import annotations


def ensure_scroll_state(st) -> None:
    if "scroll_to_answer" not in st.session_state:
        st.session_state.scroll_to_answer = False


def request_scroll_to_answer(st) -> None:
    st.session_state["scroll_to_answer"] = True


def render_scroll_to_latest_answer(components, *, delay_ms: int = 80) -> None:
    components.html(
        f"""
        <html>
          <head>
            <style>
              html, body {{
                margin: 0;
                padding: 0;
                width: 1px;
                height: 1px;
                overflow: hidden !important;
                background: transparent;
              }}
            </style>
          </head>
          <body>
            <script>
              const run = () => {{
                const doc = window.parent.document;
                const anchor = doc.getElementById('answer-anchor');
                const answers = doc.querySelectorAll('.answerbox');
                const target = anchor || (answers.length ? answers[answers.length - 1] : null);
                if (target) {{
                  target.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
                }}
              }};
              requestAnimationFrame(() => setTimeout(run, {delay_ms}));
            </script>
          </body>
        </html>
        """,
        height=1,
        width=1,
        scrolling=False,
    )


def maybe_scroll_to_latest_answer(*, st, components) -> None:
    if st.session_state.get("scroll_to_answer") and st.session_state.get("messages"):
        render_scroll_to_latest_answer(components)
        st.session_state["scroll_to_answer"] = False
