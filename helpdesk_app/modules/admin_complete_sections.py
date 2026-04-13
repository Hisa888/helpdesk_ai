from __future__ import annotations

from helpdesk_app.modules.admin_dashboard_panel import render_admin_dashboard_panel
from helpdesk_app.modules.admin_faq_generation_panel import render_admin_faq_generation_panel
from helpdesk_app.modules.admin_log_download_panel import render_admin_log_download_panel


def render_admin_complete_sections(ctx: dict) -> None:
    """Render split admin dashboard/download/FAQ-generation sections from a single context."""

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
