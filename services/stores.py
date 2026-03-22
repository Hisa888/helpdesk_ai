from pathlib import Path
from datetime import datetime
import csv
import pandas as pd

def ensure_dir(p: Path):
    p.mkdir(exist_ok=True)

def save_log(log_path: Path, user_q: str, answer: str, used_hits):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    parts = []
    for i, (row, score) in enumerate((used_hits or [])[:3], 1):
        cat = str(getattr(row, "get", lambda k, d=None: d)("category", ""))
        q = str(getattr(row, "get", lambda k, d=None: d)("question", "")).replace("\n", " ").strip()
        parts.append(f"FAQ{i}:{float(score):.3f}:{cat}:{q[:60]}")
    used_faq = " | ".join(parts) if parts else ""
    best_score = f"{float(used_hits[0][1]):.3f}" if used_hits else ""

    header = ["timestamp", "user_question", "answer", "best_score", "used_faq"]
    exists = log_path.exists()

    with log_path.open("a", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header)
        if not exists:
            w.writeheader()
        w.writerow({
            "timestamp": now,
            "user_question": user_q,
            "answer": answer,
            "best_score": best_score,
            "used_faq": used_faq
        })

def save_unknown_raw(unknown_raw_path: Path, user_q: str, best_score: float = 0.0):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    header = ["timestamp", "question", "best_score"]
    exists = unknown_raw_path.exists()

    with unknown_raw_path.open("a", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header)
        if not exists:
            w.writeheader()
        w.writerow({
            "timestamp": now,
            "question": user_q,
            "best_score": round(float(best_score), 3)
        })

def load_unknown_agg(unknown_raw_path: Path) -> pd.DataFrame:
    if not unknown_raw_path.exists():
        return pd.DataFrame(columns=["question", "count"])
    df = pd.read_csv(unknown_raw_path, encoding="utf-8-sig")
    if "question" not in df.columns:
        return pd.DataFrame(columns=["question", "count"])
    agg = df.groupby("question").size().reset_index(name="count").sort_values("count", ascending=False)
    return agg.reset_index(drop=True)

def backup_faq_file(faq_path: Path, backups_dir: Path) -> str:
    backups_dir.mkdir(exist_ok=True)
    if faq_path.exists():
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = backups_dir / f"faq_{ts}.csv"
        df = pd.read_csv(faq_path, encoding="utf-8-sig") if faq_path.exists() else pd.DataFrame()
        df.to_csv(backup_path, index=False, encoding="utf-8-sig")
        return str(backup_path)
    return ""

def append_faq_row(faq_path: Path, category: str, owner: str, question: str, answer: str):
    if faq_path.exists():
        df = pd.read_csv(faq_path, encoding="utf-8-sig")
    else:
        df = pd.DataFrame(columns=["category", "owner", "question", "answer"])

    for col in ["category", "owner", "question", "answer"]:
        if col not in df.columns:
            df[col] = ""

    new_row = {
        "category": category or "",
        "owner": owner or "",
        "question": (question or "").strip(),
        "answer": (answer or "").strip(),
    }
    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    df.to_csv(faq_path, index=False, encoding="utf-8-sig")
