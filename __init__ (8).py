import os
import hmac
import streamlit as st

def _get_admin_password() -> str:
    try:
        value = st.secrets.get("ADMIN_PASSWORD")  # type: ignore[attr-defined]
        if value:
            return str(value)
    except Exception:
        pass
    return os.environ.get("ADMIN_PASSWORD", "admin123")

def check_password(password: str) -> bool:
    expected = _get_admin_password()
    return hmac.compare_digest(str(password or ""), str(expected or ""))
