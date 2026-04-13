from __future__ import annotations

from pathlib import Path
from typing import Callable

import streamlit as st


def render_admin_log_download_panel(
    *,
    list_log_files: Callable[[], list[Path]],
    make_logs_zip: Callable[[list[Path]], bytes],
) -> None:
    with st.expander("📝 ログ閲覧 / 一括ダウンロード", expanded=False):
        st.markdown('<div class="section-caption">改善用ログをまとめて回収し、FAQ見直しや報告資料に使える形で整理します。</div>', unsafe_allow_html=True)
        try:
            log_files = list_log_files()
        except Exception:
            log_files = []

        count = len(log_files)
        st.markdown(
            f"""
<div class="kpi-grid" style="grid-template-columns: repeat(3, minmax(0, 1fr)); margin-top: 4px;">
  <div class="kpi">
    <div class="label">対象ログファイル数</div>
    <div class="value">{count}</div>
    <div class="sub">nohit_*.csv</div>
  </div>
  <div class="kpi">
    <div class="label">用途</div>
    <div class="value">改善</div>
    <div class="sub">FAQ見直しの材料</div>
  </div>
  <div class="kpi">
    <div class="label">操作</div>
    <div class="value">ZIP</div>
    <div class="sub">一括ダウンロード</div>
  </div>
</div>
""",
            unsafe_allow_html=True,
        )

        if log_files:
            try:
                zip_bytes = bytes(make_logs_zip(log_files) or b"")
            except Exception:
                zip_bytes = b""

            st.download_button(
                "⬇ nohitログ一式をZIPでダウンロード",
                data=zip_bytes,
                file_name="nohit_logs.zip",
                mime="application/zip",
                key="admin_nohit_logs_zip_download_fix5",
                on_click="ignore",
                use_container_width=True,
            )

            names = [p.name for p in log_files[:10]]
            st.markdown('<div class="card" style="margin-top:12px;">', unsafe_allow_html=True)
            st.markdown('**対象ファイル（先頭10件）**')
            for name in names:
                st.write(f"- {name}")
            if len(log_files) > 10:
                st.caption(f"ほか {len(log_files) - 10} 件あります。")
            st.markdown('</div>', unsafe_allow_html=True)
        else:
            st.info("まだ nohit ログはありません。")
