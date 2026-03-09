import streamlit as st

from core.config import init_app
from core.feature_flags import ff
from faq.faq_loader import load_faq
from ai.search_engine import search_faq
from ai.ai_answer import generate_ai_answer
from ui.header import render_header
from ui.sidebar import render_sidebar
from ui.chat_ui import render_chat
from logs.log_manager import save_nohit_log
from admin.admin_panel import render_admin_panel

init_app()
faq_df = load_faq()

render_header()
render_sidebar()

question = render_chat()

if question:
    result = search_faq(question, faq_df)
    if result["score"] >= 0.4:
        answer = generate_ai_answer(question, result["faq"])
        st.success(answer)
        if ff("reference_faq"):
            with st.expander("参照したFAQ"):
                st.write(f"質問: {result['faq'].get('question', '')}")
                st.write(f"回答: {result['faq'].get('answer', '')}")
                st.write(f"カテゴリ: {result['faq'].get('category', '')}")
                st.progress(min(max(float(result["score"]), 0.0), 1.0), text=f"一致度: {int(result['score'] * 100)}%")
    else:
        st.warning("該当するFAQが見つかりませんでした。")
        save_nohit_log(question)
        st.info("管理者が FAQ を追加すると次回以降は自動回答できるようになります。")

if st.session_state.get("admin_mode"):
    render_admin_panel(faq_df)
