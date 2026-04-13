from __future__ import annotations

from helpdesk_app.modules.admin_settings_runtime import render_admin_settings_sections


def render_admin_settings_bundle(ns: dict) -> None:
    st = ns["st"]
    if not st.session_state.get("is_admin"):
        return

    render_admin_settings_sections(ns)
