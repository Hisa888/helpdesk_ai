"""管理者サイドバーの各機能パネルを分割したモジュール。
legacy_runtime.py の機能を削らずに、将来ここだけ差し替えて修正しやすくするための分割です。
"""
from __future__ import annotations

import textwrap

def _exec_panel(code: str, ns: dict) -> None:
    scope = dict(ns)
    scope.setdefault("__builtins__", __builtins__)
    exec(textwrap.dedent(code), scope, scope)

RENDER_UI_LAYOUT_PANEL_CODE = r'''
with st.expander("📐 UIレイアウト設定", expanded=False):
    current_layout = current_ui_layout_settings()
    sidebar_width = st.slider("左メニュー幅", 240, 620, int(current_layout["sidebar_width"]), key="ui_layout_sidebar_width")
    main_max_width = st.slider("メイン画面の最大幅", 760, 2000, int(current_layout["main_max_width"]), step=10, key="ui_layout_main_max_width")
    main_padding_top = st.slider("上余白", 4, 96, int(current_layout["main_padding_top"]), key="ui_layout_main_padding_top")
    main_padding_bottom = st.slider("下余白", 72, 280, int(current_layout["main_padding_bottom"]), key="ui_layout_main_padding_bottom")
    card_radius = st.slider("フレーム角丸", 8, 40, int(current_layout["card_radius"]), key="ui_layout_card_radius")
    card_shadow_blur = st.slider("フレーム影のぼかし", 0, 80, int(current_layout["card_shadow_blur"]), key="ui_layout_card_shadow_blur")
    card_shadow_alpha_pct = st.slider("フレーム影の濃さ", 0, 40, int(round(float(current_layout["card_shadow_alpha"]) * 100)), key="ui_layout_card_shadow_alpha")

    live_layout = sanitize_ui_layout_settings({
        "sidebar_width": sidebar_width,
        "main_max_width": main_max_width,
        "main_padding_top": main_padding_top,
        "main_padding_bottom": main_padding_bottom,
        "card_radius": card_radius,
        "card_shadow_blur": card_shadow_blur,
        "card_shadow_alpha": card_shadow_alpha_pct,
    })
    st.session_state["ui_layout_settings"] = live_layout

    components.html(f"""
    <script>
    (function() {{
      const doc = window.parent.document;
      const root = doc.documentElement;
      root.style.setProperty('--user-sidebar-width', '{live_layout['sidebar_width']}px');
      root.style.setProperty('--user-main-max-width', '{live_layout['main_max_width']}px');
      root.style.setProperty('--user-main-padding-top', '{live_layout['main_padding_top']}px');
      root.style.setProperty('--user-main-padding-bottom', '{live_layout['main_padding_bottom']}px');
      root.style.setProperty('--user-card-radius', '{live_layout['card_radius']}px');
      root.style.setProperty('--user-card-shadow', '0 10px {live_layout['card_shadow_blur']}px rgba(15, 23, 42, {live_layout['card_shadow_alpha']:.2f})');
      window.localStorage.setItem('oai_sidebar_width', '{live_layout['sidebar_width']}');
      window.localStorage.setItem('oai_main_max_width', '{live_layout['main_max_width']}');
    }})();
    </script>
    """, height=0, width=0)

    col_layout1, col_layout2 = st.columns(2)
    with col_layout1:
        if st.button("💾 UIレイアウトを保存", width="stretch", key="save_ui_layout"):
            ok, _ = save_ui_layout_settings(live_layout)
            st.success("UIレイアウトを保存しました。" if ok else "UIレイアウトは反映済みですが、保存に失敗した可能性があります。")
    with col_layout2:
        if st.button("↩ UIレイアウトを初期値に戻す", width="stretch", key="reset_ui_layout"):
            default_layout = default_ui_layout_settings()
            save_ui_layout_settings(default_layout)
            st.session_state["ui_layout_settings"] = default_layout
            window_local_js = f"""<script>(function(){{const doc=window.parent.document;const root=doc.documentElement;root.style.setProperty('--user-sidebar-width','{default_layout['sidebar_width']}px');root.style.setProperty('--user-main-max-width','{default_layout['main_max_width']}px');localStorage.removeItem('oai_sidebar_width');localStorage.removeItem('oai_main_max_width');}})();</script>"""
            components.html(window_local_js, height=0, width=0)
            st.rerun()
'''


def render_ui_layout_panel(ns: dict) -> None:
    _exec_panel(RENDER_UI_LAYOUT_PANEL_CODE, ns)
