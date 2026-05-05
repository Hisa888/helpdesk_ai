from __future__ import annotations

import csv
import hashlib
from datetime import datetime
from pathlib import Path

from helpdesk_app.modules.contact_cta_panel import render_answer_contact_cta
from helpdesk_app.faq_db import save_candidate_learning_to_db
from helpdesk_app.modules.faq_answer_renderer import (
    get_row_answer_format,
    render_answer_box,
    render_ref_answer_html,
)


def build_suggest_answer(*, user_q: str, hits, nohit_template) -> str:
    if not hits:
        return nohit_template()

    parts = [
        "もしかして、以下の内容をお探しですか？",
        "入力内容に近いFAQ候補が見つかりました。該当する候補を選ぶか、まず一番近い回答を確認してください。",
    ]

    for i, (row, score) in enumerate(list(hits)[:3], 1):
        q = str(row.get("question", "")).strip()
        cat = str(row.get("category", "")).strip()
        pct = int(max(0.0, min(1.0, float(score))) * 100)
        line = f"{i}. {q}" if q else f"{i}. FAQ候補"
        meta = []
        if cat:
            meta.append(f"カテゴリ: {cat}")
        meta.append(f"一致度: {pct}%")
        parts.append(f"【候補{i}】{line}（{' / '.join(meta)}）")

    row, _score = hits[0]
    a = str(row.get("answer", "")).strip()
    if a:
        parts.append("【一番近い候補の回答】\n" + a)
    parts.append("候補が違う場合は、別の言い方で入力するか、下の『追加情報を記録』から状況を補足してください。")
    return "\n\n".join(parts)


