from __future__ import annotations


def render_llm_settings_panel(
    *,
    st,
    current_llm_settings,
    save_llm_settings,
    default_llm_settings,
) -> None:
    current_llm = current_llm_settings()
    provider = st.radio(
        "利用するLLM",
        options=["groq", "ollama"],
        index=0 if current_llm["provider"] == "groq" else 1,
        format_func=lambda x: "Groq（クラウド・高速）" if x == "groq" else "Ollama（ローカル・社内完結）",
        key="llm_provider_radio",
    )
    groq_model = st.text_input("Groqモデル名", value=current_llm["groq_model"], key="groq_model_input")
    ollama_model = st.text_input("Ollamaモデル名", value=current_llm["ollama_model"], key="ollama_model_input")
    ollama_base_url = st.text_input("Ollama URL", value=current_llm["ollama_base_url"], key="ollama_base_url_input")

    col_llm1, col_llm2 = st.columns(2)
    with col_llm1:
        if st.button("💾 LLM設定を保存", width="stretch", key="save_llm_settings"):
            ok, saved = save_llm_settings({
                "provider": provider,
                "groq_model": groq_model,
                "ollama_model": ollama_model,
                "ollama_base_url": ollama_base_url,
            })
            st.session_state["llm_settings"] = saved
            if ok:
                st.success("LLM設定を保存しました。")
            else:
                st.warning("LLM設定は反映済みですが、保存に失敗した可能性があります。")
            st.rerun()

    with col_llm2:
        if st.button("↩ LLM設定を初期値に戻す", width="stretch", key="reset_llm_settings"):
            default_llm = default_llm_settings()
            save_llm_settings(default_llm)
            st.session_state["llm_settings"] = default_llm
            st.rerun()

    provider_label = "Groq（クラウド・高速）" if provider == "groq" else "Ollama（ローカル・社内完結）"
    st.caption(f"現在の利用先: {provider_label}")
    if provider == "ollama":
        st.info("Ollamaはローカル実行です。初回はモデルを事前に pull してください。")
