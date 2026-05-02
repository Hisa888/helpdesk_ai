from __future__ import annotations

import re
import pandas as pd

from helpdesk_app.modules.manual_faq_generation_utils import collect_manual_source_text


FAQ_SAVE_COLUMNS = ["question", "answer", "intent", "keywords", "category", "answer_format"]
QUALITY_COLUMNS = ["採用", "評価", "修正メモ", "品質チェック"]


def _quality_warnings(row: pd.Series) -> str:
    warnings: list[str] = []
    q = str(row.get("question", "") or "").strip()
    a = str(row.get("answer", "") or "").strip()
    c = str(row.get("category", "") or "").strip()

    if not c:
        warnings.append("カテゴリ未設定")
    if len(q) < 6:
        warnings.append("質問が短い")
    if q and not re.search(r"[？?]$", q):
        warnings.append("質問文の末尾確認")
    if len(a) < 12:
        warnings.append("回答が短い")
    if re.search(r"■{2,}|□{2,}|�", a):
        warnings.append("文字化け疑い")
    if "資料" in a and len(a) < 30:
        warnings.append("回答が抽象的")
    return " / ".join(warnings) if warnings else "OK"


def _prepare_review_df(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return pd.DataFrame(columns=["採用", "評価", "question", "answer", "intent", "keywords", "category", "answer_format", "source", "修正メモ", "品質チェック"])

    out = df.copy().fillna("")
    for col in ["question", "answer", "intent", "keywords", "category", "answer_format", "source"]:
        if col not in out.columns:
            out[col] = ""
    out["answer_format"] = out["answer_format"].replace("", "markdown")

    if "採用" not in out.columns:
        out.insert(0, "採用", True)
    if "評価" not in out.columns:
        out.insert(1, "評価", "未確認")
    if "修正メモ" not in out.columns:
        out["修正メモ"] = ""

    out["品質チェック"] = out.apply(_quality_warnings, axis=1)
    # 文字化け・空欄疑いは初期評価を要修正に寄せる。ただし採用チェックは残す。
    for idx, record in out.iterrows():
        check = str(record.get("品質チェック", ""))
        if check != "OK" and str(record.get("評価", "")) in {"", "未確認"}:
            out.at[idx, "評価"] = "要修正"

    return out[["採用", "評価", "question", "answer", "intent", "keywords", "category", "answer_format", "source", "修正メモ", "品質チェック"]]


def _filter_save_df(edited: pd.DataFrame) -> pd.DataFrame:
    if edited is None or not isinstance(edited, pd.DataFrame) or edited.empty:
        return pd.DataFrame(columns=FAQ_SAVE_COLUMNS)
    df = edited.copy().fillna("")
    if "採用" in df.columns:
        df = df[df["採用"].astype(bool)]
    if "評価" in df.columns:
        df = df[df["評価"].astype(str) != "除外"]
    for col in FAQ_SAVE_COLUMNS:
        if col not in df.columns:
            df[col] = "markdown" if col == "answer_format" else ""
    df = df[FAQ_SAVE_COLUMNS].copy()
    df["question"] = df["question"].astype(str).str.strip()
    df["answer"] = df["answer"].astype(str).str.strip()
    df["intent"] = df["intent"].astype(str).str.strip()
    df["keywords"] = df["keywords"].astype(str).str.strip()
    df["category"] = df["category"].astype(str).str.strip()
    df["answer_format"] = df["answer_format"].astype(str).str.strip().replace("", "markdown")
    df = df[(df["question"] != "") & (df["answer"] != "")]
    df = df.drop_duplicates(subset=["question"]).reset_index(drop=True)
    return df


def _render_quality_summary(st, review_df: pd.DataFrame) -> None:
    if review_df is None or review_df.empty:
        return
    total = len(review_df)
    accepted = int(review_df.get("採用", pd.Series([True] * total)).astype(bool).sum())
    ok_count = int((review_df.get("品質チェック", pd.Series(dtype=str)).astype(str) == "OK").sum())
    need_fix = total - ok_count
    c1, c2, c3 = st.columns(3)
    c1.metric("生成FAQ案", f"{total}件")
    c2.metric("採用予定", f"{accepted}件")
    c3.metric("要確認", f"{need_fix}件")
    if need_fix:
        st.warning("品質チェックがOKでない行があります。question / answer を編集してから反映してください。")
    else:
        st.success("品質チェックはすべてOKです。内容確認後、faq.csvへ反映できます。")


def render_manual_faq_generation_panel(*, st, faq_path, generate_manual_faq_candidates, append_faq_csv, supported_extensions=("pdf", "docx", "xlsx", "xlsm", "txt", "md")) -> None:
    st.markdown("---")
    with st.expander("📚 マニュアル → FAQ自動生成", expanded=False):
        st.caption("PDF / Word / Excel / txt / md / Wiki本文からFAQ案を自動生成します。生成後に、管理者が品質確認・編集・採用/除外を選んでからFAQへ反映できます。")

        st.markdown(
            "**処理フロー**  \n"
            "1. ドキュメントを読み込み  \n"
            "2. Excel表・Word・PDF・Textを本文へ文章化  \n"
            "3. AIが内容を理解してFAQ案を生成  \n"
            "4. **管理者が編集・評価・採用/除外を判断**  \n"
            "5. 採用行だけ faq.csv へ反映"
        )

        uploaded_files = st.file_uploader(
            "マニュアル・資料をアップロード",
            type=list(supported_extensions),
            accept_multiple_files=True,
            key="manual_faq_uploader",
        )
        wiki_text = st.text_area(
            "Wiki本文の貼り付け（任意）",
            height=180,
            key="manual_faq_wiki_text",
            placeholder="社内Wikiや手順書本文を貼り付けてください",
        )
        n_items = st.number_input(
            "生成件数（0=全件・無制限）",
            min_value=0,
            value=0,
            step=10,
            key="manual_faq_n_items",
            help="0の場合、Excelから直接抽出できるFAQは全件作成します。PDF/Word/Textも上限20件ではなく、可能な範囲で生成します。",
        )
        n_items = int(n_items or 0)

        st.info(
            "Excelは全シートを自動読み込みします。生成件数を0にすると抽出できたFAQ候補を全件作成します。\n"
            "- question / answer 列がある場合 → そのままFAQ候補化\n"
            "- 項目 / 内容 / 手順 / 説明 列がある場合 → 行単位でFAQ案を作成\n"
            "- その他の表形式 → 全セルを『列名: 値』の文章へ変換してFAQ化"
        )

        if st.button("🤖 マニュアルからFAQ案を生成", use_container_width=True, key="manual_faq_generate_btn"):
            source_text, sections, direct_df = collect_manual_source_text(uploaded_files=uploaded_files or [], wiki_text=wiki_text or "")
            st.session_state["manual_faq_source_count"] = len(sections)
            st.session_state["manual_faq_extracted_text"] = source_text
            st.session_state["manual_faq_direct_df"] = direct_df

            if not source_text.strip() and (not isinstance(direct_df, pd.DataFrame) or direct_df.empty):
                st.warning("資料本文を取得できませんでした。PDF / Word / Excel / txt / md または Wiki本文を確認してください。")
            else:
                with st.spinner("資料を文章化し、内容を理解してFAQ案を生成中です…"):
                    df = generate_manual_faq_candidates(
                        source_text=source_text,
                        n_items=n_items,
                        direct_candidates=direct_df,
                    )
                review_df = _prepare_review_df(df)
                st.session_state["manual_faq_generated_df"] = review_df
                st.session_state["manual_faq_confirmed"] = False

        source_count = st.session_state.get("manual_faq_source_count")
        if source_count:
            st.caption(f"読み取り済みセクション数: {source_count}")

        direct_df = st.session_state.get("manual_faq_direct_df")
        if isinstance(direct_df, pd.DataFrame) and len(direct_df) > 0:
            st.success(f"Excel等から直接FAQ候補を {len(direct_df)} 件抽出しました。")

        with st.expander("🔍 文章化した資料本文を確認", expanded=False):
            text = st.session_state.get("manual_faq_extracted_text", "")
            if text:
                st.text_area("抽出・文章化テキスト", value=text[:8000], height=280, disabled=True, key="manual_faq_extracted_preview")
            else:
                st.caption("まだ抽出テキストはありません。")

        df = st.session_state.get("manual_faq_generated_df")
        if isinstance(df, pd.DataFrame) and len(df) > 0:
            review_df = _prepare_review_df(df)
            st.success(f"FAQ案を {len(review_df)} 件生成しました。内容を確認・編集し、採用行だけ faq.csv に反映できます。")
            _render_quality_summary(st, review_df)

            st.markdown("### ✏️ 生成FAQの精度改善")
            st.caption("採用する行だけチェックを残してください。質問・回答はこの表で直接編集できます。評価や修正メモは管理者確認用です。")

            column_config = None
            try:
                column_config = {
                    "採用": st.column_config.CheckboxColumn("採用", help="faq.csvへ反映する行だけON", default=True),
                    "評価": st.column_config.SelectboxColumn("評価", options=["未確認", "良い", "要修正", "除外"], help="管理者レビュー結果"),
                    "answer": st.column_config.TextColumn("answer", width="large"),
                    "question": st.column_config.TextColumn("question", width="large"),
                    "品質チェック": st.column_config.TextColumn("品質チェック", disabled=True),
                }
            except Exception:
                column_config = None

            edited = st.data_editor(
                review_df,
                num_rows="dynamic",
                use_container_width=True,
                key="manual_faq_generated_editor",
                column_config=column_config,
                disabled=["品質チェック"] if "品質チェック" in review_df.columns else False,
            )
            edited_df = edited if isinstance(edited, pd.DataFrame) else pd.DataFrame(edited)
            save_df = _filter_save_df(edited_df)

            with st.expander("✅ 反映前プレビュー", expanded=False):
                if len(save_df) > 0:
                    st.dataframe(save_df, use_container_width=True)
                else:
                    st.warning("faq.csvへ反映できる採用行がありません。採用チェック、質問、回答を確認してください。")

            confirmed = st.checkbox(
                f"管理者確認済み：採用予定 {len(save_df)} 件を faq.csv に反映してよい",
                key="manual_faq_confirm_checkbox",
            )
            if st.button("💾 採用FAQ案を faq.csv に追記", use_container_width=True, key="manual_faq_append_btn", disabled=(not confirmed or len(save_df) == 0)):
                added = append_faq_csv(faq_path, save_df)
                if added > 0:
                    st.success(f"faq.csv に {added} 件追記しました。")
                    st.info("反映後は、ユーザー画面で同じ質問を入力して検索・回答されるか確認してください。")
                else:
                    st.info("追記対象がありませんでした。重複や空欄を確認してください。")
        elif isinstance(df, pd.DataFrame):
            st.info("FAQ案を生成できませんでした。抽出本文の中身、Excel列名、LLM設定を確認してください。")
