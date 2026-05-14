from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any


@dataclass(frozen=True)
class TenantLicense:
    tenant_id: str
    license_type: str = "trial"
    expire_date: date | None = None
    enabled: bool = True
    note: str = ""

    @property
    def is_trial(self) -> bool:
        return str(self.license_type or "").strip().lower() in ("trial", "demo", "monitor", "free")

    @property
    def is_expired(self) -> bool:
        return bool(self.enabled and self.expire_date and date.today() > self.expire_date)

    @property
    def remaining_days(self) -> int | None:
        if not self.expire_date:
            return None
        return (self.expire_date - date.today()).days



def _license_db_path() -> Path:
    return Path(os.environ.get("TENANT_LICENSE_DB", "runtime_data/tenant_licenses.db"))


def ensure_tenant_license_schema(db_path: Path | None = None) -> Path:
    """会社単位のライセンスDBを作成・更新する。既存DBは壊さず不足カラムのみ追加。"""
    path = db_path or _license_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tenant_licenses (
                tenant_id TEXT PRIMARY KEY,
                company_name TEXT DEFAULT '',
                license_type TEXT DEFAULT 'trial',
                expire_date TEXT DEFAULT '',
                enabled TEXT DEFAULT 'TRUE',
                max_users INTEGER DEFAULT 0,
                allow_search_after_expired TEXT DEFAULT 'TRUE',
                admin_locked_after_expired TEXT DEFAULT 'TRUE',
                max_questions_after_expired INTEGER DEFAULT 3,
                note TEXT DEFAULT '',
                updated_at TEXT DEFAULT ''
            )
            """
        )
        existing = {row[1] for row in conn.execute("PRAGMA table_info(tenant_licenses)").fetchall()}
        add_cols = {
            "company_name": "TEXT DEFAULT ''",
            "license_type": "TEXT DEFAULT 'trial'",
            "expire_date": "TEXT DEFAULT ''",
            "enabled": "TEXT DEFAULT 'TRUE'",
            "max_users": "INTEGER DEFAULT 0",
            "allow_search_after_expired": "TEXT DEFAULT 'TRUE'",
            "admin_locked_after_expired": "TEXT DEFAULT 'TRUE'",
            "max_questions_after_expired": "INTEGER DEFAULT 3",
            "note": "TEXT DEFAULT ''",
            "updated_at": "TEXT DEFAULT ''",
        }
        for col, ddl in add_cols.items():
            if col not in existing:
                conn.execute(f"ALTER TABLE tenant_licenses ADD COLUMN {col} {ddl}")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tenant_licenses_expire_date ON tenant_licenses(expire_date)")
    return path


def _load_license_from_db(tenant_id: str) -> TenantLicense | None:
    path = ensure_tenant_license_schema()
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM tenant_licenses WHERE lower(tenant_id)=lower(?)",
            (tenant_id,),
        ).fetchone()
        if not row:
            return None
        return TenantLicense(
            tenant_id=_clean(row["tenant_id"]),
            license_type=_clean(row["license_type"]) or "trial",
            expire_date=_parse_date(row["expire_date"]),
            enabled=_as_bool(row["enabled"], True),
            note=_clean(row["note"]),
        )


def upsert_default_tenant_license_if_missing(tenant_id: str, license_info: TenantLicense) -> None:
    """初回起動時に、会社IDの行がなければDBへ登録する。"""
    path = ensure_tenant_license_schema()
    with sqlite3.connect(path) as conn:
        exists = conn.execute(
            "SELECT 1 FROM tenant_licenses WHERE lower(tenant_id)=lower(?)",
            (tenant_id,),
        ).fetchone()
        if exists:
            return
        conn.execute(
            """
            INSERT INTO tenant_licenses
              (tenant_id, license_type, expire_date, enabled, allow_search_after_expired,
               admin_locked_after_expired, max_questions_after_expired, note, updated_at)
            VALUES (?, ?, ?, ?, 'TRUE', 'TRUE', 3, ?, ?)
            """,
            (
                tenant_id,
                license_info.license_type,
                license_info.expire_date.isoformat() if license_info.expire_date else "",
                "TRUE" if license_info.enabled else "FALSE",
                license_info.note,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )


def _secret_raw(st, name: str, default: Any = None) -> Any:
    try:
        if name in st.secrets:
            return st.secrets.get(name, default)
    except Exception:
        pass
    return os.environ.get(name, default)


def _clean(value: object) -> str:
    return str(value or "").strip().strip("'\"").strip()


def _as_bool(value: object, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in ("1", "true", "yes", "y", "on", "あり", "有効", "enabled"):
        return True
    if text in ("0", "false", "no", "n", "off", "なし", "無効", "disabled"):
        return False
    return default


def _parse_date(value: object) -> date | None:
    text = _clean(value)
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _parse_license_value(tenant_id: str, value: object) -> TenantLicense:
    """Parse one tenant license definition.

    Supported examples:
      demo = "trial:2026-06-01:true"
      demo = { license_type = "trial", expire_date = "2026-06-01", enabled = true }
    """
    if isinstance(value, dict) or hasattr(value, "items"):
        try:
            return TenantLicense(
                tenant_id=tenant_id,
                license_type=_clean(value.get("license_type", value.get("type", "trial"))) or "trial",
                expire_date=_parse_date(value.get("expire_date", value.get("expires", ""))),
                enabled=_as_bool(value.get("enabled", True), True),
                note=_clean(value.get("note", "")),
            )
        except Exception:
            pass

    text = str(value or "")
    cols = [_clean(x) for x in text.split(":")]
    return TenantLicense(
        tenant_id=tenant_id,
        license_type=cols[0] if len(cols) >= 1 and cols[0] else "trial",
        expire_date=_parse_date(cols[1] if len(cols) >= 2 else ""),
        enabled=_as_bool(cols[2] if len(cols) >= 3 else True, True),
        note=cols[3] if len(cols) >= 4 else "",
    )


def get_tenant_license(st, tenant_id: str) -> TenantLicense:
    tenant = _clean(tenant_id).lower() or "demo"

    # 運営者(owner)は会社ライセンス管理を行うため、トライアル期限でロックしない。
    try:
        if str(st.session_state.get("tenant_role", "")).strip().lower() == "owner":
            return TenantLicense(tenant_id=tenant, license_type="owner", expire_date=None, enabled=True, note="owner")
    except Exception:
        pass

    # secrets.toml の DEFAULT_* は「デモ/自動ログイン時の現在設定」として扱う。
    # 既存DBに古い期限が残っていても、DEFAULT_TENANT_ID と一致する会社IDは
    # secrets.toml の DEFAULT_TRIAL_EXPIRE_DATE を優先して同期する。
    default_tenant = _clean(_secret_raw(st, "DEFAULT_TENANT_ID", os.environ.get("DEFAULT_TENANT_ID", "demo"))).lower() or "demo"
    default_expire_raw = _secret_raw(st, "DEFAULT_TRIAL_EXPIRE_DATE", os.environ.get("DEFAULT_TRIAL_EXPIRE_DATE", ""))
    default_expire = _parse_date(default_expire_raw)
    default_type_raw = _secret_raw(st, "DEFAULT_LICENSE_TYPE", os.environ.get("DEFAULT_LICENSE_TYPE", "trial"))
    default_enabled_raw = _secret_raw(st, "DEFAULT_LICENSE_ENABLED", os.environ.get("DEFAULT_LICENSE_ENABLED", True))
    use_default_override = (tenant == default_tenant and default_expire is not None)

    # 1) 会社単位DBを参照する。
    #    ただし DEFAULT_TENANT_ID の期限は secrets.toml を優先して、DBへも同期する。
    db_license = _load_license_from_db(tenant)
    if db_license is not None:
        if use_default_override:
            fixed = TenantLicense(
                tenant_id=db_license.tenant_id or tenant,
                license_type=_clean(default_type_raw) or db_license.license_type or "trial",
                expire_date=default_expire,
                enabled=_as_bool(default_enabled_raw, db_license.enabled),
                note=db_license.note,
            )
            try:
                path = ensure_tenant_license_schema()
                with sqlite3.connect(path) as conn:
                    conn.execute(
                        """
                        UPDATE tenant_licenses
                           SET license_type=?, expire_date=?, enabled=?, updated_at=?
                         WHERE lower(tenant_id)=lower(?)
                        """,
                        (
                            fixed.license_type,
                            fixed.expire_date.isoformat() if fixed.expire_date else "",
                            "TRUE" if fixed.enabled else "FALSE",
                            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            tenant,
                        ),
                    )
            except Exception:
                pass
            return fixed

        if db_license.expire_date is None and db_license.is_trial and default_expire is not None:
            fixed = TenantLicense(
                tenant_id=db_license.tenant_id,
                license_type=db_license.license_type or "trial",
                expire_date=default_expire,
                enabled=db_license.enabled,
                note=db_license.note,
            )
            try:
                path = ensure_tenant_license_schema()
                with sqlite3.connect(path) as conn:
                    conn.execute(
                        "UPDATE tenant_licenses SET expire_date=?, updated_at=? WHERE lower(tenant_id)=lower(?)",
                        (default_expire.isoformat(), datetime.now().strftime("%Y-%m-%d %H:%M:%S"), tenant),
                    )
            except Exception:
                pass
            return fixed
        return db_license

    # 2) DBに未登録の場合は、従来どおり secrets / 環境変数を参照する。
    raw = _secret_raw(st, "TENANT_LICENSES", "")

    if isinstance(raw, dict) or hasattr(raw, "items"):
        try:
            for key, value in raw.items():
                if _clean(key).lower() == tenant:
                    return _parse_license_value(tenant, value)
        except Exception:
            pass
    else:
        # Environment variable format:
        # TENANT_LICENSES="demo=trial:2026-06-01:true, customer-a=trial:2026-05-31:true"
        for part in str(raw or "").replace(";", ",").replace("\n", ",").split(","):
            if "=" not in part:
                continue
            key, value = part.split("=", 1)
            if _clean(key).lower() == tenant:
                return _parse_license_value(tenant, value)

    fallback = TenantLicense(
        tenant_id=tenant,
        license_type=_clean(default_type_raw) or "trial",
        expire_date=default_expire,
        enabled=_as_bool(default_enabled_raw, True),
    )
    # 初回アクセスした会社IDはDBへ登録して、以後はDBで管理できるようにする。
    try:
        upsert_default_tenant_license_if_missing(tenant, fallback)
    except Exception:
        pass
    return fallback



def list_tenant_licenses() -> list[dict]:
    """会社ライセンス一覧を取得する。owner管理画面用。"""
    path = ensure_tenant_license_schema()
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT tenant_id, company_name, license_type, expire_date, enabled,
                   max_users, allow_search_after_expired, admin_locked_after_expired,
                   max_questions_after_expired, note, updated_at
              FROM tenant_licenses
             ORDER BY lower(tenant_id)
            """
        ).fetchall()
        return [dict(row) for row in rows]


