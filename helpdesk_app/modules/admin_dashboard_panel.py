from __future__ import annotations

from typing import Callable

import pandas as pd
import streamlit as st


EMPTY_DAILY_COLUMNS = ["date", "total", "matched", "auto_rate", "saved_min", "saved_min_cum"]


def _safe_len(df: pd.DataFrame | None) -> int:
    try:
        return int(len(df)) if df is not None else 0
    except Exception:
        return 0



def _build_dashboard_daily_frame(df: pd.DataFrame | None, avg_min: float, deflect: float) -> pd.DataFrame:
    if df is None or not len(df):
        return pd.DataFrame(columns=EMPTY_DAILY_COLUMNS)
    try:
        plot_df = df.copy()
        plot_df["timestamp"] = pd.to_datetime(plot_df["timestamp"], errors="coerce")
        plot_df = plot_df.dropna(subset=["timestamp"])
        if not len(plot_df):
            return pd.DataFrame(columns=EMPTY_DAILY_COLUMNS)
        plot_df["date"] = plot_df["timestamp"].dt.date
        if "matched" not in plot_df.columns:
            plot_df["matched"] = 0
        plot_df["matched"] = pd.to_numeric(plot_df["matched"], errors="coerce").fillna(0)
        daily = (
            plot_df.groupby("date", dropna=True)
            .agg(total=("question", "count"), matched=("matched", "sum"))
            .reset_index()
            .sort_values("date")
        )
        daily["auto_rate"] = ((daily["matched"] / daily["total"]).replace([pd.NA, float("inf")], 0.0) * 100.0).fillna(0.0)
        daily["saved_min"] = daily["matched"] * float(avg_min) * float(deflect)
        daily["saved_min_cum"] = daily["saved_min"].cumsum()
        return daily
    except Exception:
        return pd.DataFrame(columns=EMPTY_DAILY_COLUMNS)



def _safe_daily_summary(df: pd.DataFrame) -> list[tuple[str, int]]:
    if not _safe_len(df) or "timestamp" not in df.columns:
        return []
    try:
        plot_df = df.copy()
        plot_df["timestamp"] = pd.to_datetime(plot_df["timestamp"], errors="coerce")
        plot_df = plot_df.dropna(subset=["timestamp"])
        if not len(plot_df):
            return []
        plot_df["date"] = plot_df["timestamp"].dt.strftime("%m-%d")
        daily = plot_df.groupby("date").size().reset_index(name="count")
        out: list[tuple[str, int]] = []
        for _, row in daily.tail(10).iterrows():
            out.append((str(row.get("date", "")), int(pd.to_numeric(row.get("count", 0), errors="coerce") or 0)))
        return out
    except Exception:
        return []



def _build_exec_commentary(*, total_7d: int, matched_7d: int, nohit_7d: int, auto_rate: float, saved_hours: float, saved_yen: int) -> tuple[str, str, str]:
    if total_7d <= 0:
        return (
            "まだ十分な利用ログがありません。",
            "まずは代表質問を数件流してログを貯めると、導入効果を数字で示しやすくなります。",
            "クイックスタートや想定質問でログを作成してください。",
        )

    if auto_rate >= 70:
        status = "FAQで自己解決がかなり進んでいます。"
    elif auto_rate >= 45:
        status = "一次対応の自動化が機能し始めています。"
    else:
        status = "問い合わせ誘導とFAQ強化の余地が大きい状態です。"

    impact = (
        f"直近7日で {matched_7d} 件をAIが自動対応し、約 {saved_hours:.1f} 時間、"
        f"金額換算で約 {saved_yen:,} 円の削減見込みです。"
    )

    if nohit_7d > matched_7d:
        action = "該当なしが多いため、未整備FAQの追加で改善余地を示しやすいです。"
    elif nohit_7d > 0:
        action = "該当なしログをFAQへ反映すると、さらに自動対応率を上げやすいです。"
    else:
        action = "該当なしが抑えられており、運用定着の説明材料として使いやすい状態です。"

    return status, impact, action



