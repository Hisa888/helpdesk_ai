from __future__ import annotations

from datetime import datetime
from uuid import uuid4
import re
from typing import Any

FOLLOWUP_TERMS = [
    "やり方", "方法", "どうやる", "どうすれば", "詳しく", "わからない", "分からない",
    "それ", "その", "手順", "教えて", "どこ", "起動って", "無効化って", "設定って",
    "とは", "できない", "できません", "教えてください", "知りたい",
]

DETAIL_INTENT_TERMS = {
    "excel_safe_mode": ["excel", "エクセル", "セーフモード", "safe"],
    "excel_addin_disable": ["excel", "エクセル", "アドオン", "アドイン", "無効"],
    "office_repair": ["office", "オフィス", "修復", "クイック修復", "オンライン修復"],
    "office_license": ["office", "excel", "エクセル", "ライセンス", "更新", "サインイン"],
}



# 問い合わせスレッドのカテゴリ固定検索に使う軽量カテゴリ判定。
# FAQのcategory列が未整備でも、スレッド開始時の質問・採用FAQからカテゴリを推定して保持する。
CATEGORY_RULES = {
    "pc_performance": {
        "label": "PC動作遅延・性能",
        "terms": ["パソコンが遅い", "pcが遅い", "遅い", "重い", "フリーズ", "固まる", "応答なし", "動作が遅い", "メモリ", "ディスク", "cpu", "タスクマネージャー", "スタートアップ", "常駐"],
        "faq_terms": ["pc", "パソコン", "端末", "遅い", "重い", "フリーズ", "メモリ", "ディスク", "スタートアップ", "常駐"],
    },
    "office_excel": {
        "label": "Office / Excel",
        "terms": ["excel", "エクセル", "office", "オフィス", "セーフモード", "アドオン", "アドイン", "修復", "ライセンス"],
        "faq_terms": ["excel", "エクセル", "office", "オフィス", "セーフモード", "アドオン", "アドイン", "修復", "ライセンス"],
    },
    "network": {
        "label": "ネットワーク / VPN / Wi-Fi",
        "terms": ["wifi", "wi-fi", "ワイファイ", "ネットワーク", "vpn", "つながらない", "接続できない", "通信", "インターネット"],
        "faq_terms": ["wifi", "wi-fi", "ワイファイ", "ネットワーク", "vpn", "通信", "インターネット", "接続"],
    },
    "account_login": {
        "label": "アカウント / ログイン / パスワード",
        "terms": ["ログイン", "サインイン", "パスワード", "アカウント", "認証", "ロック", "mfa", "多要素"],
        "faq_terms": ["ログイン", "サインイン", "パスワード", "アカウント", "認証", "ロック", "mfa", "多要素"],
    },
    "display": {
        "label": "ディスプレイ / 画面",
        "terms": ["ディスプレイ", "モニター", "モニタ", "画面", "映らない", "真っ暗", "表示されない"],
        "faq_terms": ["ディスプレイ", "モニター", "モニタ", "画面", "映らない", "表示されない"],
    },
    "print": {
        "label": "プリンタ / 印刷",
        "terms": ["プリンタ", "プリンター", "印刷", "複合機", "スキャン"],
        "faq_terms": ["プリンタ", "プリンター", "印刷", "複合機", "スキャン"],
    },
    "mail": {
        "label": "メール / Outlook",
        "terms": ["メール", "outlook", "送信", "受信", "exchange"],
        "faq_terms": ["メール", "outlook", "送信", "受信", "exchange"],
    },
    "application_form": {
        "label": "申請書 / 書式 / 業務申請",
        "terms": ["申請", "申請書", "書式", "起案書", "導入申請", "システム導入", "念書", "承諾書", "管理簿"],
        "faq_terms": ["申請", "申請書", "書式", "起案書", "導入申請", "システム導入", "念書", "承諾書", "管理簿"],
    },
    "software_install": {
        "label": "アプリ / ソフト導入",
        "terms": ["アプリ", "ソフト", "ソフトウェア", "インストール", "導入", "追加", "利用したい"],
        "faq_terms": ["アプリ", "ソフト", "ソフトウェア", "インストール", "導入", "追加"],
    },
}


def _simple_norm_text(text: Any) -> str:
    return str(text or "").strip().lower().replace("　", " ")


