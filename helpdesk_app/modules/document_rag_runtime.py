from __future__ import annotations

import hashlib
import json
import shutil
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from helpdesk_app.modules.document_rag_extractors import (
    SUPPORTED_DOC_RAG_EXTENSIONS,
    build_chunks_from_sections,
    extract_sections_from_uploaded_file,
    normalize_doc_text,
)


DEFAULT_DOC_RAG_THRESHOLD = 0.20
EMBED_MODEL_NAME = "intfloat/multilingual-e5-small"


@lru_cache(maxsize=1)
def _load_sentence_model(SentenceTransformer):
    if SentenceTransformer is None:
        return None
    return SentenceTransformer(EMBED_MODEL_NAME)


def _hash_chunk(chunk: dict[str, Any]) -> str:
    key = "|".join([
        str(chunk.get("source_name", "")),
        str(chunk.get("source_type", "")),
        str(chunk.get("location", "")),
        str(chunk.get("chunk_label", "")),
        str(chunk.get("text", ""))[:200],
    ])
    return hashlib.sha1(key.encode("utf-8", errors="ignore")).hexdigest()


def _safe_write_json(path_obj: Path, payload: Any) -> None:
    path_obj.parent.mkdir(parents=True, exist_ok=True)
    path_obj.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_json(path_obj: Path, fallback: Any):
    try:
        if path_obj.exists():
            return json.loads(path_obj.read_text(encoding="utf-8"))
    except Exception:
        pass
    return fallback


