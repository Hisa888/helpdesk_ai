from __future__ import annotations

from helpdesk_app.admin_menu_complete import render_admin_complete_tools
from helpdesk_app.modules.admin_settings_bundle import render_admin_settings_bundle
from helpdesk_app.modules.admin_surface_contexts import build_admin_surface_context
from helpdesk_app.modules.admin_surface_runtime import render_admin_surface
from helpdesk_app.modules.answer_panel import (
    build_suggest_answer as build_suggest_answer_panel,
    render_answer_message,
    render_used_hits_expander as render_used_hits_expander_panel,
)
from helpdesk_app.modules.app_runtime_contexts import (
    build_admin_surface_runtime_context,
    build_main_screen_layout_context,
    build_main_screen_session_context,
)
from helpdesk_app.modules.chat_history_panel import (
    clean_legacy_bootstrap_messages,
    is_welcome_state,
    render_chat_history,
    render_welcome_prompt,
)
from helpdesk_app.modules.chat_input_panel import (
    append_user_message,
    ensure_chat_session_state,
    render_chat_input as render_chat_input_panel,
)
from helpdesk_app.modules.chat_interaction_runtime import (
    build_suggest_answer_for_runtime,
    handle_chat_interaction,
    render_input_support_sections,
)
from helpdesk_app.modules.main_screen_layout import (
    ensure_main_screen_session_state,
    render_main_screen_layout,
)
from helpdesk_app.modules.main_view_runtime import (
    ensure_admin_session_state,
    render_admin_login_sidebar,
    render_admin_tools_if_logged_in,
    render_public_sidebar,
    render_sales_kpi_sections,
)
from helpdesk_app.modules.nohit_form_panel import render_nohit_extra_form as render_nohit_extra_form_panel
from helpdesk_app.modules.query_flow_runtime import finalize_answer_cycle, process_user_query
from helpdesk_app.modules.quick_start_panel import (
    ensure_quick_start_session_state,
    render_quick_start_compact,
    render_quick_start_hero,
)
from helpdesk_app.modules.scroll_utils import (
    ensure_scroll_state,
    maybe_scroll_to_latest_answer,
    request_scroll_to_answer,
)
from helpdesk_app.modules.ui_helpers import render_match_bar