def _append_candidate_learning_log(*, user_question: str, row, score: float) -> None:
    """候補クリックをCSVとSQLiteに残す。失敗しても画面操作は止めない。"""
    faq_id = str(row.get("faq_id", row.get("FAQ_ID", ""))).strip()
    question = str(row.get("question", "")).strip()
    category = str(row.get("category", "")).strip()
    clean_user_q = str(user_question or "").strip()
    clean_score = float(score or 0.0)

    # 1) 本番用の永続学習ログ: SQLite
    try:
        save_candidate_learning_to_db(
            user_question=clean_user_q,
            selected_faq_id=faq_id,
            selected_question=question,
            score=clean_score,
            category=category,
        )
    except Exception:
        pass

    # 2) 管理者確認・ダウンロード用: CSV
    try:
        log_dir = Path("logs")
        log_dir.mkdir(parents=True, exist_ok=True)
        path = log_dir / f"candidate_learning_{datetime.now().strftime('%Y%m%d')}.csv"
        is_new = not path.exists()
        with path.open("a", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            if is_new:
                w.writerow(["timestamp", "user_question", "selected_faq_id", "selected_question", "score", "category"])
            w.writerow([
                datetime.now().isoformat(timespec="seconds"),
                clean_user_q,
                faq_id,
                question,
                clean_score,
                category,
            ])
    except Exception:
        pass


def _remember_candidate_learning_in_session(st, *, user_question: str, row, score: float) -> None:
    try:
        events = list(st.session_state.get("faq_candidate_learning_events", []))
        events.append({
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "user_question": str(user_question or "").strip(),
            "selected_faq_id": str(row.get("faq_id", row.get("FAQ_ID", ""))).strip(),
            "selected_question": str(row.get("question", "")).strip(),
            "score": float(score),
            "category": str(row.get("category", "")).strip(),
        })
        # セッション肥大化防止。直近200件だけ保持。
        st.session_state["faq_candidate_learning_events"] = events[-200:]
    except Exception:
        pass


def render_maybe_candidate_buttons(st, *, suggestion_candidates=None, user_q: str = "", key_prefix: str = "current") -> None:
    candidates = list(suggestion_candidates or [])[:3]
    if not candidates:
        return
    st.markdown("**もしかしてこれですか？**")
    st.caption("該当する候補を押すと、そのFAQの回答を直接表示します。")
    for i, item in enumerate(candidates, 1):
        try:
            row, score = item
            question = str(row.get("question", "")).strip()
            category = str(row.get("category", "")).strip()
        except Exception:
            continue
        if not question:
            continue
        pct = int(max(0.0, min(1.0, float(score))) * 100)
        label = f"{i}. {question}（一致度 {pct}%）"
        if category:
            label += f" / {category}"
        digest = hashlib.md5(f"{key_prefix}:{i}:{question}:{user_q}".encode("utf-8")).hexdigest()[:10]
        if st.button(label, key=f"maybe_faq_candidate_{digest}", use_container_width=True):
            original_user_q = str(user_q or st.session_state.get("last_user_q_for_learning", "")).strip()
            _remember_candidate_learning_in_session(st, user_question=original_user_q, row=row, score=float(score))
            _append_candidate_learning_log(user_question=original_user_q, row=row, score=float(score))

            # 候補ボタン押下時は、Streamlit の chat_input/pending_q 経由にしない。
            # 画面下の「追加情報フォーム」が先に再描画されて、回答が出ていないように見えるため、
            # ここでチャット履歴へ「選択したFAQの回答」を直接追加して固定表示する。
            try:
                row_dict = dict(row) if not isinstance(row, dict) else dict(row)
            except Exception:
                row_dict = {
                    "question": question,
                    "answer": str(getattr(row, "get", lambda k, d='': d)("answer", "")).strip(),
                    "category": category,
                }

            answer_text = str(row_dict.get("answer", "")).strip()
            if not answer_text:
                answer_text = "選択されたFAQに回答文が登録されていません。管理者画面でFAQの回答欄を確認してください。"

            selected_question = question or str(row_dict.get("question", "")).strip() or "FAQ候補を選択"
            answer_format = get_row_answer_format(row_dict)

            messages = list(st.session_state.get("messages", []))
            # 同じボタンを連続クリックした時に、同じ回答を何度も増やさない。
            already_added = False
            if len(messages) >= 2:
                last_user = messages[-2] if isinstance(messages[-2], dict) else {}
                last_assistant = messages[-1] if isinstance(messages[-1], dict) else {}
                already_added = (
                    str(last_user.get("role", "")) == "user"
                    and str(last_user.get("content", "")) == selected_question
                    and str(last_assistant.get("role", "")) == "assistant"
                    and str(last_assistant.get("content", "")) == answer_text
                )
            if not already_added:
                messages.append({"role": "user", "content": selected_question})
                messages.append({
                    "role": "assistant",
                    "content": answer_text,
                    "answer_format": answer_format,
                    "was_nohit": False,
                    "was_suggest": False,
                    "used_doc_rag": False,
                    "was_clarification": False,
                    "suggestion_candidates": [],
                    "used_hits": [(row_dict, float(score))],
                    "best_score": float(score),
                    "answer_threshold": float(st.session_state.get("search_threshold", 0.0)),
                    "doc_hits": [],
                    "doc_best_score": 0.0,
                    "user_q": selected_question,
                })
                st.session_state["messages"] = messages

            st.session_state["used_hits"] = [(row_dict, float(score))]
            st.session_state["pending_selected_faq"] = None
            st.session_state["pending_q"] = ""

            # 候補を選択して回答が出た後も、ユーザーが「この候補では違う」と思った場合に
            # すぐ状況補足できるよう、「追加情報を記録（任意）」は残す。
            st.session_state["pending_nohit_active"] = True
            st.session_state["pending_nohit"] = {
                "day": datetime.now().strftime("%Y%m%d"),
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "question": original_user_q or selected_question,
            }
            st.session_state["scroll_to_answer"] = True

            # rerun が効かない環境/タイミングでも「押したのに回答が出ない」状態にしないため、
            # その場でも回答欄を描画してから rerun を試す。
            st.markdown("### 回答")
            render_answer_box(st, answer=answer_text, answer_format=answer_format, css_class="answerbox")
            st.info("選択したFAQの回答を表示しました。候補が違う場合は、下の『追加情報を記録（任意）』から状況を補足できます。")
            try:
                st.rerun()
            except Exception:
                try:
                    st.experimental_rerun()
                except Exception:
                    pass


def render_used_hits_expander(*, st, render_match_bar, used_hits, best_score: float, answer_threshold: float, was_nohit: bool = False, doc_hits=None, used_doc_rag: bool = False, doc_best_score: float = 0.0) -> None:
    doc_hits = doc_hits or []
    with st.expander("🔎 回答の根拠を見る", expanded=False):
        if used_doc_rag and doc_hits:
            st.caption(f"社内ドキュメントを根拠に回答しました（ドキュメント一致度: {int(max(0.0, min(1.0, float(doc_best_score))) * 100)}%）。")
            for i, hit in enumerate(doc_hits[:4], 1):
                render_match_bar(float(hit.get("score", 0.0)), label=f"資料{i} ドキュメント一致度")
                score_pct = int(max(0.0, min(1.0, float(hit.get("score", 0.0)))) * 100)
                st.markdown(
                    f"""
<div class="refbox">
<b>資料{i}</b>（ドキュメント一致度：{score_pct}% / 種別={hit.get('source_type', '')}）<br>
<b>資料名:</b> {hit.get('source_name', '')}<br>
<b>場所:</b> {hit.get('location', '')} / {hit.get('chunk_label', '')}<br>
<b>本文:</b> {hit.get('text', '')}
</div>
""",
                    unsafe_allow_html=True,
                )
            return
        if was_nohit or not used_hits:
            st.markdown('<div class="refbox">該当なし（スコアが低いため問い合わせ誘導）</div>', unsafe_allow_html=True)
            return
        st.caption(
            f"FAQ候補との一致度を表示しています"
            f"（FAQ best score: {best_score:.2f} / 自動回答しきい値: {answer_threshold:.2f}）。"
        )
        for i, (row, score) in enumerate(used_hits, 1):
            render_match_bar(score, label=f"FAQ{i} 一致度")
            q_html = render_ref_answer_html(str(row.get("question", "")), "text")
            answer_format = get_row_answer_format(row)
            a_html = render_ref_answer_html(str(row.get("answer", "")), answer_format)
            cat = str(row.get("category", ""))
            fmt_label = str(row.get("answer_format", "markdown"))
            match_pct = int(max(0.0, min(1.0, float(score))) * 100)
            st.markdown(
                f"""
<div class="refbox">
<b>FAQ{i}</b>（FAQ一致度：{match_pct}% / category={cat} / 表示形式={fmt_label}）<br>
<b>Q:</b> {q_html}<br>
<b>A:</b> {a_html}
</div>
""",
                unsafe_allow_html=True,
            )


def render_answer_message(
    *,
    st,
    answer: str,
    best_score: float,
    answer_threshold: float,
    was_nohit: bool,
    was_suggest: bool,
    answer_format: str = "markdown",
    used_doc_rag: bool = False,
    doc_best_score: float = 0.0,
    was_clarification: bool = False,
    suggestion_candidates=None,
    user_q: str = "",
) -> None:
    st.markdown('<div id="answer-anchor"></div>', unsafe_allow_html=True)
    with st.chat_message("assistant"):
        render_answer_box(st, answer=answer, answer_format=answer_format, css_class="answerbox")

        if was_clarification:
            st.info("追加情報をもとに再検索します。補足を入力してください。")
        elif was_nohit:
            st.session_state["pending_nohit_active"] = True
            st.session_state["pending_nohit"] = st.session_state.get("last_nohit", {})
            st.info("該当なしログに追加しました。必要なら下の『追加情報を記録』で状況を補足できます。")
        elif used_doc_rag:
            st.success(f"社内ドキュメントを根拠に回答しました（ドキュメント一致度: {int(max(0.0, min(1.0, float(doc_best_score))) * 100)}%）。")
            st.caption("回答の根拠は下の『回答の根拠を見る』で確認できます。")
        elif was_suggest:
            # 候補が違う場合にも、画面下に「追加情報を記録」を必ず表示する。
            st.session_state["pending_nohit_active"] = True
            if not st.session_state.get("pending_nohit"):
                st.session_state["pending_nohit"] = {
                    "day": datetime.now().strftime("%Y%m%d"),
                    "timestamp": datetime.now().isoformat(timespec="seconds"),
                    "question": str(user_q or "").strip(),
                }
            st.info(f"近いFAQ候補を表示しています（FAQ一致度: {int(max(0.0, min(1.0, float(best_score))) * 100)}% / 自動回答しきい値: {int(max(0.0, min(1.0, float(answer_threshold))) * 100)}%）。")
            render_maybe_candidate_buttons(st, suggestion_candidates=suggestion_candidates, user_q=user_q, key_prefix="current")
            st.caption("候補が違う場合は、下の『追加情報を記録（任意）』から状況を補足できます。")
            st.caption("管理者はサイドバーの『検索精度設定』から判定基準を調整できます。")

        render_answer_contact_cta(
            st=st,
            was_nohit=was_nohit,
            was_suggest=was_suggest,
            used_doc_rag=used_doc_rag,
            was_clarification=was_clarification,
        )
