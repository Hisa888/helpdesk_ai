from __future__ import annotations

import streamlit as st


def render_document_rag_panel(
    *,
    build_document_rag_index,
    get_document_rag_manifest,
    clear_document_rag,
    supported_extensions,
) -> None:
    with st.expander("📚 社内ドキュメントRAG（PDF / Word / Excel / Wiki）", expanded=False):
        st.caption("社内マニュアルや申請一覧を取り込み、FAQで答えきれない質問のときに資料を根拠に自動回答します。")

        manifest = get_document_rag_manifest()
        files = manifest.get("files", []) if isinstance(manifest, dict) else []
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
                result = build_document_rag_index(uploaded_files or [], wiki_text or "")
                if result.get("ok"):
                    st.success(f"{result.get('message')} チャンク数: {result.get('chunk_count', 0)}")
                else:
                    st.warning(result.get("message", "取り込みに失敗しました。"))
        with c2:
            if st.button("🗑 ドキュメントRAGを初期化", key="doc_rag_clear_btn", use_container_width=True):
                ok = clear_document_rag()
                if ok:
                    st.success("ドキュメントRAGを初期化しました。")
                else:
                    st.error("初期化に失敗しました。")

        if files:
            st.markdown("**登録済み資料**")
            for item in files:
                st.write(f"- {item.get('name', '')} ({item.get('type', '')})")
        if manifest.get("wiki_enabled"):
            st.write("- wiki_input.txt (wiki)")
