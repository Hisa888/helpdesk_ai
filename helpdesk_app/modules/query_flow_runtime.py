from __future__ import annotations

from datetime import datetime

from helpdesk_app.modules.clarification_llm import generate_clarification_prompt
from helpdesk_app.modules.clarification_rules import should_request_clarification
from helpdesk_app.modules.clarification_state import clear_clarification, get_clarification_count, start_clarification
from helpdesk_app.modules.faq_answer_renderer import get_row_answer_format


# FAQとかけ離れた雑談・体調・感情だけの入力で、
# 低スコアFAQ候補を無理に出さないための最低限の業務ドメイン判定。
# ここに入っている語があれば、低スコアでも「もしかしてこれですか？」候補表示の対象にする。
HELPDESK_DOMAIN_TERMS = [
    "wi-fi", "wifi", "ワイファイ", "無線", "lan", "ネット", "ネットワーク", "vpn",
    "pc", "パソコン", "端末", "windows", "mac", "ディスプレイ", "モニター", "画面",
    "ログイン", "サインイン", "パスワード", "アカウント", "認証", "ロック",
    "メール", "outlook", "teams", "sharepoint", "onedrive", "box", "nas",
    "プリンタ", "プリンター", "印刷", "スキャン", "複合機",
    "excel", "word", "powerpoint", "office", "ブラウザ", "chrome", "edge",
    "アプリ", "ソフト", "インストール", "システム", "申請", "申請書", "書式", "起案",
    "エラー", "障害", "不具合", "使えない", "つながらない", "接続", "起動", "保存", "共有",
]


def _looks_helpdesk_domain_query(text: str) -> bool:
    q = str(text or "").strip().lower()
    if not q:
        return False
    return any(term.lower() in q for term in HELPDESK_DOMAIN_TERMS)


def _use_nohit_for_out_of_domain(*, user_q: str, best_score: float, search_cfg: dict) -> bool:
    """FAQからかけ離れた入力では、低スコア候補を出さず該当なしにする。

    例: 「今日はしんどい」「眠い」「ありがとう」など。
    ただし、Wi-Fi/PC/申請書など業務・情シス系の語が含まれる場合は候補表示を許可する。
    """
    try:
        threshold = float(search_cfg.get("out_of_domain_candidate_threshold", 0.12))
    except Exception:
        threshold = 0.12
    return (not _looks_helpdesk_domain_query(user_q)) and float(best_score or 0.0) < threshold


