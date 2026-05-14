from __future__ import annotations

import hashlib
import inspect
import re
from contextlib import contextmanager
from typing import Iterator

import streamlit as st

_ADMIN_POPOVER_DEPTH = 0
_ADMIN_MODAL_STATE_KEY = "_admin_center_modal_active_key"


def _safe_key(label: str) -> str:
    """同じラベルが複数あっても衝突しにくい Streamlit key を作る。"""

    frame = inspect.currentframe()
    caller = None
    try:
        # _safe_key -> admin_popover -> 呼び出し元
        caller = frame.f_back.f_back if frame and frame.f_back else None
        location = ""
        if caller is not None:
            location = f"{caller.f_code.co_filename}:{caller.f_lineno}"
    finally:
        # 参照循環を避ける
        del frame

    raw = f"{location}:{label}"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
    slug = re.sub(r"[^0-9a-zA-Z_]+", "_", label).strip("_")[:24] or "admin"
    return f"admin_popup_{slug}_{digest}"


def _label_key(label: str) -> str:
    """ボタン側とモーダル本体側で同じになる、ラベル固定の key を作る。"""

    digest = hashlib.sha1(label.encode("utf-8")).hexdigest()[:12]
    slug = re.sub(r"[^0-9a-zA-Z_]+", "_", label).strip("_")[:24] or "admin"
    return f"admin_popup_{slug}_{digest}"


def _inject_admin_modal_css() -> None:
    """管理者メニュー用の中央モーダル CSS を注入する。"""

    st.markdown(
        """
<style>
/* ============================================================
   管理者モード: ボタン押下後の中央モーダル
   - 外側クリックは Streamlit の背景ボタンで閉じる
   - 非表示時は中身を描画しないため、開閉が軽い
   ============================================================ */

/* 互換用の非表示コンテナ */
div[class*="st-key-admin_center_modal_hidden_"] {
    display: none !important;
    visibility: hidden !important;
    width: 0 !important;
    height: 0 !important;
    min-height: 0 !important;
    max-height: 0 !important;
    overflow: hidden !important;
    padding: 0 !important;
    margin: 0 !important;
}

/* 管理者モードのメニューボタンを一覧として見やすくする */
div[class*="st-key-admin_center_open_"] button {
    justify-content: flex-start !important;
    min-height: 2.65rem !important;
    border-radius: 12px !important;
    font-weight: 700 !important;
}

/* 外側: 画面全体のオーバーレイ */
div[class*="st-key-admin_center_modal_admin_popup_"] {
    position: fixed !important;
    inset: 0 !important;
    width: 100vw !important;
    height: 100vh !important;
    min-width: 100vw !important;
    min-height: 100vh !important;
    z-index: 2147483000 !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    padding: 28px !important;
    margin: 0 !important;
    background: rgba(15, 23, 42, 0.58) !important;
    backdrop-filter: blur(3px) !important;
    box-sizing: border-box !important;
}

/* 外側 container 自体には余計な白背景・余白を持たせない */
div[class*="st-key-admin_center_modal_admin_popup_"] > div {
    width: auto !important;
    max-width: none !important;
    background: transparent !important;
    border: 0 !important;
    box-shadow: none !important;
    padding: 0 !important;
    margin: 0 !important;
}

/* 外側クリックで閉じるための背景ボタン */
div[class*="st-key-admin_center_backdrop_btn_admin_popup_"] {
    position: fixed !important;
    inset: 0 !important;
    width: 100vw !important;
    height: 100vh !important;
    z-index: 2147483001 !important;
    margin: 0 !important;
    padding: 0 !important;
}

div[class*="st-key-admin_center_backdrop_btn_admin_popup_"] button {
    position: fixed !important;
    inset: 0 !important;
    width: 100vw !important;
    height: 100vh !important;
    min-height: 100vh !important;
    border: 0 !important;
    border-radius: 0 !important;
    background: transparent !important;
    box-shadow: none !important;
    color: transparent !important;
    opacity: 0 !important;
    cursor: default !important;
    padding: 0 !important;
    margin: 0 !important;
}

/* 内側: 実際のモーダルカード。背景ボタンより前面に出す */
div[class*="st-key-admin_center_modal_card_admin_popup_"] {
    position: relative !important;
    z-index: 2147483002 !important;
    width: min(1120px, calc(100vw - 56px)) !important;
    max-width: min(1120px, calc(100vw - 56px)) !important;
    max-height: min(88vh, 900px) !important;
    overflow-y: auto !important;
    overflow-x: hidden !important;
    padding: 1.2rem 1.35rem 1.45rem !important;
    margin: 0 auto !important;
    border-radius: 20px !important;
    border: 1px solid rgba(148, 163, 184, 0.38) !important;
    background: var(--background-color, #ffffff) !important;
    box-shadow: 0 28px 80px rgba(15, 23, 42, 0.42) !important;
    box-sizing: border-box !important;
    cursor: default !important;
}

/* Streamlit が card key の内側に追加するラッパーはカード幅いっぱいにする */
div[class*="st-key-admin_center_modal_card_admin_popup_"] > div,
div[class*="st-key-admin_center_modal_card_admin_popup_"] [data-testid="stVerticalBlock"],
div[class*="st-key-admin_center_modal_card_admin_popup_"] [data-testid="stVerticalBlockBorderWrapper"] {
    width: 100% !important;
    max-width: 100% !important;
    box-sizing: border-box !important;
}

/* モーダル内タイトル */
.admin-center-modal-title {
    margin: 0.15rem 0 1rem;
    font-size: 1.25rem;
    font-weight: 800;
    line-height: 1.35;
}

/* 画面が狭い場合は余白を詰める */
@media (max-width: 720px) {
  div[class*="st-key-admin_center_modal_admin_popup_"] {
      padding: 12px !important;
  }
  div[class*="st-key-admin_center_modal_card_admin_popup_"] {
      width: calc(100vw - 24px) !important;
      max-width: calc(100vw - 24px) !important;
      max-height: calc(100vh - 24px) !important;
      border-radius: 14px !important;
      padding: 1rem !important;
  }
}
</style>
        """.strip(),
        unsafe_allow_html=True,
    )


