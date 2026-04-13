from __future__ import annotations


def render_admin_surface(*, admin_ctx: dict, render_admin_complete_tools, render_admin_settings_bundle) -> None:
    """Render all logged-in admin sections from a unified admin context."""
    complete_tools_ctx = admin_ctx.get("complete_tools") or {}
    settings_bundle_ctx = admin_ctx.get("settings_bundle") or {}

    if complete_tools_ctx:
        render_admin_complete_tools(**complete_tools_ctx)
    if settings_bundle_ctx:
        render_admin_settings_bundle(settings_bundle_ctx)
