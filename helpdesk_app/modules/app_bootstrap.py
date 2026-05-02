from __future__ import annotations

from html import escape
from pathlib import Path


def initialize_app_shell(*, st, components, current_ui_theme_settings, current_ui_layout_settings):
    st.set_page_config(page_title="情シス問い合わせAI", layout="wide")
    startup_status = st.empty()
    startup_status.caption("🚀 情シス問い合わせAI を起動しています…")

    render_base_theme_css(st)

    ui_theme = current_ui_theme_settings()
    ui_layout = current_ui_layout_settings()
    st.session_state["ui_theme_settings"] = ui_theme
    st.session_state["ui_layout_settings"] = ui_layout

    apply_user_ui_settings(
        st=st,
        components=components,
        ui_theme=ui_theme,
        ui_layout=ui_layout,
    )
    return startup_status, ui_theme, ui_layout


def finalize_startup_status(startup_status) -> None:
    try:
        startup_status.empty()
    except Exception:
        pass


def render_base_theme_css(st) -> None:
    st.markdown(
        """
<style>
:root {
  --bg-soft: #f8fafc;
  --border: #e2e8f0;
  --text-main: #0f172a;
  --text-sub: #475569;
  --brand: #0ea5e9;
  --brand-2: #22c55e;
  --shadow: 0 10px 30px rgba(15, 23, 42, 0.08);
}

.block-container {padding-top: 2rem !important; padding-bottom: 9rem !important; max-width: 1180px;}
h1, h2, h3 {line-height: 1.25 !important;}

[data-testid="stAppViewContainer"] {
  background: radial-gradient(circle at top left, #f0f9ff 0%, #ffffff 32%, #f8fafc 100%);
}
[data-testid="stSidebar"] {
  background: linear-gradient(180deg, #0f172a 0%, #111827 100%);
}
[data-testid="stSidebar"] * {color: #e5eef8 !important;}
[data-testid="stSidebar"] .stAlert * {color: inherit !important;}
[data-testid="stSidebar"] [data-testid="stExpander"] {
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 16px;
  background: rgba(255,255,255,0.04);
}

.hero-shell {
  background: linear-gradient(135deg, #0f172a 0%, #0ea5e9 52%, #22c55e 100%);
  padding: 26px 28px;
  border-radius: 24px;
  box-shadow: 0 18px 40px rgba(14, 165, 233, 0.18);
  color: #fff;
  margin-bottom: 18px;
  position: relative;
  overflow: hidden;
}
.hero-shell::after {
  content: "";
  position: absolute;
  right: -60px;
  top: -60px;
  width: 220px;
  height: 220px;
  background: rgba(255,255,255,0.10);
  border-radius: 999px;
  filter: blur(4px);
}
.hero {position: relative; z-index: 1;}
.hero h1 {font-size: 38px; margin: 0 0 8px 0; letter-spacing: -0.03em;}
.hero p {margin: 0; font-size: 15px; opacity: .96; max-width: 780px;}
.badges {margin-top: 14px; display:flex; gap:8px; flex-wrap:wrap;}
.badge {background: rgba(255,255,255,0.16); border: 1px solid rgba(255,255,255,0.22); padding: 7px 11px; border-radius: 999px; font-size: 12px; backdrop-filter: blur(6px);}
.cta-row {display:flex; gap:10px; flex-wrap:wrap; margin-top:14px;}
.cta {background: rgba(255,255,255,0.12); border: 1px solid rgba(255,255,255,0.20); padding: 10px 12px; border-radius: 14px; font-size: 13px; backdrop-filter: blur(6px);}

.topbar-card {
  background: rgba(255,255,255,0.88);
  border: 1px solid var(--border);
  border-radius: 18px;
  padding: 14px 16px;
  box-shadow: var(--shadow);
  margin-bottom: 14px;
}
.brand-row {display:flex; align-items:center; gap:12px;}
.brand-title {font-size: 1.15rem; font-weight: 800; color: var(--text-main); margin:0;}
.brand-sub {font-size: .88rem; color: var(--text-sub); margin-top:2px;}

.glass-card, .card {
  background: rgba(255,255,255,0.88);
  border: 1px solid var(--border);
  border-radius: 18px;
  padding: 16px 18px;
  box-shadow: var(--shadow);
}
.card h3 {margin: 0 0 8px 0; font-size: 16px;}
.small {font-size: 12px; color:#6b7280;}
.section-title {font-size:20px; font-weight:800; margin: 8px 0 12px 0; color: var(--text-main);}
.section-caption {font-size: 13px; color: var(--text-sub); margin-top: -2px; margin-bottom: 12px;}
.query-panel {margin: 18px 0 10px 0;}
.query-panel .eyebrow {font-size: 12px; color: #0369a1; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase;}
.query-panel h3 {margin: 5px 0 6px 0; font-size: 22px; color: var(--text-main);}
.query-panel p {margin: 0; color: var(--text-sub); font-size: 14px;}
.hero-eyebrow {font-size: 12px; font-weight: 800; letter-spacing: .08em; text-transform: uppercase; opacity: .9; margin-bottom: 8px;}
.hero-consult {margin-top: 22px; display:flex; align-items:center; gap:12px; flex-wrap:wrap;}
.hero-consult a {display:inline-flex; align-items:center; justify-content:center; min-height:52px; background:#ffffff; color:#0f172a !important; text-decoration:none !important; padding:14px 24px; border-radius:16px; font-size:18px; font-weight:900; box-shadow:0 14px 30px rgba(15,23,42,0.18);}
.hero-consult a:hover {filter: brightness(1.03); transform: translateY(-1px);}
.hero-consult-copy {font-size:13px; font-weight:800; color:rgba(255,255,255,0.92);}

.kpi-grid {display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 12px; margin: 14px 0 18px 0;}
@media (max-width: 1100px){ .kpi-grid {grid-template-columns: repeat(2, minmax(0, 1fr));} }
.kpi {background: rgba(255,255,255,0.92); border:1px solid var(--border); border-radius:20px; padding:16px 16px; box-shadow: var(--shadow);}
.kpi .label {font-size:12px; color:#64748b; margin-bottom:8px; font-weight:600;}
.kpi .value {font-size:30px; font-weight:800; letter-spacing:-0.03em; color:var(--text-main); margin:0;}
.kpi .sub {font-size:12px; color:#64748b; margin-top:6px;}

.refbox {border-left: 4px solid #0ea5e9; background: linear-gradient(180deg, #f8fbff 0%, #f8fafc 100%); padding: 12px 14px; border-radius: 14px; border:1px solid #dbeafe;}
.answerbox {border-left: 4px solid #22c55e; background: linear-gradient(180deg, #f0fdf4 0%, #ffffff 100%); padding: 14px 16px; border-radius: 16px; line-height: 1.72; border: 1px solid #bbf7d0; box-shadow: 0 8px 20px rgba(34,197,94,0.08);}

[data-testid="stExpander"] {border: 1px solid var(--border); border-radius: 16px; background: rgba(255,255,255,0.85);}
[data-testid="stChatMessage"] {background: transparent;}
[data-testid="stChatInput"] {
  background: rgba(255,255,255,0.96);
  border: 1px solid var(--border);
  border-radius: 18px;
  box-shadow: 0 10px 24px rgba(15,23,42,0.08);
}

.stButton > button, .stDownloadButton > button, .stLinkButton a {
  border-radius: 14px !important;
  font-weight: 700 !important;
}
.stButton > button[kind="primary"], .stDownloadButton > button[kind="primary"] {
  background: linear-gradient(135deg, #0ea5e9 0%, #22c55e 100%) !important;
  border: 0 !important;
  color: #fff !important;
}

div[data-testid="column"] .stButton > button {width: 100%; min-height: 54px;}
@media (max-width: 768px) {
  .block-container {padding-top: 1.2rem !important; padding-bottom: 8rem !important;}
  .hero-shell {padding: 20px 18px; border-radius: 20px;}
  .hero h1 {font-size: 30px;}
  .kpi-grid {grid-template-columns: 1fr;}
}
</style>
""",
        unsafe_allow_html=True,
    )


