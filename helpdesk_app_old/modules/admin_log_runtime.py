from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from helpdesk_app.log_service import (
    count_nohit_logs as svc_count_nohit_logs,
    list_log_files as svc_list_log_files,
    load_nohit_questions_from_logs as svc_load_nohit_questions_from_logs,
    log_interaction as svc_log_interaction,
    log_nohit as svc_log_nohit,
    make_logs_zip as svc_make_logs_zip,
    read_interactions as svc_read_interactions,
    seed_nohit_questions as svc_seed_nohit_questions,
    update_nohit_record as svc_update_nohit_record,
    csv_bytes_as_utf8_sig as svc_csv_bytes_as_utf8_sig,
)


def format_minutes_to_hours(minutes: float) -> str:
    try:
        value = float(minutes)
    except Exception:
        value = 0.0
    return f"{int(round(value))}分" if value < 60 else f"{value / 60.0:.1f}時間"



def create_admin_log_runtime(*, log_dir: Path, persist_log_now):
    """Bind log-related services to the current runtime paths/callbacks."""

    def list_log_files() -> list[Path]:
        return svc_list_log_files(log_dir)

    def make_logs_zip(files) -> bytes:
        return svc_make_logs_zip(files, log_dir=log_dir)

    def count_nohit_logs(days: int = 7):
        return svc_count_nohit_logs(log_dir=log_dir, days=days)

    def read_interactions(days: int = 7) -> pd.DataFrame:
        return svc_read_interactions(log_dir=log_dir, days=days)

    def log_nohit(question: str, extra: dict | None = None) -> str:
        return svc_log_nohit(log_dir=log_dir, question=question, extra=extra, persist_callback=persist_log_now)

    def update_nohit_record(day: str, timestamp: str, question: str, extra: dict) -> bool:
        return svc_update_nohit_record(
            log_dir=log_dir,
            day=day,
            timestamp=timestamp,
            question=question,
            extra=extra,
            persist_callback=persist_log_now,
        )

    def seed_nohit_questions(n: int = 20) -> int:
        return svc_seed_nohit_questions(log_dir=log_dir, persist_callback=persist_log_now, n=n)

    def log_interaction(question: str, matched: bool, best_score: float, category: str):
        return svc_log_interaction(
            log_dir=log_dir,
            question=question,
            matched=matched,
            best_score=best_score,
            category=category,
            persist_callback=persist_log_now,
        )

    def load_nohit_questions_from_logs(files, max_questions: int = 100) -> list[str]:
        return svc_load_nohit_questions_from_logs(files, max_questions=max_questions)

    def csv_bytes_as_utf8_sig(data) -> bytes:
        return svc_csv_bytes_as_utf8_sig(data)

    return SimpleNamespace(
        list_log_files=list_log_files,
        make_logs_zip=make_logs_zip,
        count_nohit_logs=count_nohit_logs,
        read_interactions=read_interactions,
        log_nohit=log_nohit,
        update_nohit_record=update_nohit_record,
        seed_nohit_questions=seed_nohit_questions,
        log_interaction=log_interaction,
        load_nohit_questions_from_logs=load_nohit_questions_from_logs,
        format_minutes_to_hours=format_minutes_to_hours,
        csv_bytes_as_utf8_sig=csv_bytes_as_utf8_sig,
    )
