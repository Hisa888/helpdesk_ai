from __future__ import annotations

from html import escape
from urllib.parse import quote


def _safe_link(contact_link: str) -> str:
    return (contact_link or "").strip()


def _html_attr(value: str) -> str:
    return escape(str(value or ""), quote=True)


def _build_fallback_mailto() -> str:
    mail_subject = quote("情シス問い合わせAI 導入相談")
    mail_body = quote(
        "以下の内容で導入相談を希望します。\n\n"
        "会社名：\n"
        "担当者名：\n"
        "従業員数：\n"
        "現在の課題：\n"
        "希望する相談内容：\n"
    )
    return f"mailto:?subject={mail_subject}&body={mail_body}"


def _target_attrs(link: str) -> str:
    """外部URLは別タブ、mailtoは通常遷移にする。"""
    if str(link).lower().startswith("mailto:"):
        return ""
    return ' target="_blank" rel="noopener noreferrer"'


def render_fixed_contact_button(*, st, contact_link: str) -> None:
    """スクロールしても消えない右上固定の導入相談ボタンを表示する。"""
    link = _safe_link(contact_link)
    if link:
        safe_link = _html_attr(link)
        attrs = _target_attrs(link)
        button_html = (
            f'<a class="fixed-contact-button" href="{safe_link}"{attrs}>'
            '<span class="fixed-contact-button-icon">📩</span>'
            '<span class="fixed-contact-button-text">導入相談</span>'
            '</a>'
        )
    else:
        button_html = (
            '<span class="fixed-contact-button fixed-contact-button-disabled" '
            'title="CONTACT_URL または CONTACT_EMAIL を設定してください">'
            '<span class="fixed-contact-button-icon">📩</span>'
            '<span class="fixed-contact-button-text">導入相談</span>'
            '</span>'
        )

    st.markdown(button_html, unsafe_allow_html=True)


def render_answer_contact_cta(
    *,
    st,
    contact_link: str | None = None,
    was_nohit: bool = False,
    was_suggest: bool = False,
    used_doc_rag: bool = False,
    was_clarification: bool = False,
) -> None:
    """回答直後・該当なし時に自然な導入相談導線を表示する。"""
    if was_clarification:
        return

    link = _safe_link(contact_link or st.session_state.get("contact_link", ""))
    if not link:
        return

    safe_link = _html_attr(link)
    attrs = _target_attrs(link)

    if was_nohit:
        title = "解決しない内容は、導入・運用相談にもつなげられます"
        body = "FAQにない質問はログに残ります。社内でどのように問い合わせを減らすか、運用設計まで相談できます。"
        badge = "該当なし時の相談導線"
    elif was_suggest:
        title = "回答が近いだけの場合は、運用相談で精度改善できます"
        body = "FAQの整備方法、しきい値調整、マニュアルからのFAQ化まで相談できます。"
        badge = "精度改善の相談"
    elif used_doc_rag:
        title = "社内マニュアル活用の導入相談もできます"
        body = "マニュアルRAGやFAQ自動生成を、実運用に合わせてどう使うか相談できます。"
        badge = "RAG運用の相談"
    else:
        title = "この回答品質で使えるか、導入相談できます"
        body = "デモ確認後、そのままヒアリング・見積・社内展開方法の相談へ進められます。"
        badge = "回答後の相談導線"

    st.markdown(
        f"""
<div class="answer-contact-cta {'answer-contact-cta-nohit' if was_nohit else ''}">
  <div class="answer-contact-cta-body">
    <div class="answer-contact-cta-badge">{escape(badge)}</div>
    <div class="answer-contact-cta-title">{escape(title)}</div>
    <div class="answer-contact-cta-text">{escape(body)}</div>
  </div>
  <a class="answer-contact-cta-button" href="{safe_link}"{attrs}>📩 導入相談する</a>
</div>
""",
        unsafe_allow_html=True,
    )


