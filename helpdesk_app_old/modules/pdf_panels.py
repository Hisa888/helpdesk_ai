from __future__ import annotations

from helpdesk_app.modules.pdf_panel_utils import resolve_monthly_effect_df

def render_admin_material_pdfs(ns: dict) -> None:
    st = ns["st"]
    REPORTLAB_AVAILABLE = ns["REPORTLAB_AVAILABLE"]
    generate_ops_manual_pdf = ns["generate_ops_manual_pdf"]
    generate_sales_proposal_pdf = ns["generate_sales_proposal_pdf"]

    with st.expander("📘 管理者向け資料（PDF）", expanded=False):
        if not REPORTLAB_AVAILABLE:
            st.warning("PDF出力には reportlab が必要です。requirements.txt に reportlab を追加してください。")
            return

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



def render_effect_report_pdf_panel(ns: dict) -> None:
    st = ns["st"]
    REPORTLAB_AVAILABLE = ns["REPORTLAB_AVAILABLE"]
    generate_effect_report_pdf = ns["generate_effect_report_pdf"]
    read_interactions = ns["read_interactions"]
    datetime = ns["datetime"]

    with st.expander("📄 効果レポート（PDF）", expanded=False):
        if not REPORTLAB_AVAILABLE:
            st.warning("PDF出力には reportlab が必要です。requirements.txt に reportlab を追加してください。")
            return

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

        df_month = resolve_monthly_effect_df(read_interactions=read_interactions, pd=ns["pd"], datetime=datetime)
        if df_month is None or len(df_month) == 0:
            st.caption("今月の利用ログがまだありません。質問すると自動で蓄積します。")
            return

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



def render_pdf_panels(ns: dict) -> None:
    render_admin_material_pdfs(ns)
    render_effect_report_pdf_panel(ns)
