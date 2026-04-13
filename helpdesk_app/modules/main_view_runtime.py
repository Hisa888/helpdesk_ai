from __future__ import annotations

from datetime import datetime
from typing import Callable, Iterable

import pandas as pd
import streamlit as st


def render_sales_kpi_sections(*, read_interactions: Callable[[int], pd.DataFrame | None]) -> None:
    """営業デモ用のKPIサマリーを表示する。"""
    try:
        df30 = read_interactions(days=30)
        if df30 is not None and len(df30) > 0:
            total30 = int(len(df30))
            matched30 = int(df30["matched"].sum()) if "matched" in df30.columns else 0
            rate30 = (matched30 / total30 * 100.0) if total30 else 0.0

            avg_min_kpi = float(st.session_state.get("avg_min", 5))
            deflect_kpi = float(st.session_state.get("deflect", 0.7))
            hourly_cost_kpi = int(st.session_state.get("hourly_cost", 4000))
            saved_min30 = matched30 * avg_min_kpi * deflect_kpi
            saved_h30 = saved_min30 / 60.0
            saved_yen30 = int(round(saved_h30 * hourly_cost_kpi)) if hourly_cost_kpi else 0

            st.markdown('<div class="section-title">📊 営業デモサマリー</div>', unsafe_allow_html=True)
            st.markdown('<div class="section-caption">利用ログから、導入効果をすぐ見せられるようにしています。</div>', unsafe_allow_html=True)
            st.markdown(
                f'''
<div class="kpi-grid">
  <div class="kpi">
    <div class="label">直近30日 問い合わせ</div>
    <div class="value">{total30}</div>
    <div class="sub">利用ログベース</div>
  </div>
  <div class="kpi">
    <div class="label">AI自動対応率</div>
    <div class="value">{rate30:.1f}%</div>
    <div class="sub">FAQヒット率</div>
  </div>
  <div class="kpi">
    <div class="label">削減時間（推定）</div>
    <div class="value">{saved_h30:.1f}h</div>
    <div class="sub">平均対応 {int(avg_min_kpi)}分 × 解決率 {int(deflect_kpi * 100)}%</div>
  </div>
  <div class="kpi">
    <div class="label">削減コスト（推定）</div>
    <div class="value">¥{saved_yen30:,}</div>
    <div class="sub">時給 {int(hourly_cost_kpi):,}円換算</div>
  </div>
</div>
''',
                unsafe_allow_html=True,
            )

        df7 = read_interactions(days=7)
        if df7 is not None and len(df7) > 0:
            total7 = int(len(df7))
            matched7 = int(df7["matched"].sum()) if "matched" in df7.columns else 0
            rate7 = (matched7 / total7 * 100.0) if total7 else 0.0
            today_prefix = datetime.now().strftime("%Y-%m-%d")
            today_rows = df7[df7["timestamp"].astype(str).str.startswith(today_prefix)]
            total_today = int(len(today_rows))
            avg_min_kpi = float(st.session_state.get("avg_min", 5))
            deflect_kpi = float(st.session_state.get("deflect", 0.7))
            hourly_cost_kpi = int(st.session_state.get("hourly_cost", 4000))
            saved_min7 = matched7 * avg_min_kpi * deflect_kpi
            saved_h7 = saved_min7 / 60.0
            saved_yen7 = int(round(saved_h7 * hourly_cost_kpi)) if hourly_cost_kpi else 0

            st.markdown('<div class="section-title">📈 直近の利用状況</div>', unsafe_allow_html=True)
            st.markdown('<div class="section-caption">導入するとどう良くなるかを、問い合わせ実績とセットで見せられます。</div>', unsafe_allow_html=True)
            st.markdown(
                f'''
<div class="kpi-grid">
  <div class="kpi">
    <div class="label">直近7日 問い合わせ</div>
    <div class="value">{total7}</div>
    <div class="sub">ログベース</div>
  </div>
  <div class="kpi">
    <div class="label">直近7日 自動対応率</div>
    <div class="value">{rate7:.1f}%</div>
    <div class="sub">FAQヒット率</div>
  </div>
  <div class="kpi">
    <div class="label">直近7日 自動対応件数</div>
    <div class="value">{matched7}</div>
    <div class="sub">自己解決に寄与</div>
  </div>
  <div class="kpi">
    <div class="label">推定削減（直近7日）</div>
    <div class="value">{saved_h7:.1f}h</div>
    <div class="sub">約{saved_yen7:,}円（{hourly_cost_kpi:,}円/時間）</div>
  </div>
</div>
''',
                unsafe_allow_html=True,
            )
            st.markdown(
                f'''
<div class="proof-grid">
  <div class="proof-card">
    <div class="proof-icon">🧠</div>
    <div class="title">FAQで自己解決を促進</div>
    <p>直近7日で <b>{matched7}件</b> の問い合わせがAI側で自動対応できています。</p>
  </div>
  <div class="proof-card">
    <div class="proof-icon">💬</div>
    <div class="title">利用されやすい導線</div>
    <p>今日の問い合わせは <b>{total_today}件</b>。現場が使い続けやすいUIかどうかも見せやすい状態です。</p>
  </div>
  <div class="proof-card">
    <div class="proof-icon">💰</div>
    <div class="title">導入効果を数字で説明</div>
    <p>直近7日だけでも <b>{saved_h7:.1f}時間</b>、金額換算で <b>約{saved_yen7:,}円</b> の削減イメージを提示できます。</p>
  </div>
</div>
''',
                unsafe_allow_html=True,
            )
        elif df30 is None or len(df30) == 0:
            st.markdown(
                '''
<div class="glass-card" style="margin-top:10px;">
  <div class="eyebrow">Demo Note</div>
  <h3 style="margin:4px 0 8px 0;">まずは質問してログを作ると、効果がより伝わります</h3>
  <p style="margin:0; color: var(--text-sub);">利用ログがまだないためKPIは空ですが、画面下のクイックスタートから代表質問を流すと、営業デモ向けの数値が表示されます。</p>
</div>
''',
                unsafe_allow_html=True,
            )
    except Exception:
        pass


