from __future__ import annotations


def pick_keys(ns: dict, keys: list[str]) -> dict:
    """Return a shallow dict containing only existing keys."""
    return {key: ns[key] for key in keys if key in ns}


FAQ_ADMIN_KEYS = [
    "st",
    "normalize_faq_columns",
    "read_csv_flexible",
    "FAQ_PATH",
    "faq_df_to_excel_bytes",
    "read_faq_uploaded_file",
    "save_faq_csv_full",
    "load_faq_index",
    "get_faq_index_state",
    "reset_faq_index_runtime",
    "persist_faq_now",
]

PDF_PANEL_KEYS = [
    "st",
    "REPORTLAB_AVAILABLE",
    "generate_ops_manual_pdf",
    "generate_sales_proposal_pdf",
    "generate_effect_report_pdf",
    "read_interactions",
    "pd",
    "datetime",
]

SEARCH_PANEL_KEYS = [
    "st",
    "current_search_settings",
    "save_search_settings",
    "default_search_settings",
]

LLM_PANEL_KEYS = [
    "st",
    "current_llm_settings",
    "save_llm_settings",
    "default_llm_settings",
]

UI_THEME_PANEL_KEYS = [
    "st",
    "current_ui_theme_settings",
    "sanitize_ui_theme_settings",
    "save_ui_theme_settings",
    "default_ui_theme_settings",
]

UI_LAYOUT_PANEL_KEYS = [
    "st",
    "current_ui_layout_settings",
    "sanitize_ui_layout_settings",
    "save_ui_layout_settings",
    "default_ui_layout_settings",
]


def build_faq_admin_context(ns: dict) -> dict:
    return pick_keys(ns, FAQ_ADMIN_KEYS)



def build_pdf_panel_context(ns: dict) -> dict:
    return pick_keys(ns, PDF_PANEL_KEYS)



def build_search_panel_context(ns: dict) -> dict:
    return pick_keys(ns, SEARCH_PANEL_KEYS)



def build_llm_panel_context(ns: dict) -> dict:
    return pick_keys(ns, LLM_PANEL_KEYS)



def build_ui_theme_panel_context(ns: dict) -> dict:
    return pick_keys(ns, UI_THEME_PANEL_KEYS)



def build_ui_layout_panel_context(ns: dict) -> dict:
    return pick_keys(ns, UI_LAYOUT_PANEL_KEYS)


ADMIN_SETTINGS_BUNDLE_KEYS = list(dict.fromkeys(
    SEARCH_PANEL_KEYS
    + LLM_PANEL_KEYS
    + UI_THEME_PANEL_KEYS
    + UI_LAYOUT_PANEL_KEYS
    + FAQ_ADMIN_KEYS
    + PDF_PANEL_KEYS
))


def build_admin_settings_bundle_context(ns: dict) -> dict:
    return pick_keys(ns, ADMIN_SETTINGS_BUNDLE_KEYS)
