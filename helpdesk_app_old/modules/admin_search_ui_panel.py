from __future__ import annotations

import streamlit.components.v1 as components

from helpdesk_app.modules.admin_settings_sections import (
    render_admin_knowledge_section,
    render_admin_search_and_llm_section,
    render_admin_ui_section,
)



def render_admin_search_ui_panel(
    *,
    st,
    pd,
    components=components,
    datetime,
    FAQ_PATH,
    REPORTLAB_AVAILABLE,
    current_search_settings,
    default_search_settings,
    save_search_settings,
    current_llm_settings,
    default_llm_settings,
    save_llm_settings,
    current_ui_theme_settings,
    default_ui_theme_settings,
    sanitize_ui_theme_settings,
    save_ui_theme_settings,
    current_ui_layout_settings,
    default_ui_layout_settings,
    sanitize_ui_layout_settings,
    save_ui_layout_settings,
    normalize_faq_columns,
    read_csv_flexible,
    faq_df_to_excel_bytes,
    read_faq_uploaded_file,
    save_faq_csv_full,
    load_faq_index,
    get_faq_index_state,
    reset_faq_index_runtime,
    generate_ops_manual_pdf,
    generate_sales_proposal_pdf,
    generate_effect_report_pdf,
    read_interactions,
    persist_faq_now=None,
):
    """Backward-compatible wrapper for older call sites.

    旧実装の巨大UIを維持せず、分割済みセクションへ委譲する。
    FAQ管理とPDF関連も必ず共通パネルを通す。
    """
    if not st.session_state.get("is_admin"):
        return

    ns = {
        "st": st,
        "pd": pd,
        "components": components,
        "datetime": datetime,
        "FAQ_PATH": FAQ_PATH,
        "REPORTLAB_AVAILABLE": REPORTLAB_AVAILABLE,
        "current_search_settings": current_search_settings,
        "default_search_settings": default_search_settings,
        "save_search_settings": save_search_settings,
        "current_llm_settings": current_llm_settings,
        "default_llm_settings": default_llm_settings,
        "save_llm_settings": save_llm_settings,
        "current_ui_theme_settings": current_ui_theme_settings,
        "default_ui_theme_settings": default_ui_theme_settings,
        "sanitize_ui_theme_settings": sanitize_ui_theme_settings,
        "save_ui_theme_settings": save_ui_theme_settings,
        "current_ui_layout_settings": current_ui_layout_settings,
        "default_ui_layout_settings": default_ui_layout_settings,
        "sanitize_ui_layout_settings": sanitize_ui_layout_settings,
        "save_ui_layout_settings": save_ui_layout_settings,
        "normalize_faq_columns": normalize_faq_columns,
        "read_csv_flexible": read_csv_flexible,
        "faq_df_to_excel_bytes": faq_df_to_excel_bytes,
        "read_faq_uploaded_file": read_faq_uploaded_file,
        "save_faq_csv_full": save_faq_csv_full,
        "load_faq_index": load_faq_index,
        "get_faq_index_state": get_faq_index_state,
        "reset_faq_index_runtime": reset_faq_index_runtime,
        "generate_ops_manual_pdf": generate_ops_manual_pdf,
        "generate_sales_proposal_pdf": generate_sales_proposal_pdf,
        "generate_effect_report_pdf": generate_effect_report_pdf,
        "read_interactions": read_interactions,
        "persist_faq_now": persist_faq_now,
    }

    render_admin_search_and_llm_section(ns)
    render_admin_ui_section(ns)
    render_admin_knowledge_section(ns)
