from __future__ import annotations

from pathlib import Path
from typing import Callable

import pandas as pd
import streamlit as st


def render_admin_faq_generation_panel(
    *,
    list_log_files: Callable[[], list[Path]],
    load_nohit_questions_from_logs: Callable[..., list[str]],
    generate_faq_candidates: Callable[..., pd.DataFrame],
    append_faq_csv: Callable[..., int],
    seed_nohit_questions: Callable[..., int],
    faq_path: str | Path,
) -> None:
    with st.expander("🧠 FAQ自動生成（該当なしログ → FAQ案）", expanded=False):
        st.markdown('<div class="section-caption">該当なしログを、そのままFAQ改善アクションへつなげるための管理機能です。</div>', unsafe_allow_html=True)
        st.markdown(
            """
<div class="proof-grid" style="margin-top: 8px;">
  <div class="proof-card">
    <div class="proof-icon">1</div>
    <div class="title">ログを選ぶ</div>
    <p>nohitログから、改善したい問い合わせ群を選択します。</p>
  </div>
  <div class="proof-card">
    <div class="proof-icon">2</div>
    <div class="title">FAQ案を生成</div>
    <p>重複をまとめながら、回答案まで自動生成します。</p>
  </div>
  <div class="proof-card">
    <div class="proof-icon">3</div>
    <div class="title">編集して追加</div>
    <p>内容を確認し、必要に応じて調整後に faq.csv へ反映できます。</p>
  </div>
</div>
""",
            unsafe_allow_html=True,
        )

        log_files = list_log_files()
        if not log_files:
            st.info("まだ nohit_*.csv がありません。まず質問して『該当なし』を発生させてください。")
            return

        labels = [p.name for p in log_files[:15]]
        pick = st.selectbox("参照するログファイル", labels, index=0, key="admin_ext_nohit_pick")
        picked_path = next((p for p in log_files if p.name == pick), log_files[0])
        max_q = st.slider("生成に使う質問数（重複除外後）", 10, 500, 100, step=10, key="admin_ext_max_q")
        n_items = st.number_input(
            "生成するFAQ件数（0=可能な範囲で最大）",
            min_value=0,
            value=8,
            step=10,
            key="admin_ext_n_items",
            help="20件上限は撤廃済みです。0の場合は、選択したログ内容から可能な範囲で最大件数を生成します。",
        )
        n_items = int(n_items or 0)

        col1, col2 = st.columns([2, 3])
        with col1:
            if st.button("🧪 デモ用に定番質問を追加（20件）", key="admin_ext_seed"):
                added = seed_nohit_questions(20)
                st.success(f"nohitログに {added} 件追加しました。")
                st.rerun()
        with col2:
            st.caption("営業デモ前にFAQ自動生成を試したい場合のテストデータです。")

        if st.button("🤖 FAQ案を自動生成", type="primary", key="admin_ext_generate_faq"):
            with st.spinner("FAQ案を生成中..."):
                questions = load_nohit_questions_from_logs([picked_path], max_questions=max_q)
                st.session_state["admin_generated_nohit_questions"] = questions
                if len(questions) < 5:
                    st.session_state["generated_faq_df_ext"] = pd.DataFrame(columns=["question", "answer", "intent", "keywords", "category", "answer_format"])
                    st.warning("有効な質問が少なすぎてFAQを生成できません。")
                else:
                    try:
                        generated_df = generate_faq_candidates(questions, n_items=n_items)
                    except Exception as e:
                        st.error(f"FAQ案生成でエラー: {e}")
                        generated_df = pd.DataFrame(columns=["question", "answer", "intent", "keywords", "category", "answer_format"])
                    st.session_state["generated_faq_df_ext"] = generated_df

        generated_df = st.session_state.get("generated_faq_df_ext")
        if isinstance(generated_df, pd.DataFrame) and len(generated_df) > 0:
            st.markdown("### ✅ 生成結果（編集して保存できます）")
            edited = st.data_editor(generated_df, num_rows="dynamic", use_container_width=True, key="admin_ext_faq_editor")
            c1, c2 = st.columns(2)
            with c1:
                if st.button("💾 faq.csv に追記", key="admin_ext_append_faq"):
                    added = append_faq_csv(Path(faq_path), edited.rename(columns={"category": "category"}))
                    if added > 0:
                        st.success(f"faq.csv に {added} 件追記しました。")
                        st.session_state["generated_faq_df_ext"] = pd.DataFrame()
                        st.rerun()
                    else:
                        st.warning("追記できる新規FAQがありません。")
            with c2:
                if st.button("🧹 生成結果をクリア", key="admin_ext_clear_faq"):
                    st.session_state["generated_faq_df_ext"] = pd.DataFrame()
                    st.rerun()
        elif isinstance(generated_df, pd.DataFrame) and len(generated_df) == 0 and st.session_state.get("generated_faq_df_ext") is not None:
            st.warning("FAQ案が生成できませんでした。ログの内容が少ないか、出力形式が崩れています。")
