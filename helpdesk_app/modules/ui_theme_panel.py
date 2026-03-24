"""管理者サイドバーの各機能パネルを分割したモジュール。
legacy_runtime.py の機能を削らずに、将来ここだけ差し替えて修正しやすくするための分割です。
"""
from __future__ import annotations

import textwrap

def _exec_panel(code: str, ns: dict) -> None:
    scope = dict(ns)
    scope.setdefault("__builtins__", __builtins__)
    exec(textwrap.dedent(code), scope, scope)

RENDER_UI_THEME_PANEL_CODE = r'''
with st.expander("🎨 UI配色設定", expanded=False):
    current_theme = current_ui_theme_settings()

    c1, c2 = st.columns(2)
    with c1:
        sidebar_bg_start = st.color_picker("左メニュー背景（開始色）", current_theme["sidebar_bg_start"], key="ui_sidebar_bg_start")
        sidebar_text = st.color_picker("左メニュー文字色", current_theme["sidebar_text"], key="ui_sidebar_text")
        sidebar_text_muted = st.color_picker("左メニュー補助文字色", current_theme["sidebar_text_muted"], key="ui_sidebar_text_muted")
        button_bg = st.color_picker("ボタン背景色", current_theme["button_bg"], key="ui_button_bg")
        button_text = st.color_picker("ボタン文字色", current_theme["button_text"], key="ui_button_text")
        button_border = st.color_picker("ボタン枠線色", current_theme["button_border"], key="ui_button_border")
        button_hover_bg = st.color_picker("ボタンホバー背景", current_theme["button_hover_bg"], key="ui_button_hover_bg")
        button_hover_text = st.color_picker("ボタンホバー文字", current_theme["button_hover_text"], key="ui_button_hover_text")
        button_disabled_bg = st.color_picker("無効ボタン背景色", current_theme["button_disabled_bg"], key="ui_button_disabled_bg")
        button_disabled_text = st.color_picker("無効ボタン文字色", current_theme["button_disabled_text"], key="ui_button_disabled_text")
    with c2:
        sidebar_bg_end = st.color_picker("左メニュー背景（終了色）", current_theme["sidebar_bg_end"], key="ui_sidebar_bg_end")
        main_bg_start = st.color_picker("メイン背景（開始色）", current_theme["main_bg_start"], key="ui_main_bg_start")
        main_bg_mid = st.color_picker("メイン背景（中央色）", current_theme["main_bg_mid"], key="ui_main_bg_mid")
        main_bg_end = st.color_picker("メイン背景（終了色）", current_theme["main_bg_end"], key="ui_main_bg_end")
        card_border = st.color_picker("カード枠線色", current_theme["card_border"], key="ui_card_border")
        resizer_knob = st.color_picker("ドラッグつまみ色", current_theme["resizer_knob"], key="ui_resizer_knob")

    sidebar_panel_bg = st.text_input("左メニューパネル背景（hex または rgba）", value=current_theme["sidebar_panel_bg"], key="ui_sidebar_panel_bg")
    sidebar_panel_border = st.text_input("左メニューパネル枠線（hex または rgba）", value=current_theme["sidebar_panel_border"], key="ui_sidebar_panel_border")
    card_bg = st.text_input("カード背景色（hex または rgba）", value=current_theme["card_bg"], key="ui_card_bg")
    resizer_line = st.text_input("ドラッグライン色（hex または rgba）", value=current_theme["resizer_line"], key="ui_resizer_line")

    live_theme = sanitize_ui_theme_settings({
        "sidebar_bg_start": sidebar_bg_start,
        "sidebar_bg_end": sidebar_bg_end,
        "sidebar_text": sidebar_text,
        "sidebar_text_muted": sidebar_text_muted,
        "sidebar_panel_bg": sidebar_panel_bg,
        "sidebar_panel_border": sidebar_panel_border,
        "button_bg": button_bg,
        "button_text": button_text,
        "button_border": button_border,
        "button_hover_bg": button_hover_bg,
        "button_hover_text": button_hover_text,
        "button_disabled_bg": button_disabled_bg,
        "button_disabled_text": button_disabled_text,
        "main_bg_start": main_bg_start,
        "main_bg_mid": main_bg_mid,
        "main_bg_end": main_bg_end,
        "card_bg": card_bg,
        "card_border": card_border,
        "resizer_line": resizer_line,
        "resizer_knob": resizer_knob,
    })
    st.session_state["ui_theme_settings"] = live_theme

    col_ui1, col_ui2 = st.columns(2)
    with col_ui1:
        if st.button("💾 UI配色を保存", width="stretch", key="save_ui_theme"):
            ok, _ = save_ui_theme_settings(live_theme)
            st.success("UI配色を保存しました。" if ok else "UI配色は反映済みですが、保存に失敗した可能性があります。")
    with col_ui2:
        if st.button("↩ UI配色を初期値に戻す", width="stretch", key="reset_ui_theme"):
            default_theme = default_ui_theme_settings()
            save_ui_theme_settings(default_theme)
            for k, v in default_theme.items():
                st.session_state[f"ui_{k}"] = v
            st.session_state["ui_theme_settings"] = default_theme
            st.rerun()
'''


def render_ui_theme_panel(ns: dict) -> None:
    _exec_panel(RENDER_UI_THEME_PANEL_CODE, ns)
