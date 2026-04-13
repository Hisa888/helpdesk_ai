from __future__ import annotations

import pandas as pd


FAQ_ADMIN_COLUMNS = ["question", "answer", "category"]


def _empty_faq_df() -> pd.DataFrame:
    return pd.DataFrame(columns=FAQ_ADMIN_COLUMNS)


def load_current_faq_df(ns: dict) -> pd.DataFrame:
    normalize_faq_columns = ns["normalize_faq_columns"]
    read_csv_flexible = ns["read_csv_flexible"]
    FAQ_PATH = ns["FAQ_PATH"]
    return normalize_faq_columns(read_csv_flexible(FAQ_PATH)) if FAQ_PATH.exists() else _empty_faq_df()


def clear_faq_admin_runtime(ns: dict) -> None:
    st = ns["st"]
    load_faq_index = ns["load_faq_index"]
    get_faq_index_state = ns["get_faq_index_state"]
    reset_faq_index_runtime = ns["reset_faq_index_runtime"]

    try:
        load_faq_index.clear()
    except Exception:
        pass
    try:
        get_faq_index_state.clear()
    except Exception:
        pass
    try:
        reset_faq_index_runtime()
    except Exception:
        pass
    try:
        st.cache_resource.clear()
    except Exception:
        pass
    try:
        st.cache_data.clear()
    except Exception:
        pass


def replace_faq_from_uploaded_df(ns: dict, incoming_df: pd.DataFrame) -> tuple[int, pd.DataFrame]:
    save_faq_csv_full = ns["save_faq_csv_full"]
    FAQ_PATH = ns["FAQ_PATH"]
    persist_faq_now = ns.get("persist_faq_now")

    saved = save_faq_csv_full(FAQ_PATH, incoming_df, persist_callback=persist_faq_now)
    reloaded_df = load_current_faq_df(ns)
    clear_faq_admin_runtime(ns)
    return int(saved), reloaded_df


def render_faq_admin_panel(ns: dict) -> None:
    st = ns["st"]
    faq_df_to_excel_bytes = ns["faq_df_to_excel_bytes"]
    read_faq_uploaded_file = ns["read_faq_uploaded_file"]

    with st.expander("📂 FAQ管理（Excelダウンロード / アップロード）", expanded=False):
        st.caption("管理者は FAQ を Excel(.xlsx) で一括入出力できます。500件以上でもまとめて置き換え可能です。推奨列名は『質問 / 回答 / カテゴリ』です。")

        if st.session_state.get("faq_replace_result"):
            st.success(st.session_state["faq_replace_result"])
            st.session_state.pop("faq_replace_result", None)

        current_faq_df = load_current_faq_df(ns)
        excel_bytes = faq_df_to_excel_bytes(current_faq_df)
        st.download_button(
            "⬇ 現在のFAQをExcelでダウンロード",
            data=excel_bytes,
            file_name="faq.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            width="stretch",
        )
        st.caption(f"現在登録中のFAQ件数: {len(current_faq_df)} 件")

        uploaded_faq = st.file_uploader(
            "FAQファイルをアップロード",
            type=["xlsx", "xls", "csv"],
            key="faq_excel_uploader_admin",
            help="Excel(.xlsx) 推奨。質問 / 回答 / カテゴリ、または question / answer / category に対応。類義語を含む代表質問（例: パソコンが起動しません / 電源が入りません）を入れると精度が上がります。",
        )

        if uploaded_faq is not None:
            try:
                incoming_df = read_faq_uploaded_file(uploaded_faq.name, uploaded_faq.getvalue())
                st.success(f"アップロード確認OK: {len(incoming_df)} 件のFAQを検出しました。")
                preview_df = incoming_df.rename(columns={"question": "質問", "answer": "回答", "category": "カテゴリ"})
                st.dataframe(preview_df.head(20), width="stretch", height=420)
                if len(incoming_df) > 20:
                    st.caption(f"先頭20件を表示中です。保存対象は全 {len(incoming_df)} 件です。")

                if st.button("📥 この内容でFAQを反映する", type="primary", key="replace_faq_excel_admin", width="stretch"):
                    with st.spinner("FAQを保存しています..."):
                        saved, reloaded_df = replace_faq_from_uploaded_df(ns, incoming_df)

                        if int(saved) != int(len(reloaded_df)):
                            st.error(f"保存件数と再読込件数が一致しません。保存: {saved} 件 / 再読込: {len(reloaded_df)} 件")
                        else:
                            msg = f"FAQを {saved} 件反映しました。現在登録中のFAQ件数も {len(reloaded_df)} 件です。"
                            st.session_state["faq_replace_result"] = msg
                            st.success(msg)
                            st.info("FAQの反映が完了しました。再読み込みは不要です。GitHub永続化ONなら自動で外部保存されます。")
            except Exception as e:
                st.error(f"FAQファイルの取込でエラー: {e}")
