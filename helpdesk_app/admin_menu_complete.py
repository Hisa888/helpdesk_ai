from __future__ import annotations

from pathlib import Path
from typing import Callable

import pandas as pd
import streamlit as st

from helpdesk_app.modules.admin_complete_sections import render_admin_complete_sections


def render_admin_complete_tools(
    *,
    read_interactions: Callable[..., pd.DataFrame],
    count_nohit_logs: Callable[..., tuple[int, int, int]],
    list_log_files: Callable[[], list[Path]],
    make_logs_zip: Callable[[list[Path]], bytes],
    load_nohit_questions_from_logs: Callable[..., list[str]],
    generate_faq_candidates: Callable[..., pd.DataFrame],
    append_faq_csv: Callable[..., int],
    seed_nohit_questions: Callable[..., int],
    faq_path: str | Path,
    build_document_rag_index=None,
    get_document_rag_manifest=None,
    clear_document_rag=None,
    list_document_rag_documents=None,
    delete_document_rag_document=None,
    supported_doc_rag_extensions=None,
    get_current_admin_name=None,
    generate_manual_faq_candidates=None,
    supported_manual_faq_extensions=None,
) -> None:
    """Backward-compatible thin wrapper for split admin complete sections."""

    st.markdown("---")
    render_admin_complete_sections({
        "st": st,
        "read_interactions": read_interactions,
        "count_nohit_logs": count_nohit_logs,
        "list_log_files": list_log_files,
        "make_logs_zip": make_logs_zip,
        "load_nohit_questions_from_logs": load_nohit_questions_from_logs,
        "generate_faq_candidates": generate_faq_candidates,
        "append_faq_csv": append_faq_csv,
        "seed_nohit_questions": seed_nohit_questions,
        "faq_path": faq_path,
        "build_document_rag_index": build_document_rag_index,
        "get_document_rag_manifest": get_document_rag_manifest,
        "clear_document_rag": clear_document_rag,
        "list_document_rag_documents": list_document_rag_documents,
        "delete_document_rag_document": delete_document_rag_document,
        "supported_doc_rag_extensions": supported_doc_rag_extensions,
        "get_current_admin_name": get_current_admin_name,
        "generate_manual_faq_candidates": generate_manual_faq_candidates,
        "supported_manual_faq_extensions": supported_manual_faq_extensions,
    })
