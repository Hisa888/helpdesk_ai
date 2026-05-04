from __future__ import annotations

import hashlib

import streamlit as st


def _fmt(value) -> str:
    text = str(value or "").strip()
    return text if text else "-"


def _row_key(name: str, source_type: str) -> str:
    raw = f"{name}|{source_type}"
    return hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()[:12]


def _fallback_documents_from_manifest(manifest: dict) -> list[dict]:
    rows: list[dict] = []
    updated_at = str(manifest.get("updated_at", "") or "")
    for item in manifest.get("files", []) or []:
        if not isinstance(item, dict):
            continue
        rows.append({
            "name": item.get("name", ""),
            "type": item.get("type", ""),
            "uploaded_at": item.get("uploaded_at", updated_at),
            "uploaded_by": item.get("uploaded_by", "不明"),
            "chunk_count": item.get("chunk_count", 0),
        })
    if manifest.get("wiki_enabled"):
        rows.append({
            "name": "wiki_input.txt",
            "type": "wiki",
            "uploaded_at": manifest.get("wiki_uploaded_at", updated_at),
            "uploaded_by": manifest.get("wiki_uploaded_by", "不明"),
            "chunk_count": 0,
        })
    return rows


def render_document_rag_panel(
    *,
    build_document_rag_index,
    get_document_rag_manifest,
    clear_document_rag,
    supported_extensions,
    list_document_rag_documents=None,
    delete_document_rag_document=None,
    get_current_admin_name=None,
) -> None:
    with st.expander("📚 社内ドキュメントRAG（PDF / Word / Excel / Wiki）", expanded=False):
        st.caption("社内マニュアルや申請一覧を取り込み、FAQで答えきれない質問のときに資料を根拠に自動回答します。")

        manifest = get_document_rag_manifest()
        st.info(
            f"現在の登録資料: {int(manifest.get('doc_count', 0))}件 / チャンク数: {int(manifest.get('chunk_count', 0))}"
        )

        uploaded_files = st.file_uploader(
            "資料をドラッグ＆ドロップ",
            type=list(supported_extensions),
            accept_multiple_files=True,
            key="doc_rag_files",
            help="PDF / docx / xlsx / txt / md に対応",
        )
        wiki_text = st.text_area(
            "Wiki本文の貼り付け（任意）",
            key="doc_rag_wiki_text",
            height=180,
            placeholder="Confluence や社内Wikiの本文をここに貼り付け",
        )

        c1, c2 = st.columns(2)
        with c1:
            if st.button("📥 この内容でRAGへ反映", key="doc_rag_build_btn", use_container_width=True):
                uploaded_by = get_current_admin_name() if callable(get_current_admin_name) else "管理者"
                result = build_document_rag_index(uploaded_files or [], wiki_text or "", uploaded_by=uploaded_by)
                if result.get("ok"):
                    st.success(f"{result.get('message')} チャンク数: {result.get('chunk_count', 0)}")
                    st.rerun()
                else:
                    st.warning(result.get("message", "取り込みに失敗しました。"))
        with c2:
            if st.button("🗑 ドキュメントRAGを初期化", key="doc_rag_clear_btn", use_container_width=True):
                ok = clear_document_rag()
                if ok:
                    st.success("ドキュメントRAGを初期化しました。")
                    st.rerun()
                else:
                    st.error("初期化に失敗しました。")

        st.markdown("### 社内ドキュメントRAG管理")
        st.caption("アップロード済みドキュメント一覧です。削除すると、その資料のチャンクもRAG検索対象から外れます。")

        if callable(list_document_rag_documents):
            documents = list_document_rag_documents()
        else:
            documents = _fallback_documents_from_manifest(manifest)

        if not documents:
            st.info("アップロード済みドキュメントはありません。")
            return

        header_cols = st.columns([3.0, 1.0, 1.6, 1.3, 1.0, 1.0])
        header_cols[0].markdown("**ファイル名**")
        header_cols[1].markdown("**種類**")
        header_cols[2].markdown("**取込日**")
        header_cols[3].markdown("**登録者**")
        header_cols[4].markdown("**チャンク数**")
        header_cols[5].markdown("**削除**")

        for item in documents:
            name = str(item.get("name", "") or "")
            source_type = str(item.get("type", "") or "")
            row_cols = st.columns([3.0, 1.0, 1.6, 1.3, 1.0, 1.0])
            row_cols[0].write(_fmt(name))
            row_cols[1].write(_fmt(source_type).upper() if source_type != "wiki" else "Wiki")
            row_cols[2].write(_fmt(item.get("uploaded_at", "")))
            row_cols[3].write(_fmt(item.get("uploaded_by", "")))
            row_cols[4].write(int(item.get("chunk_count", 0) or 0))

            if callable(delete_document_rag_document):
                with row_cols[5]:
                    if st.button("削除", key=f"delete_doc_rag_{_row_key(name, source_type)}"):
                        deleted_by = get_current_admin_name() if callable(get_current_admin_name) else "管理者"
                        result = delete_document_rag_document(name, source_type, deleted_by=deleted_by)
                        if result.get("ok"):
                            st.success(result.get("message", "削除しました。"))
                            st.rerun()
                        else:
                            st.error(result.get("message", "削除に失敗しました。"))
            else:
                row_cols[5].write("-")
