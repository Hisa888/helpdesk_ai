from __future__ import annotations

import streamlit.components.v1 as components


def render_client_submit_overlay() -> None:
    """Show a visible waiting overlay immediately when the user submits chat_input.

    Streamlit only sends Python-rendered placeholders after the rerun reaches that line.
    On some browsers this makes the screen look frozen between Enter/send and the first
    server-side delta. This small client-side helper listens to Enter/send on
    st.chat_input and displays a temporary overlay in the parent page immediately.
    """

    components.html(
        r"""
<script>
(function() {
  const OVERLAY_ID = "helpdesk-submit-thinking-overlay";
  const STYLE_ID = "helpdesk-submit-thinking-overlay-style";
  const BOUND_ATTR = "data-helpdesk-submit-overlay-bound";

  function parentDoc() {
    try { return window.parent.document; } catch (e) { return document; }
  }

  function ensureStyle() {
    const doc = parentDoc();
    if (doc.getElementById(STYLE_ID)) return;
    const style = doc.createElement("style");
    style.id = STYLE_ID;
    style.textContent = `
      #${OVERLAY_ID} {
        position: fixed !important;
        inset: 0 !important;
        z-index: 2147483647 !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        background: rgba(255,255,255,.58) !important;
        backdrop-filter: blur(2px) !important;
        -webkit-backdrop-filter: blur(2px) !important;
        pointer-events: all !important;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif !important;
      }
      #${OVERLAY_ID} .helpdesk-submit-card {
        width: min(460px, calc(100vw - 32px)) !important;
        border-radius: 22px !important;
        padding: 20px 22px !important;
        background: linear-gradient(135deg, rgba(10,37,64,.96), rgba(3,169,244,.94)) !important;
        color: #fff !important;
        box-shadow: 0 22px 70px rgba(15,23,42,.28) !important;
        display: flex !important;
        gap: 14px !important;
        align-items: center !important;
      }
      #${OVERLAY_ID} .helpdesk-submit-icon {
        width: 44px !important;
        height: 44px !important;
        border-radius: 999px !important;
        background: rgba(255,255,255,.18) !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        font-size: 24px !important;
        flex: 0 0 auto !important;
        animation: helpdeskSubmitPulse 1.05s ease-in-out infinite !important;
      }
      #${OVERLAY_ID} .helpdesk-submit-title {
        font-size: 17px !important;
        font-weight: 800 !important;
        line-height: 1.35 !important;
        margin: 0 !important;
      }
      #${OVERLAY_ID} .helpdesk-submit-sub {
        margin-top: 4px !important;
        font-size: 13px !important;
        opacity: .92 !important;
        line-height: 1.5 !important;
      }
      #${OVERLAY_ID} .helpdesk-submit-bar {
        margin-top: 10px !important;
        height: 5px !important;
        border-radius: 999px !important;
        overflow: hidden !important;
        background: rgba(255,255,255,.25) !important;
      }
      #${OVERLAY_ID} .helpdesk-submit-bar span {
        display: block !important;
        width: 45% !important;
        height: 100% !important;
        border-radius: 999px !important;
        background: #fff !important;
        animation: helpdeskSubmitBar 1.25s ease-in-out infinite !important;
      }
      @keyframes helpdeskSubmitPulse {
        0%, 100% { transform: scale(1); opacity: .88; }
        50% { transform: scale(1.08); opacity: 1; }
      }
      @keyframes helpdeskSubmitBar {
        0% { transform: translateX(-110%); }
        100% { transform: translateX(245%); }
      }
      @media (max-width: 640px) {
        #${OVERLAY_ID} { align-items: flex-end !important; padding: 0 14px 96px 14px !important; }
        #${OVERLAY_ID} .helpdesk-submit-card { padding: 16px 15px !important; border-radius: 18px !important; gap: 11px !important; }
        #${OVERLAY_ID} .helpdesk-submit-icon { width: 38px !important; height: 38px !important; font-size: 21px !important; }
        #${OVERLAY_ID} .helpdesk-submit-title { font-size: 15px !important; }
        #${OVERLAY_ID} .helpdesk-submit-sub { font-size: 12px !important; }
      }
    `;
    doc.head.appendChild(style);
  }

  function showOverlay() {
    const doc = parentDoc();
    ensureStyle();
    if (doc.getElementById(OVERLAY_ID)) return;
    const overlay = doc.createElement("div");
    overlay.id = OVERLAY_ID;
    overlay.setAttribute("role", "status");
    overlay.setAttribute("aria-live", "polite");
    overlay.innerHTML = `
      <div class="helpdesk-submit-card">
        <div class="helpdesk-submit-icon">🤖</div>
        <div style="min-width:0;flex:1;">
          <div class="helpdesk-submit-title">AIが回答を作成しています</div>
          <div class="helpdesk-submit-sub">FAQ・社内マニュアルを検索中です。少しお待ちください。</div>
          <div class="helpdesk-submit-bar"><span></span></div>
        </div>
      </div>`;
    doc.body.appendChild(overlay);
    setTimeout(function() {
      const current = doc.getElementById(OVERLAY_ID);
      if (current) current.remove();
    }, 45000);
  }

  function findTextarea() {
    const doc = parentDoc();
    return doc.querySelector('textarea[data-testid="stChatInputTextArea"], div[data-testid="stChatInput"] textarea, textarea[aria-label]');
  }

  function chatInputHasText() {
    const textarea = findTextarea();
    return !!(textarea && String(textarea.value || "").trim());
  }

  function bind() {
    const doc = parentDoc();
    if (doc.documentElement.getAttribute(BOUND_ATTR) === "1") return;
    doc.documentElement.setAttribute(BOUND_ATTR, "1");

    doc.addEventListener("keydown", function(ev) {
      const target = ev.target;
      const isTextarea = target && target.tagName && target.tagName.toLowerCase() === "textarea";
      if (!isTextarea) return;
      const insideChat = target.closest && target.closest('div[data-testid="stChatInput"]');
      if (!insideChat) return;
      if (ev.key === "Enter" && !ev.shiftKey && String(target.value || "").trim()) {
        showOverlay();
      }
    }, true);

    doc.addEventListener("click", function(ev) {
      const target = ev.target;
      if (!target || !target.closest) return;
      const chat = target.closest('div[data-testid="stChatInput"]');
      if (!chat) return;
      const btn = target.closest('button');
      if (btn && chatInputHasText()) showOverlay();
    }, true);

    doc.addEventListener("submit", function(ev) {
      const target = ev.target;
      if (target && target.querySelector && target.querySelector('div[data-testid="stChatInput"], textarea[data-testid="stChatInputTextArea"]')) {
        if (chatInputHasText()) showOverlay();
      }
    }, true);
  }

  bind();
})();
</script>
        """,
        height=0,
        width=0,
    )
