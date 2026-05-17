from __future__ import annotations

from datetime import datetime

from helpdesk_app.modules.clarification_llm import generate_clarification_prompt
from helpdesk_app.modules.clarification_rules import should_request_clarification
from helpdesk_app.modules.clarification_state import clear_clarification, get_clarification_count, start_clarification
from helpdesk_app.modules.faq_answer_renderer import get_row_answer_format


def process_user_query(
    *,
    st,
    user_q: str,
    try_ultrafast_answer,
    retrieve_faq_cached,
    faq_cache_token_getter,
    ensure_faq_index_loaded,
    render_match_bar,
    current_search_settings,
    current_search_threshold,
    current_suggest_threshold,
    nohit_template,
    log_nohit,
    build_suggest_answer,
    fastlane_direct_answer,
    top_hit_is_ambiguous=None,
    build_prompt,
    llm_answer_cached,
    log_interaction,
    search_document_rag,
    answer_with_document_rag,
    doc_rag_threshold,
    llm_chat,
    skip_clarification: bool = False,
):
    ultrafast = try_ultrafast_answer(user_q)
    if ultrafast:
        hits = ultrafast.get("hits", [])
        best_score = float(ultrafast.get("best_score", 0.0))
    else:
        packed_hits = retrieve_faq_cached(user_q, faq_cache_token_getter())
        local_df, *_ = ensure_faq_index_loaded()
        hits = []
        for idx, score in packed_hits:
            try:
                if local_df is not None and int(idx) >= 0:
                    hits.append((local_df.iloc[int(idx)], float(score)))
            except Exception:
                continue
        best_score = hits[0][1] if hits else 0.0

    search_cfg = current_search_settings() if callable(current_search_settings) else {}

    # 低一致度の候補表示ガード。
    # 0.30以下の候補は「腹減った」のような業務外/雑談にも無理やりFAQ候補を出してしまい、
    # 品質が低く見えるため、候補表示・候補回答には進めない。
    try:
        candidate_min_display_score = float(search_cfg.get("candidate_min_display_score", 0.30))
    except Exception:
        candidate_min_display_score = 0.30

    def _candidate_display_allowed(score: float) -> bool:
        try:
            # 要件: 候補表示 0.3以下は回答/候補を表示しない
            return float(score) > float(candidate_min_display_score)
        except Exception:
            return False

    # 候補が表示可能な一致度の場合だけ、追加質問より「もしかしてこれ？」を優先する。
    # 低一致度では無関係なFAQ候補を出さず、該当なしに回す。
    try:
        maybe_threshold_for_clarify = max(float(search_cfg.get("maybe_candidate_threshold", 0.03)), candidate_min_display_score)
    except Exception:
        maybe_threshold_for_clarify = candidate_min_display_score
    has_candidate_for_suggest = bool(hits) and _candidate_display_allowed(float(best_score)) and float(best_score) >= maybe_threshold_for_clarify

    if (
        not skip_clarification
        and not has_candidate_for_suggest
        and get_clarification_count(st) < 1
    ):
        should_clarify, clarify_reason = should_request_clarification(
            question=user_q,
            best_score=float(best_score),
            answer_threshold=float(current_search_threshold()),
            suggest_threshold=float(current_suggest_threshold()),
        )
        if should_clarify:
            prompt_text = generate_clarification_prompt(user_q=user_q, llm_chat=llm_chat)
            start_clarification(st=st, original_question=user_q, prompt_text=prompt_text)
            return {
                "answer": prompt_text,
                "best_score": float(best_score),
                "answer_threshold": float(current_search_threshold()),
                "suggest_threshold": float(current_suggest_threshold()),
                "used_hits": [],
                "doc_hits": [],
                "used_doc_rag": False,
                "doc_best_score": 0.0,
                "was_nohit": False,
                "was_suggest": False,
                "was_clarification": True,
                "clarification_reason": clarify_reason,
                "answer_format": "markdown",
            }

    answer_threshold = current_search_threshold()
    suggest_threshold = current_suggest_threshold()
    answer_format = "markdown"
    doc_hits = []
    used_doc_rag = False
    doc_best_score = 0.0

    # 高速化: RAG検索は重いため、最初から毎回走らせない。
    # FAQで十分に回答できる場合はFAQだけで即時回答し、
    # FAQが弱い/曖昧な場合だけ後段でRAGを呼ぶ。
    def _lazy_search_document_rag() -> tuple[list, float]:
        if not callable(search_document_rag):
            return [], 0.0
        try:
            lazy_hits = search_document_rag(user_q, top_k=5) or []
            lazy_score = float(lazy_hits[0].get("score", 0.0)) if lazy_hits else 0.0
            return lazy_hits, lazy_score
        except Exception:
            return [], 0.0

    suggestion_candidates = []

    if ultrafast:
        used_hits = hits[:1]
        if hits:
            render_match_bar(best_score, label="FAQ一致度（採用）")
        answer = str(ultrafast.get("answer", "")).strip() or nohit_template()
        answer_format = get_row_answer_format(used_hits[0][0]) if used_hits else "markdown"
        was_nohit = False
        was_suggest = False
    else:
        doc_threshold = float(search_cfg.get("doc_rag_threshold", doc_rag_threshold))
        doc_compare_margin = float(search_cfg.get("doc_compare_margin", 0.05))
        faq_auto_ok = best_score >= answer_threshold
        doc_auto_ok = False
        prefer_doc = False
        ambiguous_auto = False
        if faq_auto_ok and callable(top_hit_is_ambiguous):
            try:
                # 高スコアでも候補差が小さい、または個別語が合っていない場合は、
                # 嘘の自動回答を避けて「もしかしてこれ？」に回す。
                ambiguous_auto = bool(top_hit_is_ambiguous(
                    user_q, hits, answer_threshold=float(answer_threshold), search_cfg=search_cfg
                ))
            except Exception:
                ambiguous_auto = False

        # FAQが弱い、またはFAQ側が曖昧な場合だけRAG検索する。
        # 管理画面で doc_rag_always_compare=true にすると従来通り比較検索も可能。
        should_search_doc = (
            bool(search_cfg.get("doc_rag_always_compare", False))
            or (not faq_auto_ok)
            or ambiguous_auto
        )
        if should_search_doc:
            doc_hits, doc_best_score = _lazy_search_document_rag()
            doc_auto_ok = bool(doc_hits) and doc_best_score >= doc_threshold
            prefer_doc = doc_auto_ok and (not faq_auto_ok or ambiguous_auto or doc_best_score >= (float(best_score) + doc_compare_margin))

        if hits:
            faq_label = "FAQ一致度（採用）" if (faq_auto_ok and not prefer_doc and not ambiguous_auto) else "FAQ一致度（参考候補）"
            render_match_bar(best_score, label=faq_label)
        if doc_hits:
            doc_label = "ドキュメント一致度（採用）" if prefer_doc else "ドキュメント一致度（参考候補）"
            render_match_bar(doc_best_score, label=doc_label)

        if prefer_doc:
            used_hits = []
            answer = answer_with_document_rag(user_q, doc_hits)
            answer_format = "markdown"
            was_nohit = False
            was_suggest = False
            used_doc_rag = True
        elif faq_auto_ok and not ambiguous_auto:
            used_hits = hits
            answer_format = get_row_answer_format(hits[0][0]) if hits else "markdown"
            was_nohit = False
            was_suggest = False
            faq_answer = ""
            top_question = ""
            try:
                faq_answer = str(hits[0][0].get("answer", "")).strip()
                top_question = str(hits[0][0].get("question", "")).strip()
            except Exception:
                faq_answer = ""
                top_question = ""

            fastlane_answer = fastlane_direct_answer(
                user_q=user_q,
                hits=hits,
                best_score=float(best_score),
                answer_threshold=float(answer_threshold),
                suggest_threshold=float(suggest_threshold),
            )

            if fastlane_answer:
                answer = fastlane_answer
            else:
                # 高速化: FAQに十分一致している場合は、LLMで言い換えずFAQ回答をそのまま返す。
                # LLM呼び出しは外部API/ローカルLLMで数秒以上かかるため、必要な場合だけ有効化する。
                use_llm_for_faq = bool(search_cfg.get("faq_llm_answer_enabled", False))
                llm_trigger_max_score = float(search_cfg.get("faq_llm_trigger_max_score", 0.55))
                if use_llm_for_faq and float(best_score) <= llm_trigger_max_score:
                    prompt = build_prompt(user_q, hits)
                    cached_answer = llm_answer_cached(user_q, prompt, faq_cache_token_getter(), top_question)
                    answer = cached_answer or faq_answer or "現在AIの回答機能でエラーが発生しています。しばらくしてから再度お試しください。"
                else:
                    answer = faq_answer if faq_answer else "現在AIの回答機能でエラーが発生しています。しばらくしてから再度お試しください。"
        elif doc_auto_ok:
            used_hits = []
            answer = answer_with_document_rag(user_q, doc_hits)
            answer_format = "markdown"
            was_nohit = False
            was_suggest = False
            used_doc_rag = True
        elif ambiguous_auto and _candidate_display_allowed(float(best_score)):
            maybe_count = max(1, int(search_cfg.get("maybe_candidate_count", 3)))
            used_hits = hits[:maybe_count]
            suggestion_candidates = used_hits
            answer = build_suggest_answer(user_q, used_hits)
            answer_format = get_row_answer_format(used_hits[0][0]) if used_hits else "markdown"
            was_nohit = False
            was_suggest = True
        elif best_score < suggest_threshold:
            maybe_threshold = max(float(search_cfg.get("maybe_candidate_threshold", 0.03)), candidate_min_display_score)
            maybe_count = max(1, int(search_cfg.get("maybe_candidate_count", 3)))
            if hits and _candidate_display_allowed(float(best_score)) and float(best_score) >= maybe_threshold:
                used_hits = hits[:maybe_count]
                suggestion_candidates = used_hits
                answer = build_suggest_answer(user_q, used_hits)
                answer_format = get_row_answer_format(used_hits[0][0]) if used_hits else "markdown"
                was_nohit = False
                was_suggest = True
            else:
                used_hits = []
                answer = nohit_template()
                answer_format = "markdown"
                ts_nohit = log_nohit(user_q)
                st.session_state["last_nohit"] = {"day": datetime.now().strftime("%Y%m%d"), "timestamp": ts_nohit, "question": user_q}
                was_nohit = True
                was_suggest = False
        elif best_score < answer_threshold:
            if hits and _candidate_display_allowed(float(best_score)):
                maybe_count = max(1, int(search_cfg.get("maybe_candidate_count", 3)))
                used_hits = hits[:maybe_count]
                suggestion_candidates = used_hits
                answer = build_suggest_answer(user_q, used_hits)
                answer_format = get_row_answer_format(used_hits[0][0]) if used_hits else "markdown"
                was_nohit = False
                was_suggest = True
            else:
                used_hits = []
                answer = nohit_template()
                answer_format = "markdown"
                ts_nohit = log_nohit(user_q)
                st.session_state["last_nohit"] = {"day": datetime.now().strftime("%Y%m%d"), "timestamp": ts_nohit, "question": user_q}
                was_nohit = True
                was_suggest = False

    top_cat = ""
    if used_hits:
        try:
            top_cat = str(used_hits[0][0].get("category", ""))
        except Exception:
            top_cat = ""
    elif used_doc_rag and doc_hits:
        top_cat = f"doc_rag:{doc_hits[0].get('source_type', '')}"

    log_interaction(user_q, matched=(best_score >= answer_threshold or used_doc_rag), best_score=max(float(best_score), float(doc_best_score)), category=top_cat)

    return {
        "answer": answer,
        "best_score": float(best_score),
        "answer_threshold": float(answer_threshold),
        "suggest_threshold": float(suggest_threshold),
        "used_hits": used_hits,
        "doc_hits": doc_hits,
        "used_doc_rag": bool(used_doc_rag),
        "doc_best_score": float(doc_best_score),
        "was_nohit": bool(was_nohit),
        "was_suggest": bool(was_suggest),
        "answer_format": answer_format,
        "was_clarification": False,
        "suggestion_candidates": suggestion_candidates,
    }


