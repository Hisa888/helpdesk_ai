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
    from helpdesk_app.modules.app_mode import get_app_mode, is_demo_mode
    from helpdesk_app.modules.contact_cta_panel import (
        render_contact_cta_css,
        render_contact_cta_panel,
        render_fixed_contact_button,
    )
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

    app_mode = get_app_mode(st)
    demo_mode = is_demo_mode(app_mode)
    st.session_state["app_mode"] = app_mode
    st.session_state["demo_mode"] = demo_mode

    # 本番用では導入相談ボタンや営業CTAを非表示にする。
    effective_contact_link = services.contact_link if demo_mode else ""
    st.session_state["contact_link"] = effective_contact_link

    render_contact_cta_css(st=st)
    if demo_mode:
        render_fixed_contact_button(st=st, contact_link=effective_contact_link)

    render_brand_header(
        st=st,
        logo_path=services.LOGO_PATH,
        company_name=services.COMPANY_NAME,
        contact_link=effective_contact_link,
        demo_mode=demo_mode,
    )
    render_hero_header(st=st, contact_link=effective_contact_link, demo_mode=demo_mode)
    if demo_mode:
        render_contact_cta_panel(
            st=st,
            contact_link=effective_contact_link,
            company_name=services.COMPANY_NAME,
        )
    finalize_startup_status(startup_status)

    render_runtime_surfaces(
        st=st,
        components=components,
        services=services,
        app_mode=app_mode,
        demo_mode=demo_mode,
    )