def admin_modal_button(label: str, *, key: str | None = None) -> bool:
    """管理者メニューのボタンを表示し、対象モーダルが開いているか返す。

    旧版の contextmanager 方式では、閉じているメニューの中身まで毎回描画していたため、
    グラフ・DB・RAG・PDFなどがある画面で開閉が重くなっていました。
    この関数は、開いているボタンの中身だけ描画させるための軽量入口です。
    """

    _inject_admin_modal_css()
    modal_key = key or _label_key(label)
    if st.button(label, key=f"admin_center_open_{modal_key}", use_container_width=True):
        st.session_state[_ADMIN_MODAL_STATE_KEY] = modal_key
    return st.session_state.get(_ADMIN_MODAL_STATE_KEY) == modal_key


@contextmanager
def admin_modal_body(label: str, *, key: str | None = None) -> Iterator[None]:
    """画面中央のモーダル本体を描画する。admin_modal_button が True の時だけ使う。"""

    global _ADMIN_POPOVER_DEPTH

    _inject_admin_modal_css()
    modal_key = key or _label_key(label)

    try:
        modal_cm = st.container(key=f"admin_center_modal_{modal_key}")
    except TypeError:
        st.warning(
            "この Streamlit バージョンでは中央ポップアップ表示に必要な "
            "st.container(key=...) が使えません。streamlit を新しめの版へ更新してください。"
        )
        with st.expander(label, expanded=True):
            yield
        return

    with modal_cm:
        # 見た目には表示しない背景ボタンです。ポップアップ外の暗い部分をクリックすると閉じます。
        if st.button("背景をクリックして閉じる", key=f"admin_center_backdrop_btn_{modal_key}"):
            st.session_state[_ADMIN_MODAL_STATE_KEY] = None
            st.rerun()

        try:
            card_cm = st.container(key=f"admin_center_modal_card_{modal_key}")
        except TypeError:
            card_cm = st.container()

        with card_cm:
            st.markdown(
                f'<div class="admin-center-modal-title">{label}</div>',
                unsafe_allow_html=True,
            )
            _ADMIN_POPOVER_DEPTH += 1
            try:
                yield
            finally:
                _ADMIN_POPOVER_DEPTH -= 1


@contextmanager
def admin_popover(label: str, *, expanded: bool = False) -> Iterator[None]:
    """管理者メニュー内の詳細表示。

    トップレベルの管理者メニューは、速度のために admin_modal_button +
    admin_modal_body を使ってください。この関数はモーダル内の入れ子項目を
    枠付きカードとして表示する互換用です。
    """

    global _ADMIN_POPOVER_DEPTH

    _inject_admin_modal_css()

    # モーダル内の入れ子は二重モーダルにせず、枠付き詳細カードとして表示する。
    if _ADMIN_POPOVER_DEPTH > 0:
        st.markdown(f"#### {label}")
        try:
            with st.container(border=True):
                yield
        except TypeError:
            st.markdown("---")
            yield
            st.markdown("---")
        return

    # 互換用: もし旧形式のトップレベル呼び出しが残っていても表示は壊さない。
    if admin_modal_button(label):
        with admin_modal_body(label):
            yield
    else:
        # 旧形式の with 本文はPythonの仕様上スキップできないため、内容は実行されます。
        # 表示の重さを避けるため、トップレベル呼び出しは新形式へ置き換えるのが前提です。
        hidden_key = f"admin_center_modal_hidden_{_safe_key(label)}"
        try:
            with st.container(key=hidden_key):
                _ADMIN_POPOVER_DEPTH += 1
                try:
                    yield
                finally:
                    _ADMIN_POPOVER_DEPTH -= 1
        except TypeError:
            _ADMIN_POPOVER_DEPTH += 1
            try:
                yield
            finally:
                _ADMIN_POPOVER_DEPTH -= 1
