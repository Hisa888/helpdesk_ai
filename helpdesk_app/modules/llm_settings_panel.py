from __future__ import annotations


def render_llm_settings_panel(
    *,
    st,
    current_llm_settings,
    save_llm_settings,
    default_llm_settings,
) -> None:
    current_llm = current_llm_settings()

    provider_options = ["gemini", "groq", "ollama"]
    provider_labels = {
        "gemini": "Gemini Flash（無料枠・推奨）",
        "groq": "Groq（クラウド・高速）",
        "ollama": "Ollama（ローカル・社内完結）",
    }
    current_provider = str(current_llm.get("provider", "gemini")).strip().lower()
    if current_provider not in provider_options:
        current_provider = "gemini"

    provider = st.radio(
        "利用するLLM",
        options=provider_options,
        index=provider_options.index(current_provider),
        format_func=lambda x: provider_labels.get(x, x),
        key="llm_provider_radio",
    )

    gemini_model = st.text_input(
        "Geminiモデル名",
        value=current_llm.get("gemini_model", "gemini-2.5-flash-lite"),
        key="gemini_model_input",
        help="無料枠で使う場合は gemini-2.5-flash-lite を推奨します。",
    )
    groq_model = st.text_input("Groqモデル名", value=current_llm.get("groq_model", "llama-3.1-8b-instant"), key="groq_model_input")
    ollama_model = st.text_input("Ollamaモデル名", value=current_llm.get("ollama_model", "qwen2.5:7b"), key="ollama_model_input")
    ollama_base_url = st.text_input("Ollama URL", value=current_llm.get("ollama_base_url", "http://localhost:11434"), key="ollama_base_url_input")

    col_llm1, col_llm2 = st.columns(2)
    with col_llm1:
        if st.button("💾 LLM設定を保存", width="stretch", key="save_llm_settings"):
            ok, saved = save_llm_settings({
                "provider": provider,
                "gemini_model": gemini_model,
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

    st.caption(f"現在の利用先: {provider_labels.get(provider, provider)}")
    if provider == "gemini":
        st.info("Gemini Flash Liteを使います。Streamlit Secrets または環境変数に GEMINI_API_KEY を設定してください。")
    elif provider == "ollama":
        st.info("Ollamaはローカル実行です。初回はモデルを事前に pull してください。")
