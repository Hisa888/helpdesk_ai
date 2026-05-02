from __future__ import annotations


def pick_keys(ns: dict, keys: list[str]) -> dict:
    return {key: ns[key] for key in keys if key in ns}


ADMIN_COMPLETE_TOOLS_KEYS = [
    "read_interactions",
    "count_nohit_logs",
    "list_log_files",
    "make_logs_zip",
    "load_nohit_questions_from_logs",
    "generate_faq_candidates",
    "append_faq_csv",
    "seed_nohit_questions",
    "faq_path",
    "build_document_rag_index",
    "get_document_rag_manifest",
    "clear_document_rag",
    "supported_doc_rag_extensions",
    "generate_manual_faq_candidates",
    "supported_manual_faq_extensions",
]


ADMIN_SURFACE_RUNTIME_KEYS = [
    "render_admin_surface",
    "admin_ctx",
    "render_admin_complete_tools",
    "render_admin_settings_bundle",
]


MAIN_SCREEN_SESSION_KEYS = [
    "st",
    "SEARCH_SETTINGS",
    "DEFAULT_SEARCH_THRESHOLD",
    "DEFAULT_SUGGEST_THRESHOLD",
    "_sanitize_search_settings",
    "sanitize_llm_settings",
    "LLM_SETTINGS",
    "ensure_chat_session_state",
    "ensure_quick_start_session_state",
    "ensure_scroll_state",
    "clean_legacy_bootstrap_messages",
]


MAIN_SCREEN_LAYOUT_KEYS = [
    "st",
    "components",
    "is_welcome_state",
    "render_welcome_prompt",
    "render_quick_start_hero",
    "render_chat_history",
    "render_nohit_extra_form_panel",
    "update_nohit_record",
    "render_input_support_sections",
    "render_quick_start_compact",
    "handle_chat_interaction",
    "render_chat_input_panel",
    "request_scroll_to_answer",
    "append_user_message",
    "process_user_query",
    "finalize_answer_cycle",
    "render_answer_message",
    "render_used_hits_expander_panel",
    "render_match_bar",
    "try_ultrafast_answer",
    "retrieve_faq_cached",
    "faq_cache_token_getter",
    "ensure_faq_index_loaded",
    "current_search_settings",
    "current_search_threshold",
    "current_suggest_threshold",
    "nohit_template",
    "log_nohit",
    "build_suggest_answer_for_runtime",
    "build_suggest_answer_panel",
    "_fastlane_direct_answer",
    "build_prompt",
    "llm_answer_cached",
    "log_interaction",
    "maybe_scroll_to_latest_answer",
    "search_document_rag",
    "answer_with_document_rag",
    "doc_rag_threshold",
    "llm_chat",
]


def build_admin_complete_tools_context(ns: dict) -> dict:
    return pick_keys(ns, ADMIN_COMPLETE_TOOLS_KEYS)


def build_admin_surface_runtime_context(ns: dict) -> dict:
    return pick_keys(ns, ADMIN_SURFACE_RUNTIME_KEYS)


def build_main_screen_session_context(ns: dict) -> dict:
    return pick_keys(ns, MAIN_SCREEN_SESSION_KEYS)


def build_main_screen_layout_context(ns: dict) -> dict:
    return pick_keys(ns, MAIN_SCREEN_LAYOUT_KEYS)
