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
    from helpdesk_app.modules.tenant_auth import ensure_tenant_login, render_tenant_sidebar
    from helpdesk_app.modules.trial_license import (
        get_tenant_license,
        render_trial_expired_screen,
        render_trial_status_banner,
        should_lock_trial,
    )

    try:
        st.set_page_config(page_title="情シス問い合わせAI", layout="wide", initial_sidebar_state="expanded")
    except Exception:
        pass

    if not ensure_tenant_login(st):
        return

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

    license_info = get_tenant_license(st, str(st.session_state.get("tenant_id", "demo")))
    st.session_state["tenant_license_type"] = license_info.license_type
    st.session_state["tenant_expire_date"] = license_info.expire_date.isoformat() if license_info.expire_date else ""
    st.session_state["tenant_remaining_days"] = license_info.remaining_days
    st.session_state["tenant_license_expired"] = should_lock_trial(license_info)

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
    render_tenant_sidebar(st)
    # 期限表示は左サイドバーに固定表示する。
    # st.sidebar を渡すことで、本文側の表示崩れや色設定の影響を抑えます。
    render_trial_status_banner(st.sidebar, license_info, contact_link=effective_contact_link)

    trial_expired = should_lock_trial(license_info)
    if trial_expired:
        # 期限切れ時だけは本番モードでも導入相談導線を出せるようにする。
        trial_contact_link = services.contact_link or effective_contact_link
        render_trial_expired_screen(
            st,
            license_info,
            contact_link=trial_contact_link,
            company_name=services.COMPANY_NAME,
        )

    render_runtime_surfaces(
        st=st,
        components=components,
        services=services,
        app_mode=app_mode,
        demo_mode=demo_mode,
        trial_expired=trial_expired,
    )
