from __future__ import annotations

from helpdesk_app.modules.admin_dashboard_panel import render_admin_dashboard_panel
from helpdesk_app.modules.admin_faq_generation_panel import render_admin_faq_generation_panel
from helpdesk_app.modules.admin_log_download_panel import render_admin_log_download_panel
from helpdesk_app.modules.document_rag_panel import render_document_rag_panel
from helpdesk_app.modules.manual_faq_generation_panel import render_manual_faq_generation_panel


def _render_admin_zone_intro() -> str:
    return """
<div class="glass-card" style="margin: 8px 0 14px 0;">
  <div class="eyebrow" style="font-size:12px; color:#0369a1; font-weight:700; letter-spacing:.08em; text-transform:uppercase;">Admin Control Center</div>
  <h3 style="margin:6px 0 8px 0; font-size:24px;">管理者エリア</h3>
  <p style="margin:0 0 14px 0; color:var(--text-sub);">運用状況の確認、ログ回収、FAQ改善までをひとつの導線で扱えるように整理した管理者向けエリアです。</p>
  <div class="proof-grid">
    <div class="proof-card">
      <div class="proof-icon">📊</div>
      <div class="title">ダッシュボードで説明</div>
      <p>問い合わせ数・自動対応率・削減効果をその場で提示できます。</p>
    </div>
    <div class="proof-card">
      <div class="proof-icon">📝</div>
      <div class="title">ログを回収</div>
      <p>nohitログをまとめて確認し、改善ポイントを見つけやすくします。</p>
    </div>
    <div class="proof-card">
      <div class="proof-icon">🧠</div>
      <div class="title">FAQ改善へ接続</div>
      <p>該当なしログからFAQ案を生成し、そのまま追加できます。</p>
    </div>
  </div>
</div>
"""


def render_admin_complete_sections(ctx: dict) -> None:
    """Render split admin dashboard/download/FAQ-generation sections from a single context."""

    st = ctx.get("st")
    if st is not None:
        st.markdown(_render_admin_zone_intro(), unsafe_allow_html=True)

    render_admin_dashboard_panel(
        read_interactions=ctx["read_interactions"],
        count_nohit_logs=ctx["count_nohit_logs"],
    )
    render_admin_log_download_panel(
        list_log_files=ctx["list_log_files"],
        make_logs_zip=ctx["make_logs_zip"],
    )
    render_admin_faq_generation_panel(
        list_log_files=ctx["list_log_files"],
        load_nohit_questions_from_logs=ctx["load_nohit_questions_from_logs"],
        generate_faq_candidates=ctx["generate_faq_candidates"],
        append_faq_csv=ctx["append_faq_csv"],
        seed_nohit_questions=ctx["seed_nohit_questions"],
        faq_path=ctx["faq_path"],
    )
    if ctx.get("build_document_rag_index"):
        render_document_rag_panel(
            build_document_rag_index=ctx["build_document_rag_index"],
            get_document_rag_manifest=ctx["get_document_rag_manifest"],
            clear_document_rag=ctx["clear_document_rag"],
            supported_extensions=ctx.get("supported_doc_rag_extensions", ("pdf", "docx", "xlsx", "xlsm", "txt", "md")),
        )

    if ctx.get("generate_manual_faq_candidates"):
        render_manual_faq_generation_panel(
            st=ctx["st"],
            faq_path=ctx["faq_path"],
            generate_manual_faq_candidates=ctx["generate_manual_faq_candidates"],
            append_faq_csv=ctx["append_faq_csv"],
            supported_extensions=ctx.get("supported_manual_faq_extensions", ("pdf", "docx", "xlsx", "xlsm", "txt", "md")),
        )
