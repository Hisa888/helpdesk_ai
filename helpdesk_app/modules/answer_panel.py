from __future__ import annotations


def build_suggest_answer(*, user_q: str, hits, nohit_template) -> str:
    if not hits:
        return nohit_template()
    row, score = hits[0]
    q = str(row.get("question", "")).strip()
    a = str(row.get("answer", "")).strip()
    cat = str(row.get("category", "")).strip()
    parts = [
        "入力内容に近いFAQ候補が見つかりました。完全一致ではありませんが、まずはこちらを確認してください。",
    ]
    if q:
        parts.append(f"【候補FAQ】{q}")
    if cat:
        parts.append(f"【カテゴリ】{cat}")
    if a:
        parts.append(f"【回答】\n{a}")
    parts.append("解決しない場合は、下の『追加情報を記録』から状況を補足してください。")
    return "\n\n".join(parts)


def render_used_hits_expander(*, st, render_match_bar, used_hits, best_score: float, answer_threshold: float, was_nohit: bool = False) -> None:
    with st.expander("🔎 回答の根拠を見る", expanded=False):
        if was_nohit or not used_hits:
            st.markdown('<div class="refbox">該当なし（スコアが低いため問い合わせ誘導）</div>', unsafe_allow_html=True)
            return
        st.caption(f"上位FAQ候補の一致度を表示しています（best score: {best_score:.2f} / 自動回答しきい値: {answer_threshold:.2f}）。")
        for i, (row, score) in enumerate(used_hits, 1):
            render_match_bar(score)
            q_html = str(row.get("question", "")).replace("\n", "<br>")
            a_html = str(row.get("answer", "")).replace("\n", "<br>")
            cat = str(row.get("category", ""))
            match_pct = int(max(0.0, min(1.0, float(score))) * 100)
            st.markdown(
                f"""
<div class="refbox">
<b>FAQ{i}</b>（一致度：{match_pct}% / category={cat}）<br>
<b>Q:</b> {q_html}<br>
<b>A:</b> {a_html}
</div>
""",
                unsafe_allow_html=True,
            )


def render_answer_message(*, st, answer: str, best_score: float, answer_threshold: float, was_nohit: bool, was_suggest: bool) -> None:
    st.markdown('<div id="answer-anchor"></div>', unsafe_allow_html=True)
    with st.chat_message("assistant"):
        answer_html = str(answer).replace("\n", "<br>")
        st.markdown(f'<div class="answerbox">{answer_html}</div>', unsafe_allow_html=True)

        if was_nohit:
            st.session_state["pending_nohit_active"] = True
            st.session_state["pending_nohit"] = st.session_state.get("last_nohit", {})
            st.info("該当なしログに追加しました。必要なら下の『追加情報を記録』で状況を補足できます。")
        elif was_suggest:
            st.info(f"近いFAQ候補を表示しています（スコア: {best_score:.2f} / 自動回答しきい値: {answer_threshold:.2f}）。")
            st.caption("管理者はサイドバーの『検索精度設定』から判定基準を調整できます。")