def classify_thread_category(text: str, row: Any | None = None) -> str:
    """質問文と採用FAQから問い合わせカテゴリを推定する。"""
    parts = [_simple_norm_text(text)]
    if row is not None:
        try:
            parts.extend([
                _simple_norm_text(row.get("category", "")),
                _simple_norm_text(row.get("question", "")),
                _simple_norm_text(row.get("intent", "")),
                _simple_norm_text(row.get("keywords", "")),
                _simple_norm_text(row.get("answer", ""))[:400],
            ])
        except Exception:
            pass
    target = " / ".join([p for p in parts if p])
    if not target:
        return ""
    best_cat = ""
    best_score = 0
    for cat, rule in CATEGORY_RULES.items():
        score = 0
        for term in rule.get("terms", []):
            if term.lower() in target:
                score += 3
        for term in rule.get("faq_terms", []):
            if term.lower() in target:
                score += 1
        if score > best_score:
            best_cat = cat
            best_score = score
    return best_cat if best_score > 0 else ""


def get_thread_category_label(category: str) -> str:
    return str(CATEGORY_RULES.get(str(category or ""), {}).get("label", category or ""))


def set_thread_category_if_needed(st, text: str = "", row: Any | None = None, *, force: bool = False) -> None:
    t = get_current_thread(st)
    if t.get("category") and not force:
        return
    cat = classify_thread_category(text, row=row)
    if cat:
        t["category"] = cat
        t["category_label"] = get_thread_category_label(cat)
        st.session_state["current_thread_category"] = cat
        st.session_state["current_thread_category_label"] = t["category_label"]


def _now_label() -> str:
    return datetime.now().strftime("%m/%d %H:%M")


def _new_thread(title: str = "新規問い合わせ") -> dict:
    now = datetime.now().isoformat(timespec="seconds")
    return {
        "thread_id": uuid4().hex[:12],
        "title": title,
        "status": "open",
        "created_at": now,
        "updated_at": now,
        "messages": [],
        "last_parent_question": "",
        "last_parent_faq_id": "",
        "last_parent_answer": "",
        "last_used_hits": [],
        "category": "",
        "category_label": "",
    }


def ensure_thread_session_state(st) -> None:
    if "inquiry_threads" not in st.session_state or not isinstance(st.session_state.get("inquiry_threads"), list):
        existing_messages = list(st.session_state.get("messages", []) or [])
        first_title = "新規問い合わせ"
        for m in existing_messages:
            if str(m.get("role", "")) == "user" and str(m.get("content", "")).strip():
                first_title = str(m.get("content", "")).strip().splitlines()[0][:28]
                break
        t = _new_thread(first_title)
        t["messages"] = existing_messages
        st.session_state.inquiry_threads = [t]
        st.session_state.current_thread_id = t["thread_id"]
    if not st.session_state.get("current_thread_id"):
        if not st.session_state.inquiry_threads:
            st.session_state.inquiry_threads.append(_new_thread())
        st.session_state.current_thread_id = st.session_state.inquiry_threads[0]["thread_id"]


def get_current_thread(st) -> dict:
    ensure_thread_session_state(st)
    current_id = st.session_state.get("current_thread_id")
    for t in st.session_state.inquiry_threads:
        if t.get("thread_id") == current_id:
            st.session_state["current_thread_category"] = str(t.get("category", "") or "")
            st.session_state["current_thread_category_label"] = str(t.get("category_label", "") or "")
            return t
    t = st.session_state.inquiry_threads[0]
    st.session_state.current_thread_id = t.get("thread_id")
    st.session_state["current_thread_category"] = str(t.get("category", "") or "")
    st.session_state["current_thread_category_label"] = str(t.get("category_label", "") or "")
    return t


def load_current_thread_messages(st) -> None:
    t = get_current_thread(st)
    st.session_state.messages = list(t.get("messages", []) or [])


def save_current_thread_messages(st) -> None:
    t = get_current_thread(st)
    t["messages"] = list(st.session_state.get("messages", []) or [])
    t["updated_at"] = datetime.now().isoformat(timespec="seconds")


