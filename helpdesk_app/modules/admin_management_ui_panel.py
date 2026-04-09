from __future__ import annotations

from datetime import datetime
import pandas as pd


def render_admin_management_ui(**ctx):
    st = ctx["st"]
    pd = ctx.get("pd", pd)
    datetime = ctx.get("datetime", datetime)
    REPORTLAB_AVAILABLE = ctx["REPORTLAB_AVAILABLE"]
    generate_effect_report_pdf = ctx["generate_effect_report_pdf"]
    generate_ops_manual_pdf = ctx["generate_ops_manual_pdf"]
    generate_sales_proposal_pdf = ctx["generate_sales_proposal_pdf"]
    read_interactions = ctx["read_interactions"]
    normalize_faq_columns = ctx["normalize_faq_columns"]
    read_csv_flexible = ctx["read_csv_flexible"]
    FAQ_PATH = ctx["FAQ_PATH"]
    faq_df_to_excel_bytes = ctx["faq_df_to_excel_bytes"]
    read_faq_uploaded_file = ctx["read_faq_uploaded_file"]
    save_faq_csv_full = ctx["save_faq_csv_full"]
    load_faq_index = ctx["load_faq_index"]
    get_faq_index_state = ctx["get_faq_index_state"]
    reset_faq_index_runtime = ctx["reset_faq_index_runtime"]

    with st.expander("📂 FAQ管理（Excelダウンロード / アップロード）", expanded=False):
        st.caption("管理者は FAQ を Excel(.xlsx) で一括入出力できます。500件以上でもまとめて置き換え可能です。推奨列名は『質問 / 回答 / カテゴリ』です。")

        if st.session_state.get("faq_replace_result"):
            st.success(st.session_state["faq_replace_result"])
            st.session_state.pop("faq_replace_result", None)

        current_faq_df = normalize_faq_columns(read_csv_flexible(FAQ_PATH)) if FAQ_PATH.exists() else pd.DataFrame(columns=["question", "answer", "category"])
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
                        saved = save_faq_csv_full(FAQ_PATH, incoming_df)
                        reloaded_df = normalize_faq_columns(read_csv_flexible(FAQ_PATH)) if FAQ_PATH.exists() else pd.DataFrame(columns=["question", "answer", "category"])

                        try:
                            load_faq_index.clear()
                            get_faq_index_state.clear()
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

                        if int(saved) != int(len(reloaded_df)):
                            st.error(f"保存件数と再読込件数が一致しません。保存: {saved} 件 / 再読込: {len(reloaded_df)} 件")
                        else:
                            msg = f"FAQを {saved} 件反映しました。現在登録中のFAQ件数も {len(reloaded_df)} 件です。"
                            st.session_state["faq_replace_result"] = msg
                            st.success(msg)
                            st.info("FAQの反映が完了しました。再読み込みは不要です。GitHub永続化ONなら自動で外部保存されます。")
                            current_faq_df = reloaded_df
            except Exception as e:
                st.error(f"FAQファイルの取込でエラー: {e}")

    # =========================
    # 管理者向け資料（PDF）ダウンロード
    # =========================
    with st.expander("📘 管理者向け資料（PDF）", expanded=False):
        if not REPORTLAB_AVAILABLE:
            st.warning("PDF出力には reportlab が必要です。requirements.txt に reportlab を追加してください。")
        else:
            col_a, col_b = st.columns(2)
            with col_a:
                ops_pdf = generate_ops_manual_pdf()
                st.download_button(
                    "📄 操作説明書PDFをダウンロード",
                    data=ops_pdf,
                    file_name="操作説明書_情シス問い合わせAI.pdf",
                    mime="application/pdf",
                    width="stretch",
                )
            with col_b:
                proposal_pdf = generate_sales_proposal_pdf()
                st.download_button(
                    "📑 提案資料PDFをダウンロード",
                    data=proposal_pdf,
                    file_name="提案資料_情シス問い合わせAI.pdf",
                    mime="application/pdf",
                    width="stretch",
                )
            st.caption("※ どちらもアプリの現状に合わせて自動生成されます（必要に応じて文面はカスタマイズ可能）。")

    with st.expander("📄 効果レポート（PDF）", expanded=False):
        if not REPORTLAB_AVAILABLE:
            st.warning("PDF出力には reportlab が必要です。requirements.txt に reportlab を追加してください。")
        else:
            hourly_cost = st.number_input(
                "想定人件費（円/時間）",
                min_value=0,
                max_value=20000,
                value=int(st.session_state.get("hourly_cost", 4000)),
                step=500,
                key="admin_hourly_cost",
            )

            avg_min_pdf = float(st.session_state.get("avg_min", 5))
            deflect_pdf = float(st.session_state.get("deflect_rate", st.session_state.get("deflect", 0.7)))

            df_month_all = read_interactions(days=60)
            if df_month_all is None or len(df_month_all) == 0:
                st.caption("今月の利用ログがまだありません。質問すると自動で蓄積します。")
            else:
                try:
                    ts = pd.to_datetime(df_month_all["timestamp"], errors="coerce")
                    month_start = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                    df_month = df_month_all[ts >= month_start]
                except Exception:
                    df_month = df_month_all

                try:
                    pdf_bytes = generate_effect_report_pdf(
                        df=df_month,
                        avg_min=avg_min_pdf,
                        deflect=deflect_pdf,
                        hourly_cost_yen=int(hourly_cost),
                    )
                    st.download_button(
                        "📄 今月の導入効果レポートをダウンロード",
                        data=pdf_bytes,
                        file_name=f"effect_report_{datetime.now().strftime('%Y%m')}.pdf",
                        mime="application/pdf",
                        width="stretch",
                    )
                except Exception as e:
                    st.error(f"PDF生成でエラー: {e}")

