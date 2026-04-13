def run_app():
    import requests
    import streamlit as st
    import streamlit.components.v1 as components

    from helpdesk_app.modules.app_bootstrap import (
        finalize_startup_status,
        initialize_app_shell,
        render_brand_header,
        render_hero_header,
    )
    from helpdesk_app.modules.app_runtime_services import create_runtime_services
    from helpdesk_app.modules.app_surface_runner import render_runtime_surfaces

    services = create_runtime_services(
        st=st,
        requests=requests,
        root_dir=".",
    )

    startup_status, _ui_theme, _ui_layout = initialize_app_shell(
        st=st,
        components=components,
        current_ui_theme_settings=services.current_ui_theme_settings,
        current_ui_layout_settings=services.current_ui_layout_settings,
    )

    render_brand_header(
        st=st,
        logo_path=services.LOGO_PATH,
        company_name=services.COMPANY_NAME,
        contact_link=services.contact_link,
    )
    render_hero_header(st=st, contact_link=services.contact_link)
    finalize_startup_status(startup_status)

    render_runtime_surfaces(
        st=st,
        components=components,
        services=services,
    )