def _activate_extra_info_form(*, st, log_nohit, user_q: str) -> None:
    """候補表示時にも「追加情報を記録」を使えるように、ログ行を準備する。

    既存の nohit ログ更新ロジックを流用するため、候補表示も
    「要確認ログ」として1行作っておく。失敗しても画面表示は継続する。
    """
    try:
        ts_nohit = log_nohit(user_q) if callable(log_nohit) else ""
    except Exception:
        ts_nohit = ""
    st.session_state["last_nohit"] = {
        "day": datetime.now().strftime("%Y%m%d"),
        "timestamp": ts_nohit,
        "question": str(user_q or "").strip(),
    }
    st.session_state["pending_nohit"] = dict(st.session_state["last_nohit"])
    st.session_state["pending_nohit_active"] = True


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
    # 候補が少しでも取れている場合は、追加質問より「もしかしてこれ？」を優先する。
    # これにより「モニター死んだ」「画面黒い」のような短いユーザー語でも取りこぼしにくくする。
    try:
        maybe_threshold_for_clarify = float(search_cfg.get("maybe_candidate_threshold", 0.03))
    except Exception:
        maybe_threshold_for_clarify = 0.03
    has_candidate_for_suggest = bool(hits) and float(best_score) >= maybe_threshold_for_clarify

    out_of_domain_low_score = _use_nohit_for_out_of_domain(
        user_q=user_q,
        best_score=float(best_score),
        search_cfg=search_cfg,
    )

    # FAQとかけ離れた低スコア入力は、追加質問や候補表示に進めず「該当なし」に寄せる。
    # 低スコアの偶然一致で関係ないFAQ候補を3件出すことを防ぐ。
    if out_of_domain_low_score:
        has_candidate_for_suggest = False

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

    if not ultrafast and callable(search_document_rag):
        try:
            doc_hits = search_document_rag(user_q, top_k=5) or []
            doc_best_score = float(doc_hits[0].get("score", 0.0)) if doc_hits else 0.0
        except Exception:
            doc_hits = []
            doc_best_score = 0.0

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
        doc_auto_ok = bool(doc_hits) and doc_best_score >= doc_threshold
        prefer_doc = doc_auto_ok and (not faq_auto_ok or doc_best_score >= (float(best_score) + doc_compare_margin))
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
                prompt = build_prompt(user_q, hits)
                cached_answer = llm_answer_cached(user_q, prompt, faq_cache_token_getter(), top_question)
                if cached_answer:
                    answer = cached_answer
                else:
                    answer = faq_answer if faq_answer else "現在AIの回答機能でエラーが発生しています。しばらくしてから再度お試しください。"
        elif doc_auto_ok:
            used_hits = []
            answer = answer_with_document_rag(user_q, doc_hits)
            answer_format = "markdown"
            was_nohit = False
            was_suggest = False
            used_doc_rag = True
        elif ambiguous_auto:
            maybe_count = max(1, int(search_cfg.get("maybe_candidate_count", 3)))
            used_hits = hits[:maybe_count]
            suggestion_candidates = used_hits
            answer = build_suggest_answer(user_q, used_hits)
            answer_format = get_row_answer_format(used_hits[0][0]) if used_hits else "markdown"
            was_nohit = False
            was_suggest = True
            _activate_extra_info_form(st=st, log_nohit=log_nohit, user_q=user_q)
        elif best_score < suggest_threshold:
            maybe_threshold = float(search_cfg.get("maybe_candidate_threshold", 0.03))
            maybe_count = max(1, int(search_cfg.get("maybe_candidate_count", 3)))
            if hits and float(best_score) >= maybe_threshold and not out_of_domain_low_score:
                used_hits = hits[:maybe_count]
                suggestion_candidates = used_hits
                answer = build_suggest_answer(user_q, used_hits)
                answer_format = get_row_answer_format(used_hits[0][0]) if used_hits else "markdown"
                was_nohit = False
                was_suggest = True
                _activate_extra_info_form(st=st, log_nohit=log_nohit, user_q=user_q)
            else:
                used_hits = []
                answer = nohit_template()
                answer_format = "markdown"
                ts_nohit = log_nohit(user_q)
                st.session_state["last_nohit"] = {"day": datetime.now().strftime("%Y%m%d"), "timestamp": ts_nohit, "question": user_q}
                was_nohit = True
                was_suggest = False
        elif best_score < answer_threshold:
            if out_of_domain_low_score:
                used_hits = []
                answer = nohit_template()
                answer_format = "markdown"
                ts_nohit = log_nohit(user_q)
                st.session_state["last_nohit"] = {"day": datetime.now().strftime("%Y%m%d"), "timestamp": ts_nohit, "question": user_q}
                was_nohit = True
                was_suggest = False
            else:
                maybe_count = max(1, int(search_cfg.get("maybe_candidate_count", 3)))
                used_hits = hits[:maybe_count]
                suggestion_candidates = used_hits
                answer = build_suggest_answer(user_q, used_hits)
                answer_format = get_row_answer_format(used_hits[0][0]) if used_hits else "markdown"
                was_nohit = False
                was_suggest = True
                _activate_extra_info_form(st=st, log_nohit=log_nohit, user_q=user_q)

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
    if callable(render_used_hits_expander) and not bool(result.get("was_clarification", False)):
        render_used_hits_expander(
            used_hits=result.get("used_hits", []),
            best_score=float(result.get("best_score", 0.0)),
            answer_threshold=float(result.get("answer_threshold", 0.0)),
            was_nohit=bool(result.get("was_nohit", False)),
            doc_hits=result.get("doc_hits", []),
            used_doc_rag=bool(result.get("used_doc_rag", False)),
            doc_best_score=float(result.get("doc_best_score", 0.0)),
        )

    # 回答が正しいとは限らないため、回答後は必ず画面下に
    # 「追加情報を記録（任意）」を閉じた状態で表示できるようにする。
    # nohit / 候補表示だけでなく、通常回答・RAG回答・候補選択後の回答も対象。
    if not bool(result.get("was_clarification", False)):
        from datetime import datetime
        st.session_state["pending_nohit_active"] = True
        st.session_state["pending_nohit"] = {
            "day": datetime.now().strftime("%Y%m%d"),
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "question": str(user_q or "").strip() or "追加情報",
        }
    # 履歴再描画時にも「もしかしてこれですか？」ボタンを表示できるよう、
    # pandas Seriesをそのまま保存せず、dict化してセッションに保持する。
    serialized_suggestions = []
    try:
        for row, score in list(result.get("suggestion_candidates", []) or [])[:3]:
            try:
                row_dict = dict(row) if not isinstance(row, dict) else dict(row)
            except Exception:
                row_dict = {}
            if str(row_dict.get("question", "")).strip():
                serialized_suggestions.append((row_dict, float(score or 0.0)))
    except Exception:
        serialized_suggestions = []

    serialized_used_hits = []
    try:
        for row, score in list(result.get("used_hits", []) or [])[:5]:
            try:
                row_dict = dict(row) if not isinstance(row, dict) else dict(row)
            except Exception:
                row_dict = {}
            serialized_used_hits.append((row_dict, float(score or 0.0)))
    except Exception:
        serialized_used_hits = []

    serialized_doc_hits = []
    try:
        for hit in list(result.get("doc_hits", []) or [])[:5]:
            serialized_doc_hits.append(dict(hit) if isinstance(hit, dict) else hit)
    except Exception:
        serialized_doc_hits = []

    st.session_state.messages.append({
        "role": "assistant",
        "content": str(result.get("answer", "")),
        "answer_format": str(result.get("answer_format", "markdown")),
        "was_nohit": bool(result.get("was_nohit", False)),
        "was_suggest": bool(result.get("was_suggest", False)),
        "used_doc_rag": bool(result.get("used_doc_rag", False)),
        "was_clarification": bool(result.get("was_clarification", False)),
        "suggestion_candidates": serialized_suggestions,
        "used_hits": serialized_used_hits,
        "best_score": float(result.get("best_score", 0.0)),
        "answer_threshold": float(result.get("answer_threshold", 0.0)),
        "doc_hits": serialized_doc_hits,
        "doc_best_score": float(result.get("doc_best_score", 0.0)),
        "user_q": str(user_q or "").strip(),
    })
