from __future__ import annotations


def render_search_settings_panel(
    *,
    st,
    current_search_settings,
    save_search_settings,
    default_search_settings,
) -> None:
    with st.expander("🎯 検索精度設定", expanded=False):
        current_cfg = current_search_settings()
        st.caption("管理者が検索の厳しさを分かりやすく調整できます。まずは上の基本設定だけ触れば十分です。")
        st.info(
            f"現在値：FAQ自動回答 {current_cfg['answer_threshold']:.2f} / 候補表示 {current_cfg['suggest_threshold']:.2f} / "
            f"Doc採用しきい値 {float(current_cfg.get('doc_rag_threshold', 0.55)):.2f} / "
            f"DocがFAQを上回る差分 {float(current_cfg.get('doc_compare_margin', 0.05)):.2f} / "
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


        st.markdown("#### ② FAQ / Doc 比較設定")
        doc_rag_threshold = st.slider(
            "Doc採用しきい値",
            min_value=0.10,
            max_value=1.20,
            value=float(current_cfg.get("doc_rag_threshold", 0.55)),
            step=0.01,
            key="admin_doc_rag_threshold_slider",
            help="社内ドキュメントの一致度がこの値以上なら、Doc回答候補として使います。高いほど慎重です。",
        )
        doc_compare_margin = st.slider(
            "DocがFAQを上回る差分",
            min_value=0.00,
            max_value=0.50,
            value=float(current_cfg.get("doc_compare_margin", 0.05)),
            step=0.01,
            key="admin_doc_compare_margin_slider",
            help="FAQとDocの両方がしきい値を超えたとき、DocスコアがFAQスコアをこの値以上上回ったらDocを採用します。",
        )
        st.caption(
            "判定ルール: FAQが自動回答しきい値以上ならFAQ候補になります。DocがDoc採用しきい値以上で、さらにFAQより差分以上強い場合はDocを採用します。"
        )

        st.markdown("#### ③ FAQ項目別の重み")
        st.caption("FAQのどの項目を検索で強く見るかを調整します。通常は question / intent / keywords を高め、answer は低めがおすすめです。")
        w1, w2, w3 = st.columns(3)
        with w1:
            question_weight = st.slider("question（ユーザー言語）", 0.00, 5.00, float(current_cfg.get("question_weight", 3.00)), 0.10, key="search_question_weight")
            answer_weight = st.slider("answer（結論→手順）", 0.00, 5.00, float(current_cfg.get("answer_weight", 0.50)), 0.10, key="search_answer_weight")
        with w2:
            intent_weight = st.slider("intent（意味）", 0.00, 5.00, float(current_cfg.get("intent_weight", 2.50)), 0.10, key="search_intent_weight")
            keywords_weight = st.slider("keywords（言い換え）", 0.00, 5.00, float(current_cfg.get("keywords_weight", 2.00)), 0.10, key="search_keywords_weight")
        with w3:
            category_weight = st.slider("category（分類）", 0.00, 5.00, float(current_cfg.get("category_weight", 1.00)), 0.10, key="search_category_weight")
            st.info("目安: question 3.0 / intent 2.5 / keywords 2.0 / category 1.0 / answer 0.5")

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

            st.markdown("##### 安全検索ガード")
            st.caption("嘘回答を避けるため、業務用語が合わない場合や候補差が小さい場合は自動回答せず『もしかしてこれですか？』に回します。")
            g1, g2 = st.columns(2)
            with g1:
                strict_safety_mode = st.checkbox("安全検索ガードを有効にする", value=bool(current_cfg.get("strict_safety_mode", True)), key="search_strict_safety_mode")
                auto_answer_min_gap = st.slider("1位と2位の最低差分", 0.00, 0.50, float(current_cfg.get("auto_answer_min_gap", 0.10)), 0.01, key="search_auto_answer_min_gap")
                high_confidence_score = st.slider("高信頼スコア", 0.10, 1.20, float(current_cfg.get("high_confidence_score", 0.80)), 0.01, key="search_high_confidence_score")
                maybe_candidate_threshold = st.slider("低スコア候補表示しきい値", 0.00, 0.50, float(current_cfg.get("maybe_candidate_threshold", 0.01)), 0.01, key="search_maybe_candidate_threshold")
                maybe_candidate_count = st.slider("もしかして候補数", 1, 10, int(current_cfg.get("maybe_candidate_count", 5)), 1, key="search_maybe_candidate_count")
            with g2:
                specific_term_bonus = st.slider("業務用語一致ボーナス", 0.00, 2.00, float(current_cfg.get("specific_term_bonus", 0.70)), 0.01, key="search_specific_term_bonus")
                specific_mismatch_penalty = st.slider("業務用語不一致ペナルティ", 0.00, 2.00, float(current_cfg.get("specific_mismatch_penalty", 0.70)), 0.01, key="search_specific_mismatch_penalty")
                required_keyword_mismatch_penalty = st.slider("必須キーワード不一致ペナルティ", 0.00, 2.00, float(current_cfg.get("required_keyword_mismatch_penalty", 0.90)), 0.01, key="search_required_keyword_mismatch_penalty")
                exclude_keyword_penalty = st.slider("除外キーワード一致ペナルティ", 0.00, 2.00, float(current_cfg.get("exclude_keyword_penalty", 1.00)), 0.01, key="search_exclude_keyword_penalty")

        col_th1, col_th2 = st.columns(2)
        with col_th1:
            if st.button("💾 検索設定を保存", width="stretch", key="save_search_settings_btn"):
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
                        "doc_rag_threshold": doc_rag_threshold,
                        "doc_compare_margin": doc_compare_margin,
                        "question_weight": question_weight,
                        "answer_weight": answer_weight,
                        "intent_weight": intent_weight,
                        "keywords_weight": keywords_weight,
                        "category_weight": category_weight,
                        "strict_safety_mode": strict_safety_mode,
                        "auto_answer_min_gap": auto_answer_min_gap,
                        "high_confidence_score": high_confidence_score,
                        "maybe_candidate_threshold": maybe_candidate_threshold,
                        "maybe_candidate_count": maybe_candidate_count,
                        "specific_term_bonus": specific_term_bonus,
                        "specific_mismatch_penalty": specific_mismatch_penalty,
                        "required_keyword_mismatch_penalty": required_keyword_mismatch_penalty,
                        "exclude_keyword_penalty": exclude_keyword_penalty,
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
                try:
                    st.cache_resource.clear()
                    st.cache_data.clear()
                except Exception:
                    pass
                st.rerun()
        with col_th2:
            if st.button("↩ 初期値に戻す", width="stretch", key="reset_search_settings_btn"):
                ok, settings = save_search_settings(extra_settings=default_search_settings())
                st.session_state.search_threshold = settings["answer_threshold"]
                st.session_state.suggest_threshold = settings["suggest_threshold"]
                st.session_state.search_settings = settings
                if ok:
                    st.success("検索設定を初期値に戻しました。")
                else:
                    st.warning("初期値に戻しましたが、外部保存に失敗した可能性があります。")
                try:
                    st.cache_resource.clear()
                    st.cache_data.clear()
                except Exception:
                    pass
                st.rerun()
