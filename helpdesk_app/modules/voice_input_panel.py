from __future__ import annotations

import streamlit.components.v1 as components


def render_voice_input_widget(st, *, auto_submit: bool = False) -> None:
    """Render a browser speech-to-text helper inside the existing st.chat_input.

    既存のFAQ検索・回答ロジックには触らず、Chrome/Edge の Web Speech API で
    認識したテキストを Streamlit の chat_input へ入れるための補助UIです。

    2026-05-02 修正:
    Google検索/ChatGPTのように、音声入力ボタンを画面下部のテキストボックス内へ
    差し込む方式に変更。入力欄の上に余計なボタンを表示しません。
    """

    # 画面上部に音声ボタンを出さず、st.chat_input が描画されたあとに
    # JavaScriptで入力欄の中へマイクボタンを差し込みます。
    html = f"""
<style>
  #helpdesk-voice-toast {{
    position: fixed;
    right: 88px;
    bottom: 92px;
    z-index: 2147483647;
    max-width: 420px;
    padding: 9px 13px;
    border-radius: 999px;
    background: rgba(17, 24, 39, .92);
    color: #fff;
    font-size: 13px;
    line-height: 1.4;
    box-shadow: 0 10px 30px rgba(0,0,0,.18);
    opacity: 0;
    transform: translateY(8px);
    pointer-events: none;
    transition: opacity .18s ease, transform .18s ease;
    font-family: sans-serif;
  }}
  #helpdesk-voice-toast.show {{
    opacity: 1;
    transform: translateY(0);
  }}
  @media (max-width: 640px) {{
    #helpdesk-voice-toast {{
      left: 16px;
      right: 16px;
      bottom: 92px;
      max-width: none;
      border-radius: 16px;
    }}
  }}
</style>
<script>
(function() {{
  const AUTO_SUBMIT = {str(bool(auto_submit)).lower()};
  const BUTTON_ID = "helpdesk-voice-chat-button";
  const TOAST_ID = "helpdesk-voice-toast";
  const STYLE_ID = "helpdesk-voice-parent-style";

  function parentDoc() {{
    try {{ return window.parent.document; }} catch (e) {{ return document; }}
  }}

  function parentWin() {{
    try {{ return window.parent; }} catch (e) {{ return window; }}
  }}

  function ensureParentStyle() {{
    const doc = parentDoc();
    if (doc.getElementById(STYLE_ID)) return;
    const style = doc.createElement("style");
    style.id = STYLE_ID;
    style.textContent = `
      #${{BUTTON_ID}} {{
        position: absolute !important;
        right: 54px !important;
        top: 50% !important;
        transform: translateY(-50%) !important;
        width: 36px !important;
        height: 36px !important;
        border-radius: 999px !important;
        border: none !important;
        display: inline-flex !important;
        align-items: center !important;
        justify-content: center !important;
        background: transparent !important;
        color: #2563eb !important;
        font-size: 20px !important;
        line-height: 1 !important;
        cursor: pointer !important;
        z-index: 2147483647 !important;
        box-shadow: none !important;
        padding: 0 !important;
        user-select: none !important;
      }}
      #${{BUTTON_ID}}:hover {{
        background: rgba(37, 99, 235, .10) !important;
      }}
      #${{BUTTON_ID}}.recording {{
        color: #dc2626 !important;
        background: rgba(220, 38, 38, .10) !important;
        animation: helpdeskVoicePulseInInput 1s infinite !important;
      }}
      #${{BUTTON_ID}}:disabled {{
        color: #9ca3af !important;
        cursor: not-allowed !important;
        background: transparent !important;
      }}
      @keyframes helpdeskVoicePulseInInput {{
        0% {{ box-shadow: 0 0 0 0 rgba(220,38,38,.35); }}
        70% {{ box-shadow: 0 0 0 10px rgba(220,38,38,0); }}
        100% {{ box-shadow: 0 0 0 0 rgba(220,38,38,0); }}
      }}
      div[data-testid="stChatInput"] textarea,
      textarea[data-testid="stChatInputTextArea"] {{
        padding-right: 96px !important;
      }}
    `;
    doc.head.appendChild(style);
  }}

  function ensureToast() {{
    const doc = parentDoc();
    let toast = doc.getElementById(TOAST_ID);
    if (!toast) {{
      toast = doc.createElement("div");
      toast.id = TOAST_ID;
      doc.body.appendChild(toast);
    }}
    return toast;
  }}

  let toastTimer = null;
  function setStatus(message, keep) {{
    const toast = ensureToast();
    toast.textContent = message || "";
    toast.classList.add("show");
    if (toastTimer) clearTimeout(toastTimer);
    if (!keep) {{
      toastTimer = setTimeout(function() {{ toast.classList.remove("show"); }}, 2800);
    }}
  }}

  function isSupported() {{
    const win = parentWin();
    return !!(win.SpeechRecognition || win.webkitSpeechRecognition || window.SpeechRecognition || window.webkitSpeechRecognition);
  }}

  function speechCtor() {{
    const win = parentWin();
    return win.SpeechRecognition || win.webkitSpeechRecognition || window.SpeechRecognition || window.webkitSpeechRecognition;
  }}

  function findChatTextarea() {{
    const doc = parentDoc();
    const candidates = [
      'textarea[data-testid="stChatInputTextArea"]',
      'div[data-testid="stChatInput"] textarea',
      'textarea[aria-label]',
      'textarea'
    ];
    for (const selector of candidates) {{
      const el = doc.querySelector(selector);
      if (el) return el;
    }}
    return null;
  }}

  function findChatContainer(textarea) {{
    if (!textarea) return null;
    return textarea.closest('div[data-testid="stChatInput"]') || textarea.parentElement;
  }}

  function findSubmitButton() {{
    const doc = parentDoc();
    const candidates = [
      'button[data-testid="stChatInputSubmitButton"]',
      'div[data-testid="stChatInput"] button',
      'button[aria-label="Send"]',
      'button[aria-label="送信"]'
    ];
    for (const selector of candidates) {{
      const el = doc.querySelector(selector);
      if (el && el.id !== BUTTON_ID) return el;
    }}
    return null;
  }}

  function setChatInputValue(text) {{
    const textarea = findChatTextarea();
    if (!textarea) {{
      setStatus("入力欄が見つかりません。画面下部の入力欄を表示してから再度押してください。");
      return false;
    }}
    textarea.focus();
    const current = (textarea.value || "").trim();
    const next = current ? (current + " " + text) : text;
    const setter = Object.getOwnPropertyDescriptor(parentWin().HTMLTextAreaElement.prototype, "value").set;
    setter.call(textarea, next);
    textarea.dispatchEvent(new Event("input", {{ bubbles: true }}));
    textarea.dispatchEvent(new Event("change", {{ bubbles: true }}));

    if (AUTO_SUBMIT) {{
      setTimeout(function() {{
        const sendButton = findSubmitButton();
        if (sendButton && !sendButton.disabled) sendButton.click();
      }}, 250);
    }}
    return true;
  }}

  let recognition = null;
  let listening = false;

  function stop(button) {{
    try {{ if (recognition) recognition.stop(); }} catch(e) {{}}
    listening = false;
    if (button) button.classList.remove("recording");
  }}

  function startRecognition(button) {{
    if (!isSupported()) {{
      setStatus("音声入力は Chrome / Edge 推奨です。非対応ブラウザでは通常入力をご利用ください。");
      return;
    }}

    if (listening) {{
      stop(button);
      setStatus("音声入力を停止しました。");
      return;
    }}

    const SpeechRecognition = speechCtor();
    recognition = new SpeechRecognition();
    recognition.lang = "ja-JP";
    recognition.interimResults = false;
    recognition.continuous = false;
    recognition.maxAlternatives = 1;

    recognition.onstart = function() {{
      listening = true;
      button.classList.add("recording");
      setStatus("聞き取り中です。問い合わせ内容を話してください…", true);
    }};

    recognition.onresult = function(event) {{
      const text = event.results && event.results[0] && event.results[0][0]
        ? event.results[0][0].transcript
        : "";
      if (text.trim()) {{
        const ok = setChatInputValue(text.trim());
        if (ok) setStatus("入力しました：" + text.trim());
      }} else {{
        setStatus("音声を認識できませんでした。もう一度お試しください。");
      }}
    }};

    recognition.onerror = function(event) {{
      const err = event && event.error ? event.error : "unknown";
      if (err === "not-allowed") {{
        setStatus("マイク利用が許可されていません。ブラウザの権限設定を確認してください。");
      }} else {{
        setStatus("音声入力エラー：" + err);
      }}
    }};

    recognition.onend = function() {{
      listening = false;
      button.classList.remove("recording");
    }};

    try {{
      recognition.start();
    }} catch(e) {{
      setStatus("音声入力を開始できませんでした。もう一度お試しください。");
      stop(button);
    }}
  }}

  function installButton() {{
    ensureParentStyle();
    const doc = parentDoc();
    const textarea = findChatTextarea();
    const container = findChatContainer(textarea);
    if (!textarea || !container) return false;

    container.style.position = "relative";

    let button = doc.getElementById(BUTTON_ID);
    if (!button) {{
      button = doc.createElement("button");
      button.id = BUTTON_ID;
      button.type = "button";
      button.title = "音声入力（Chrome / Edge 推奨）";
      button.setAttribute("aria-label", "音声入力");
      button.textContent = "🎤";
      button.addEventListener("click", function(e) {{
        e.preventDefault();
        e.stopPropagation();
        startRecognition(button);
      }});
    }}

    if (button.parentElement !== container) {{
      container.appendChild(button);
    }}
    return true;
  }}

  let count = 0;
  const timer = setInterval(function() {{
    count += 1;
    const ok = installButton();
    if (ok || count > 40) clearInterval(timer);
  }}, 250);

  // Streamlitの再描画で入力欄が差し替わることがあるため、少し間隔を空けて再確認します。
  setInterval(installButton, 2000);
}})();
</script>
"""
    components.html(html, height=0, width=0)
