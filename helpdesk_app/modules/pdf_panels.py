from __future__ import annotations


def render_pdf_panels(ns: dict) -> None:
    globals().update(ns)
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
                        avg_min=float(avg_min),
                        deflect=float(deflect),
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
