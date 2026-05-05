from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_TENANT_ID_RE = re.compile(r"[^a-zA-Z0-9_-]+")


@dataclass(frozen=True)
class TenantUser:
    tenant_id: str
    login_id: str
    password: str
    display_name: str = ""
    role: str = "user"


def sanitize_tenant_id(value: object, default: str = "demo") -> str:
    text = str(value or "").strip().lower()
    text = _TENANT_ID_RE.sub("-", text).strip("-_")
    return text or default


def _secret_raw(st, name: str, default: Any = None) -> Any:
    try:
        if name in st.secrets:
            return st.secrets.get(name, default)
    except Exception:
        pass
    return os.environ.get(name, default)


def _clean(value: object) -> str:
    return str(value or "").strip().strip("'\"").strip()


def _add_user(users: dict[tuple[str, str], TenantUser], tenant_id: object, login_id: object, password: object, display_name: object = "", role: object = "user") -> None:
    tenant = sanitize_tenant_id(tenant_id)
    login = _clean(login_id)
    pwd = str(password or "")
    if not tenant or not login:
        return
    users[(tenant, login)] = TenantUser(
        tenant_id=tenant,
        login_id=login,
        password=pwd,
        display_name=_clean(display_name) or login,
        role=_clean(role) or "user",
    )



