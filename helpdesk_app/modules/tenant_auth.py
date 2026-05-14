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
        st.session_state["is_admin"] = True
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
/* =========================================
   Luxury Login UI - 情シス問い合わせAI
   Streamlitネイティブ描画版
   ※HTML文字列が画面に出ないよう、フォームはst.formで描画
========================================= */
[data-testid="stAppViewContainer"] {
    background:
        radial-gradient(circle at 12% 12%, rgba(124, 58, 237, .13), transparent 31%),
        radial-gradient(circle at 92% 82%, rgba(14, 165, 233, .12), transparent 30%),
        linear-gradient(135deg, #fbfaff 0%, #f4f1ff 48%, #f8fbff 100%) !important;
}
[data-testid="stHeader"] { background: transparent !important; }
[data-testid="stToolbar"], #MainMenu, footer { display: none !important; }
.block-container {
    max-width: 1180px !important;
    padding-top: 7vh !important;
    padding-bottom: 2rem !important;
}

.login-brand-panel {
    position: relative;
    padding: 42px 28px 36px 8px;
    color: #0f172a;
}
.login-logo-mark, .login-card-icon {
    width: 88px;
    height: 88px;
    border-radius: 999px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: linear-gradient(135deg, rgba(124,58,237,.10), rgba(14,165,233,.12));
    box-shadow: 0 18px 44px rgba(99,102,241,.16), inset 0 0 0 1px rgba(99,102,241,.13);
}
.login-logo-mark { margin: 0 auto 24px 92px; }
.login-card-icon { margin: 0 auto 18px; }
.login-brand-title {
    font-size: 40px;
    font-weight: 950;
    letter-spacing: -.045em;
    line-height: 1.15;
    margin: 0 0 14px 0;
    color: #0f172a;
}
.login-brand-subtitle {
    font-size: 17px;
    line-height: 1.85;
    color: #64748b;
    margin-bottom: 28px;
}
.login-accent-line {
    width: 54px;
    height: 4px;
    border-radius: 999px;
    background: linear-gradient(90deg, #a855f7, #22d3ee);
    margin: 0 0 34px 112px;
    box-shadow: 0 8px 20px rgba(168,85,247,.28);
}
.login-feature {
    display: grid;
    grid-template-columns: 76px 1fr;
    gap: 18px;
    align-items: center;
    margin: 25px 0;
}
.login-feature-icon {
    width: 62px;
    height: 62px;
    border-radius: 999px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 27px;
    background: rgba(255,255,255,.74);
    box-shadow: 0 16px 34px rgba(30,41,59,.08), inset 0 0 0 1px rgba(99,102,241,.10);
}
.login-feature-title {
    font-size: 18px;
    font-weight: 900;
    color: #0f172a;
    margin-bottom: 8px;
}
.login-feature-text {
    font-size: 15px;
    line-height: 1.75;
    color: #64748b;
}
.login-card-shell {
    background: rgba(255,255,255,.84);
    border: 1px solid rgba(226,232,240,.96);
    border-radius: 28px;
    padding: 54px 56px 42px;
    box-shadow: 0 32px 80px rgba(30,41,59,.13), 0 1px 0 rgba(255,255,255,.90) inset;
    backdrop-filter: blur(18px);
}
.login-card-title {
    text-align:center;
    font-size: 36px;
    font-weight: 950;
    letter-spacing: -.04em;
    color:#0f172a;
    margin:0 0 8px;
}
.login-card-caption {
    text-align:center;
    color:#64748b;
    font-size:16px;
    line-height:1.7;
    margin: 0 0 30px;
}
.login-secure-note {
    text-align:center;
    color:#94a3b8;
    font-weight:700;
    font-size:14px;
    margin-top: 18px;
}
.login-footer {
    text-align: center;
    color: #64748b;
    font-size: 13px;
    margin-top: 26px;
}

/* ログインカード内のStreamlit入力をSaaS風に調整 */
div[data-testid="stTextInput"] label p {
    font-weight: 900 !important;
    color: #0f172a !important;
    font-size: 14px !important;
}
div[data-testid="stTextInput"] input {
    min-height: 56px !important;
    border-radius: 12px !important;
    border: 1px solid #d7deea !important;
    background: rgba(255,255,255,.94) !important;
    box-shadow: 0 1px 0 rgba(255,255,255,.92) inset !important;
    font-size: 16px !important;
}
div[data-testid="stTextInput"] input:focus {
    border-color: #8b5cf6 !important;
    box-shadow: 0 0 0 3px rgba(139,92,246,.15) !important;
}
div[data-testid="stForm"] {
    border: 1px solid rgba(226,232,240,.96) !important;
    background: rgba(255,255,255,.86) !important;
    padding: 50px 54px 38px !important;
    border-radius: 28px !important;
    box-shadow: 0 32px 80px rgba(30,41,59,.13), 0 1px 0 rgba(255,255,255,.90) inset !important;
    backdrop-filter: blur(18px);
}
div[data-testid="stForm"] button[kind="primary"] {
    min-height: 58px !important;
    border-radius: 12px !important;
    border: 0 !important;
    color: #fff !important;
    font-size: 17px !important;
    font-weight: 900 !important;
    letter-spacing: .03em;
    background: linear-gradient(90deg, #2563eb 0%, #7c3aed 100%) !important;
    box-shadow: 0 16px 34px rgba(79,70,229,.24) !important;
}

@media (max-width: 980px) {
    .block-container { padding-top: 2rem !important; }
    .login-brand-panel { text-align: center; padding: 20px 18px 0; }
    .login-logo-mark { margin-left: auto; margin-right: auto; }
    .login-accent-line { margin-left: auto; margin-right: auto; }
    .login-feature { text-align: left; }
    .login-card-shell { padding: 42px 28px 34px; }
}
</style>
        """,
        unsafe_allow_html=True,
    )

    left, right = st.columns([0.92, 1.08], gap="large")

    with left:
        st.markdown(
            """
<div class="login-brand-panel">
  <div class="login-logo-mark">💬</div>
  <h1 class="login-brand-title">情シス問い合わせAI</h1>
  <div class="login-brand-subtitle">社内の「わからない」を、最短で解決。</div>
  <div class="login-accent-line"></div>

  <div class="login-feature">
    <div class="login-feature-icon">💡</div>
    <div><div class="login-feature-title">いつでも頼れる社内サポート</div><div class="login-feature-text">よくある社内問い合わせに、AIが自動で回答します。</div></div>
  </div>
  <div class="login-feature">
    <div class="login-feature-icon">🛡️</div>
    <div><div class="login-feature-title">安心・安全なセキュリティ</div><div class="login-feature-text">社内データを安全に管理し、安心してご利用いただけます。</div></div>
  </div>
  <div class="login-feature">
    <div class="login-feature-icon">👥</div>
    <div><div class="login-feature-title">業務効率を向上</div><div class="login-feature-text">問い合わせ対応を自動化し、情シス担当者の負担を軽減します。</div></div>
  </div>
</div>
            """,
            unsafe_allow_html=True,
        )

    with right:
        # Streamlitでは st.markdown の <div> で st.form を安全に包めないため、
        # 空の白いカードが表示されないよう st.form 自体をカード化しています。
        with st.form("tenant_login_form"):
            st.markdown(
                """
<div class="login-card-icon">💬</div>
<div class="login-card-title">ログイン</div>
<div class="login-card-caption">会社ID・ログインID・パスワードを入力してください</div>
                """,
                unsafe_allow_html=True,
            )
            tenant_id = st.text_input("会社ID", value=str(st.session_state.get("tenant_id_input", "demo")), placeholder="例：demo / customer-a")
            login_id = st.text_input("ログインID", value=str(st.session_state.get("tenant_user_input", "demo")))
            password = st.text_input("パスワード", type="password")
            submitted = st.form_submit_button("ログイン", type="primary", use_container_width=True)
            st.markdown('<div class="login-secure-note">🔒 セキュアな接続で保護されています</div>', unsafe_allow_html=True)

    st.markdown('<div class="login-footer">© 2025 情シス問い合わせAI All rights reserved.</div>', unsafe_allow_html=True)

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
                st.session_state["is_admin"] = True
                st.session_state["admin_login_id"] = f"{user.tenant_id}/{user.login_id}"
                st.session_state["admin_display_name"] = user.display_name or user.login_id
            st.rerun()
        else:
            st.error("会社ID、ログインID、またはパスワードが違います。")

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
                "admin_ok", "is_admin", "admin_login_id", "admin_display_name",
                "faq_search_warmup_token", "faq_search_warmup_info",
            ]:
                st.session_state.pop(key, None)
            st.rerun()
