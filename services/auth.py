import os
import hmac
import streamlit as st


def _get_admin_password() -> str:
    """
    管理者パスワードを取得
    優先順位:
    1. Streamlit secrets の ADMIN_PASSWORD
    2. 環境変数 ADMIN_PASSWORD
    3. デフォルト値
    """
    try:
        if "ADMIN_PASSWORD" in st.secrets:
            return str(st.secrets["ADMIN_PASSWORD"])
    except Exception:
        pass

    return os.getenv("ADMIN_PASSWORD", "admin123")


def check_password(password: str) -> bool:
    """
    入力されたパスワードが正しいか判定
    """
    expected_password = _get_admin_password()
    return hmac.compare_digest(str(password or ""), str(expected_password or ""))