def finalize_answer_cycle(
    *,
    st,
    user_q: str,
    result: dict,
    render_answer_message,
    render_used_hits_expander=None,
) -> None:
    st.session_state.used_hits = result.get("used_hits", [])
    st.session_state["last_user_q_for_learning"] = str(user_q or "").strip()
    if not bool(result.get("was_clarification", False)):
        clear_clarification(st=st, reset_count=True)
    render_answer_message(
        st=st,
        answer=result.get("answer", ""),
        best_score=float(result.get("best_score", 0.0)),
        answer_threshold=float(result.get("answer_threshold", 0.0)),
        was_nohit=bool(result.get("was_nohit", False)),
        was_suggest=bool(result.get("was_suggest", False)),
        answer_format=str(result.get("answer_format", "markdown")),
        used_doc_rag=bool(result.get("used_doc_rag", False)),
        doc_best_score=float(result.get("doc_best_score", 0.0)),
        was_clarification=bool(result.get("was_clarification", False)),
        suggestion_candidates=result.get("suggestion_candidates", []),
        user_q=str(user_q or "").strip(),
    )
    # 候補表示中は、候補ボタンを3件出すだけにする。
    # ここで used_hits をそのまま根拠表示すると、候補3件すべてのFAQ本文が展開され、
    # ユーザーには「どれが採用された回答なのか」が分かりにくくなる。
    # 根拠は、候補ボタンを押してFAQを1件選択した後に、その選択FAQだけ表示する。
    should_show_evidence = (
        callable(render_used_hits_expander)
        and not bool(result.get("was_clarification", False))
        and not bool(result.get("was_suggest", False))
    )
    if should_show_evidence:
        render_used_hits_expander(
            used_hits=result.get("used_hits", []),
            best_score=float(result.get("best_score", 0.0)),
            answer_threshold=float(result.get("answer_threshold", 0.0)),
            was_nohit=bool(result.get("was_nohit", False)),
            doc_hits=result.get("doc_hits", []),
            used_doc_rag=bool(result.get("used_doc_rag", False)),
            doc_best_score=float(result.get("doc_best_score", 0.0)),
        )
    # 履歴再描画後も「回答の根拠」を正しく表示するため、
    # 回答本文だけでなく検索結果メタ情報も messages に保存する。
    # ここが無いと、rerun 後に used_hits/doc_hits が空扱いになり、
    # 回答は表示されているのに根拠だけ「該当なし」と表示される。
    st.session_state.messages.append({
        "role": "assistant",
        "content": str(result.get("answer", "")),
        "answer_format": str(result.get("answer_format", "markdown")),
        "was_nohit": bool(result.get("was_nohit", False)),
        "was_suggest": bool(result.get("was_suggest", False)),
        "used_doc_rag": bool(result.get("used_doc_rag", False)),
        "was_clarification": bool(result.get("was_clarification", False)),
        "suggestion_candidates": result.get("suggestion_candidates", []),
        "used_hits": result.get("used_hits", []),
        "best_score": float(result.get("best_score", 0.0) or 0.0),
        "answer_threshold": float(result.get("answer_threshold", 0.0) or 0.0),
        "suggest_threshold": float(result.get("suggest_threshold", 0.0) or 0.0),
        "doc_hits": result.get("doc_hits", []),
        "doc_best_score": float(result.get("doc_best_score", 0.0) or 0.0),
        "user_q": str(user_q or "").strip(),
    })
