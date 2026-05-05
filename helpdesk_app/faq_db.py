from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path

import pandas as pd

FAQ_DB_NAME = "helpdesk.db"
FAQ_TABLE_NAME = "faq"
CANDIDATE_LEARNING_TABLE_NAME = "candidate_learning"
FAQ_COLUMNS = [
    "faq_id", "question", "answer", "intent", "keywords", "category",
    "answer_format", "enabled", "updated_at", "updated_by", "note",
    "required_keywords", "exclude_keywords", "ambiguity_keywords",
    "prefer_candidate", "auto_answer_allowed",
]

# DB読み込みキャッシュ。
# FAQ検索時に同一DBを短時間に何度も read_sql しないよう、
# dbファイルの mtime/size が変わらない限り DataFrame を再利用する。
_DB_DF_CACHE: dict[str, tuple[tuple[int, int], float, pd.DataFrame]] = {}
_DB_CACHE_TTL_SEC = float(os.environ.get("HELP_DESK_FAQ_DB_CACHE_TTL", "30") or 30)


def _db_signature(db_path: Path) -> tuple[int, int]:
    try:
        st = db_path.stat()
        wal_path = Path(str(db_path) + "-wal")
        wal_mtime = wal_path.stat().st_mtime_ns if wal_path.exists() else 0
        return (max(st.st_mtime_ns, wal_mtime), int(st.st_size))
    except Exception:
        return (0, 0)


def clear_faq_db_cache(db_path: Path | str | None = None) -> None:
    """FAQ DB読み込みキャッシュをクリアする。保存後・管理画面更新後に使用。"""
    if db_path is None:
        _DB_DF_CACHE.clear()
        return
    _DB_DF_CACHE.pop(str(Path(db_path)), None)


def is_managed_faq_path(path: Path | str) -> bool:
    """SQLite管理対象のFAQパス判定。

    旧構成: runtime_data/faq.csv
    新構成: runtime_data/tenants/{company_id}/faq.csv

    会社別分離後もDB化の高速化を使えるよう、runtime_data配下のfaq.csvを
    管理対象にする。
    """
    p = Path(path)
    if p.name.lower() != "faq.csv":
        return False
    return any(parent.name == "runtime_data" for parent in p.parents)


def db_path_for_faq_path(faq_path: Path | str) -> Path:
    return Path(faq_path).parent / FAQ_DB_NAME