def create_new_thread(st, title: str = "新規問い合わせ") -> dict:
    ensure_thread_session_state(st)
    cur = get_current_thread(st)
    if not cur.get("category"):
        set_thread_category_if_needed(st, str(cur.get("title") or ""))
    save_current_thread_messages(st)
    t = _new_thread(title)
    st.session_state.inquiry_threads.insert(0, t)
    st.session_state.current_thread_id = t["thread_id"]
    st.session_state.messages = []
    st.session_state.pending_q = ""
    st.session_state.used_hits = []
    st.session_state.pending_nohit_active = False
    st.session_state.pending_nohit = {}
    st.session_state["current_thread_category"] = ""
    st.session_state["current_thread_category_label"] = ""
    return t


def _set_status(st, thread_id: str, status: str) -> None:
    ensure_thread_session_state(st)
    for t in st.session_state.inquiry_threads:
        if t.get("thread_id") == thread_id:
            t["status"] = status
            t["updated_at"] = datetime.now().isoformat(timespec="seconds")
            break


def _delete_empty_threads(st) -> None:
    threads = list(st.session_state.get("inquiry_threads", []) or [])
    keep = [t for t in threads if t.get("messages") or t.get("thread_id") == st.session_state.get("current_thread_id")]
    if not keep:
        keep = [_new_thread()]
    st.session_state.inquiry_threads = keep
    if not any(t.get("thread_id") == st.session_state.get("current_thread_id") for t in keep):
        st.session_state.current_thread_id = keep[0].get("thread_id")


def render_thread_sidebar(st) -> None:
    ensure_thread_session_state(st)
    with st.sidebar:
        st.markdown("---")
        st.markdown("### 🧵 問い合わせスレッド")
        if st.button("＋ 新規問い合わせ", use_container_width=True, key="thread_new_real_ui_top"):
            create_new_thread(st)
            st.toast("新規問い合わせを開始しました", icon="🧵")

        cur = get_current_thread(st)
        c1, c2 = st.columns(2)
        with c1:
            if st.button("対応中", use_container_width=True, key="thread_mark_open"):
                _set_status(st, cur["thread_id"], "open")
                st.toast("対応中に変更しました", icon="🧵")
        with c2:
            if st.button("完了", use_container_width=True, key="thread_mark_done"):
                _set_status(st, cur["thread_id"], "done")
                st.toast("完了に変更しました", icon="✅")

        def draw_group(label: str, status: str):
            items = [t for t in st.session_state.inquiry_threads if t.get("status", "open") == status]
            with st.expander(f"{label}（{len(items)}）", expanded=(status == "open")):
                if not items:
                    st.caption("なし")
                for t in items[:30]:
                    title = str(t.get("title") or "新規問い合わせ")[:24]
                    selected = t.get("thread_id") == st.session_state.get("current_thread_id")
                    button_label = ("▶ " if selected else "・ ") + title
                    if st.button(button_label, use_container_width=True, key=f"thread_select_{t.get('thread_id')}"):
                        save_current_thread_messages(st)
                        st.session_state.current_thread_id = t.get("thread_id")
                        st.session_state["current_thread_category"] = str(t.get("category", "") or "")
                        st.session_state["current_thread_category_label"] = str(t.get("category_label", "") or "")
                        load_current_thread_messages(st)
        draw_group("対応中", "open")
        draw_group("完了", "done")
        _delete_empty_threads(st)


def render_thread_header(st) -> None:
    t = get_current_thread(st)
    status = "対応中" if t.get("status") == "open" else "完了"
    st.markdown(
        f"""
<div class="glass-card" style="padding:12px 16px;margin-bottom:10px;border-left:5px solid #38bdf8;">
  <div style="font-size:12px;color:#64748b;">現在の問い合わせスレッド：{status} / 更新 {_now_label()}</div>
  <div style="font-size:18px;font-weight:800;">🧵 {str(t.get('title') or '新規問い合わせ')}</div>
  <div style="font-size:12px;color:#64748b;">カテゴリ：{str(t.get('category_label') or '未判定')} / このスレッド内の追加質問は、前の質問の続きとして検索します。</div>
</div>
""",
        unsafe_allow_html=True,
    )
    c1, c2, c3 = st.columns([1.2, 1, 1])
    with c1:
        if st.button("＋ 新規問い合わせを開始", key="thread_new_from_header", use_container_width=True):
            create_new_thread(st)
            st.toast("新規問い合わせを開始しました", icon="🧵")
    with c2:
        if st.button("この問い合わせを完了", key="thread_done_from_header", use_container_width=True):
            _set_status(st, t["thread_id"], "done")
            st.toast("この問い合わせを完了にしました", icon="✅")
    with c3:
        if st.button("対応中に戻す", key="thread_open_from_header", use_container_width=True):
            _set_status(st, t["thread_id"], "open")
            st.toast("対応中に戻しました", icon="🧵")


