from __future__ import annotations

import os
from typing import Any


DEMO_MODE_VALUES = {"demo", "demonstration", "sales", "staging", "test", "local"}
PRODUCTION_MODE_VALUES = {"prod", "production", "real", "customer", "honban", "本番"}


def _get_from_secrets(st: Any, key: str) -> str | None:
    try:
        value = st.secrets.get(key, None)  # type: ignore[attr-defined]
    except Exception:
        value = None
    if value is None:
        return None
    return str(value).strip()


def get_app_mode(st: Any | None = None, default: str = "demo") -> str:
    """画面モードを取得する。

    設定例:
      .streamlit/secrets.toml
        APP_MODE = "demo"        # デモ・営業用
        APP_MODE = "production"  # 本番・顧客利用用

      環境変数でも可:
        APP_MODE=production

    未設定時は既存挙動を壊さないため demo とする。
    """
    value = None
    if st is not None:
        value = _get_from_secrets(st, "APP_MODE")
    if not value:
        value = os.environ.get("APP_MODE", "").strip()
    value = (value or default or "demo").strip().lower()
    if value in {"production", "prod", "honban", "customer", "real", "本番"}:
        return "production"
    return "demo"


def is_demo_mode(app_mode: str | None) -> bool:
    return str(app_mode or "demo").strip().lower() != "production"


def is_production_mode(app_mode: str | None) -> bool:
    return not is_demo_mode(app_mode)


def app_mode_label(app_mode: str | None) -> str:
    return "デモ用" if is_demo_mode(app_mode) else "本番用"
