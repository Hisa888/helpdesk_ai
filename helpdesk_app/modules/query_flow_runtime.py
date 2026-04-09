from __future__ import annotations

from datetime import datetime


def process_user_query(
    *,
    st,
    user_q: str,
    try_ultrafast_answer,
    retrieve_faq_cached,
    faq_cache_token_getter,
    ensure_faq_index_loaded,
    render_match_bar,
    current_search_threshold,
    current_suggest_threshold,
    nohit_template,
    log_nohit,
    build_suggest_answer,
    fastlane_direct_answer,
    build_prompt,
    llm_answer_cached,
    log_interaction,
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

    if hits:
        render_match_bar(best_score)

    answer_threshold = current_search_threshold()
    suggest_threshold = current_suggest_threshold()

    if ultrafast:
        used_hits = hits[:1]
        answer = str(ultrafast.get("answer", "")).strip() or nohit_template()
        was_nohit = False
        was_suggest = False
    elif best_score < suggest_threshold:
        used_hits = []
        answer = nohit_template()
        ts_nohit = log_nohit(user_q)
        st.session_state["last_nohit"] = {"day": datetime.now().strftime("%Y%m%d"), "timestamp": ts_nohit, "question": user_q}
        was_nohit = True
        was_suggest = False
    elif best_score < answer_threshold:
        used_hits = hits[:1]
        answer = build_suggest_answer(user_q, used_hits)
        was_nohit = False
        was_suggest = True
    else:
        used_hits = hits
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
            prompt = build_prompt(user_q, hits)
            cached_answer = llm_answer_cached(user_q, prompt, faq_cache_token_getter(), top_question)
            if cached_answer:
                answer = cached_answer
            else:
                answer = faq_answer if faq_answer else "現在AIの回答機能でエラーが発生しています。しばらくしてから再度お試しください。"

    top_cat = ""
    if used_hits:
        try:
            top_cat = str(used_hits[0][0].get("category", ""))
        except Exception:
            top_cat = ""

    log_interaction(user_q, matched=(best_score >= answer_threshold), best_score=best_score, category=top_cat)

    return {
        "answer": answer,
        "best_score": float(best_score),
        "answer_threshold": float(answer_threshold),
        "suggest_threshold": float(suggest_threshold),
        "used_hits": used_hits,
        "was_nohit": bool(was_nohit),
        "was_suggest": bool(was_suggest),
    }


def finalize_answer_cycle(*, st, user_q: str, result: dict, render_answer_message) -> None:
    st.session_state.used_hits = result.get("used_hits", [])
    render_answer_message(
        st=st,
        answer=result.get("answer", ""),
        best_score=float(result.get("best_score", 0.0)),
        answer_threshold=float(result.get("answer_threshold", 0.0)),
        was_nohit=bool(result.get("was_nohit", False)),
        was_suggest=bool(result.get("was_suggest", False)),
    )
    st.session_state.messages.append({"role": "assistant", "content": str(result.get("answer", ""))})