def _connect(db_path: Path) -> sqlite3.Connection:
    """SQLite接続を返す。

    高速化ポイント:
    - WAL / NORMAL / MEMORY / cache_size を設定して読み書きを軽くする。
    - ただし一部のStreamlitローカル環境では .db-wal/.db-shm の監視で不安定になるため、
      HELP_DESK_SQLITE_WAL=0 を指定すると DELETE ジャーナルへ戻せる。
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.execute("PRAGMA busy_timeout=30000")
    use_wal = str(os.environ.get("HELP_DESK_SQLITE_WAL", "1")).strip().lower() not in {"0", "false", "no", "off"}
    try:
        conn.execute("PRAGMA journal_mode=WAL" if use_wal else "PRAGMA journal_mode=DELETE")
    except Exception:
        try:
            conn.execute("PRAGMA journal_mode=DELETE")
        except Exception:
            pass
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA cache_size=-64000")
    return conn


def ensure_schema(db_path: Path) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {FAQ_TABLE_NAME} (
                faq_id TEXT PRIMARY KEY,
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                intent TEXT DEFAULT '',
                keywords TEXT DEFAULT '',
                category TEXT DEFAULT '',
                answer_format TEXT DEFAULT 'markdown',
                enabled TEXT DEFAULT 'TRUE',
                updated_at TEXT DEFAULT '',
                updated_by TEXT DEFAULT '',
                note TEXT DEFAULT '',
                required_keywords TEXT DEFAULT '',
                exclude_keywords TEXT DEFAULT '',
                ambiguity_keywords TEXT DEFAULT '',
                prefer_candidate TEXT DEFAULT '',
                auto_answer_allowed TEXT DEFAULT ''
            )
            """
        )
        # 既存DBを壊さずに新列を追加する。
        existing_cols = {row[1] for row in conn.execute(f"PRAGMA table_info({FAQ_TABLE_NAME})").fetchall()}
        for col in FAQ_COLUMNS:
            if col not in existing_cols:
                conn.execute(f"ALTER TABLE {FAQ_TABLE_NAME} ADD COLUMN {col} TEXT DEFAULT ''")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_faq_question ON faq(question)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_faq_enabled ON faq(enabled)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_faq_category ON faq(category)")
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {CANDIDATE_LEARNING_TABLE_NAME} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                user_question TEXT NOT NULL,
                selected_faq_id TEXT DEFAULT '',
                selected_question TEXT DEFAULT '',
                score REAL DEFAULT 0,
                category TEXT DEFAULT ''
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_candidate_learning_user_question ON candidate_learning(user_question)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_candidate_learning_faq_id ON candidate_learning(selected_faq_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_candidate_learning_timestamp ON candidate_learning(timestamp)")
        conn.commit()


def load_faq_df_from_db(faq_path: Path | str) -> pd.DataFrame | None:
    faq_path = Path(faq_path)
    if not is_managed_faq_path(faq_path):
        return None
    db_path = db_path_for_faq_path(faq_path)
    if not db_path.exists():
        return None
    ensure_schema(db_path)

    cache_key = str(db_path)
    sig = _db_signature(db_path)
    now = time.time()
    cached = _DB_DF_CACHE.get(cache_key)
    if cached is not None:
        cached_sig, cached_at, cached_df = cached
        if cached_sig == sig and (now - cached_at) <= _DB_CACHE_TTL_SEC:
            return cached_df.copy()

    with _connect(db_path) as conn:
        df = pd.read_sql_query(
            f"SELECT {', '.join(FAQ_COLUMNS)} FROM {FAQ_TABLE_NAME} ORDER BY rowid",
            conn,
        )
    for col in FAQ_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    df = df[FAQ_COLUMNS]
    _DB_DF_CACHE[cache_key] = (sig, now, df.copy())
    return df


def save_faq_df_to_db(faq_path: Path | str, df: pd.DataFrame) -> Path:
    """FAQ DataFrameをSQLiteへ高速同期する。

    以前の方式: DELETE全件削除 -> 全件INSERT
    現在の方式: FAQ_ID単位でUPSERT -> 今回DFに存在しないFAQ_IDだけ削除

    これにより、CSVアップロード/管理画面更新時に既存DBを毎回作り直さず、
    既存データを保ちながら差分反映できる。
    """
    faq_path = Path(faq_path)
    db_path = db_path_for_faq_path(faq_path)
    ensure_schema(db_path)
    clean = df.copy() if df is not None else pd.DataFrame(columns=FAQ_COLUMNS)
    for col in FAQ_COLUMNS:
        if col not in clean.columns:
            clean[col] = ""
    clean = clean[FAQ_COLUMNS].fillna("").astype(str)
    clean = clean[clean["faq_id"].astype(str).str.strip() != ""].copy()

    rows = list(clean.itertuples(index=False, name=None))
    placeholders = ",".join(["?"] * len(FAQ_COLUMNS))
    insert_sql = f"INSERT INTO {FAQ_TABLE_NAME} ({', '.join(FAQ_COLUMNS)}) VALUES ({placeholders})"

    # FAQ全体を保存する場面では、UPSERT+削除差分よりも
    # DELETE一括 + executemany一括INSERT の方がSQLiteでは速いことが多い。
    # 既存FAQを消さない制御は、この関数へ渡す前のDataFrame生成
    # apply_faq_upload_operations 側で行っているため、DB内部は高速な全置換でよい。
    # 差分UPSERTに戻したい場合のみ HELP_DESK_FAQ_DB_SYNC_MODE=upsert を指定。
    sync_mode = str(os.environ.get("HELP_DESK_FAQ_DB_SYNC_MODE", "replace")).strip().lower()

    with _connect(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        if sync_mode == "upsert":
            incoming_ids = [str(r[0]).strip() for r in rows if str(r[0]).strip()]
            update_cols = [c for c in FAQ_COLUMNS if c != "faq_id"]
            update_sql = ", ".join([f"{c}=excluded.{c}" for c in update_cols])
            upsert_sql = (
                f"INSERT INTO {FAQ_TABLE_NAME} ({', '.join(FAQ_COLUMNS)}) "
                f"VALUES ({placeholders}) "
                f"ON CONFLICT(faq_id) DO UPDATE SET {update_sql}"
            )
            if rows:
                conn.executemany(upsert_sql, rows)
            conn.execute("CREATE TEMP TABLE IF NOT EXISTS _faq_sync_ids (faq_id TEXT PRIMARY KEY)")
            conn.execute("DELETE FROM _faq_sync_ids")
            if incoming_ids:
                conn.executemany("INSERT OR IGNORE INTO _faq_sync_ids(faq_id) VALUES (?)", [(x,) for x in incoming_ids])
                conn.execute(
                    f"DELETE FROM {FAQ_TABLE_NAME} "
                    f"WHERE faq_id NOT IN (SELECT faq_id FROM _faq_sync_ids)"
                )
            else:
                conn.execute(f"DELETE FROM {FAQ_TABLE_NAME}")
        else:
            conn.execute(f"DELETE FROM {FAQ_TABLE_NAME}")
            if rows:
                conn.executemany(insert_sql, rows)
        conn.commit()

    clear_faq_db_cache(db_path)
    return db_path



def default_runtime_faq_path() -> Path:
    """通常実行時のFAQパスを返す。answer_panelなどFAQ_PATHを持たない場所で使う。"""
    return Path("runtime_data") / "faq.csv"


def save_candidate_learning_to_db(
    *,
    user_question: str,
    selected_faq_id: str = "",
    selected_question: str = "",
    score: float = 0.0,
    category: str = "",
    faq_path: Path | str | None = None,
) -> bool:
    """候補クリック学習ログをSQLiteへ保存する。

    CSVログは確認・ダウンロード用、SQLiteは本番の永続学習用として使う。
    失敗時はFalseを返すだけで、画面操作は止めない。
    """
    try:
        fp = Path(faq_path) if faq_path is not None else default_runtime_faq_path()
        db_path = db_path_for_faq_path(fp)
        ensure_schema(db_path)
        ts = time.strftime("%Y-%m-%dT%H:%M:%S")
        with _connect(db_path) as conn:
            conn.execute(
                f"""
                INSERT INTO {CANDIDATE_LEARNING_TABLE_NAME}
                    (timestamp, user_question, selected_faq_id, selected_question, score, category)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    ts,
                    str(user_question or "").strip(),
                    str(selected_faq_id or "").strip(),
                    str(selected_question or "").strip(),
                    float(score or 0.0),
                    str(category or "").strip(),
                ),
            )
            conn.commit()
        return True
    except Exception:
        return False


def load_candidate_learning_from_db(
    faq_path: Path | str | None = None,
    *,
    limit: int = 500,
) -> list[dict[str, str]]:
    """SQLiteに保存した候補クリック学習ログを新しい順に取得する。"""
    try:
        fp = Path(faq_path) if faq_path is not None else default_runtime_faq_path()
        db_path = db_path_for_faq_path(fp)
        if not db_path.exists():
            return []
        ensure_schema(db_path)
        n = max(1, int(limit or 500))
        with _connect(db_path) as conn:
            rows = conn.execute(
                f"""
                SELECT user_question, selected_faq_id, selected_question, category, score, timestamp
                FROM {CANDIDATE_LEARNING_TABLE_NAME}
                WHERE TRIM(user_question) <> ''
                ORDER BY id DESC
                LIMIT ?
                """,
                (n,),
            ).fetchall()
        out: list[dict[str, str]] = []
        for user_question, selected_faq_id, selected_question, category, score, timestamp in rows:
            out.append({
                "user_question": str(user_question or "").strip(),
                "selected_faq_id": str(selected_faq_id or "").strip(),
                "selected_question": str(selected_question or "").strip(),
                "category": str(category or "").strip(),
                "score": str(score or ""),
                "timestamp": str(timestamp or ""),
                "source": "sqlite",
            })
        # 既存ロジックは末尾側を使うため、古い順に戻す。
        return list(reversed(out))
    except Exception:
        return []


def clear_candidate_learning_db(faq_path: Path | str | None = None) -> bool:
    """候補クリック学習ログをSQLiteから削除する。管理画面からのリセット用。"""
    try:
        fp = Path(faq_path) if faq_path is not None else default_runtime_faq_path()
        db_path = db_path_for_faq_path(fp)
        ensure_schema(db_path)
        with _connect(db_path) as conn:
            conn.execute(f"DELETE FROM {CANDIDATE_LEARNING_TABLE_NAME}")
            conn.commit()
        return True
    except Exception:
        return False

def sync_faq_csv_cache(faq_path: Path | str, df: pd.DataFrame) -> None:
    import csv
    faq_path = Path(faq_path)
    faq_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(faq_path, index=False, encoding="utf-8-sig", quoting=csv.QUOTE_ALL)


def initialize_faq_database(faq_path: Path | str, raw_csv_loader) -> bool:
    """Create runtime_data/helpdesk.db from existing faq.csv once.

    raw_csv_loader must read CSV without consulting this DB module.
    """
    faq_path = Path(faq_path)
    if not is_managed_faq_path(faq_path):
        return False
    db_path = db_path_for_faq_path(faq_path)
    if db_path.exists():
        # Git/手動配置などで faq.csv の方が新しい場合だけDBへ同期する。
        # 通常検索時はDBを正本にするため、毎回CSV全件読み込みはしない。
        try:
            if faq_path.exists() and faq_path.stat().st_mtime_ns > db_path.stat().st_mtime_ns:
                df = raw_csv_loader(faq_path)
                save_faq_df_to_db(faq_path, df)
        except Exception:
            pass
        return True
    if not faq_path.exists():
        ensure_schema(db_path)
        return True
    df = raw_csv_loader(faq_path)
    save_faq_df_to_db(faq_path, df)
    sync_faq_csv_cache(faq_path, df)
    return True
