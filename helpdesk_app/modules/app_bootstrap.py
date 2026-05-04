from __future__ import annotations

from html import escape
from pathlib import Path


def initialize_app_shell(*, st, components, current_ui_theme_settings, current_ui_layout_settings):
    st.set_page_config(page_title="情シス問い合わせAI", layout="wide", initial_sidebar_state="expanded")
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
/* サイドバー幅は「開いている時だけ」上書きします。
   閉じている時まで width を固定すると、Streamlit標準の >> ボタン位置や再表示処理と競合します。 */
[data-testid="stSidebar"]:not([aria-expanded="false"]) {{
  min-width: var(--user-sidebar-width) !important;
  max-width: var(--user-sidebar-width) !important;
  width: var(--user-sidebar-width) !important;
  background: linear-gradient(180deg, var(--user-sidebar-bg-start) 0%, var(--user-sidebar-bg-end) 100%) !important;
}}
[data-testid="stSidebar"][aria-expanded="false"] {{
  min-width: 0 !important;
  max-width: 0 !important;
  width: 0 !important;
  overflow: hidden !important;
}}
/* Streamlit標準のサイドバー再表示ボタン。独自ボタンは使わず、標準ボタンだけを左上に寄せます。 */
[data-testid="collapsedControl"] {{
  position: fixed !important;
  left: 16px !important;
  top: 16px !important;
  z-index: 1000001 !important;
  transform: none !important;
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
/* 左メニューと中央画面の境界ドラッグバー。
   重要：独自の「>>」ボタンは作らず、開閉は Streamlit 標準ボタンに任せます。
   ドラッグバーは stSidebar の子要素に置くため、左メニューを閉じると一緒に消えます。 */
[data-testid="stSidebar"]:not([aria-expanded="false"]) {{
  position: relative !important;
  overflow: visible !important;
}}
#oai-sidebar-resizer {{
  position: absolute !important;
  right: -9px !important;
  top: 0 !important;
  bottom: 0 !important;
  width: 18px !important;
  z-index: 1000000 !important;
  cursor: col-resize !important;
  background: transparent !important;
  opacity: 1 !important;
  touch-action: none !important;
  user-select: none !important;
  -webkit-user-select: none !important;
  pointer-events: auto !important;
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
[data-testid="stSidebar"][aria-expanded="false"] #oai-sidebar-resizer,
#oai-main-resizer,
#oai-sidebar-reopen-button,
.oai-sidebar-reopen-button,
.oai-native-sidebar-open-fake {{
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
        """
<script>
(function() {
  const win = window.parent || window;
  const doc = win.document;
  const root = doc.documentElement;
  const storage = win.localStorage || window.localStorage;
  const sidebarKey = 'oai_sidebar_width';
  const defaultSidebar = __DEFAULT_SIDEBAR_WIDTH__;
  const clamp = (n, min, max) => Math.max(min, Math.min(max, n));

  // 過去版の監視処理を停止。今回は setInterval / MutationObserver は使いません。
  try {
    if (win.__oaiSidebarCollapseObserver) {
      win.__oaiSidebarCollapseObserver.disconnect();
      win.__oaiSidebarCollapseObserver = null;
    }
  } catch (e) {}
  try {
    if (win.__oaiSidebarCollapseSyncTimer) {
      win.clearInterval(win.__oaiSidebarCollapseSyncTimer);
      win.__oaiSidebarCollapseSyncTimer = null;
    }
  } catch (e) {}

  // 前回実行分のドラッグイベントだけを解除。
  try {
    if (typeof win.__oaiSidebarResizeCleanup === 'function') {
      win.__oaiSidebarResizeCleanup();
    }
  } catch (e) {}

  // 初期表示は必ず左メニューを開く。
  // Streamlitはブラウザ側にサイドバーの開閉状態が残ることがあるため、
  // set_page_config(initial_sidebar_state='expanded') に加えて、初回ロード時だけ標準の「>>」を一度押します。
  // 連続監視は使わず、数回だけ再試行するので応答停止の原因になりません。
  const ensureInitialSidebarExpanded = () => {
    if (win.__oaiInitialSidebarExpandedApplied || win.__oaiInitialSidebarExpandedScheduled) return;
    win.__oaiInitialSidebarExpandedScheduled = true;

    let tries = 0;
    const run = () => {
      tries += 1;
      const sidebar = doc.querySelector('[data-testid="stSidebar"]');
      const collapsedControl = doc.querySelector('[data-testid="collapsedControl"] button, [data-testid="collapsedControl"]');
      const isCollapsed = !!sidebar && sidebar.getAttribute('aria-expanded') === 'false';

      if (isCollapsed && collapsedControl) {
        collapsedControl.click();
        win.__oaiInitialSidebarExpandedApplied = true;
        return;
      }

      if (tries < 5 && !win.__oaiInitialSidebarExpandedApplied) {
        win.setTimeout(run, tries === 1 ? 120 : 260);
      } else {
        win.__oaiInitialSidebarExpandedApplied = true;
      }
    };

    win.setTimeout(run, 80);
  };

  ensureInitialSidebarExpanded();

  // 旧独自「>>」ボタンと旧メイン幅リサイズバーは使用しない。
  try {
    ['oai-main-resizer', 'oai-sidebar-reopen-button'].forEach((id) => {
      const el = doc.getElementById(id);
      if (el) el.remove();
    });
  } catch (e) {}

  // 旧バージョンで標準の >> ボタンに付けた強制スタイルを戻します。
  try {
    doc.querySelectorAll('.oai-native-sidebar-open').forEach((el) => {
      el.classList.remove('oai-native-sidebar-open');
      ['left','top','position','z-index','transform','display','opacity','pointer-events'].forEach((prop) => {
        el.style.removeProperty(prop);
      });
    });
  } catch (e) {}

  const applyStoredSidebarWidth = () => {
    let stored = null;
    try { stored = parseInt(storage.getItem(sidebarKey) || '', 10); } catch (e) {}
    const val = Number.isFinite(stored) ? clamp(stored, 240, 620) : defaultSidebar;
    root.style.setProperty('--user-sidebar-width', val + 'px');
  };

  const attachResizer = () => {
    const sidebar = doc.querySelector('[data-testid="stSidebar"]');
    if (!sidebar) return null;

    let bar = doc.getElementById('oai-sidebar-resizer');
    if (!bar) {
      bar = doc.createElement('div');
      bar.id = 'oai-sidebar-resizer';
      bar.title = '左右ドラッグで左メニュー幅を変更 / ダブルクリックで初期幅に戻す';
    }
    // body ではなく sidebar の子要素にすることで、閉じた時に残らないようにする。
    if (bar.parentElement !== sidebar) sidebar.appendChild(bar);
    return bar;
  };

  applyStoredSidebarWidth();
  let bar = null;

  let dragging = false;

  const startDrag = (e) => {
    dragging = true;
    doc.body.style.cursor = 'col-resize';
    doc.body.style.userSelect = 'none';
    e.preventDefault();
    e.stopPropagation();
  };

  const onMove = (e) => {
    if (!dragging) return;
    const clientX = (e.touches && e.touches.length) ? e.touches[0].clientX : e.clientX;
    const val = clamp(clientX, 240, 620);
    root.style.setProperty('--user-sidebar-width', val + 'px');
    try { storage.setItem(sidebarKey, String(val)); } catch (err) {}
    e.preventDefault();
  };

  const stopDrag = () => {
    if (!dragging) return;
    dragging = false;
    doc.body.style.cursor = '';
    doc.body.style.userSelect = '';
  };

  const resetWidth = (e) => {
    e.preventDefault();
    try { storage.removeItem(sidebarKey); } catch (err) {}
    root.style.setProperty('--user-sidebar-width', defaultSidebar + 'px');
  };

  const bindResizer = () => {
    const activeBar = attachResizer();
    if (activeBar) {
      activeBar.onmousedown = startDrag;
      activeBar.ontouchstart = startDrag;
      activeBar.ondblclick = resetWidth;
    }
    return activeBar;
  };

  bar = bindResizer();
  setTimeout(bindResizer, 120);
  setTimeout(bindResizer, 500);

  doc.addEventListener('mousemove', onMove, { passive: false });
  doc.addEventListener('mouseup', stopDrag);
  doc.addEventListener('mouseleave', stopDrag);
  doc.addEventListener('touchmove', onMove, { passive: false });
  doc.addEventListener('touchend', stopDrag);

  win.__oaiSidebarResizeCleanup = function() {
    try { doc.removeEventListener('mousemove', onMove); } catch (e) {}
    try { doc.removeEventListener('mouseup', stopDrag); } catch (e) {}
    try { doc.removeEventListener('mouseleave', stopDrag); } catch (e) {}
    try { doc.removeEventListener('touchmove', onMove); } catch (e) {}
    try { doc.removeEventListener('touchend', stopDrag); } catch (e) {}
    try {
      const b = doc.getElementById('oai-sidebar-resizer');
      if (b) {
        b.onmousedown = null;
        b.ontouchstart = null;
        b.ondblclick = null;
      }
    } catch (e) {}
  };

  try {
    root.removeAttribute('data-oai-sidebar-collapsed');
    root.style.removeProperty('--user-main-max-width');
    storage.removeItem('oai_main_max_width');
  } catch (e) {}
})();
</script>
""".replace("__DEFAULT_SIDEBAR_WIDTH__", str(int(ui_layout["sidebar_width"]))),
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
