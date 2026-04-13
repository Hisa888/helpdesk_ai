from __future__ import annotations

import streamlit.components.v1 as components


def render_search_settings_ui(**ctx):
    st = ctx["st"]
    current_search_settings = ctx["current_search_settings"]
    save_search_settings = ctx["save_search_settings"]
    default_search_settings = ctx["default_search_settings"]
    current_llm_settings = ctx["current_llm_settings"]
    save_llm_settings = ctx["save_llm_settings"]
    default_llm_settings = ctx["default_llm_settings"]
    current_ui_theme_settings = ctx["current_ui_theme_settings"]
    sanitize_ui_theme_settings = ctx["sanitize_ui_theme_settings"]
    save_ui_theme_settings = ctx["save_ui_theme_settings"]
    default_ui_theme_settings = ctx["default_ui_theme_settings"]
    current_ui_layout_settings = ctx["current_ui_layout_settings"]
    sanitize_ui_layout_settings = ctx["sanitize_ui_layout_settings"]
    save_ui_layout_settings = ctx["save_ui_layout_settings"]
    default_ui_layout_settings = ctx["default_ui_layout_settings"]

    with st.expander("🎯 検索精度設定", expanded=False):
        current_cfg = current_search_settings()
        st.caption("管理者が検索の厳しさを分かりやすく調整できます。まずは上の基本設定だけ触れば十分です。")
        st.info(
            f"現在値：自動回答 {current_cfg['answer_threshold']:.2f} / 候補表示 {current_cfg['suggest_threshold']:.2f} / "
            f"単語重視 {int(current_cfg['word_weight'] * 100)}% / 文字重視 {int(current_cfg['char_weight'] * 100)}%"
        )

        st.markdown("#### ① 基本設定（通常はここだけ）")
        admin_answer_threshold = st.slider(
            "自動回答しきい値",
            min_value=0.10,
            max_value=1.20,
            value=float(current_cfg["answer_threshold"]),
            step=0.01,
            key="admin_answer_threshold_slider",
            help="この値以上ならそのまま回答します。高いほど慎重、低いほど積極的です。",
        )
        max_suggest_value = max(0.05, round(admin_answer_threshold - 0.05, 2))
        suggest_default = min(float(current_cfg["suggest_threshold"]), max_suggest_value)
        admin_suggest_threshold = st.slider(
            "候補表示しきい値",
            min_value=0.05,
            max_value=max_suggest_value,
            value=suggest_default,
            step=0.01,
            key="admin_suggest_threshold_slider",
            help="この値以上かつ自動回答未満なら『近いFAQ候補』として表示します。",
        )

        search_balance = st.radio(
            "検索バランス",
            options=["バランス型", "単語重視", "表記ゆれ重視"],
            index=0 if abs(float(current_cfg["word_weight"]) - 0.54) < 0.03 else (1 if float(current_cfg["word_weight"]) >= 0.60 else 2),
            horizontal=True,
            help="単語重視は意味の近い語句に強く、表記ゆれ重視は細かな言い回し違いに強くなります。",
        )
        if search_balance == "単語重視":
            word_weight, char_weight = 0.65, 0.35
        elif search_balance == "表記ゆれ重視":
            word_weight, char_weight = 0.40, 0.60
        else:
            word_weight, char_weight = 0.54, 0.46

        answer_gap = round(admin_answer_threshold - admin_suggest_threshold, 2)
        if answer_gap >= 0.18:
            st.success("判定差は広めです。誤回答を抑えやすい設定です。")
        elif answer_gap >= 0.10:
            st.info("判定差は標準です。迷ったときは候補表示へ回しやすい設定です。")
        else:
            st.warning("判定差が狭めです。自動回答と候補表示の境目が近くなります。")

        st.markdown("""- 自動回答以上: 通常回答
    - 候補表示以上: 近いFAQ候補を表示
    - 候補表示未満: 該当なしとして追加情報フォームへ""")

        with st.expander("🔧 詳細設定（上級者向け）", expanded=False):
            st.caption("より細かく精度を触りたい場合だけ使ってください。未設定なら基本設定のままでも十分です。")

            c_adv1, c_adv2 = st.columns(2)
            with c_adv1:
                exact_bonus = st.slider("完全一致ボーナス", 0.00, 0.80, float(current_cfg["exact_bonus"]), 0.01, key="search_exact_bonus")
                contains_bonus = st.slider("部分一致ボーナス", 0.00, 0.60, float(current_cfg["contains_bonus"]), 0.01, key="search_contains_bonus")
                token_bonus_max = st.slider("単語一致ボーナス上限", 0.00, 0.80, float(current_cfg["token_bonus_max"]), 0.01, key="search_token_bonus")
                concept_bonus_max = st.slider("概念一致ボーナス上限", 0.00, 0.80, float(current_cfg["concept_bonus_max"]), 0.01, key="search_concept_bonus")
                prefix_bonus = st.slider("書き出し一致ボーナス", 0.00, 0.30, float(current_cfg["prefix_bonus"]), 0.01, key="search_prefix_bonus")
                top_k = st.slider("候補として保持する件数", 1, 5, int(current_cfg["top_k"]), 1, key="search_top_k")
            with c_adv2:
                semantic_enabled = st.checkbox("意味検索を使う", value=bool(current_cfg["semantic_enabled"]), key="search_semantic_enabled")
                semantic_skip_fastlane = st.checkbox("頻出問い合わせでは意味検索を省略", value=bool(current_cfg["semantic_skip_fastlane"]), key="search_semantic_skip_fastlane")
                semantic_boost = st.slider("意味検索の補正強さ", 0.00, 0.80, float(current_cfg["semantic_boost"]), 0.01, key="search_semantic_boost")
                semantic_candidate_count = st.slider("意味検索をかける候補数", 1, 20, int(current_cfg["semantic_candidate_count"]), 1, key="search_semantic_candidate_count")
                semantic_min_query_len = st.slider("意味検索を始める最小文字数", 1, 50, int(current_cfg["semantic_min_query_len"]), 1, key="search_semantic_min_query_len")
                semantic_trigger_min = st.slider("意味検索を始める下限スコア", 0.00, 1.20, float(current_cfg["semantic_trigger_min"]), 0.01, key="search_semantic_trigger_min")
                semantic_trigger_max = st.slider("意味検索を始める上限スコア", max(semantic_trigger_min, 0.00), 1.50, float(max(current_cfg["semantic_trigger_max"], semantic_trigger_min)), 0.01, key="search_semantic_trigger_max")

        col_th1, col_th2 = st.columns(2)
        with col_th1:
            if st.button("💾 検索設定を保存", width="stretch"):
                ok, settings = save_search_settings(
                    admin_answer_threshold,
                    admin_suggest_threshold,
                    extra_settings={
                        "word_weight": word_weight,
                        "char_weight": char_weight,
                        "exact_bonus": exact_bonus,
                        "contains_bonus": contains_bonus,
                        "token_bonus_max": token_bonus_max,
                        "concept_bonus_max": concept_bonus_max,
                        "prefix_bonus": prefix_bonus,
                        "semantic_enabled": semantic_enabled,
                        "semantic_skip_fastlane": semantic_skip_fastlane,
                        "semantic_boost": semantic_boost,
                        "semantic_candidate_count": semantic_candidate_count,
                        "semantic_min_query_len": semantic_min_query_len,
                        "semantic_trigger_min": semantic_trigger_min,
                        "semantic_trigger_max": semantic_trigger_max,
                        "top_k": top_k,
                    },
                )
                st.session_state.search_threshold = settings["answer_threshold"]
                st.session_state.suggest_threshold = settings["suggest_threshold"]
                st.session_state.search_settings = settings
                if ok:
                    st.success(
                        f"保存しました。自動回答={settings['answer_threshold']:.2f} / 候補表示={settings['suggest_threshold']:.2f} / "
                        f"単語重視={int(settings['word_weight'] * 100)}%"
                    )
                else:
                    st.warning("ローカル保存またはGitHub保存に失敗した可能性があります。設定値自体はこのセッションに反映しています。")
                st.rerun()
        with col_th2:
            if st.button("↩ 初期値に戻す", width="stretch"):
                ok, settings = save_search_settings(extra_settings=default_search_settings())
                st.session_state.search_threshold = settings["answer_threshold"]
                st.session_state.suggest_threshold = settings["suggest_threshold"]
                st.session_state.search_settings = settings
                if ok:
                    st.success("検索設定を初期値に戻しました。")
                else:
                    st.warning("初期値に戻しましたが、外部保存に失敗した可能性があります。")
                st.rerun()


        # ===== FAQ自動生成（該当なしログ → FAQ案）=====
    with st.expander("🧠 LLM切替設定", expanded=False):
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

    with st.expander("🎨 UI配色設定", expanded=False):
        current_theme = current_ui_theme_settings()

        c1, c2 = st.columns(2)
        with c1:
            sidebar_bg_start = st.color_picker("左メニュー背景（開始色）", current_theme["sidebar_bg_start"], key="ui_sidebar_bg_start")
            sidebar_text = st.color_picker("左メニュー文字色", current_theme["sidebar_text"], key="ui_sidebar_text")
            sidebar_text_muted = st.color_picker("左メニュー補助文字色", current_theme["sidebar_text_muted"], key="ui_sidebar_text_muted")
            button_bg = st.color_picker("ボタン背景色", current_theme["button_bg"], key="ui_button_bg")
            button_text = st.color_picker("ボタン文字色", current_theme["button_text"], key="ui_button_text")
            button_border = st.color_picker("ボタン枠線色", current_theme["button_border"], key="ui_button_border")
            button_hover_bg = st.color_picker("ボタンホバー背景", current_theme["button_hover_bg"], key="ui_button_hover_bg")
            button_hover_text = st.color_picker("ボタンホバー文字", current_theme["button_hover_text"], key="ui_button_hover_text")
            button_disabled_bg = st.color_picker("無効ボタン背景色", current_theme["button_disabled_bg"], key="ui_button_disabled_bg")
            button_disabled_text = st.color_picker("無効ボタン文字色", current_theme["button_disabled_text"], key="ui_button_disabled_text")
        with c2:
            sidebar_bg_end = st.color_picker("左メニュー背景（終了色）", current_theme["sidebar_bg_end"], key="ui_sidebar_bg_end")
            main_bg_start = st.color_picker("メイン背景（開始色）", current_theme["main_bg_start"], key="ui_main_bg_start")
            main_bg_mid = st.color_picker("メイン背景（中央色）", current_theme["main_bg_mid"], key="ui_main_bg_mid")
            main_bg_end = st.color_picker("メイン背景（終了色）", current_theme["main_bg_end"], key="ui_main_bg_end")
            card_border = st.color_picker("カード枠線色", current_theme["card_border"], key="ui_card_border")
            resizer_knob = st.color_picker("ドラッグつまみ色", current_theme["resizer_knob"], key="ui_resizer_knob")

        sidebar_panel_bg = st.text_input("左メニューパネル背景（hex または rgba）", value=current_theme["sidebar_panel_bg"], key="ui_sidebar_panel_bg")
        sidebar_panel_border = st.text_input("左メニューパネル枠線（hex または rgba）", value=current_theme["sidebar_panel_border"], key="ui_sidebar_panel_border")
        card_bg = st.text_input("カード背景色（hex または rgba）", value=current_theme["card_bg"], key="ui_card_bg")
        resizer_line = st.text_input("ドラッグライン色（hex または rgba）", value=current_theme["resizer_line"], key="ui_resizer_line")

        live_theme = sanitize_ui_theme_settings({
            "sidebar_bg_start": sidebar_bg_start,
            "sidebar_bg_end": sidebar_bg_end,
            "sidebar_text": sidebar_text,
            "sidebar_text_muted": sidebar_text_muted,
            "sidebar_panel_bg": sidebar_panel_bg,
            "sidebar_panel_border": sidebar_panel_border,
            "button_bg": button_bg,
            "button_text": button_text,
            "button_border": button_border,
            "button_hover_bg": button_hover_bg,
            "button_hover_text": button_hover_text,
            "button_disabled_bg": button_disabled_bg,
            "button_disabled_text": button_disabled_text,
            "main_bg_start": main_bg_start,
            "main_bg_mid": main_bg_mid,
            "main_bg_end": main_bg_end,
            "card_bg": card_bg,
            "card_border": card_border,
            "resizer_line": resizer_line,
            "resizer_knob": resizer_knob,
        })
        st.session_state["ui_theme_settings"] = live_theme

        col_ui1, col_ui2 = st.columns(2)
        with col_ui1:
            if st.button("💾 UI配色を保存", width="stretch", key="save_ui_theme"):
                ok, _ = save_ui_theme_settings(live_theme)
                st.success("UI配色を保存しました。" if ok else "UI配色は反映済みですが、保存に失敗した可能性があります。")
        with col_ui2:
            if st.button("↩ UI配色を初期値に戻す", width="stretch", key="reset_ui_theme"):
                default_theme = default_ui_theme_settings()
                save_ui_theme_settings(default_theme)
                for k, v in default_theme.items():
                    st.session_state[f"ui_{k}"] = v
                st.session_state["ui_theme_settings"] = default_theme
                st.rerun()

    with st.expander("📐 UIレイアウト設定", expanded=False):
        current_layout = current_ui_layout_settings()
        sidebar_width = st.slider("左メニュー幅", 240, 620, int(current_layout["sidebar_width"]), key="ui_layout_sidebar_width")
        main_max_width = st.slider("メイン画面の最大幅", 760, 2000, int(current_layout["main_max_width"]), step=10, key="ui_layout_main_max_width")
        main_padding_top = st.slider("上余白", 4, 96, int(current_layout["main_padding_top"]), key="ui_layout_main_padding_top")
        main_padding_bottom = st.slider("下余白", 72, 280, int(current_layout["main_padding_bottom"]), key="ui_layout_main_padding_bottom")
        card_radius = st.slider("フレーム角丸", 8, 40, int(current_layout["card_radius"]), key="ui_layout_card_radius")
        card_shadow_blur = st.slider("フレーム影のぼかし", 0, 80, int(current_layout["card_shadow_blur"]), key="ui_layout_card_shadow_blur")
        card_shadow_alpha_pct = st.slider("フレーム影の濃さ", 0, 40, int(round(float(current_layout["card_shadow_alpha"]) * 100)), key="ui_layout_card_shadow_alpha")

        live_layout = sanitize_ui_layout_settings({
            "sidebar_width": sidebar_width,
            "main_max_width": main_max_width,
            "main_padding_top": main_padding_top,
            "main_padding_bottom": main_padding_bottom,
            "card_radius": card_radius,
            "card_shadow_blur": card_shadow_blur,
            "card_shadow_alpha": card_shadow_alpha_pct,
        })
        st.session_state["ui_layout_settings"] = live_layout

        components.html(f"""
        <script>
        (function() {{
            const doc = window.parent.document;
            const root = doc.documentElement;
            root.style.setProperty('--user-sidebar-width', '{live_layout['sidebar_width']}px');
            root.style.setProperty('--user-main-max-width', '{live_layout['main_max_width']}px');
            root.style.setProperty('--user-main-padding-top', '{live_layout['main_padding_top']}px');
            root.style.setProperty('--user-main-padding-bottom', '{live_layout['main_padding_bottom']}px');
            root.style.setProperty('--user-card-radius', '{live_layout['card_radius']}px');
            root.style.setProperty('--user-card-shadow', '0 10px {live_layout['card_shadow_blur']}px rgba(15, 23, 42, {live_layout['card_shadow_alpha']:.2f})');
            window.localStorage.setItem('oai_sidebar_width', '{live_layout['sidebar_width']}');
            window.localStorage.setItem('oai_main_max_width', '{live_layout['main_max_width']}');
        }})();
        </script>
        """, height=0, width=0)

        col_layout1, col_layout2 = st.columns(2)
        with col_layout1:
            if st.button("💾 UIレイアウトを保存", width="stretch", key="save_ui_layout"):
                ok, _ = save_ui_layout_settings(live_layout)
                st.success("UIレイアウトを保存しました。" if ok else "UIレイアウトは反映済みですが、保存に失敗した可能性があります。")
        with col_layout2:
            if st.button("↩ UIレイアウトを初期値に戻す", width="stretch", key="reset_ui_layout"):
                default_layout = default_ui_layout_settings()
                save_ui_layout_settings(default_layout)
                st.session_state["ui_layout_settings"] = default_layout
                window_local_js = f"""<script>(function(){{const doc=window.parent.document;const root=doc.documentElement;root.style.setProperty('--user-sidebar-width','{default_layout['sidebar_width']}px');root.style.setProperty('--user-main-max-width','{default_layout['main_max_width']}px');localStorage.removeItem('oai_sidebar_width');localStorage.removeItem('oai_main_max_width');}})();</script>"""
                components.html(window_local_js, height=0, width=0)
                st.rerun()