def _as_bool(value: object, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in ("1", "true", "yes", "y", "on", "あり", "有効"):
        return True
    if text in ("0", "false", "no", "n", "off", "なし", "無効"):
        return False
    return default


def is_company_login_enabled(st) -> bool:
    """会社IDログイン画面を出すかどうか。

    .streamlit/secrets.toml または環境変数で切替できます。
    ENABLE_COMPANY_LOGIN = true   -> ログイン画面あり
    ENABLE_COMPANY_LOGIN = false  -> ログイン画面なし（DEFAULT_TENANT_IDで自動ログイン）
    """
    raw = _secret_raw(st, "ENABLE_COMPANY_LOGIN", os.environ.get("ENABLE_COMPANY_LOGIN", True))
    return _as_bool(raw, default=True)


def setup_no_login_tenant(st) -> None:
    """ログインなし運用時の会社ID・ユーザー情報をセットする。"""
    tenant_id = sanitize_tenant_id(_secret_raw(st, "DEFAULT_TENANT_ID", os.environ.get("DEFAULT_TENANT_ID", "demo")))
    login_id = _clean(_secret_raw(st, "DEFAULT_LOGIN_ID", os.environ.get("DEFAULT_LOGIN_ID", "demo"))) or "demo"
    display_name = _clean(_secret_raw(st, "DEFAULT_DISPLAY_NAME", os.environ.get("DEFAULT_DISPLAY_NAME", login_id))) or login_id
    role = _clean(_secret_raw(st, "DEFAULT_TENANT_ROLE", os.environ.get("DEFAULT_TENANT_ROLE", "admin"))) or "admin"

    st.session_state["tenant_login_ok"] = True
    st.session_state["tenant_login_disabled"] = True
    st.session_state["tenant_id"] = tenant_id
    st.session_state["tenant_login_id"] = login_id
    st.session_state["tenant_display_name"] = display_name
    st.session_state["tenant_role"] = role

    # ログインなしモードは、従来通り管理機能を触れるようにadmin扱いを初期値にします。
    # 本番で管理画面を隠したい場合は DEFAULT_TENANT_ROLE = "user" にしてください。
    if str(role).strip().lower() in ("admin", "owner", "manager"):
        st.session_state["admin_ok"] = True
        st.session_state["admin_login_id"] = f"{tenant_id}/{login_id}"
        st.session_state["admin_display_name"] = display_name

def load_tenant_users(st) -> dict[tuple[str, str], TenantUser]:
    """会社別ログインユーザーを読み込む。

    対応形式:
    1) TENANT_USERS = "demo:admin:demo123, customer-a:sato:pass"
    2) TENANT_USERS = ["demo:admin:demo123", "customer-a:sato:pass:佐藤:admin"]
    3) [TENANT_USERS]\n   "demo/admin" = "demo123"\n   "customer-a/sato" = "pass"
    4) [TENANT_USERS]\n   demo = "admin:demo123,suzuki:pass"
    """
    raw = _secret_raw(st, "TENANT_USERS", "")
    users: dict[tuple[str, str], TenantUser] = {}

    if isinstance(raw, dict) or hasattr(raw, "items"):
        try:
            for key, value in raw.items():
                key_s = _clean(key)
                value_s = str(value or "")
                if "/" in key_s:
                    tenant, login = key_s.split("/", 1)
                    _add_user(users, tenant, login, value_s)
                else:
                    tenant = key_s
                    for part in value_s.replace(";", ",").replace("\n", ",").split(","):
                        cols = [_clean(x) for x in part.split(":")]
                        if len(cols) >= 2:
                            _add_user(users, tenant, cols[0], cols[1], cols[2] if len(cols) >= 3 else "", cols[3] if len(cols) >= 4 else "user")
        except Exception:
            pass
    else:
        items = raw if isinstance(raw, (list, tuple, set)) else [raw]
        for item in items:
            text = str(item or "")
            for part in text.replace("\r", "\n").replace(";", ",").replace("\n", ",").split(","):
                cols = [_clean(x) for x in part.split(":")]
                if len(cols) >= 3:
                    _add_user(users, cols[0], cols[1], cols[2], cols[3] if len(cols) >= 4 else "", cols[4] if len(cols) >= 5 else "user")

    # 初回検証用のデモユーザー。TENANT_USERSを設定すると上書きされます。
    # demo / demo / demo は管理者ロールにして、管理画面まで確認できるようにする。
    if not users:
        _add_user(users, "demo", "demo", "demo", "デモ管理者", "admin")
    return users


def authenticate_tenant_user(st, tenant_id: str, login_id: str, password: str) -> TenantUser | None:
    tenant = sanitize_tenant_id(tenant_id)
    login = _clean(login_id)
    users = load_tenant_users(st)
    user = users.get((tenant, login))
    if user and user.password == str(password or ""):
        return user
    return None


def tenant_data_dir(root_dir: Path | str, tenant_id: str) -> Path:
    return Path(root_dir) / "runtime_data" / "tenants" / sanitize_tenant_id(tenant_id)


def ensure_tenant_login(st) -> bool:
    """ログイン済みならTrue。未ログインならログイン画面だけ表示してFalse。

    ENABLE_COMPANY_LOGIN=false の場合はログイン画面を出さず、
    DEFAULT_TENANT_ID の会社として自動ログインします。
    """
    if not is_company_login_enabled(st):
        setup_no_login_tenant(st)
        return True

    if st.session_state.get("tenant_login_ok"):
        return True

    st.markdown(
        """
<style>
.login-shell {max-width: 560px; margin: 7vh auto 0 auto; background: rgba(255,255,255,.94); border: 1px solid #e2e8f0; border-radius: 24px; padding: 28px 30px; box-shadow: 0 18px 45px rgba(15,23,42,.10);} 
.login-title {font-size: 28px; font-weight: 900; color: #0f172a; margin-bottom: 8px;}
.login-caption {color:#475569; font-size: 14px; line-height: 1.7; margin-bottom: 8px;}
.login-note {font-size: 12px; color:#64748b; background:#f8fafc; border:1px solid #e2e8f0; border-radius:14px; padding:10px 12px; margin-top:12px;}
</style>
<div class="login-shell">
  <div class="login-title">情シス問い合わせAI</div>
  <div class="login-caption">会社ID・ログインID・パスワードを入力してください。会社ごとにFAQ、RAG、ログ、設定を分離して管理します。</div>
</div>
        """,
        unsafe_allow_html=True,
    )

    with st.form("tenant_login_form"):
        tenant_id = st.text_input("会社ID", value=str(st.session_state.get("tenant_id_input", "demo")), placeholder="例：demo / customer-a")
        login_id = st.text_input("ログインID", value=str(st.session_state.get("tenant_user_input", "demo")))
        password = st.text_input("パスワード", type="password")
        submitted = st.form_submit_button("ログイン", type="primary", use_container_width=True)

    if submitted:
        user = authenticate_tenant_user(st, tenant_id, login_id, password)
        if user:
            st.session_state["tenant_login_ok"] = True
            st.session_state["tenant_id"] = user.tenant_id
            st.session_state["tenant_login_id"] = user.login_id
            st.session_state["tenant_display_name"] = user.display_name or user.login_id
            st.session_state["tenant_role"] = user.role
            # 会社ログインの role が admin の場合は、既存の管理者画面にも入れる。
            # 既存の管理者ログイン機能は残したまま、会社別管理者を追加する。
            if str(user.role or "").strip().lower() in ("admin", "owner", "manager"):
                st.session_state["admin_ok"] = True
                st.session_state["admin_login_id"] = f"{user.tenant_id}/{user.login_id}"
                st.session_state["admin_display_name"] = user.display_name or user.login_id
            st.rerun()
        else:
            st.error("会社ID、ログインID、またはパスワードが違います。")

    st.info("初期状態では demo / demo / demo でログインできます。本番では .streamlit/secrets.toml の TENANT_USERS を必ず変更してください。")
    st.caption("管理者権限を付ける場合は TENANT_USERS に demo:admin:password:表示名:admin のように role=admin を指定します。")
    return False


def render_tenant_sidebar(st) -> None:
    tenant = st.session_state.get("tenant_id", "")
    login = st.session_state.get("tenant_login_id", "")
    if not tenant:
        return
    with st.sidebar:
        st.caption(f"🏢 会社ID: {tenant}")
        st.caption(f"👤 ログイン: {login or '-'}")
        st.caption(f"🔐 権限: {st.session_state.get('tenant_role', 'user')}")
        if st.session_state.get("tenant_login_disabled"):
            st.caption("ログイン画面: なし（自動ログイン）")
            return
        if st.button("ログアウト", key="tenant_logout_button", use_container_width=True):
            for key in [
                "tenant_login_ok", "tenant_login_disabled", "tenant_id", "tenant_login_id", "tenant_display_name", "tenant_role",
                "admin_ok", "admin_login_id", "admin_display_name",
                "faq_search_warmup_token", "faq_search_warmup_info",
            ]:
                st.session_state.pop(key, None)
            st.rerun()
