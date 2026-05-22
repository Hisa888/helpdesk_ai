from __future__ import annotations

import hashlib
import json
import re
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
        str(chunk.get("sheet_name", "")),
        str(chunk.get("heading", "")),
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


_DOC_STOP_TOKENS = {
    "あります", "できます", "ください", "する", "した", "して", "です", "ます", "よう", "方法", "場合", "について",
    "確認", "事項", "対象", "内容", "当社", "サービス", "契約", "変更", "解除", "会員", "保護",
}


def _doc_tokens(text: str) -> set[str]:
    """日本語向けの軽量重要語抽出。

    以前の実装は日本語文を長い1語として扱いやすく、質問語との重なり判定が弱かったため、
    カタカナ語・漢字語・英数字を中心に切り出します。
    """
    s = normalize_doc_text(text).lower()
    if not s:
        return set()
    tokens: set[str] = set()
    tokens.update(re.findall(r"[a-z0-9]{2,}", s))
    tokens.update(re.findall(r"[ァ-ヴー]{2,}", s))
    tokens.update(re.findall(r"[一-龥]{2,}", s))
    # ひらがな混じりでも業務上重要な語は追加
    for word in [
        "キャッシュ", "ブラウザ", "chrome", "edge", "ie", "cookie", "クッキー", "履歴", "一時ファイル",
        "入室", "入館", "立入", "入場", "制限", "復旧", "対策", "不正アクセス", "監査", "承認", "申請",
        "有無", "権限", "退室", "ログイン", "パスワード", "ロック", "vpn", "wifi", "wi-fi",
    ]:
        if word.lower() in s:
            tokens.add(word.lower())
    return {t for t in tokens if len(t) >= 2 and t not in _DOC_STOP_TOKENS}


def _meaningful_overlap(query: str, chunk: dict[str, Any]) -> int:
    q_tokens = _doc_tokens(query)
    if not q_tokens:
        return 0
    target = normalize_doc_text("\n".join([
        str(chunk.get("sheet_name", "")),
        str(chunk.get("heading", "")),
        str(chunk.get("keywords", "")),
        str(chunk.get("search_text", "")),
        str(chunk.get("text", "")),
    ]))
    return len(q_tokens & _doc_tokens(target))


def _is_probably_bad_excel_hit(query: str, chunk: dict[str, Any], score: float) -> bool:
    """Excelの別行・管理列ノイズによる誤回答を抑止する。"""
    if chunk.get("source_type") not in {"xlsx", "xlsm"}:
        return False
    q_tokens = _doc_tokens(query)
    if not q_tokens:
        return False
    overlap = _meaningful_overlap(query, chunk)
    if overlap == 0:
        return True
    # 質問語が1個しか合わず、スコアも低い場合は危険候補扱い
    if overlap == 1 and score < 0.18 and len(q_tokens) >= 2:
        return True
    return False


def _doc_weighted_text(chunk: dict[str, Any]) -> str:
    """本文だけでなく、Excelのシート名・見出し・場所を強めに検索対象へ入れる。"""
    source_type = str(chunk.get("source_type", ""))
    source_name = normalize_doc_text(chunk.get("source_name", ""))
    location = normalize_doc_text(chunk.get("location", ""))
    sheet_name = normalize_doc_text(chunk.get("sheet_name", ""))
    heading = normalize_doc_text(chunk.get("heading", ""))
    keywords = normalize_doc_text(chunk.get("keywords", ""))
    text = normalize_doc_text(chunk.get("text", ""))
    search_text = normalize_doc_text(chunk.get("search_text", "")) or text

    parts: list[str] = []
    parts.append(source_name)
    # Excelの行番号/場所は検索ノイズになりやすいので、重みを上げすぎない
    parts.append(location)
    if source_type in {"xlsx", "xlsm"}:
        # Excelは表の列名・見出し・シート名が質問と一致することが多いので強める
        parts.extend([sheet_name] * 4)
        parts.extend([heading] * 5)
        parts.extend([keywords] * 3)
        parts.extend([search_text] * 3)
        parts.extend([text] * 2)
    else:
        parts.extend([heading] * 3)
        parts.extend([keywords] * 2)
        parts.extend([search_text] * 2)
        parts.append(text)
    return "\n".join([p for p in parts if p])