def upsert_tenant_license(
    *,
    tenant_id: str,
    company_name: str | None = None,
    license_type: str | None = None,
    expire_date: str | None = None,
    enabled: bool | str | None = None,
    max_users: int | None = None,
    allow_search_after_expired: bool | str | None = None,
    admin_locked_after_expired: bool | str | None = None,
    max_questions_after_expired: int | None = None,
    note: str | None = None,
    updated_at: str | None = None,
) -> None:
    """会社ライセンスを追加/更新する。Noneの項目は既存値を維持する。"""
    tenant = _clean(tenant_id).lower()
    if not tenant:
        raise ValueError("tenant_id is required")

    path = ensure_tenant_license_schema()
    now = updated_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        current = conn.execute(
            "SELECT * FROM tenant_licenses WHERE lower(tenant_id)=lower(?)",
            (tenant,),
        ).fetchone()
        if current is None:
            conn.execute(
                """
                INSERT INTO tenant_licenses
                  (tenant_id, company_name, license_type, expire_date, enabled, max_users,
                   allow_search_after_expired, admin_locked_after_expired,
                   max_questions_after_expired, note, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tenant,
                    _clean(company_name),
                    _clean(license_type) or "trial",
                    _clean(expire_date),
                    "TRUE" if _as_bool(enabled, True) else "FALSE",
                    int(max_users or 0),
                    "TRUE" if _as_bool(allow_search_after_expired, True) else "FALSE",
                    "TRUE" if _as_bool(admin_locked_after_expired, True) else "FALSE",
                    int(max_questions_after_expired if max_questions_after_expired is not None else 3),
                    _clean(note),
                    now,
                ),
            )
            return

        def keep(col: str, value: object) -> object:
            return current[col] if value is None else value

        conn.execute(
            """
            UPDATE tenant_licenses
               SET company_name=?, license_type=?, expire_date=?, enabled=?, max_users=?,
                   allow_search_after_expired=?, admin_locked_after_expired=?,
                   max_questions_after_expired=?, note=?, updated_at=?
             WHERE lower(tenant_id)=lower(?)
            """,
            (
                _clean(keep("company_name", company_name)),
                _clean(keep("license_type", license_type)) or "trial",
                _clean(keep("expire_date", expire_date)),
                "TRUE" if _as_bool(keep("enabled", enabled), True) else "FALSE",
                int(keep("max_users", max_users) or 0),
                "TRUE" if _as_bool(keep("allow_search_after_expired", allow_search_after_expired), True) else "FALSE",
                "TRUE" if _as_bool(keep("admin_locked_after_expired", admin_locked_after_expired), True) else "FALSE",
                int(keep("max_questions_after_expired", max_questions_after_expired) or 3),
                _clean(keep("note", note)),
                now,
                tenant,
            ),
        )


def delete_tenant_license(tenant_id: str) -> None:
    """会社ライセンス行だけを削除する。FAQ/RAG/ログの実データは消さない。"""
    tenant = _clean(tenant_id).lower()
    if not tenant:
        return
    path = ensure_tenant_license_schema()
    with sqlite3.connect(path) as conn:
        conn.execute("DELETE FROM tenant_licenses WHERE lower(tenant_id)=lower(?)", (tenant,))

def render_trial_status_banner(st, license_info: TenantLicense, *, contact_link: str = "") -> None:
    if not license_info.enabled:
        st.error("この会社IDは現在停止中です。利用再開をご希望の場合は管理者へお問い合わせください。")
        return

    if not license_info.is_trial:
        return

    remaining = license_info.remaining_days
    if remaining is None:
        st.info("無料トライアル期間中です。")
        return

    if remaining >= 0:
        label = f"残り{remaining}日" if remaining != 0 else "本日まで"
        st.markdown(
            f"""
<div class=\"trial-license-card\" style=\"border:1px solid #bfdbfe;background:#eff6ff;border-radius:16px;padding:14px 16px;margin:10px 0 16px 0;\">
  <div style=\"font-weight:800;color:#1e3a8a;font-size:16px;\">無料トライアル期間中</div>
  <div style=\"color:#334155;margin-top:4px;\">{label}利用できます。</div>
</div>
            """,
            unsafe_allow_html=True,
        )


def render_trial_expired_screen(st, license_info: TenantLicense, *, contact_link: str = "", company_name: str = "") -> None:
    expire_text = license_info.expire_date.strftime("%Y-%m-%d") if license_info.expire_date else "未設定"
    button_html = ""
    if contact_link:
        button_html = f"""
<a href=\"{contact_link}\" target=\"_blank\" rel=\"noopener noreferrer\" style=\"display:inline-block;margin-top:16px;background:#2563eb;color:white;text-decoration:none;font-weight:800;padding:12px 20px;border-radius:999px;box-shadow:0 10px 24px rgba(37,99,235,.25);\">導入相談</a>
        """
    st.markdown(
        f"""
<div style=\"max-width:760px;margin:40px auto 24px auto;background:white;border:1px solid #e2e8f0;border-radius:24px;padding:30px;box-shadow:0 20px 50px rgba(15,23,42,.10);text-align:center;\">
  <div style=\"display:inline-block;background:#fff7ed;color:#9a3412;border:1px solid #fed7aa;border-radius:999px;padding:6px 12px;font-size:13px;font-weight:800;margin-bottom:14px;\">無料トライアル終了</div>
  <div style=\"font-size:28px;font-weight:900;color:#0f172a;margin-bottom:10px;\">無料トライアル期間が終了しました</div>
  <div style=\"color:#475569;line-height:1.8;font-size:15px;\">
    継続利用をご希望の場合は導入相談へお進みください。<br>
    会社ID: <b>{license_info.tenant_id}</b> ／ 期限日: <b>{expire_text}</b>
  </div>
  {button_html}
  <div style=\"margin-top:18px;color:#64748b;font-size:13px;line-height:1.7;\">
    評価期間中のご要望や改善希望も、導入相談時にそのままお伝えください。<br>
    現場運用に合わせて調整できます。
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )


def should_lock_trial(license_info: TenantLicense) -> bool:
    """期限切れ時に通常画面を止めるかどうか。"""
    if not license_info.enabled:
        return True
    return license_info.is_trial and license_info.is_expired
