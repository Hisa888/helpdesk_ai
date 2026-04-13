from __future__ import annotations

from helpdesk_app.modules.admin_contexts import build_admin_settings_bundle_context
from helpdesk_app.modules.app_runtime_contexts import build_admin_complete_tools_context


def build_admin_surface_context(ns: dict) -> dict:
    """Build the two admin sub-contexts together so runtime_main passes one object forward."""
    return {
        "complete_tools": build_admin_complete_tools_context(ns),
        "settings_bundle": build_admin_settings_bundle_context(ns),
    }
