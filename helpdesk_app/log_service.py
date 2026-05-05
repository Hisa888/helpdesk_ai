from __future__ import annotations

import csv
import re
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from helpdesk_app.faq_io import pick_question_column, read_csv_flexible
from helpdesk_app.modules.download_utils import (
    csv_bytes_as_utf8_sig as download_csv_bytes_as_utf8_sig,
    list_log_files as util_list_log_files,
    make_logs_zip as util_make_logs_zip,
)


def csv_bytes_as_utf8_sig(data) -> bytes:
    return download_csv_bytes_as_utf8_sig(data)


def list_log_files(log_dir: Path) -> list[Path]:
    return util_list_log_files(log_dir)


def make_logs_zip(files, *, log_dir: Path | None = None) -> bytes:
    return util_make_logs_zip(files, csv_bytes_fn=csv_bytes_as_utf8_sig)


def count_nohit_logs(*, log_dir: Path, days: int = 7):
    files = list_log_files(log_dir)
    if not files:
        return 0, 0, 0
    today_str = datetime.now().strftime("%Y%m%d")
    today = datetime.now().date()
    recent_days = {(today - timedelta(days=i)).strftime("%Y%m%d") for i in range(days)}
    today_count = recent_count = total_count = 0
    for p in files:
        m = re.match(r"nohit_(\d{8})\.csv$", Path(p).name)
        day = m.group(1) if m else ""
        try:
            cnt = int(len(read_csv_flexible(Path(p))))
        except Exception:
            cnt = 0
        total_count += cnt
        if day == today_str:
            today_count += cnt
        if day in recent_days:
            recent_count += cnt
    return today_count, recent_count, total_count


def read_interactions(*, log_dir: Path, days: int = 7) -> pd.DataFrame:
    frames = []
    for i in range(days):
        d = (datetime.now() - timedelta(days=i)).strftime("%Y%m%d")
        p = log_dir / f"interactions_{d}.csv"
        if p.exists():
            try:
                frames.append(read_csv_flexible(p))
            except Exception:
                pass
    if not frames:
        return pd.DataFrame(columns=["timestamp", "question", "matched", "best_score", "category"])
    df_all = pd.concat(frames, ignore_index=True)
    if "matched" in df_all.columns:
        df_all["matched"] = pd.to_numeric(df_all["matched"], errors="coerce").fillna(0).astype(int)
    else:
        df_all["matched"] = 0
    if "best_score" in df_all.columns:
        df_all["best_score"] = pd.to_numeric(df_all["best_score"], errors="coerce").fillna(0.0)
    else:
        df_all["best_score"] = 0.0
    if "category" not in df_all.columns:
        df_all["category"] = ""
    return df_all


def ensure_nohit_schema(path: Path):
    """既存nohit CSVが旧形式（timestamp,questionのみ）でも、新スキーマに移行する。"""
    cols = ["timestamp", "question", "device", "location", "network", "error_text", "impact", "channel"]
    if not path.exists():
        return cols

    try:
        with path.open("r", encoding="utf-8", errors="ignore") as f:
            header = f.readline().strip()
        header_cols = [h.strip() for h in header.split(",")] if header else []
    except Exception:
        header_cols = []

    if set(cols).issubset(set(header_cols)):
        return header_cols

    try:
        old_df = read_csv_flexible(path)
        if old_df is None:
            old_df = pd.DataFrame()
    except Exception:
        old_df = pd.DataFrame()

    if len(old_df) == 0:
        with path.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(cols)
        return cols

    qcol = pick_question_column(old_df.columns) or ("question" if "question" in old_df.columns else None)
    tcol = "timestamp" if "timestamp" in old_df.columns else None

    rows = []
    for _, r in old_df.iterrows():
        ts = str(r.get(tcol, "")).strip() if tcol else ""
        q = str(r.get(qcol, "")).strip() if qcol else ""
        if not q:
            continue
        rows.append([ts, q, "", "", "", "", "", ""])

    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        w.writerows(rows)

    return cols


