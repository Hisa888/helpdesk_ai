from __future__ import annotations

from helpdesk_app.modules.admin_contexts import (
    build_faq_admin_context,
    build_pdf_panel_context,
)
from helpdesk_app.modules.faq_admin_panel import render_faq_admin_panel
from helpdesk_app.modules.pdf_panels import render_pdf_panels



def render_admin_management_ui(**ctx):
    """Backward-compatible wrapper for older call sites.

    FAQ管理とPDF関連は分割済みパネルへ委譲し、重複実装を持たないようにする。
    """
    st = ctx["st"]
    if not st.session_state.get("is_admin"):
        return

    faq_ctx = build_faq_admin_context(ctx)
    if faq_ctx:
        render_faq_admin_panel(faq_ctx)

    pdf_ctx = build_pdf_panel_context(ctx)
    if pdf_ctx:
        render_pdf_panels(pdf_ctx)