def update_thread_after_user_message(st, user_q: str) -> None:
    t = get_current_thread(st)
    q = str(user_q or "").strip()
    if not q:
        return
    if not t.get("messages") or str(t.get("title", "")) in ("", "新規問い合わせ"):
        t["title"] = q.splitlines()[0][:28]
    if not t.get("last_parent_question"):
        t["last_parent_question"] = q.splitlines()[0][:80]
    set_thread_category_if_needed(st, q)
    t["updated_at"] = datetime.now().isoformat(timespec="seconds")


def is_followup_question(text: str) -> bool:
    q = str(text or "").strip().lower()
    if not q:
        return False
    return any(term.lower() in q for term in FOLLOWUP_TERMS)


def build_thread_context_query(st, user_q: str) -> str:
    """補足質問時だけ、現在スレッドの主題を足して検索精度を上げる。"""
    q = str(user_q or "").strip()
    t = get_current_thread(st)
    parent = str(t.get("last_parent_question") or t.get("title") or "").strip()
    answer = str(t.get("last_parent_answer") or "").strip()
    if parent and is_followup_question(q):
        category_label = str(t.get("category_label") or "").strip()
        parts = []
        if category_label:
            parts.append(f"現在の問い合わせカテゴリ：{category_label}")
        parts.append(f"現在の問い合わせテーマ：{parent}")
        if answer:
            parts.append(f"直前の回答：{answer[:180]}")
        parts.append(f"追加質問：{q}")
        return "\n".join(parts)
    return q


def _norm(v: Any) -> str:
    return str(v or "").strip().lower()


def _row_get(row: Any, names: list[str]) -> str:
    for name in names:
        try:
            v = row.get(name, "")
            if str(v or "").strip():
                return str(v).strip()
        except Exception:
            pass
    return ""


def _answer_result(answer: str, *, user_q: str, row: Any | None = None, score: float = 1.0) -> dict:
    used_hits = []
    answer_format = "markdown"
    if row is not None:
        try:
            row_dict = dict(row) if not isinstance(row, dict) else dict(row)
        except Exception:
            row_dict = {}
        used_hits = [(row_dict, float(score))]
        answer_format = str(row_dict.get("answer_format") or row_dict.get("表示形式") or "markdown")
    return {
        "answer": answer,
        "best_score": float(score),
        "answer_threshold": 0.0,
        "suggest_threshold": 0.0,
        "used_hits": used_hits,
        "doc_hits": [],
        "used_doc_rag": False,
        "doc_best_score": 0.0,
        "was_nohit": False,
        "was_suggest": False,
        "answer_format": answer_format,
        "was_clarification": False,
        "suggestion_candidates": [],
        "thread_detail_answer": True,
        "user_q": user_q,
    }


def _builtin_detail_answer(theme: str, q: str) -> str:
    text = f"{theme}\n{q}".lower()
    if ("セーフモード" in text or "safe" in text) and ("excel" in text or "エクセル" in text):
        return """Excelのセーフモード起動方法です。

1. Excelをすべて閉じます。
2. キーボードで **Windowsキー + R** を押します。
3. 「ファイル名を指定して実行」に次を入力します。

```text
excel /safe
```

4. **OK** または Enter を押します。
5. Excelの上部に「セーフ モード」と表示されれば起動成功です。

セーフモードで起動できる場合は、アドオンが原因の可能性があります。次は「アドオン無効化の方法」と聞いてください。"""
    if ("アドオン" in text or "アドイン" in text) and ("excel" in text or "エクセル" in text):
        return """Excelのアドオン無効化手順です。

1. Excelを開きます。
2. **ファイル** → **オプション** を開きます。
3. 左メニューの **アドイン** を選びます。
4. 画面下の「管理」で **COMアドイン** を選び、**設定** を押します。
5. 表示されたアドインのチェックを外します。
6. Excelを再起動して、通常起動できるか確認します。

原因切り分けのため、最初はすべて外して確認し、必要なものを1つずつ戻すのがおすすめです。"""
    if "修復" in text and ("office" in text or "オフィス" in text or "excel" in text or "エクセル" in text):
        return """Office修復の手順です。

1. Windowsの **設定** を開きます。
2. **アプリ** → **インストールされているアプリ** を開きます。
3. **Microsoft 365** または **Microsoft Office** を探します。
4. **変更** または **修正** を選びます。
5. まず **クイック修復** を実行します。
6. 直らない場合は **オンライン修復** を実行します。

オンライン修復は時間がかかり、インターネット接続が必要です。"""
    return ""