def _render_exec_summary(*, total_7d: int, matched_7d: int, nohit_7d: int, auto_rate: float, saved_hours: float, saved_yen: int) -> None:
    status, impact, action = _build_exec_commentary(
        total_7d=total_7d,
        matched_7d=matched_7d,
        nohit_7d=nohit_7d,
        auto_rate=auto_rate,
        saved_hours=saved_hours,
        saved_yen=saved_yen,
    )
    st.markdown(
        f"""
<div class="glass-card" style="margin: 6px 0 14px 0;">
  <div class="eyebrow">Admin Demo Summary</div>
  <h3 style="margin:4px 0 10px 0;">管理者向けサマリー</h3>
  <p style="margin:0 0 8px 0; color: var(--text-main); font-weight: 700;">{status}</p>
  <p style="margin:0 0 8px 0; color: var(--text-sub);">{impact}</p>
  <p style="margin:0; color: var(--text-sub);">{action}</p>
</div>
""",
        unsafe_allow_html=True,
    )



def _render_kpi_cards(*, total_7d: int, matched_7d: int, nohit_7d: int, auto_rate: float, saved_hours: float, saved_yen: int) -> None:
    st.markdown('<div class="section-title">📊 管理KPI</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-caption">問い合わせ量・AI対応率・削減効果を、導入説明に使いやすい形でまとめています。</div>', unsafe_allow_html=True)
    st.markdown(
        f"""
<div class="kpi-grid">
  <div class="kpi">
    <div class="label">直近7日 総問い合わせ</div>
    <div class="value">{total_7d}</div>
    <div class="sub">AI対応 + 該当なし</div>
  </div>
  <div class="kpi">
    <div class="label">AI自動対応件数</div>
    <div class="value">{matched_7d}</div>
    <div class="sub">FAQヒット件数</div>
  </div>
  <div class="kpi">
    <div class="label">該当なし件数</div>
    <div class="value">{nohit_7d}</div>
    <div class="sub">FAQ追加候補</div>
  </div>
  <div class="kpi">
    <div class="label">AI自動対応率</div>
    <div class="value">{auto_rate:.1f}%</div>
    <div class="sub">一次対応の自動化率</div>
  </div>
  <div class="kpi">
    <div class="label">削減効果</div>
    <div class="value">{saved_hours:.1f}h</div>
    <div class="sub">約 {saved_yen:,} 円</div>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )



def _render_operation_cards(*, matched_7d: int, nohit_7d: int, avg_min: int, deflect_pct: int, hourly_cost: int) -> None:
    st.markdown('<div class="section-title">🧭 管理アクションの見どころ</div>', unsafe_allow_html=True)
    st.markdown(
        f"""
<div class="proof-grid">
  <div class="proof-card">
    <div class="proof-icon">⚙️</div>
    <div class="title">前提条件をその場で調整</div>
    <p>平均対応時間 <b>{avg_min}分</b>、自己解決率 <b>{deflect_pct}%</b>、時給 <b>{hourly_cost:,}円</b> を変えながら、顧客に合う効果試算を見せられます。</p>
  </div>
  <div class="proof-card">
    <div class="proof-icon">📚</div>
    <div class="title">FAQ改善ポイントを可視化</div>
    <p>直近7日で <b>{nohit_7d}件</b> の該当なし。どこをFAQ追加すべきか説明しやすい状態です。</p>
  </div>
  <div class="proof-card">
    <div class="proof-icon">💡</div>
    <div class="title">導入価値を数字で伝える</div>
    <p>自動対応 <b>{matched_7d}件</b> を根拠に、問い合わせ削減と標準化の効果を管理画面だけで説明できます。</p>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )



def render_admin_dashboard_panel(
    *,
    read_interactions: Callable[..., pd.DataFrame],
    count_nohit_logs: Callable[..., tuple[int, int, int]],
) -> None:
    with st.expander("📊 管理ダッシュボード（拡張版）", expanded=False):
        try:
            df7 = read_interactions(days=7)
        except Exception:
            df7 = pd.DataFrame(columns=["timestamp", "question", "category", "best_score", "matched"])
        try:
            df30 = read_interactions(days=30)
        except Exception:
            df30 = pd.DataFrame(columns=["timestamp", "question", "category", "best_score", "matched"])
        try:
            _, nohit_7d, _ = count_nohit_logs(days=7)
        except Exception:
            nohit_7d = 0

        try:
            matched_series = df7["matched"] if _safe_len(df7) and "matched" in df7.columns else pd.Series(dtype=float)
            matched_7d = int(pd.to_numeric(matched_series, errors="coerce").fillna(0).sum())
        except Exception:
            matched_7d = 0
        total_7d = matched_7d + int(nohit_7d or 0)
        auto_rate = (matched_7d / total_7d * 100.0) if total_7d > 0 else 0.0

        st.markdown('<div class="section-title">🎯 ダッシュボード概要</div>', unsafe_allow_html=True)
        st.markdown('<div class="section-caption">管理者が、利用状況・効果試算・改善余地をその場で説明できるようにした拡張ビューです。</div>', unsafe_allow_html=True)

        control_col, summary_col = st.columns([1.1, 1.7])
        with control_col:
            st.markdown('<div class="card"><h3>⚙️ 効果試算の前提</h3><p class="small">この場で数字を調整し、顧客や部門ごとの条件に合わせて説明できます。</p></div>', unsafe_allow_html=True)
            avg_min = st.number_input(
                "1件あたり削減時間（分）",
                min_value=1,
                max_value=60,
                value=int(st.session_state.get("avg_min", 5)),
                step=1,
                key="admin_ext_avg_min",
            )
            deflect_pct = st.slider(
                "AIで解決できる割合（推定）",
                min_value=30,
                max_value=100,
                value=int(st.session_state.get("deflect_pct", 70)),
                step=1,
                key="admin_ext_deflect_pct",
            )
            hourly_cost = st.number_input(
                "想定人件費（円/時間）",
                min_value=0,
                max_value=20000,
                value=4000,
                step=500,
                key="admin_ext_hourly_cost",
            )

        deflect = float(deflect_pct) / 100.0
        st.session_state["admin_ext_deflect"] = deflect
        saved_hours = round((matched_7d * float(avg_min) * float(deflect)) / 60.0, 1)
        saved_yen = int(saved_hours * int(hourly_cost))

        with summary_col:
            _render_exec_summary(
                total_7d=total_7d,
                matched_7d=matched_7d,
                nohit_7d=int(nohit_7d or 0),
                auto_rate=auto_rate,
                saved_hours=saved_hours,
                saved_yen=saved_yen,
            )

        _render_kpi_cards(
            total_7d=total_7d,
            matched_7d=matched_7d,
            nohit_7d=int(nohit_7d or 0),
            auto_rate=auto_rate,
            saved_hours=saved_hours,
            saved_yen=saved_yen,
        )
        _render_operation_cards(
            matched_7d=matched_7d,
            nohit_7d=int(nohit_7d or 0),
            avg_min=int(avg_min),
            deflect_pct=int(deflect_pct),
            hourly_cost=int(hourly_cost),
        )

        daily_chart = _build_dashboard_daily_frame(df7, avg_min=float(avg_min), deflect=float(deflect))
        st.markdown('<div class="section-title">📈 推移グラフ</div>', unsafe_allow_html=True)
        st.markdown('<div class="section-caption">必要なグラフだけ開いて、管理者説明や営業デモに使える構成です。</div>', unsafe_allow_html=True)
        if len(daily_chart):
            with st.expander("📈 7日間の問い合わせ件数推移", expanded=False):
                st.line_chart(daily_chart.set_index("date")[["total"]])
            with st.expander("🧠 AI自動対応率の推移（FAQヒット率）", expanded=False):
                st.line_chart(daily_chart.set_index("date")[["auto_rate"]])
            with st.expander("⏱ 削減時間の累計（推定）", expanded=False):
                st.line_chart(daily_chart.set_index("date")[["saved_min_cum"]])
        else:
            st.info("まだ表示できる推移データがありません。代表質問を流してログを作るとグラフが出ます。")

        daily_summary = _safe_daily_summary(df30)
        if daily_summary:
            st.markdown('<div class="section-title">🗓 直近10日サマリー</div>', unsafe_allow_html=True)
            st.markdown('<div class="section-caption">問い合わせの発生傾向を短く確認できます。</div>', unsafe_allow_html=True)
            for d, cnt in daily_summary:
                st.write(f"- {d}: {cnt} 件")

        if _safe_len(df7):
            with st.expander("🧾 直近7日ログ（先頭10件・簡易表示）", expanded=False):
                show_cols = [c for c in ["timestamp", "question", "category", "best_score", "matched"] if c in df7.columns]
                try:
                    preview = df7[show_cols].head(10).copy() if show_cols else pd.DataFrame()
                    if len(preview):
                        for _, row in preview.iterrows():
                            ts = str(row.get("timestamp", ""))
                            q = str(row.get("question", ""))
                            cat = str(row.get("category", ""))
                            score = str(row.get("best_score", ""))
                            matched = str(row.get("matched", ""))
                            st.write(f"- {ts} | {q} | {cat} | score={score} | matched={matched}")
                except Exception:
                    st.info("ログ詳細の表示で問題があったため、要約のみ表示しています。")