def render_public_sidebar(
    *,
    contact_link: str,
    count_nohit_logs: Callable[[int], tuple[int, int, int]],
    read_interactions: Callable[[int], pd.DataFrame | None],
    list_log_files: Callable[[], list],
    make_logs_zip: Callable[[Iterable], bytes],
    csv_bytes_as_utf8_sig: Callable,
    format_minutes_to_hours: Callable[[float], str],
) -> None:
    with st.sidebar:
        st.markdown("### 📌 このAIでできること")
        st.markdown(
            """
        このAIは、社内のIT問い合わせを自己解決につなげるための **情シス問い合わせ支援AI** です。

        主な機能

        ・FAQデータを検索し、最も近い回答を自動表示  
        ・RAG検索により、表現が少し違う質問でも近いFAQを提示  
        ・回答の根拠となるFAQ候補と一致度を表示  
        ・該当するFAQがない場合は問い合わせテンプレートを提示  
        ・問い合わせログを自動記録し、未整備FAQを可視化  

        管理者機能

        ・FAQを **Excelでダウンロード / アップロード / 更新反映**  
        ・問い合わせログの確認  
        ・削減時間シミュレーション  
        ・導入効果レポートPDFの出力  
        ・操作説明書 / 提案資料PDFのダウンロード
        """
        )

        st.markdown("### 📈 想定効果（例）")
        st.markdown(
            """
        このAIを導入すると、次のような効果が期待できます。

        ・よくある問い合わせを自己解決できるようになる  
        ・情シス担当者の対応時間を削減できる  
        ・回答内容のばらつきを減らし、対応品質を安定化できる  
        ・新人担当者でも一定品質の対応が可能になる  
        ・問い合わせログをもとにFAQを継続改善できる  

        例（100人規模の企業）

        ・月100件の問い合わせ  
        ・1件5分対応  

        → 月 **約500分（約8時間）削減**  
        → 年間 **約96時間削減**
        """
        )

        st.markdown("### 🧭 使い方")
        st.markdown(
            """
        ① 質問を入力します  
        例  
        ・Wi-Fiがつながらない  
        ・PCが起動しない  
        ・ソフトをインストールしたい  

        ② AIがFAQを検索します  

        ③ 回答と参考FAQが表示されます  

        ④ 該当FAQがない場合  
        問い合わせテンプレートを使って情シスへ連絡できます  

        ⑤ 管理者はFAQを更新して  
        AIの回答精度を継続的に改善できます
        """
        )
        if contact_link:
            st.markdown(
                f'''
<div class="glass-card" style="margin-top: 18px; padding: 20px;">
  <div class="eyebrow">Consulting CTA</div>
  <h3 style="margin:4px 0 8px 0;">このまま導入相談につなげられます</h3>
  <p style="margin:0 0 12px 0; color: var(--text-sub);">デモ確認後、そのままヒアリング・導入相談へ進めるための導線です。</p>
  <a href="{contact_link}" target="_blank" style="display:inline-block;background:#0f172a;color:#ffffff;text-decoration:none;padding:10px 16px;border-radius:10px;font-weight:700;">🚀 導入のご相談</a>
</div>
''',
                unsafe_allow_html=True,
            )

        st.markdown("### 📊 問い合わせログ状況（該当なし）")
        t_cnt, w_cnt, total_cnt = count_nohit_logs(days=7)
        col_a, col_b, col_c = st.columns(3)
        col_a.metric("今日", t_cnt)
        col_b.metric("過去7日", w_cnt)
        col_c.metric("累計", total_cnt)

        st.markdown("### ⏱ 削減時間シミュレーター")
        avg_min = st.slider(
            "1件あたりの平均対応時間（分）",
            1,
            20,
            int(st.session_state.get("avg_min", 5)),
            help="情シスが1件対応する平均時間の目安",
            key="avg_min",
        )
        deflect_pct = st.slider(
            "AIで解決できる割合（推定）",
            30,
            100,
            int(st.session_state.get("deflect_pct", 70)),
            help="AI回答で自己解決に至る割合の推定",
            key="deflect_pct",
        )
        deflect = deflect_pct / 100.0
        st.session_state["deflect"] = deflect

        df_int = read_interactions(days=7)
        if df_int is None or len(df_int) == 0:
            st.caption("まだ利用ログがありません（質問すると自動で蓄積します）。")
        else:
            matched_7d = int(df_int["matched"].sum()) if "matched" in df_int.columns else 0
            total_7d = int(len(df_int))
            nohit_7d = total_7d - matched_7d
            saved_min_7d = matched_7d * float(avg_min) * float(deflect)
            st.metric("推定削減（過去7日）", format_minutes_to_hours(saved_min_7d))
            st.caption(f"内訳：自動対応 {matched_7d} 件 / 該当なし {nohit_7d} 件（合計 {total_7d} 件）")

            try:
                today_prefix = datetime.now().strftime("%Y-%m-%d")
                df_today = df_int[df_int["timestamp"].astype(str).str.startswith(today_prefix)]
                matched_today = int(df_today["matched"].sum()) if len(df_today) else 0
                saved_min_today = matched_today * float(avg_min) * float(deflect)
                st.metric("推定削減（今日）", format_minutes_to_hours(saved_min_today))
            except Exception:
                pass

        # 直近7日の見える化グラフは、管理者ログイン後に
        # 「📊 管理ダッシュボード（拡張版）」内へ移動して表示します。

        st.markdown("### 📥 ログ（該当なし）ダウンロード")
        log_files = list_log_files()
        if not log_files:
            st.caption("まだログはありません。")
        else:
            latest = log_files[0]
            latest_bytes = csv_bytes_as_utf8_sig(latest)
            st.download_button(
                "⬇ 最新ログCSVをダウンロード",
                data=latest_bytes,
                file_name=latest.name,
                mime="text/csv",
                width="stretch",
            )

            zip_bytes = make_logs_zip(log_files)
            st.download_button(
                "⬇ ログをZIPでまとめてDL",
                data=zip_bytes,
                file_name="nohit_logs.zip",
                mime="application/zip",
                width="stretch",
            )

            with st.expander("ログ一覧を見る"):
                for p in log_files[:20]:
                    st.write(f"• {p.name}")


def ensure_admin_session_state() -> None:
    if "is_admin" not in st.session_state:
        st.session_state.is_admin = False


def render_admin_login_sidebar(*, check_password: Callable[[str], bool]) -> None:
    with st.sidebar:
        st.markdown("## 🛠 管理者")
        if not st.session_state.is_admin:
            pwd = st.text_input("管理者パスワード", type="password")
            if st.button("ログイン"):
                if check_password(pwd):
                    st.session_state.is_admin = True
                    st.success("ログイン成功")
                    st.rerun()
                else:
                    st.error("パスワードが違います")
        else:
            st.success("ログイン中")
            if st.button("ログアウト"):
                st.session_state.is_admin = False
                st.rerun()


def render_admin_tools_if_logged_in(
    *,
    render_admin_surface: Callable,
    admin_ctx: dict,
    render_admin_complete_tools: Callable,
    render_admin_settings_bundle: Callable,
) -> None:
    if st.session_state.is_admin:
        render_admin_surface(
            admin_ctx=admin_ctx,
            render_admin_complete_tools=render_admin_complete_tools,
            render_admin_settings_bundle=render_admin_settings_bundle,
        )