def try_thread_detail_answer(st, user_q: str, ensure_faq_index_loaded=None) -> dict | None:
    """同一スレッド内の追加質問に対して、親FAQの繰り返しを避けて詳細手順を返す。"""
    q = str(user_q or "").strip()
    if not q or not is_followup_question(q):
        return None
    t = get_current_thread(st)
    theme = str(t.get("last_parent_question") or t.get("title") or "").strip()
    if not theme:
        return None

    # 1) FAQに親子FAQがあれば、現在スレッドの親FAQ_ID配下だけを優先検索
    parent_id = str(t.get("last_parent_faq_id") or "").strip()
    if callable(ensure_faq_index_loaded):
        try:
            local_df, *_ = ensure_faq_index_loaded()
        except Exception:
            local_df = None
        if local_df is not None:
            rows = []
            for _, row in local_df.iterrows():
                rid_parent = _row_get(row, ["PARENT_ID", "parent_id", "親FAQ_ID", "親ID"])
                ftype = _norm(_row_get(row, ["FAQ_TYPE", "faq_type", "種別"]))
                is_child = bool(rid_parent) or ftype in ("child", "子", "detail", "詳細")
                if parent_id and rid_parent and rid_parent != parent_id:
                    continue
                if not is_child:
                    continue
                target = " ".join([
                    _row_get(row, ["question", "QUESTION", "質問"]),
                    _row_get(row, ["intent", "INTENT", "意図"]),
                    _row_get(row, ["keywords", "KEYWORDS", "キーワード・言い換え"]),
                    _row_get(row, ["DETAIL_KEYWORDS", "detail_keywords", "詳細キーワード"]),
                    _row_get(row, ["FOLLOWUP_LABEL", "followup_label", "表示ラベル"]),
                ]).lower()
                score = 0
                for term in re.split(r"[\s　、,。？?]+", q.lower()):
                    if term and term in target:
                        score += 1
                for key_terms in DETAIL_INTENT_TERMS.values():
                    if any(term in q.lower() for term in key_terms) and any(term in target for term in key_terms):
                        score += 3
                if score > 0:
                    rows.append((score, row))
            if rows:
                rows.sort(key=lambda x: x[0], reverse=True)
                row = rows[0][1]
                answer = _row_get(row, ["answer", "ANSWER", "回答"])
                if answer:
                    return _answer_result(answer, user_q=q, row=row, score=1.0)

    # 2) 子FAQがまだ未登録でも、代表的なOffice詳細質問は同じ回答を繰り返さず手順で返す
    built = _builtin_detail_answer(theme, q)
    if built:
        return _answer_result(built, user_q=q, row=None, score=1.0)
    return None


def update_thread_after_answer(st, result: dict) -> None:
    t = get_current_thread(st)
    if str(result.get("answer", "")).strip():
        t["last_parent_answer"] = str(result.get("answer", "")).strip()[:500]
    hits = list(result.get("used_hits", []) or [])
    if hits:
        try:
            row = hits[0][0]
            if not isinstance(row, dict):
                row = dict(row)
            q = str(row.get("question") or row.get("QUESTION") or row.get("質問") or "").strip()
            fid = str(row.get("FAQ_ID") or row.get("faq_id") or row.get("ID") or "").strip()
            parent_id = str(row.get("PARENT_ID") or row.get("parent_id") or row.get("親FAQ_ID") or "").strip()
            # 子FAQを回答した場合は、親文脈を上書きしない
            if q and not parent_id:
                t["last_parent_question"] = q[:120]
            if fid and not parent_id:
                t["last_parent_faq_id"] = fid
            set_thread_category_if_needed(st, str(result.get("user_q") or t.get("title") or ""), row=row)
            t["last_used_hits"] = [dict(row)]
        except Exception:
            pass
    save_current_thread_messages(st)
