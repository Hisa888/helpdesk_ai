from __future__ import annotations

from typing import Callable

import pandas as pd
import streamlit as st


def _safe_len(df: pd.DataFrame | None) -> int:
    try:
        return int(len(df)) if df is not None else 0
    except Exception:
        return 0


def _build_dashboard_daily_frame(df: pd.DataFrame | None, avg_min: float, deflect: float) -> pd.DataFrame:
    if df is None or not len(df):
        return pd.DataFrame(columns=["date", "total", "matched", "auto_rate", "saved_min", "saved_min_cum"])
    try:
        plot_df = df.copy()
        plot_df["timestamp"] = pd.to_datetime(plot_df["timestamp"], errors="coerce")
        plot_df = plot_df.dropna(subset=["timestamp"])
        if not len(plot_df):
            return pd.DataFrame(columns=["date", "total", "matched", "auto_rate", "saved_min", "saved_min_cum"])
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
        return pd.DataFrame(columns=["date", "total", "matched", "auto_rate", "saved_min", "saved_min_cum"])


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
        deflect = float(deflect_pct) / 100.0
        st.session_state["admin_ext_deflect"] = deflect

        hourly_cost = st.number_input(
            "想定人件費（円/時間）",
            min_value=0,
            max_value=20000,
            value=4000,
            step=500,
            key="admin_ext_hourly_cost",
        )

        saved_hours = round((matched_7d * float(avg_min) * float(deflect)) / 60.0, 1)
        saved_yen = int(saved_hours * int(hourly_cost))

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("7日間の総問い合わせ", int(total_7d))
        c2.metric("AI自動対応", int(matched_7d))
        c3.metric("該当なし", int(nohit_7d or 0))
        c4.metric("AI対応率", f"{auto_rate:.1f}%")

        c5, c6 = st.columns(2)
        c5.metric("削減時間（推定）", f"{saved_hours} 時間")
        c6.metric("削減金額（推定）", f"{saved_yen:,} 円")

        daily_chart = _build_dashboard_daily_frame(df7, avg_min=float(avg_min), deflect=float(deflect))
        if len(daily_chart):
            st.markdown("#### 📈 見える化（直近7日）")
            with st.expander("📈 7日間の問い合わせ件数推移", expanded=False):
                st.line_chart(daily_chart.set_index("date")[["total"]])
            with st.expander("🧠 AI自動対応率の推移（FAQヒット率）", expanded=False):
                st.line_chart(daily_chart.set_index("date")[["auto_rate"]])
            with st.expander("⏱ 削減時間の累計（推定）", expanded=False):
                st.line_chart(daily_chart.set_index("date")[["saved_min_cum"]])

        daily_summary = _safe_daily_summary(df30)
        if daily_summary:
            st.caption("直近10日分の問い合わせ件数")
            for d, cnt in daily_summary:
                st.write(f"- {d}: {cnt} 件")

        if _safe_len(df7):
            st.caption("直近7日ログ（先頭10件・簡易表示）")
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