def render_runtime_surfaces(*, st, components, services, app_mode: str = "demo", demo_mode: bool = True) -> None:
    if demo_mode:
        render_sales_kpi_sections(read_interactions=services.read_interactions)
    render_public_sidebar(
        contact_link=services.contact_link if demo_mode else "",
        demo_mode=demo_mode,
        count_nohit_logs=services.count_nohit_logs,
        read_interactions=services.read_interactions,
        list_log_files=services.list_log_files,
        make_logs_zip=services.make_logs_zip,
        csv_bytes_as_utf8_sig=services.csv_bytes_as_utf8_sig,
        format_minutes_to_hours=services.format_minutes_to_hours,
    )

    ensure_admin_session_state()
    render_admin_login_sidebar(check_password=services.check_password)

    admin_surface_ctx = build_admin_surface_context({
        "st": st,
        "render_admin_complete_tools": render_admin_complete_tools,
        "read_interactions": services.read_interactions,
        "count_nohit_logs": services.count_nohit_logs,
        "list_log_files": services.list_log_files,
        "make_logs_zip": services.make_logs_zip,
        "load_nohit_questions_from_logs": services.load_nohit_questions_from_logs,
        "generate_faq_candidates": services.generate_faq_candidates,
        "append_faq_csv": services.append_faq_csv,
        "seed_nohit_questions": services.seed_nohit_questions,
        "faq_path": services.FAQ_PATH,
        "build_document_rag_index": services.build_document_rag_index,
        "get_document_rag_manifest": services.get_document_rag_manifest,
        "clear_document_rag": services.clear_document_rag,
        "supported_doc_rag_extensions": services.SUPPORTED_DOC_RAG_EXTENSIONS,
        "generate_manual_faq_candidates": services.generate_manual_faq_candidates,
        "supported_manual_faq_extensions": services.SUPPORTED_MANUAL_FAQ_EXTENSIONS,
        "current_search_settings": services.current_search_settings,
        "save_search_settings": services.save_search_settings,
        "default_search_settings": services.default_search_settings,
        "current_llm_settings": services.current_llm_settings,
        "save_llm_settings": services.save_llm_settings,
        "default_llm_settings": services.default_llm_settings,
        "current_ui_theme_settings": services.current_ui_theme_settings,
        "sanitize_ui_theme_settings": services.sanitize_ui_theme_settings,
        "save_ui_theme_settings": services.save_ui_theme_settings,
        "default_ui_theme_settings": services.default_ui_theme_settings,
        "current_ui_layout_settings": services.current_ui_layout_settings,
        "sanitize_ui_layout_settings": services.sanitize_ui_layout_settings,
        "save_ui_layout_settings": services.save_ui_layout_settings,
        "default_ui_layout_settings": services.default_ui_layout_settings,
        "normalize_faq_columns": services.normalize_faq_columns,
        "read_csv_flexible": services.read_csv_flexible,
        "FAQ_PATH": services.FAQ_PATH,
        "faq_df_to_excel_bytes": services.faq_df_to_excel_bytes,
        "read_faq_uploaded_file": services.read_faq_uploaded_file,
        "read_faq_operation_uploaded_file": services.read_faq_operation_uploaded_file,
        "apply_faq_upload_operations": services.apply_faq_upload_operations,
        "append_faq_import_history": services.append_faq_import_history,
        "save_faq_csv_full": services.save_faq_csv_full,
        "get_current_admin_name": services.get_current_admin_name,
        "load_faq_index": services.load_faq_index,
        "get_faq_index_state": services.get_faq_index_state,
        "reset_faq_index_runtime": services.reset_faq_index_runtime,
        "persist_faq_now": services.persist_faq_now,
        "REPORTLAB_AVAILABLE": services.REPORTLAB_AVAILABLE,
        "generate_ops_manual_pdf": services.generate_ops_manual_pdf,
        "generate_sales_proposal_pdf": services.generate_sales_proposal_pdf,
        "generate_effect_report_pdf": services.generate_effect_report_pdf,
        "pd": services.pd,
        "datetime": services.datetime,
    })
    render_admin_tools_if_logged_in(
        **build_admin_surface_runtime_context({
            "render_admin_surface": render_admin_surface,
            "admin_ctx": admin_surface_ctx,
            "render_admin_complete_tools": render_admin_complete_tools,
            "render_admin_settings_bundle": render_admin_settings_bundle,
        })
    )

    ensure_main_screen_session_state(
        **build_main_screen_session_context({
            "st": st,
            "SEARCH_SETTINGS": services.SEARCH_SETTINGS,
            "DEFAULT_SEARCH_THRESHOLD": services.DEFAULT_SEARCH_THRESHOLD,
            "DEFAULT_SUGGEST_THRESHOLD": services.DEFAULT_SUGGEST_THRESHOLD,
            "_sanitize_search_settings": services._sanitize_search_settings,
            "sanitize_llm_settings": services.sanitize_llm_settings,
            "LLM_SETTINGS": services.settings_ctx.LLM_SETTINGS,
            "ensure_chat_session_state": ensure_chat_session_state,
            "ensure_quick_start_session_state": ensure_quick_start_session_state,
            "ensure_scroll_state": ensure_scroll_state,
            "clean_legacy_bootstrap_messages": clean_legacy_bootstrap_messages,
        })
    )

    render_main_screen_layout(
        **build_main_screen_layout_context({
            "st": st,
            "components": components,
            "is_welcome_state": is_welcome_state,
            "render_welcome_prompt": render_welcome_prompt,
            "render_quick_start_hero": render_quick_start_hero,
            "render_chat_history": render_chat_history,
            "render_nohit_extra_form_panel": render_nohit_extra_form_panel,
            "update_nohit_record": services.update_nohit_record,
            "render_input_support_sections": render_input_support_sections,
            "render_quick_start_compact": render_quick_start_compact,
            "handle_chat_interaction": handle_chat_interaction,
            "render_chat_input_panel": render_chat_input_panel,
            "request_scroll_to_answer": request_scroll_to_answer,
            "append_user_message": append_user_message,
            "process_user_query": process_user_query,
            "finalize_answer_cycle": finalize_answer_cycle,
            "render_answer_message": render_answer_message,
            "render_used_hits_expander_panel": render_used_hits_expander_panel,
            "render_match_bar": render_match_bar,
            "try_ultrafast_answer": services.try_ultrafast_answer,
            "retrieve_faq_cached": services.retrieve_faq_cached,
            "faq_cache_token_getter": services.faq_cache_token_getter,
            "ensure_faq_index_loaded": services.ensure_faq_index_loaded,
            "current_search_settings": services.current_search_settings,
            "current_search_threshold": services.current_search_threshold,
            "current_suggest_threshold": services.current_suggest_threshold,
            "nohit_template": services.nohit_template,
            "log_nohit": services.log_nohit,
            "build_suggest_answer_for_runtime": build_suggest_answer_for_runtime,
            "build_suggest_answer_panel": build_suggest_answer_panel,
            "_fastlane_direct_answer": services._fastlane_direct_answer,
            "build_prompt": services.build_prompt,
            "llm_answer_cached": services.llm_answer_cached,
            "log_interaction": services.log_interaction,
            "search_document_rag": services.search_document_rag,
            "answer_with_document_rag": services.answer_with_document_rag,
            "doc_rag_threshold": services.DEFAULT_DOC_RAG_THRESHOLD,
            "llm_chat": services.llm_chat,
            "maybe_scroll_to_latest_answer": maybe_scroll_to_latest_answer,
        })
    )