def apply_user_ui_settings(*, st, components, ui_theme: dict, ui_layout: dict) -> None:
    st.markdown(
        f"""
<style>
:root {{
  --user-sidebar-width: {int(ui_layout['sidebar_width'])}px;
  --user-main-max-width: {int(ui_layout['main_max_width'])}px;
  --user-main-padding-top: {int(ui_layout['main_padding_top'])}px;
  --user-main-padding-bottom: {int(ui_layout['main_padding_bottom'])}px;
  --user-card-radius: {int(ui_layout['card_radius'])}px;
  --user-card-shadow: 0 10px {int(ui_layout['card_shadow_blur'])}px rgba(15, 23, 42, {float(ui_layout['card_shadow_alpha']):.2f});
  --user-sidebar-bg-start: {ui_theme['sidebar_bg_start']};
  --user-sidebar-bg-end: {ui_theme['sidebar_bg_end']};
  --user-sidebar-text: {ui_theme['sidebar_text']};
  --user-sidebar-text-muted: {ui_theme['sidebar_text_muted']};
  --user-sidebar-panel-bg: {ui_theme['sidebar_panel_bg']};
  --user-sidebar-panel-border: {ui_theme['sidebar_panel_border']};
  --user-button-bg: {ui_theme['button_bg']};
  --user-button-text: {ui_theme['button_text']};
  --user-button-border: {ui_theme['button_border']};
  --user-button-hover-bg: {ui_theme['button_hover_bg']};
  --user-button-hover-text: {ui_theme['button_hover_text']};
  --user-button-disabled-bg: {ui_theme['button_disabled_bg']};
  --user-button-disabled-text: {ui_theme['button_disabled_text']};
  --user-main-bg-start: {ui_theme['main_bg_start']};
  --user-main-bg-mid: {ui_theme['main_bg_mid']};
  --user-main-bg-end: {ui_theme['main_bg_end']};
  --user-card-bg: {ui_theme['card_bg']};
  --user-card-border: {ui_theme['card_border']};
  --user-resizer-line: {ui_theme['resizer_line']};
  --user-resizer-knob: {ui_theme['resizer_knob']};
}}
[data-testid="stSidebar"] {{
  min-width: var(--user-sidebar-width) !important;
  max-width: var(--user-sidebar-width) !important;
  width: var(--user-sidebar-width) !important;
  background: linear-gradient(180deg, var(--user-sidebar-bg-start) 0%, var(--user-sidebar-bg-end) 100%) !important;
}}
[data-testid="stSidebar"] * {{color: var(--user-sidebar-text) !important;}}
[data-testid="stSidebar"] small,
[data-testid="stSidebar"] .small,
[data-testid="stSidebar"] .stCaption,
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {{color: var(--user-sidebar-text-muted) !important;}}
[data-testid="stSidebar"] [data-testid="stExpander"] {{
  background: var(--user-sidebar-panel-bg) !important;
  border-color: var(--user-sidebar-panel-border) !important;
  border-radius: 16px !important;
}}
[data-testid="stSidebar"] .stButton > button,
[data-testid="stSidebar"] .stDownloadButton > button,
[data-testid="stSidebar"] .stLinkButton a {{
  background: var(--user-button-bg) !important;
  color: var(--user-button-text) !important;
  border: 1px solid var(--user-button-border) !important;
}}
[data-testid="stSidebar"] .stButton > button:hover,
[data-testid="stSidebar"] .stDownloadButton > button:hover,
[data-testid="stSidebar"] .stLinkButton a:hover {{
  background: var(--user-button-hover-bg) !important;
  color: var(--user-button-hover-text) !important;
  border-color: var(--user-button-hover-bg) !important;
}}
[data-testid="stSidebar"] .stButton > button:disabled,
[data-testid="stSidebar"] .stDownloadButton > button:disabled {{
  background: var(--user-button-disabled-bg) !important;
  color: var(--user-button-disabled-text) !important;
  opacity: 1 !important;
}}
[data-testid="stAppViewContainer"] {{
  background: radial-gradient(circle at top left, var(--user-main-bg-start) 0%, var(--user-main-bg-mid) 32%, var(--user-main-bg-end) 100%) !important;
}}
.block-container {{
  max-width: var(--user-main-max-width) !important;
  padding-top: var(--user-main-padding-top) !important;
  padding-bottom: var(--user-main-padding-bottom) !important;
}}
.topbar-card, .glass-card, .card, .kpi, [data-testid="stExpander"] {{
  border-radius: var(--user-card-radius) !important;
  box-shadow: var(--user-card-shadow) !important;
}}
.topbar-card, .glass-card, .card, .kpi {{
  background: var(--user-card-bg) !important;
  border-color: var(--user-card-border) !important;
}}
#oai-sidebar-resizer {{
  position: fixed;
  left: calc(var(--user-sidebar-width) - 7px);
  top: 0;
  bottom: 0;
  width: 18px;
  z-index: 1000000;
  cursor: col-resize;
  background: transparent;
  opacity: 1;
  touch-action: none;
  user-select: none;
  -webkit-user-select: none;
  pointer-events: auto;
}}
#oai-sidebar-resizer::after {{
  content: "";
  position: absolute;
  left: 7px;
  top: 50%;
  transform: translateY(-50%);
  width: 4px;
  height: 96px;
  border-radius: 999px;
  background: var(--user-resizer-knob);
  box-shadow: 0 4px 18px rgba(56, 189, 248, 0.35);
  opacity: 0.95;
}}
#oai-sidebar-resizer:hover::after {{
  width: 6px;
  left: 6px;
  filter: brightness(1.05);
}}
#oai-main-resizer {{
  display: none !important;
  opacity: 0 !important;
  pointer-events: none !important;
  width: 0 !important;
  height: 0 !important;
  overflow: hidden !important;
}}
</style>
""",
        unsafe_allow_html=True,
    )

    components.html(
        f"""
<script>
(function() {{
  const doc = window.parent.document;
  const root = doc.documentElement;
  const storage = window.parent.localStorage || window.localStorage;
  const sidebarKey = 'oai_sidebar_width';
  const mainKey = 'oai_main_max_width';
  const clamp = (n, min, max) => Math.max(min, Math.min(max, n));
  const defaults = {{ sidebar: {int(ui_layout['sidebar_width'])}, main: {int(ui_layout['main_max_width'])} }};

  const applyStored = () => {{
    const sw = parseInt(storage.getItem(sidebarKey) || String(defaults.sidebar), 10);
    const mw = parseInt(storage.getItem(mainKey) || String(defaults.main), 10);
    if (!Number.isNaN(sw)) root.style.setProperty('--user-sidebar-width', clamp(sw, 240, 620) + 'px');
    if (!Number.isNaN(mw)) root.style.setProperty('--user-main-max-width', clamp(mw, 760, 2000) + 'px');
  }};

  const ensureBar = (id, title) => {{
    let el = doc.getElementById(id);
    if (!el) {{
      el = doc.createElement('div');
      el.id = id;
      el.title = title;
      doc.body.appendChild(el);
    }}
    return el;
  }};

  const sidebarBar = ensureBar('oai-sidebar-resizer', '左右ドラッグで管理者画面幅を変更');
  storage.removeItem(mainKey);
  root.style.removeProperty('--user-main-max-width');

  const removeOldMainResizer = () => {{
    const oldMainBar = doc.getElementById('oai-main-resizer');
    if (oldMainBar) oldMainBar.remove();
  }};
  removeOldMainResizer();
  setTimeout(removeOldMainResizer, 50);
  setTimeout(removeOldMainResizer, 250);
  applyStored();

  let drag = false;

  const startSidebarDrag = (e) => {{
    drag = true;
    e.preventDefault();
    e.stopPropagation();
  }};

  const onMove = (e) => {{
    if (!drag) return;
    const clientX = ('touches' in e && e.touches && e.touches.length) ? e.touches[0].clientX : e.clientX;
    const val = clamp(clientX, 240, 620);
    root.style.setProperty('--user-sidebar-width', val + 'px');
    storage.setItem(sidebarKey, String(val));
    e.preventDefault();
  }};

  const stopDrag = () => {{ drag = false; }};

  const resetSidebarWidth = (e) => {{
    e.preventDefault();
    storage.removeItem(sidebarKey);
    root.style.setProperty('--user-sidebar-width', defaults.sidebar + 'px');
  }};

  sidebarBar.onmousedown = startSidebarDrag;
  sidebarBar.ontouchstart = startSidebarDrag;
  sidebarBar.ondblclick = resetSidebarWidth;

  doc.removeEventListener('mousemove', onMove);
  doc.removeEventListener('mouseup', stopDrag);
  doc.removeEventListener('touchmove', onMove);
  doc.removeEventListener('touchend', stopDrag);
  doc.addEventListener('mousemove', onMove, {{ passive: false }});
  doc.addEventListener('mouseup', stopDrag);
  doc.addEventListener('touchmove', onMove, {{ passive: false }});
  doc.addEventListener('touchend', stopDrag);

  setTimeout(applyStored, 50);
}})();
</script>
""",
        height=0,
        width=0,
    )


