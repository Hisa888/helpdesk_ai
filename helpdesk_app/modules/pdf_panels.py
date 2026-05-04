from __future__ import annotations

from pathlib import Path

from helpdesk_app.modules.pdf_panel_utils import resolve_monthly_effect_df


PPT_GUIDE_FILENAME = "情シス問い合わせAI操作ガイド.pptx"
PPT_GUIDE_PATH = Path(__file__).resolve().parents[1] / "assets" / PPT_GUIDE_FILENAME
PPTX_MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


def _read_bytes_if_exists(path: Path) -> bytes | None:
    """アプリ同梱資料を安全に読み込む。"""
    try:
        if path.exists() and path.is_file():
            return path.read_bytes()
    except Exception:
        return None
    return None


def render_admin_material_pdfs(ns: dict) -> None:
    st = ns["st"]
    REPORTLAB_AVAILABLE = ns["REPORTLAB_AVAILABLE"]
    generate_ops_manual_pdf = ns["generate_ops_manual_pdf"]
    generate_sales_proposal_pdf = ns["generate_sales_proposal_pdf"]

    with st.expander("📘 管理者向け資料（PDF）", expanded=False):
        st.caption("操作説明書・画面付きPPT・提案資料をダウンロードできます。")

        # 1. 操作説明書PDF
        if REPORTLAB_AVAILABLE:
            ops_pdf = generate_ops_manual_pdf()
            st.download_button(
                "📄 操作説明書PDFをダウンロード",
                data=ops_pdf,
                file_name="操作説明書_情シス問い合わせAI.pdf",
                mime="application/pdf",
                width="stretch",
            )
        else:
            st.warning("操作説明書PDF・提案資料PDFの出力には reportlab が必要です。requirements.txt に reportlab を追加してください。")

        # 2. 操作説明書PPT（画面付き）
        ppt_bytes = _read_bytes_if_exists(PPT_GUIDE_PATH)
        if ppt_bytes:
            st.download_button(
                "📊 操作説明書PPTをダウンロード（画面付き）",
                data=ppt_bytes,
                file_name=PPT_GUIDE_FILENAME,
                mime=PPTX_MIME,
                width="stretch",
            )
        else:
            st.info("操作説明書PPT（画面付き）が見つかりません。assets フォルダに PPT ファイルを配置してください。")

        # 3. 提案資料PDF
        if REPORTLAB_AVAILABLE:
            proposal_pdf = generate_sales_proposal_pdf()
            st.download_button(
                "📑 提案資料PDFをダウンロード",
                data=proposal_pdf,
                file_name="提案資料_情シス問い合わせAI.pdf",
                mime="application/pdf",
                width="stretch",
            )

        st.caption("※ 操作説明書PPT（画面付き）はアプリに同梱した資料をそのままダウンロードします。PDF資料はアプリの現状に合わせて自動生成されます。")



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
