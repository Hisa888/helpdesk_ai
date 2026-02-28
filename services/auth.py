import os
import hmac

def check_password(input_password: str) -> bool:
    admin_pw = os.getenv("ADMIN_PASSWORD", "")
    if not admin_pw:
        return False
    return hmac.compare_digest(input_password or "", admin_pw)