def render_brand_header(*, st, logo_path: str, company_name: str, contact_link: str = "", demo_mode: bool = True) -> None:
    logo_path_obj = Path(logo_path)
    st.markdown('<div class="topbar-card">', unsafe_allow_html=True)
    col_logo, col_name, col_btn = st.columns([1, 7, 2])
    with col_logo:
        if logo_path and logo_path_obj.exists():
            st.image(str(logo_path_obj), width=54)
        else:
            st.markdown("### 🏢")
    with col_name:
        st.markdown(f'<div class="brand-title">{company_name}</div>', unsafe_allow_html=True)
        st.markdown('<div class="brand-sub">社内問い合わせの自己解決率を高める、情シス向けAIヘルプデスク</div>', unsafe_allow_html=True)
    with col_btn:
        if demo_mode:
            if contact_link:
                st.link_button("📩 導入相談", contact_link, width="stretch")
            else:
                st.button("📩 導入相談（リンク未設定）", disabled=True, width="stretch", key="brand_header_contact_disabled")
        else:
            st.caption("本番モード")
    st.markdown('</div>', unsafe_allow_html=True)


def render_hero_header(*, st, contact_link: str = "", demo_mode: bool = True) -> None:
    safe_contact_link = escape(str(contact_link or ""), quote=True)
    contact_html = ""
    if safe_contact_link:
        target_attrs = "" if safe_contact_link.lower().startswith("mailto:") else ' target="_blank" rel="noopener noreferrer"'
        contact_html = (
            f"<div class='hero-consult'>"
            f"<a href='{safe_contact_link}'{target_attrs}>📩 導入相談はこちら</a>"
            f"<span class='hero-consult-copy'>デモ確認後、すぐ相談へ進めます</span>"
            f"</div>"
        )

    if demo_mode:
        eyebrow = "導入デモ / 情シス問い合わせAI"
        title = "情シス問い合わせを削減するAI"
        lead = "FAQを根拠付きで即回答し、未解決は問い合わせ導線へつなぎ、ナレッジを継続的に蓄積します。営業デモ、管理者運用、効果レポートまで1画面で見せられる営業仕様です。"
        extra_badge = '<span class="badge">📄 提案・操作資料DL</span>'
    else:
        eyebrow = "社内利用 / 情シス問い合わせAI"
        title = "社内IT問い合わせを自己解決するAI"
        lead = "FAQと社内ナレッジをもとに、よくあるIT問い合わせへすばやく回答します。回答できない場合は、必要情報を整理して問い合わせにつなげます。"
        extra_badge = ""
        contact_html = ""

    st.markdown(
        f"""
<div class="hero-shell">
<div class="hero">
<div class="hero-eyebrow">{eyebrow}</div>
<h1>{title}</h1>
<p>{lead}</p>
<div class="cta-row">
<span class="cta">✔ FAQで即回答</span>
<span class="cta">✔ 未解決は問い合わせ誘導</span>
<span class="cta">✔ ログ可視化と効果測定</span>
</div>
<div class="badges">
<span class="badge">✅ FAQ参照（根拠表示）</span>
<span class="badge">⚡ 高速回答</span>
<span class="badge">📝 ログ / 該当なし蓄積</span>
<span class="badge">🔐 管理者でFAQ育成</span>
<span class="badge">📊 KPI・導入効果可視化</span>
{extra_badge}
</div>
{contact_html}
</div>
</div>
""",
        unsafe_allow_html=True,
    )
