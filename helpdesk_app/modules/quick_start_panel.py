from __future__ import annotations

from typing import Sequence, Tuple

DEFAULT_QUICK_STARTS: Sequence[Tuple[str, str, str]] = (
    ("🔐 パスワードを忘れた", "パスワードを忘れました", "quick_start_password"),
    ("🧩 アカウントがロックされた", "アカウントがロックされました", "quick_start_lock"),
    ("🌐 VPNに接続できない", "VPNに接続できません", "quick_start_vpn"),
)


def ensure_quick_start_session_state(st) -> None:
    if "pending_q" not in st.session_state:
        st.session_state.pending_q = ""


def _render_buttons(st, *, quick_starts: Sequence[Tuple[str, str, str]], key_suffix: str) -> None:
    cols = st.columns(len(quick_starts))
    for col, (label, query, key) in zip(cols, quick_starts):
        if col.button(label, key=f"{key}_{key_suffix}", width="stretch"):
            st.session_state.pending_q = query
            st.session_state["scroll_to_answer"] = True
            st.rerun()


def render_quick_start_hero(st, *, quick_starts: Sequence[Tuple[str, str, str]] = DEFAULT_QUICK_STARTS) -> None:
    st.markdown(
        """
<div class="hero-shell">
  <div class="hero hero-grid">
    <div>
      <div class="hero-eyebrow">IT Helpdesk AI / Sales Ready UI</div>
      <h1>情シス問い合わせAI</h1>
      <p>社内のIT問い合わせを自己解決につなげ、情シス担当の対応負荷を軽くする一次受付AIです。FAQ資産を活かしながら、回答の標準化・対応スピード向上・ログ蓄積までまとめて実現できます。</p>
      <div class="badges">
        <span class="badge">FAQを活かして早く回答</span>
        <span class="badge">該当なし時は問い合わせ誘導</span>
        <span class="badge">ログで継続改善</span>
        <span class="badge">営業デモ向けUI</span>
      </div>
      <div class="cta-row">
        <span class="cta">⏱ 問い合わせ対応の時間削減</span>
        <span class="cta">📘 FAQ運用を見える化</span>
        <span class="cta">🧾 対応品質のばらつき抑制</span>
      </div>
    </div>
    <div class="hero-consult-card">
      <h4>導入イメージ</h4>
      <p>単なるチャットではなく、<b>一次受付・自己解決促進・問い合わせ標準化</b> をまとめて見せられる構成です。</p>
      <ul>
        <li>よくある問い合わせはその場で自己解決</li>
        <li>FAQにない場合は必要情報つきで問い合わせ誘導</li>
        <li>利用ログをもとにFAQを継続改善</li>
      </ul>
      <div class="hero-consult">
        <a href="#query-start">まずはデモを試す</a>
      </div>
    </div>
  </div>
</div>
<div class="section-title">💎 導入価値が伝わるポイント</div>
<div class="section-caption">企業向け提案で刺さりやすい価値を、最初の画面で伝えます。</div>
<div class="sales-grid">
  <div class="sales-card">
    <div class="sales-icon">⚡</div>
    <div class="title">一次対応を高速化</div>
    <p>パスワード忘れやVPN接続不良など、繰り返し発生する問い合わせをすばやく自己解決に導きます。</p>
  </div>
  <div class="sales-card">
    <div class="sales-icon">🧭</div>
    <div class="title">対応の標準化</div>
    <p>FAQを根拠に回答するため、担当者ごとの回答ばらつきを減らし、説明品質を揃えやすくなります。</p>
  </div>
  <div class="sales-card">
    <div class="sales-icon">📈</div>
    <div class="title">導入後も改善できる</div>
    <p>該当なしログや質問傾向が残るので、FAQ強化や運用改善の優先順位を決めやすくなります。</p>
  </div>
</div>
<div class="section-title">🛣 利用の流れ</div>
<div class="journey-grid">
  <div class="journey-card">
    <div class="journey-icon">1</div>
    <div class="title">質問する</div>
    <p>社員が自然な言葉で問い合わせを入力します。専門用語でなくても近いFAQを探します。</p>
  </div>
  <div class="journey-card">
    <div class="journey-icon">2</div>
    <div class="title">AIがFAQから回答</div>
    <p>一致度や参考FAQを見せながら回答するため、根拠が分かりやすく、デモでも説明しやすい構成です。</p>
  </div>
  <div class="journey-card">
    <div class="journey-icon">3</div>
    <div class="title">未解決なら問い合わせ誘導</div>
    <p>解決できない場合も、そのまま必要情報を整理して情シスへ渡せるので対応漏れを防ぎやすくなります。</p>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )
    st.markdown('<div id="query-start"></div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="glass-card query-panel"><div class="eyebrow">Quick Start</div><h3>すぐ試せる代表質問</h3><p>営業デモで見せやすい定番の質問です。クリックすると、そのまま送信されます。</p></div>',
        unsafe_allow_html=True,
    )
    _render_buttons(st, quick_starts=quick_starts, key_suffix="hero")
    st.markdown(
        """
<div class="cta-banner">
  <h3>そのまま提案につなげやすいUIにしています</h3>
  <p>「よくある問い合わせへの即答」「FAQにない時の問い合わせ誘導」「ログによる改善」の3点を、1画面で説明しやすくしています。</p>
  <div class="cta-actions">
    <span class="cta-main">✅ デモしやすい</span>
    <span>✅ 効果を伝えやすい</span>
    <span>✅ 導入後の運用まで見せやすい</span>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )


def render_quick_start_compact(st, *, quick_starts: Sequence[Tuple[str, str, str]] = DEFAULT_QUICK_STARTS) -> None:
    st.markdown('<div class="eyebrow" style="margin-top:8px;">Quick Start</div>', unsafe_allow_html=True)
    st.caption("よく使う質問をすぐ送信できます")
    _render_buttons(st, quick_starts=quick_starts, key_suffix="compact")
