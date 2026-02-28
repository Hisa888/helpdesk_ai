import os
import hmac

def check_password(input_password: str) -> bool:
    """管理者パスワードを安全に比較（環境変数/Streamlit Secrets）。"""
    admin_pw = os.getenv("ADMIN_PASSWORD", "")
    if not admin_pw:
        return False
    return hmac.compare_digest(input_password or "", admin_pw)