def _apply_doc_rerank(query: str, chunks: list[dict[str, Any]], scores: np.ndarray, candidate_idxs: list[int]) -> None:
    q = normalize_doc_text(query)
    if not q or scores is None:
        return
    q_tokens = _doc_tokens(q)
    q_lower = q.lower()
    for idx in candidate_idxs:
        if idx < 0 or idx >= len(chunks):
            continue
        ch = chunks[idx]
        text = normalize_doc_text(ch.get("text", ""))
        stxt = normalize_doc_text(ch.get("search_text", "")) or text
        meta = normalize_doc_text(" ".join([
            str(ch.get("source_name", "")),
            str(ch.get("location", "")),
            str(ch.get("sheet_name", "")),
            str(ch.get("heading", "")),
            str(ch.get("keywords", "")),
        ]))
        all_text = f"{meta}\n{stxt}"
        all_lower = all_text.lower()
        tokens = _doc_tokens(all_text)

        # 完全/部分一致は強く加点
        if q and q in all_text:
            scores[idx] += 0.35
        if q and q in meta:
            scores[idx] += 0.22

        if q_tokens:
            overlap = len(q_tokens & tokens) / max(1, len(q_tokens))
            scores[idx] += min(0.30, overlap * 0.30)

        # Excel表・見出し・行番号があるチャンクは質問と項目名が合えば優先
        if ch.get("source_type") in {"xlsx", "xlsm"}:
            scores[idx] += 0.04
            if any(w in q for w in ["入室", "入館", "立入", "入場"]):
                if any(w in all_text for w in ["入室", "入館", "立入", "入場"]):
                    scores[idx] += 0.22
                else:
                    scores[idx] -= 0.12
            if "制限" in q and "制限" in all_text:
                scores[idx] += 0.16
            if any(w in q for w in ["復旧", "対策", "不正アクセス"]):
                if any(w in all_text for w in ["復旧", "対策", "不正アクセス", "インシデント"]):
                    scores[idx] += 0.20
                else:
                    scores[idx] -= 0.10

        # 「○」「有」だけの回答が本文中にある場合、項目名一致がないと誤ヒットしやすいので抑制
        compact = re.sub(r"\s+", "", text)
        if len(compact) <= 20 and not (q_tokens & _doc_tokens(meta)):
            scores[idx] -= 0.10

        # 質問語がほぼ入っていないチャンクは、埋め込み検索の暴走を強く抑える
        if q_tokens and len(q_tokens & tokens) == 0:
            scores[idx] -= 0.22
        elif q_tokens and len(q_tokens & tokens) == 1 and ch.get("source_type") in {"xlsx", "xlsm"} and len(q_tokens) >= 2:
            scores[idx] -= 0.06


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
                "heading": "wiki",
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
                    # 埋め込みにもメタデータを入れることで「シート名/見出し/項目名」で拾えるようにする
                    texts = [f"passage: {_doc_weighted_text(x)}" for x in chunks]
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

    def _merge_hits(primary: list[dict[str, Any]], secondary: list[dict[str, Any]], top_k: int) -> list[dict[str, Any]]:
        by_id: dict[str, dict[str, Any]] = {}
        for source_weight, hits in [(1.0, primary), (0.96, secondary)]:
            for h in hits:
                key = str(h.get("chunk_id") or f"{h.get('source_name')}|{h.get('location')}|{h.get('chunk_label')}|{h.get('text', '')[:40]}")
                item = dict(h)
                item["score"] = float(item.get("score", 0.0)) * source_weight
                if key not in by_id or item["score"] > float(by_id[key].get("score", 0.0)):
                    by_id[key] = item
        return sorted(by_id.values(), key=lambda x: float(x.get("score", 0.0)), reverse=True)[:top_k]

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
            count = min(len(scores), max(top_k * 4, 20))
            order = np.argsort(scores)[::-1][:count]
            _apply_doc_rerank(query, chunks, scores, [int(i) for i in order])
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
        texts = [_doc_weighted_text(x) for x in chunks]
        if not texts:
            return []
        vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), min_df=1)
        matrix = vectorizer.fit_transform(texts)
        qv = vectorizer.transform([query])
        scores = cosine_similarity(qv, matrix).flatten()
        count = min(len(scores), max(top_k * 5, 25))
        order = np.argsort(scores)[::-1][:count]
        _apply_doc_rerank(query, chunks, scores, [int(i) for i in order])
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
        emb_hits = _search_with_embeddings(query, chunks, top_k=top_k)
        tfidf_hits = _search_with_tfidf(query, chunks, top_k=top_k)
        hits = _merge_hits(emb_hits, tfidf_hits, top_k=max(top_k, 8))
        # Excelは「別行を拾う」誤回答が起きやすいため、質問との重要語重なりが無い候補は除外する。
        safe_hits: list[dict[str, Any]] = []
        for h in hits:
            score = float(h.get("score", 0.0))
            if score < 0.10:
                continue
            if _is_probably_bad_excel_hit(query, h, score):
                continue
            safe_hits.append(h)
        return safe_hits[:top_k]

    def build_document_rag_prompt(user_q: str, hits: list[dict[str, Any]]) -> str:
        contexts: list[str] = []
        for i, hit in enumerate(hits[:4], start=1):
            contexts.append(
                "\n".join([
                    f"[根拠{i}]",
                    f"資料名: {hit.get('source_name', '')}",
                    f"種類: {hit.get('source_type', '')}",
                    f"場所: {hit.get('location', '')} / {hit.get('chunk_label', '')}",
                    f"シート名: {hit.get('sheet_name', '')}",
                    f"見出し: {hit.get('heading', '')}",
                    f"本文: {hit.get('text', '')}",
                ])
            )
        context_text = "\n\n".join(contexts)
        return (
            "あなたは社内ヘルプデスクAIです。"
            "以下の社内資料だけを根拠に、日本語で簡潔かつ正確に回答してください。"
            "根拠に書かれていないことは断定しないでください。"
            "Excel資料の場合は、シート名・行番号・見出し・項目名を優先して判断してください。"
            "複数の根拠が矛盾する場合は、最も質問語と一致する根拠を採用してください。質問と根拠の意味が合わない場合は、回答せず該当資料なしと述べてください。"
            "回答の最後に '参照資料:' を付けて、資料名と場所を箇条書きで並べてください。\n\n"
            f"[質問]\n{user_q}\n\n"
            f"[社内資料]\n{context_text}"
        )

    def answer_with_document_rag(user_q: str, hits: list[dict[str, Any]]) -> str:
        prompt = build_document_rag_prompt(user_q, hits)
        try:
            messages = [
                {"role": "system", "content": "あなたは情シス担当です。資料に基づいて日本語で回答してください。資料外の内容は断定しないでください。"},
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
        refs = "\n".join(
            f"- {x.get('source_name', '')} / {x.get('location', '')} / {x.get('heading', '')}"
            for x in hits[:3]
        )
        return f"社内資料から該当箇所が見つかりました。\n\n{excerpt}\n\n参照資料:\n{refs}"

    def list_document_rag_documents() -> list[dict[str, Any]]:
        manifest = get_document_rag_manifest()
        chunks = load_document_chunks()
        files = manifest.get("files", []) if isinstance(manifest.get("files", []), list) else []
        out: list[dict[str, Any]] = []
        for f in files:
            name = str(f.get("name", ""))
            chunk_count = sum(1 for c in chunks if str(c.get("source_name", "")) == name)
            out.append({
                "ファイル名": name,
                "種類": f.get("type", ""),
                "取込日": manifest.get("updated_at", ""),
                "登録者": f.get("uploaded_by", ""),
                "チャンク数": chunk_count,
            })
        return out

    def delete_document_rag_document(source_name: str) -> bool:
        source_name = str(source_name or "").strip()
        if not source_name:
            return False
        try:
            chunks = [c for c in load_document_chunks() if str(c.get("source_name", "")) != source_name]
            manifest = get_document_rag_manifest()
            files = [f for f in manifest.get("files", []) if str(f.get("name", "")) != source_name]
            manifest["files"] = files
            manifest["doc_count"] = len(files) + (1 if manifest.get("wiki_enabled") else 0)
            manifest["chunk_count"] = len(chunks)
            manifest["enabled"] = bool(chunks)
            _safe_write_json(DOC_RAG_CHUNKS_PATH, chunks)
            _safe_write_json(DOC_RAG_MANIFEST_PATH, manifest)
            # 削除後は埋め込み件数が合わなくなるため再取込を促すために削除
            if DOC_RAG_EMBEDDINGS_PATH.exists():
                DOC_RAG_EMBEDDINGS_PATH.unlink()
            src_path = DOC_RAG_FILES_DIR / source_name
            if src_path.exists():
                src_path.unlink()
            _persist_doc_paths(DOC_RAG_CHUNKS_PATH, DOC_RAG_MANIFEST_PATH)
            return True
        except Exception:
            return False

    return SimpleNamespace(
        DOC_RAG_DIR=DOC_RAG_DIR,
        DOC_RAG_FILES_DIR=DOC_RAG_FILES_DIR,
        DOC_RAG_MANIFEST_PATH=DOC_RAG_MANIFEST_PATH,
        DOC_RAG_CHUNKS_PATH=DOC_RAG_CHUNKS_PATH,
        DEFAULT_DOC_RAG_THRESHOLD=DEFAULT_DOC_RAG_THRESHOLD,
        SUPPORTED_DOC_RAG_EXTENSIONS=SUPPORTED_DOC_RAG_EXTENSIONS,
        get_document_rag_manifest=get_document_rag_manifest,
        load_document_chunks=load_document_chunks,
        list_document_rag_documents=list_document_rag_documents,
        build_document_rag_index=build_document_rag_index,
        delete_document_rag_document=delete_document_rag_document,
        clear_document_rag=clear_document_rag,
        search_document_rag=search_document_rag,
        build_document_rag_prompt=build_document_rag_prompt,
        answer_with_document_rag=answer_with_document_rag,
    )


__all__ = ["create_document_rag_runtime", "DEFAULT_DOC_RAG_THRESHOLD"]
