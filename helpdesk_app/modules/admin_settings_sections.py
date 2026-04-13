from __future__ import annotations

from helpdesk_app.modules.admin_contexts import (
    build_faq_admin_context,
    build_llm_panel_context,
    build_pdf_panel_context,
    build_search_panel_context,
    build_ui_layout_panel_context,
    build_ui_theme_panel_context,
)
from helpdesk_app.modules.faq_admin_panel import render_faq_admin_panel
from helpdesk_app.modules.llm_settings_panel import render_llm_settings_panel
from helpdesk_app.modules.pdf_panels import render_pdf_panels
from helpdesk_app.modules.search_settings_panel import render_search_settings_panel
from helpdesk_app.modules.ui_layout_panel import render_ui_layout_panel
from helpdesk_app.modules.ui_theme_panel import render_ui_theme_panel



def render_admin_search_and_llm_section(ns: dict) -> None:
    search_ctx = build_search_panel_context(ns)
    if search_ctx:
        render_search_settings_panel(**search_ctx)

    llm_ctx = build_llm_panel_context(ns)
    if llm_ctx:
        with ns["st"].expander("🧠 LLM切替設定", expanded=False):
            render_llm_settings_panel(**llm_ctx)



def render_admin_ui_section(ns: dict) -> None:
    theme_ctx = build_ui_theme_panel_context(ns)
    if theme_ctx:
        render_ui_theme_panel(**theme_ctx)

    layout_ctx = build_ui_layout_panel_context(ns)
    if layout_ctx:
        render_ui_layout_panel(**layout_ctx)



def render_admin_knowledge_section(ns: dict) -> None:
    faq_ctx = build_faq_admin_context(ns)
    if faq_ctx:
        render_faq_admin_panel(faq_ctx)

    pdf_ctx = build_pdf_panel_context(ns)
    if pdf_ctx:
        render_pdf_panels(pdf_ctx)