def render_contact_cta_panel(*, st, contact_link: str, company_name: str = "") -> None:
    """導入相談につなげるCTAパネルを表示する。

    StreamlitDuplicateElementIdを避けるため、ボタン部分はst.buttonではなく
    HTMLリンク/疑似ボタンとして描画する。同じ画面で複数回呼ばれても安全。
    """
    link = _safe_link(contact_link)
    fallback_mailto = _build_fallback_mailto()

    if link:
        safe_link = _html_attr(link)
        attrs = _target_attrs(link)
        contact_button_html = (
            f'<a class="contact-cta-button primary" href="{safe_link}"{attrs}>📩 導入相談（無料）</a>'
        )
    else:
        contact_button_html = '<span class="contact-cta-button disabled">📩 導入相談（リンク未設定）</span>'

    mail_button_html = (
        f'<a class="contact-cta-button secondary" href="{_html_attr(fallback_mailto)}">✉️ メール文面を作成</a>'
    )

    st.markdown(
        f"""
<div class="glass-card contact-cta-card">
  <div class="contact-cta-grid">
    <div>
      <div class="eyebrow">導入導線 / Contact</div>
      <h3>デモ確認後、そのまま導入相談へつなげられます</h3>
      <p>
        FAQ検索、社内マニュアルRAG、マニュアル→FAQ自動生成、効果レポートまで確認した後、
        すぐにヒアリング・見積相談へ進めるための導線です。
      </p>
      <div class="contact-cta-points">
        <span>✅ 無料相談</span>
        <span>✅ 現状ヒアリング</span>
        <span>✅ デモ依頼</span>
        <span>✅ 導入可否の確認</span>
      </div>
      <div class="contact-cta-actions">
        {contact_button_html}
        {mail_button_html}
      </div>
      <div class="contact-cta-note">CONTACT_URL または CONTACT_EMAIL を設定すると、相談ボタンが有効になります。</div>
    </div>
    <div class="contact-cta-side">
      <div class="contact-cta-mini-title">相談で確認すること</div>
      <ul>
        <li>問い合わせ件数・削減したい対応時間</li>
        <li>FAQ / マニュアル / Excel台帳の有無</li>
        <li>社内公開方法・セキュリティ要件</li>
        <li>初期導入と月額運用の範囲</li>
      </ul>
    </div>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )


def render_contact_cta_css(*, st) -> None:
    st.markdown(
        """
<style>
.fixed-contact-button {
  position: fixed;
  top: 86px;
  right: 76px;
  z-index: 1000001;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  min-height: 42px;
  padding: 10px 18px;
  border-radius: 999px;
  background: linear-gradient(135deg, #0ea5e9, #22c55e);
  color: #ffffff !important;
  text-decoration: none !important;
  font-size: 14px;
  font-weight: 900;
  letter-spacing: .01em;
  border: 1px solid rgba(255, 255, 255, 0.42);
  box-shadow: 0 12px 28px rgba(14, 165, 233, 0.28), 0 2px 8px rgba(15, 23, 42, 0.12);
  backdrop-filter: blur(8px);
  transition: transform .12s ease, box-shadow .12s ease, filter .12s ease;
}
.fixed-contact-button:hover {
  transform: translateY(-1px);
  filter: brightness(1.04);
  box-shadow: 0 16px 34px rgba(14, 165, 233, 0.34), 0 4px 12px rgba(15, 23, 42, 0.16);
}
.fixed-contact-button-disabled {
  background: #e5e7eb;
  color: #64748b !important;
  cursor: not-allowed;
}
.fixed-contact-button-icon {font-size: 15px; line-height: 1;}
.fixed-contact-button-text {line-height: 1; white-space: nowrap;}

.answer-contact-cta {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 12px;
  align-items: center;
  margin-top: 12px;
  padding: 13px 14px;
  border: 1px solid rgba(14, 165, 233, 0.22);
  border-radius: 16px;
  background: linear-gradient(135deg, rgba(240, 249, 255, 0.94), rgba(255, 255, 255, 0.96));
  box-shadow: 0 8px 22px rgba(15, 23, 42, 0.06);
}
.answer-contact-cta-nohit {
  border-color: rgba(245, 158, 11, 0.32);
  background: linear-gradient(135deg, rgba(255, 251, 235, 0.96), rgba(255, 255, 255, 0.96));
}
.answer-contact-cta-badge {
  display: inline-block;
  margin-bottom: 4px;
  padding: 3px 8px;
  border-radius: 999px;
  background: rgba(14, 165, 233, 0.10);
  color: #0369a1;
  font-size: 11px;
  font-weight: 900;
}
.answer-contact-cta-title {
  color: var(--text-main);
  font-size: 14px;
  font-weight: 900;
  line-height: 1.45;
}
.answer-contact-cta-text {
  color: var(--text-sub);
  font-size: 12px;
  line-height: 1.55;
  margin-top: 2px;
}
.answer-contact-cta-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 36px;
  padding: 8px 13px;
  border-radius: 999px;
  background: #0f172a;
  color: #ffffff !important;
  text-decoration: none !important;
  font-size: 13px;
  font-weight: 900;
  white-space: nowrap;
  box-shadow: 0 8px 18px rgba(15, 23, 42, 0.14);
}
.answer-contact-cta-button:hover {filter: brightness(1.08);}

.contact-cta-card {
  margin: 12px 0 18px 0;
  border: 1px solid rgba(14, 165, 233, 0.22) !important;
  background: linear-gradient(135deg, rgba(255,255,255,0.94), rgba(240,249,255,0.92)) !important;
}
.contact-cta-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.6fr) minmax(240px, .9fr);
  gap: 18px;
  align-items: start;
}
.contact-cta-card h3 {
  margin: 4px 0 8px 0;
  color: var(--text-main);
  font-size: 20px;
}
.contact-cta-card p {
  margin: 0;
  color: var(--text-sub);
  line-height: 1.65;
  font-size: 14px;
}
.contact-cta-points {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}
.contact-cta-points span {
  display: inline-block;
  padding: 7px 10px;
  border-radius: 999px;
  background: #e0f2fe;
  color: #075985;
  font-size: 12px;
  font-weight: 700;
}
.contact-cta-side {
  background: rgba(15, 23, 42, 0.04);
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 16px;
  padding: 14px 16px;
}
.contact-cta-mini-title {
  font-size: 13px;
  font-weight: 800;
  color: var(--text-main);
  margin-bottom: 6px;
}
.contact-cta-side ul {
  margin: 0;
  padding-left: 18px;
  color: var(--text-sub);
  font-size: 13px;
  line-height: 1.7;
}

.contact-cta-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 14px;
}
.contact-cta-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 38px;
  padding: 8px 14px;
  border-radius: 12px;
  font-size: 14px;
  font-weight: 800;
  text-decoration: none !important;
  border: 1px solid rgba(14, 165, 233, 0.25);
}
.contact-cta-button.primary {
  background: linear-gradient(135deg, #0ea5e9, #22c55e);
  color: #ffffff !important;
  box-shadow: 0 10px 24px rgba(14, 165, 233, 0.18);
}
.contact-cta-button.secondary {
  background: #ffffff;
  color: #075985 !important;
}
.contact-cta-button.disabled {
  background: #e5e7eb;
  color: #64748b !important;
  cursor: not-allowed;
}
.contact-cta-note {
  margin-top: 8px;
  font-size: 12px;
  color: #64748b;
}

@media (max-width: 760px) {
  .fixed-contact-button {
    top: 72px;
    right: 12px;
    min-height: 38px;
    padding: 9px 13px;
    font-size: 13px;
  }
  .answer-contact-cta {grid-template-columns: 1fr;}
  .answer-contact-cta-button {width: 100%;}
  .contact-cta-grid { grid-template-columns: 1fr; }
}
</style>
""",
        unsafe_allow_html=True,
    )
