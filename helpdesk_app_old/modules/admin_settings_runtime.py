from __future__ import annotations

from helpdesk_app.modules.admin_settings_sections import (
    render_admin_knowledge_section,
    render_admin_search_and_llm_section,
    render_admin_ui_section,
)


def render_admin_settings_sections(ns: dict) -> None:
    """Render all split admin setting sections from a prepared namespace/context."""

    render_admin_search_and_llm_section(ns)
    render_admin_ui_section(ns)
    render_admin_knowledge_section(ns)