def log_nohit(*, log_dir: Path, question: str, persist_callback=None, extra: dict | None = None) -> str:
    """該当なしログを追記して、記録したtimestamp（秒）を返す。"""
    if not question:
        return ""
    extra = extra or {}
    day = datetime.now().strftime("%Y%m%d")
    path = log_dir / f"nohit_{day}.csv"
    cols = ensure_nohit_schema(path)

    ts = datetime.now().isoformat(timespec="seconds")
    row = {
        "timestamp": ts,
        "question": question,
        "device": extra.get("device", ""),
        "location": extra.get("location", ""),
        "network": extra.get("network", ""),
        "error_text": extra.get("error_text", ""),
        "impact": extra.get("impact", ""),
        "channel": extra.get("channel", "web"),
    }

    try:
        is_new = not path.exists()
        with path.open("a", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            if is_new:
                w.writerow(cols)
            w.writerow([row.get(c, "") for c in cols])
        if callable(persist_callback):
            persist_callback(path)
    except Exception:
        pass
    return ts


def update_nohit_record(*, log_dir: Path, day: str, timestamp: str, question: str, extra: dict, persist_callback=None) -> bool:
    """同じday/timestamp/question の行があれば更新。無ければ追記。

    候補表示から「追加情報を記録」した場合は、まだ nohit 行が存在せず
    timestamp が空のことがあります。その場合でも保存失敗にせず、
    現在時刻の行として追記します。
    """
    if not day:
        day = datetime.now().strftime("%Y%m%d")
    if not timestamp:
        timestamp = datetime.now().isoformat(timespec="seconds")
    if not question:
        question = "追加情報"
    path = log_dir / f"nohit_{day}.csv"
    cols = ensure_nohit_schema(path)

    try:
        df_log = read_csv_flexible(path)
        if df_log is None:
            df_log = pd.DataFrame(columns=cols)
    except Exception:
        df_log = pd.DataFrame(columns=cols)

    for c in cols:
        if c not in df_log.columns:
            df_log[c] = ""

    mask = (df_log["timestamp"].astype(str) == str(timestamp)) & (df_log["question"].astype(str) == str(question))
    idxs = df_log.index[mask].tolist()
    if idxs:
        i = idxs[0]
        for k, v in (extra or {}).items():
            if k in df_log.columns:
                df_log.at[i, k] = v
        df_log.at[i, "channel"] = extra.get("channel", df_log.at[i, "channel"] or "web")
    else:
        row = {c: "" for c in cols}
        row["timestamp"] = timestamp
        row["question"] = question
        for k, v in (extra or {}).items():
            if k in row:
                row[k] = v
        if not row.get("channel"):
            row["channel"] = "web"
        df_log = pd.concat([df_log, pd.DataFrame([row])], ignore_index=True)

    try:
        with path.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(cols)
            for _, r in df_log[cols].iterrows():
                w.writerow([str(r.get(c, "")) for c in cols])
        if callable(persist_callback):
            persist_callback(path)
        return True
    except Exception:
        return False


def seed_nohit_questions(*, log_dir: Path, persist_callback=None, n: int = 20) -> int:
    """本番前のデモ用：情シス定番のnohit質問を今日のログに追加する。"""
    seeds = [
        "VPNにつながらない", "Outlookの送受信ができない", "Teamsにログインできない", "パスワードを忘れた",
        "アカウントがロックされた", "共有フォルダにアクセスできない", "プリンタが印刷できない", "Wi-Fiが頻繁に切れる",
        "PCが重い", "PCが固まる", "Excelが起動しない", "Excelがフリーズする", "OneDriveが同期しない",
        "メール添付ファイルが開けない", "二段階認証が通らない", "カメラが映らない", "マイクが認識されない",
        "ソフトのインストール申請方法が分からない", "Windows更新が終わらない", "画面が真っ黒になる",
    ]
    added = 0
    for q in seeds[:n]:
        ts = log_nohit(log_dir=log_dir, question=q, persist_callback=persist_callback, extra={"channel": "seed"})
        if ts:
            added += 1
    return added


def log_interaction(*, log_dir: Path, question: str, matched: bool, best_score: float, category: str, persist_callback=None):
    """全ての質問をログ化（削減時間の見える化用）: logs/interactions_YYYYMMDD.csv"""
    if not question:
        return
    day = datetime.now().strftime("%Y%m%d")
    path = log_dir / f"interactions_{day}.csv"
    try:
        is_new = not path.exists()
        with path.open("a", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            if is_new:
                w.writerow(["timestamp", "question", "matched", "best_score", "category"])
            w.writerow([datetime.now().isoformat(timespec="seconds"), question, int(bool(matched)), float(best_score), category or ""])
        if callable(persist_callback):
            persist_callback(path)
    except Exception:
        pass



def normalize_question(q: str) -> str:
    q = (q or "").strip().lower()
    q = re.sub(r"\s+", " ", q)
    q = re.sub(r"[\u3000\s\t\r\n]+", " ", q)
    q = re.sub(r"[!！?？。、,.，:：;；\-_=+~`'\"()（）\[\]{}<>＜＞/\\|@#%^&*]", "", q)
    return q.strip()



def load_nohit_questions_from_logs(files, max_questions: int = 100) -> list[str]:
    """nohit_*.csv から質問を収集（新しいログから優先）。文字コード/カラム揺れに強く読む。"""
    questions: list[str] = []
    seen: set[str] = set()
    for p in files:
        try:
            _df = read_csv_flexible(Path(p))
            if _df is None or len(_df) == 0:
                continue

            qcol = pick_question_column(_df.columns)
            if not qcol:
                continue

            for q in _df[qcol].fillna("").astype(str).tolist():
                nq = normalize_question(q)
                if not nq:
                    continue
                if nq in seen:
                    continue
                seen.add(nq)
                questions.append(q.strip())
                if len(questions) >= max_questions:
                    return questions
        except Exception:
            continue
    return questions
