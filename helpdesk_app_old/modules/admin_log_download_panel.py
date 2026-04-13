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
        try:
            log_files = list_log_files()
        except Exception:
            log_files = []
        st.caption(f"nohitログファイル数: {len(log_files)} 件")
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
            st.caption("対象ファイル")
            for p in log_files[:10]:
                st.write(f"- {p.name}")
        else:
            st.info("まだ nohit ログはありません。")