def create_document_rag_runtime(
    *,
    st,
    Path,
    DATA_DIR,
    llm_chat,
    persist_runtime_file,
    SENTENCE_TRANSFORMERS_AVAILABLE,
    SentenceTransformer,
):
    DOC_RAG_DIR = Path(DATA_DIR) / "doc_rag"
    DOC_RAG_DIR.mkdir(parents=True, exist_ok=True)
    DOC_RAG_FILES_DIR = DOC_RAG_DIR / "source_files"
    DOC_RAG_FILES_DIR.mkdir(parents=True, exist_ok=True)

    DOC_RAG_MANIFEST_PATH = DOC_RAG_DIR / "manifest.json"
    DOC_RAG_CHUNKS_PATH = DOC_RAG_DIR / "chunks.json"
    DOC_RAG_EMBEDDINGS_PATH = DOC_RAG_DIR / "embeddings.npy"

    def get_document_rag_manifest() -> dict:
        base = {
            "enabled": False,
            "doc_count": 0,
            "chunk_count": 0,
            "files": [],
            "wiki_enabled": False,
            "updated_at": "",
        }
        data = _load_json(DOC_RAG_MANIFEST_PATH, base)
        if not isinstance(data, dict):
            return base
        clean = base.copy()
        clean.update(data)
        return clean

    def load_document_chunks() -> list[dict[str, Any]]:
        rows = _load_json(DOC_RAG_CHUNKS_PATH, [])
        return rows if isinstance(rows, list) else []

    def clear_document_rag() -> bool:
        try:
            if DOC_RAG_FILES_DIR.exists():
                shutil.rmtree(DOC_RAG_FILES_DIR, ignore_errors=True)
            DOC_RAG_FILES_DIR.mkdir(parents=True, exist_ok=True)
            for path_obj in [DOC_RAG_MANIFEST_PATH, DOC_RAG_CHUNKS_PATH, DOC_RAG_EMBEDDINGS_PATH]:
                if path_obj.exists():
                    path_obj.unlink()
            _safe_write_json(DOC_RAG_MANIFEST_PATH, {
                "enabled": False,
                "doc_count": 0,
                "chunk_count": 0,
                "files": [],
                "wiki_enabled": False,
                "updated_at": "",
            })
            persist_runtime_file(DOC_RAG_MANIFEST_PATH, label="doc_rag_manifest")
            return True
        except Exception:
            return False

    def _persist_doc_paths(*paths: Path) -> None:
        for path_obj in paths:
            try:
                persist_runtime_file(path_obj, label="doc_rag")
            except Exception:
                continue

    def build_document_rag_index(uploaded_files: list[Any] | None, wiki_text: str = "") -> dict:
        uploaded_files = list(uploaded_files or [])
        wiki_text = normalize_doc_text(wiki_text)
        all_sections: list[dict[str, str]] = []
        saved_files: list[dict[str, str]] = []

        DOC_RAG_FILES_DIR.mkdir(parents=True, exist_ok=True)

        for uploaded in uploaded_files:
            try:
                sections = extract_sections_from_uploaded_file(uploaded)
                if not sections:
                    continue
                all_sections.extend(sections)
                raw_bytes = uploaded.getvalue() if hasattr(uploaded, "getvalue") else uploaded.read()
                filename = str(getattr(uploaded, "name", "document")).strip() or "document"
                save_path = DOC_RAG_FILES_DIR / filename
                save_path.write_bytes(raw_bytes)
                saved_files.append({"name": filename, "type": Path(filename).suffix.lower().lstrip("."), "path": str(save_path)})
            except Exception as exc:
                st.warning(f"ドキュメント取込に失敗しました: {getattr(uploaded, 'name', 'document')} / {exc}")

        if wiki_text:
            all_sections.append({
                "source_name": "wiki_input.txt",
                "source_type": "wiki",
                "location": "wiki",
                "text": wiki_text,
            })

        chunks = build_chunks_from_sections(all_sections)
        for row in chunks:
            row["chunk_id"] = _hash_chunk(row)

        if not chunks:
            return {"ok": False, "message": "取り込める本文がありませんでした。", "chunk_count": 0}

        embeddings = None
        if SENTENCE_TRANSFORMERS_AVAILABLE:
            try:
                model = _load_sentence_model(SentenceTransformer)
                if model is not None:
                    texts = [f"passage: {str(x.get('text', ''))}" for x in chunks]
                    emb = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
                    embeddings = np.asarray(emb, dtype=np.float32)
            except Exception as exc:
                st.warning(f"sentence-transformers での索引化に失敗したため通常検索に切り替えます: {exc}")
                embeddings = None

        _safe_write_json(DOC_RAG_CHUNKS_PATH, chunks)
        if embeddings is not None:
            np.save(DOC_RAG_EMBEDDINGS_PATH, embeddings)
        elif DOC_RAG_EMBEDDINGS_PATH.exists():
            DOC_RAG_EMBEDDINGS_PATH.unlink()

        manifest = {
            "enabled": True,
            "doc_count": len(saved_files) + (1 if wiki_text else 0),
            "chunk_count": len(chunks),
            "files": [{"name": x["name"], "type": x["type"]} for x in saved_files],
            "wiki_enabled": bool(wiki_text),
            "updated_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        }
        _safe_write_json(DOC_RAG_MANIFEST_PATH, manifest)
        _persist_doc_paths(DOC_RAG_CHUNKS_PATH, DOC_RAG_MANIFEST_PATH)
        if DOC_RAG_EMBEDDINGS_PATH.exists():
            _persist_doc_paths(DOC_RAG_EMBEDDINGS_PATH)
        for item in saved_files:
            _persist_doc_paths(Path(item["path"]))

        return {"ok": True, "message": f"{manifest['doc_count']}件の資料を取り込みました。", "chunk_count": len(chunks), "manifest": manifest}

    def _search_with_embeddings(query: str, chunks: list[dict[str, Any]], top_k: int = 5) -> list[dict[str, Any]]:
        if not DOC_RAG_EMBEDDINGS_PATH.exists():
            return []
        try:
            embeddings = np.load(DOC_RAG_EMBEDDINGS_PATH)
            if len(embeddings) != len(chunks):
                return []
            model = _load_sentence_model(SentenceTransformer)
            if model is None:
                return []
            q_emb = model.encode([f"query: {query}"], normalize_embeddings=True, show_progress_bar=False)[0]
            scores = np.dot(embeddings, q_emb)
            order = np.argsort(scores)[::-1][:top_k]
            hits: list[dict[str, Any]] = []
            for idx in order:
                item = dict(chunks[int(idx)])
                item["score"] = float(scores[int(idx)])
                hits.append(item)
            return hits
        except Exception:
            return []

    def _search_with_tfidf(query: str, chunks: list[dict[str, Any]], top_k: int = 5) -> list[dict[str, Any]]:
        texts = [str(x.get("text", "")) for x in chunks]
        if not texts:
            return []
        vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4))
        matrix = vectorizer.fit_transform(texts)
        qv = vectorizer.transform([query])
        scores = cosine_similarity(qv, matrix).flatten()
        order = np.argsort(scores)[::-1][:top_k]
        hits: list[dict[str, Any]] = []
        for idx in order:
            item = dict(chunks[int(idx)])
            item["score"] = float(scores[int(idx)])
            hits.append(item)
        return hits

    def search_document_rag(query: str, top_k: int = 5) -> list[dict[str, Any]]:
        query = normalize_doc_text(query)
        if not query:
            return []
        manifest = get_document_rag_manifest()
        if not manifest.get("enabled"):
            return []
        chunks = load_document_chunks()
        if not chunks:
            return []
        hits = _search_with_embeddings(query, chunks, top_k=top_k)
        if not hits:
            hits = _search_with_tfidf(query, chunks, top_k=top_k)
        return hits

    def build_document_rag_prompt(user_q: str, hits: list[dict[str, Any]]) -> str:
        contexts: list[str] = []
        for i, hit in enumerate(hits[:4], start=1):
            contexts.append(
                "\n".join([
                    f"[根拠{i}]",
                    f"資料名: {hit.get('source_name', '')}",
                    f"場所: {hit.get('location', '')} / {hit.get('chunk_label', '')}",
                    f"本文: {hit.get('text', '')}",
                ])
            )
        context_text = "\n\n".join(contexts)
        return (
            "あなたは社内ヘルプデスクAIです。"
            "以下の社内資料だけを根拠に、日本語で簡潔かつ正確に回答してください。"
            "根拠に書かれていないことは断定しないでください。"
            "回答の最後に '参照資料:' を付けて、資料名を箇条書きで並べてください。\n\n"
            f"[質問]\n{user_q}\n\n"
            f"[社内資料]\n{context_text}"
        )

    def answer_with_document_rag(user_q: str, hits: list[dict[str, Any]]) -> str:
        prompt = build_document_rag_prompt(user_q, hits)
        try:
            messages = [
                {"role": "system", "content": "あなたは情シス担当です。資料に基づいて日本語で回答してください。"},
                {"role": "user", "content": prompt},
            ]
            answer = str(llm_chat(messages) or "").strip()
            if answer:
                return answer
        except Exception:
            pass
        top = hits[0] if hits else {}
        excerpt = str(top.get("text", "")).strip()
        if len(excerpt) > 260:
            excerpt = excerpt[:260].rstrip() + "…"
        refs = "\n".join(f"- {x.get('source_name', '')}" for x in hits[:3])
        return f"社内資料から該当箇所が見つかりました。\n\n{excerpt}\n\n参照資料:\n{refs}"

    return SimpleNamespace(
        DOC_RAG_DIR=DOC_RAG_DIR,
        DOC_RAG_FILES_DIR=DOC_RAG_FILES_DIR,
        DOC_RAG_MANIFEST_PATH=DOC_RAG_MANIFEST_PATH,
        DOC_RAG_CHUNKS_PATH=DOC_RAG_CHUNKS_PATH,
        DEFAULT_DOC_RAG_THRESHOLD=DEFAULT_DOC_RAG_THRESHOLD,
        SUPPORTED_DOC_RAG_EXTENSIONS=SUPPORTED_DOC_RAG_EXTENSIONS,
        get_document_rag_manifest=get_document_rag_manifest,
        load_document_chunks=load_document_chunks,
        build_document_rag_index=build_document_rag_index,
        clear_document_rag=clear_document_rag,
        search_document_rag=search_document_rag,
        build_document_rag_prompt=build_document_rag_prompt,
        answer_with_document_rag=answer_with_document_rag,
    )


__all__ = ["create_document_rag_runtime", "DEFAULT_DOC_RAG_THRESHOLD"]
