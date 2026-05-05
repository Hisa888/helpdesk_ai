from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

STATUSES = ("未対応", "対応中", "解決済み")


def _safe_id(value: str) -> str:
    value = str(value or "demo").strip().lower()
    value = re.sub(r"[^a-z0-9_-]+", "-", value)
    return value.strip("-") or "demo"


def _tenant_id(st) -> str:
    return _safe_id(
        st.session_state.get("company_id")
        or st.session_state.get("tenant_id")
        or st.session_state.get("selected_company_id")
        or "demo"
    )


def _thread_store_path(st) -> Path:
    tenant = _tenant_id(st)
    base = Path("runtime_data") / "tenants" / tenant / "threads"
    base.mkdir(parents=True, exist_ok=True)
    return base / "inquiry_threads.json"


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def load_threads(st) -> List[Dict[str, Any]]:
    path = _thread_store_path(st)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
    except Exception:
        return []
    return []


def save_threads(st, threads: List[Dict[str, Any]]) -> None:
    path = _thread_store_path(st)
    path.write_text(json.dumps(threads, ensure_ascii=False, indent=2), encoding="utf-8")


def create_thread(st, title: str = "新規問い合わせ") -> Dict[str, Any]:
    threads = load_threads(st)
    seq = len(threads) + 1
    tid = f"TCK-{datetime.now().strftime('%Y%m%d')}-{seq:04d}-{uuid.uuid4().hex[:6]}"
    thread = {
        "thread_id": tid,
        "company_id": _tenant_id(st),
        "user_id": st.session_state.get("login_id") or st.session_state.get("tenant_user_id") or "demo",
        "title": str(title or "新規問い合わせ")[:80],
        "status": "未対応",
        "created_at": _now(),
        "updated_at": _now(),
        "messages": [],
        "admin_memo": "",
    }
    threads.insert(0, thread)
    save_threads(st, threads)
    st.session_state["active_thread_id"] = tid
    return thread


def get_active_thread(st) -> Dict[str, Any] | None:
    active_id = st.session_state.get("active_thread_id")
    for thread in load_threads(st):
        if thread.get("thread_id") == active_id:
            return thread
    return None


def append_thread_message(st, role: str, message: str, meta: Dict[str, Any] | None = None) -> None:
    if not message:
        return
    if not st.session_state.get("active_thread_id"):
        create_thread(st, title=str(message)[:40])
    active_id = st.session_state.get("active_thread_id")
    threads = load_threads(st)
    changed = False
    for thread in threads:
        if thread.get("thread_id") == active_id:
            if thread.get("title") in ("新規問い合わせ", "") and role == "user":
                thread["title"] = str(message)[:80]
            thread.setdefault("messages", []).append({
                "role": role,
                "message": str(message),
                "created_at": _now(),
                "meta": meta or {},
            })
            thread["updated_at"] = _now()
            changed = True
            break
    if changed:
        save_threads(st, threads)


def render_thread_sidebar(st) -> None:
    """問い合わせ単位で画面を分けるためのサイドバー。

    既存チャット機能は残しつつ、現在の問い合わせIDを session_state に保持します。
    追加情報や管理ログ側から active_thread_id を参照すれば、同じ問い合わせに追記できます。
    """
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🧵 問い合わせスレッド")

    if st.sidebar.button("＋ 新規問い合わせ", key="thread_new_inquiry_btn", use_container_width=True):
        create_thread(st)
        # 既存チャット表示も新規問い合わせとして見やすくする
        for key in ("chat_messages", "messages", "selected_faq", "candidate_faqs"):
            if key in st.session_state:
                try:
                    del st.session_state[key]
                except Exception:
                    pass
        st.rerun()

    threads = load_threads(st)
    if not threads:
        st.sidebar.caption("まだ問い合わせはありません。")
        return

    active_id = st.session_state.get("active_thread_id") or threads[0].get("thread_id")
    st.session_state["active_thread_id"] = active_id

    for status in STATUSES:
        group = [t for t in threads if t.get("status", "未対応") == status]
        with st.sidebar.expander(f"{status}（{len(group)}）", expanded=(status != "解決済み")):
            for t in group[:30]:
                label = f"{t.get('title','問い合わせ')[:24]}"
                if st.button(label, key=f"thread_select_{t.get('thread_id')}", use_container_width=True):
                    st.session_state["active_thread_id"] = t.get("thread_id")
                    st.rerun()


def render_active_thread_header(st) -> None:
    thread = get_active_thread(st)
    if not thread:
        return
    with st.expander(f"🧵 問い合わせID: {thread.get('thread_id')} / {thread.get('status')}", expanded=False):
        st.write(f"**件名:** {thread.get('title','')}")
        st.caption(f"作成: {thread.get('created_at','')} / 更新: {thread.get('updated_at','')}")
        new_status = st.selectbox(
            "ステータス",
            STATUSES,
            index=STATUSES.index(thread.get("status", "未対応")) if thread.get("status", "未対応") in STATUSES else 0,
            key=f"thread_status_{thread.get('thread_id')}",
        )
        memo = st.text_area("管理者メモ", value=thread.get("admin_memo", ""), key=f"thread_memo_{thread.get('thread_id')}")
        if st.button("スレッド情報を保存", key=f"thread_save_{thread.get('thread_id')}"):
            threads = load_threads(st)
            for t in threads:
                if t.get("thread_id") == thread.get("thread_id"):
                    t["status"] = new_status
                    t["admin_memo"] = memo
                    t["updated_at"] = _now()
                    break
            save_threads(st, threads)
            st.success("保存しました。")
