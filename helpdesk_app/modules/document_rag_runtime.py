from __future__ import annotations

import hashlib
import json
import pickle
import re
import shutil
import unicodedata
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from openpyxl import load_workbook

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


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _safe_source_filename(filename: str) -> str:
    """アップロード名からパス要素を除き、安全なファイル名だけを残す。"""
    name = Path(str(filename or "document")).name.strip()
    return name or "document"


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
    DOC_RAG_TFIDF_INDEX_PATH = DOC_RAG_DIR / "tfidf_index.pkl"

    def _empty_manifest() -> dict[str, Any]:
        return {
            "enabled": False,
            "doc_count": 0,
            "chunk_count": 0,
            "files": [],
            "wiki_enabled": False,
            "updated_at": "",
        }

    def get_document_rag_manifest() -> dict:
        base = _empty_manifest()
        data = _load_json(DOC_RAG_MANIFEST_PATH, base)
        if not isinstance(data, dict):
            return base
        clean = base.copy()
        clean.update(data)
        if not isinstance(clean.get("files"), list):
            clean["files"] = []
        return clean

    def _parse_legacy_xlsx_row_text(source_text: str) -> list[tuple[str, str]]:
        """旧版のExcelチャンク（row 36: ...\nrow 37: ...）を行単位に分解する。"""
        text = normalize_doc_text(source_text)
        if not text:
            return []
        pattern = re.compile(r"(?ms)^row\s+(\d+)\s*:\s*(.*?)(?=^row\s+\d+\s*:|\Z)")
        rows: list[tuple[str, str]] = []
        for match in pattern.finditer(text):
            row_no = match.group(1).strip()
            body = normalize_doc_text(match.group(2))
            if body:
                rows.append((row_no, body))
        return rows

    def _expand_legacy_xlsx_chunks(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """旧データ互換: 1シート/複数行チャンクを1行チャンクへ展開する。

        既に取り込み済みの chunks.json が残っている環境でも、
        コード更新だけで「前後行が混ざる回答」を避けられるようにする。
        """
        expanded: list[dict[str, Any]] = []
        changed = False
        for row in rows:
            if not isinstance(row, dict):
                continue
            source_type = str(row.get("source_type", "") or "").lower()
            text = str(row.get("text", "") or "")
            legacy_rows = _parse_legacy_xlsx_row_text(text) if source_type in {"xlsx", "xlsm"} else []
            if len(legacy_rows) >= 2:
                changed = True
                for row_no, body in legacy_rows:
                    new_row = dict(row)
                    old_location = str(row.get("location", "") or "sheet")
                    # 旧テキストには列ラベルが無いため、元データとして残す。
                    new_row["location"] = f"{old_location} row {row_no}"
                    new_row["chunk_label"] = f"row {row_no}"
                    new_row["text"] = normalize_doc_text(f"Excel行: {row_no}\n元データ: {body}")
                    new_row["chunk_id"] = _hash_chunk(new_row)
                    expanded.append(new_row)
            else:
                if not row.get("chunk_id"):
                    row = dict(row)
                    row["chunk_id"] = _hash_chunk(row)
                expanded.append(row)
        return expanded if changed else expanded

    def load_document_chunks() -> list[dict[str, Any]]:
        rows = _load_json(DOC_RAG_CHUNKS_PATH, [])
        if not isinstance(rows, list):
            return []
        return _expand_legacy_xlsx_chunks(rows)

    def _persist_doc_paths(*paths: Path) -> None:
        for path_obj in paths:
            try:
                persist_runtime_file(path_obj, label="doc_rag")
            except Exception:
                continue

    def _chunk_matches_document(chunk: dict[str, Any], document_name: str, source_type: str = "") -> bool:
        chunk_name = str(chunk.get("source_name", "")).strip()
        chunk_type = str(chunk.get("source_type", "")).strip().lower()
        target_name = str(document_name or "").strip()
        target_type = str(source_type or "").strip().lower()
        if chunk_name != target_name:
            return False
        return not target_type or chunk_type == target_type

    def _chunk_count_for(chunks: list[dict[str, Any]], document_name: str, source_type: str = "") -> int:
        return sum(1 for row in chunks if _chunk_matches_document(row, document_name, source_type))

    def list_document_rag_documents() -> list[dict[str, Any]]:
        """管理画面用: 取り込み済みRAG資料を一覧化する。

        旧manifestには取込日・登録者・チャンク数が無い場合があるため、
        chunks.jsonから補完して表示できる形に整える。
        """
        manifest = get_document_rag_manifest()
        chunks = load_document_chunks()
        updated_at = str(manifest.get("updated_at", "") or "")
        rows: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()

        for item in manifest.get("files", []) or []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "") or "").strip()
            if not name:
                continue
            source_type = str(item.get("type", "") or Path(name).suffix.lower().lstrip(".")).strip().lower()
            key = (name, source_type)
            if key in seen:
                continue
            seen.add(key)
            rows.append({
                "name": name,
                "type": source_type or "file",
                "uploaded_at": str(item.get("uploaded_at", "") or updated_at),
                "uploaded_by": str(item.get("uploaded_by", "") or "不明"),
                "chunk_count": int(item.get("chunk_count", 0) or _chunk_count_for(chunks, name, source_type)),
                "path": str(item.get("path", "") or str(DOC_RAG_FILES_DIR / name)),
                "is_wiki": False,
            })

        # 旧データやmanifestに無いチャンクも拾って一覧に出す。
        for chunk in chunks:
            if not isinstance(chunk, dict):
                continue
            name = str(chunk.get("source_name", "") or "").strip()
            if not name:
                continue
            source_type = str(chunk.get("source_type", "") or Path(name).suffix.lower().lstrip(".") or "file").strip().lower()
            key = (name, source_type)
            if key in seen:
                continue
            seen.add(key)
            rows.append({
                "name": name,
                "type": source_type,
                "uploaded_at": updated_at,
                "uploaded_by": "不明",
                "chunk_count": _chunk_count_for(chunks, name, source_type),
                "path": str(DOC_RAG_FILES_DIR / name) if source_type != "wiki" else "",
                "is_wiki": source_type == "wiki" or name == "wiki_input.txt",
            })

        if manifest.get("wiki_enabled") and ("wiki_input.txt", "wiki") not in seen:
            rows.append({
                "name": "wiki_input.txt",
                "type": "wiki",
                "uploaded_at": updated_at,
                "uploaded_by": "不明",
                "chunk_count": _chunk_count_for(chunks, "wiki_input.txt", "wiki"),
                "path": "",
                "is_wiki": True,
            })

        return rows

    def _safe_unlink_source_file(path_text: str, document_name: str) -> None:
        """source_files配下の元ファイルだけを安全に削除する。"""
        candidates = []
        if path_text:
            candidates.append(Path(path_text))
        if document_name:
            candidates.append(DOC_RAG_FILES_DIR / _safe_source_filename(document_name))

        try:
            base = DOC_RAG_FILES_DIR.resolve()
        except Exception:
            base = DOC_RAG_FILES_DIR

        for candidate in candidates:
            try:
                path_obj = Path(candidate)
                resolved = path_obj.resolve()
                if str(resolved).startswith(str(base)) and resolved.exists() and resolved.is_file():
                    resolved.unlink()
            except Exception:
                continue

    def _write_manifest_after_change(manifest: dict[str, Any], chunks: list[dict[str, Any]]) -> None:
        files = manifest.get("files", []) if isinstance(manifest.get("files"), list) else []
        wiki_enabled = bool(manifest.get("wiki_enabled"))
        manifest.update({
            "enabled": bool(files or wiki_enabled or chunks),
            "doc_count": len(files) + (1 if wiki_enabled else 0),
            "chunk_count": len(chunks),
            "updated_at": _now_iso(),
        })
        _safe_write_json(DOC_RAG_MANIFEST_PATH, manifest)
        _safe_write_json(DOC_RAG_CHUNKS_PATH, chunks)
        # ファイル単位削除後はembeddingsとchunksの件数がズレるため、いったん削除してTF-IDF検索に戻す。
        # 次回「この内容でRAGへ反映」時にsentence-transformersが使える環境なら再生成される。
        for index_path in [DOC_RAG_EMBEDDINGS_PATH, DOC_RAG_TFIDF_INDEX_PATH]:
            if index_path.exists():
                try:
                    index_path.unlink()
                except Exception:
                    pass
        _persist_doc_paths(DOC_RAG_MANIFEST_PATH, DOC_RAG_CHUNKS_PATH)

    def delete_document_rag_document(document_name: str, source_type: str = "", deleted_by: str = "") -> dict[str, Any]:
        """管理画面用: 指定資料をRAG検索対象から外し、元ファイルも削除する。"""
        target_name = str(document_name or "").strip()
        target_type = str(source_type or "").strip().lower()
        if not target_name:
            return {"ok": False, "message": "削除対象のファイル名が不明です。"}

        manifest = get_document_rag_manifest()
        chunks = load_document_chunks()
        before_chunk_count = len(chunks)
        removed_file_count = 0
        source_path = ""

        new_files = []
        for item in manifest.get("files", []) or []:
            if not isinstance(item, dict):
                continue
            item_name = str(item.get("name", "") or "").strip()
            item_type = str(item.get("type", "") or Path(item_name).suffix.lower().lstrip(".")).strip().lower()
            if item_name == target_name and (not target_type or item_type == target_type):
                removed_file_count += 1
                source_path = str(item.get("path", "") or "")
                continue
            new_files.append(item)
        manifest["files"] = new_files

        if target_type == "wiki" or target_name == "wiki_input.txt":
            manifest["wiki_enabled"] = False

        new_chunks = [row for row in chunks if not _chunk_matches_document(row, target_name, target_type)]
        removed_chunk_count = before_chunk_count - len(new_chunks)

        _safe_unlink_source_file(source_path, target_name)
        manifest["last_deleted"] = {
            "name": target_name,
            "type": target_type,
            "deleted_by": str(deleted_by or "不明"),
            "deleted_at": _now_iso(),
            "removed_chunks": removed_chunk_count,
        }
        _write_manifest_after_change(manifest, new_chunks)

        if removed_file_count == 0 and removed_chunk_count == 0 and target_name != "wiki_input.txt":
            return {"ok": False, "message": "対象資料が見つかりませんでした。"}
        return {
            "ok": True,
            "message": f"{target_name} を削除しました。削除チャンク数: {removed_chunk_count}",
            "removed_chunks": removed_chunk_count,
        }

    def clear_document_rag() -> bool:
        try:
            if DOC_RAG_FILES_DIR.exists():
                shutil.rmtree(DOC_RAG_FILES_DIR, ignore_errors=True)
            DOC_RAG_FILES_DIR.mkdir(parents=True, exist_ok=True)
            for path_obj in [DOC_RAG_MANIFEST_PATH, DOC_RAG_CHUNKS_PATH, DOC_RAG_EMBEDDINGS_PATH, DOC_RAG_TFIDF_INDEX_PATH]:
                if path_obj.exists():
                    path_obj.unlink()
            _safe_write_json(DOC_RAG_MANIFEST_PATH, _empty_manifest())
            persist_runtime_file(DOC_RAG_MANIFEST_PATH, label="doc_rag_manifest")
            return True
        except Exception:
            return False

    def _build_tfidf_index(chunks: list[dict[str, Any]]) -> dict[str, Any] | None:
        """RAG用TF-IDF indexを作成する。

        以前は検索のたびに fit_transform していたため、資料数が増えると毎回遅くなっていた。
        取込時に一度だけ作り、質問時は保存済みindexを読み込む。
        """
        try:
            texts = [str(x.get("text", "")) for x in chunks]
            if not texts:
                return None
            vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4))
            matrix = vectorizer.fit_transform(texts)
            chunk_ids = [str(x.get("chunk_id", "")) for x in chunks]
            return {"vectorizer": vectorizer, "matrix": matrix, "chunk_count": len(chunks), "chunk_ids": chunk_ids}
        except Exception:
            return None

    def _save_tfidf_index(chunks: list[dict[str, Any]]) -> None:
        try:
            payload = _build_tfidf_index(chunks)
            if payload is None:
                return
            DOC_RAG_TFIDF_INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
            with DOC_RAG_TFIDF_INDEX_PATH.open("wb") as fh:
                pickle.dump(payload, fh, protocol=pickle.HIGHEST_PROTOCOL)
        except Exception:
            pass

    def _load_tfidf_index(chunks: list[dict[str, Any]]):
        try:
            if not DOC_RAG_TFIDF_INDEX_PATH.exists():
                return None
            with DOC_RAG_TFIDF_INDEX_PATH.open("rb") as fh:
                payload = pickle.load(fh)
            if not isinstance(payload, dict):
                return None
            if int(payload.get("chunk_count", -1)) != len(chunks):
                return None
            expected_ids = [str(x.get("chunk_id", "")) for x in chunks]
            if payload.get("chunk_ids") != expected_ids:
                return None
            if payload.get("vectorizer") is None or payload.get("matrix") is None:
                return None
            return payload
        except Exception:
            return None

    def build_document_rag_index(uploaded_files: list[Any] | None, wiki_text: str = "", uploaded_by: str = "") -> dict:
        uploaded_files = list(uploaded_files or [])
        wiki_text = normalize_doc_text(wiki_text)
        all_sections: list[dict[str, str]] = []
        saved_files: list[dict[str, str]] = []
        now = _now_iso()
        uploaded_by = str(uploaded_by or "不明").strip() or "不明"

        DOC_RAG_FILES_DIR.mkdir(parents=True, exist_ok=True)

        for uploaded in uploaded_files:
            try:
                original_name = str(getattr(uploaded, "name", "document")).strip() or "document"
                filename = _safe_source_filename(original_name)
                source_type = Path(filename).suffix.lower().lstrip(".") or "file"

                sections = extract_sections_from_uploaded_file(uploaded)
                if not sections:
                    continue
                # 一覧削除のキーと検索時の根拠名を揃える。
                for section in sections:
                    section["source_name"] = filename
                    section["source_type"] = str(section.get("source_type") or source_type).lower()
                all_sections.extend(sections)

                raw_bytes = uploaded.getvalue() if hasattr(uploaded, "getvalue") else uploaded.read()
                save_path = DOC_RAG_FILES_DIR / filename
                save_path.write_bytes(raw_bytes)
                saved_files.append({
                    "name": filename,
                    "type": source_type,
                    "path": str(save_path),
                    "uploaded_at": now,
                    "uploaded_by": uploaded_by,
                    "chunk_count": 0,
                })
            except Exception as exc:
                st.warning(f"ドキュメント取込に失敗しました: {getattr(uploaded, 'name', 'document')} / {exc}")

        if wiki_text:
            all_sections.append({
                "source_name": "wiki_input.txt",
                "source_type": "wiki",
                "location": "wiki",
                "text": wiki_text,
            })

        new_chunks = build_chunks_from_sections(all_sections)
        for row in new_chunks:
            row["chunk_id"] = _hash_chunk(row)

        if not new_chunks:
            return {"ok": False, "message": "取り込める本文がありませんでした。", "chunk_count": 0}

        # 既存資料を保持し、新規アップロード分だけ追加/同名差し替えする。
        # ここで全上書きすると、複数資料を入れたのに最後の1件だけ表示される。
        existing_manifest = get_document_rag_manifest()
        existing_chunks = load_document_chunks()
        replaced_keys = {
            (str(item.get("name", "") or ""), str(item.get("type", "") or "").lower())
            for item in saved_files
        }
        if wiki_text:
            replaced_keys.add(("wiki_input.txt", "wiki"))

        kept_chunks: list[dict[str, Any]] = []
        for row in existing_chunks:
            name = str(row.get("source_name", "") or "")
            typ = str(row.get("source_type", "") or "").lower()
            if (name, typ) in replaced_keys:
                continue
            kept_chunks.append(row)
        chunks = kept_chunks + new_chunks

        existing_files = existing_manifest.get("files", []) if isinstance(existing_manifest.get("files"), list) else []
        kept_files: list[dict[str, Any]] = []
        for item in existing_files:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "") or "")
            typ = str(item.get("type", "") or Path(name).suffix.lower().lstrip(".")).lower()
            if (name, typ) in replaced_keys:
                continue
            kept_files.append(item)
        manifest_files = kept_files + saved_files

        # ファイル別チャンク数をmanifestへ保存する。
        for item in manifest_files:
            item["chunk_count"] = _chunk_count_for(chunks, item["name"], item["type"])

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
        _save_tfidf_index(chunks)
        if embeddings is not None:
            np.save(DOC_RAG_EMBEDDINGS_PATH, embeddings)
        elif DOC_RAG_EMBEDDINGS_PATH.exists():
            DOC_RAG_EMBEDDINGS_PATH.unlink()

        wiki_still_enabled = bool(wiki_text) or any(
            str(row.get("source_type", "") or "").lower() == "wiki" or str(row.get("source_name", "") or "") == "wiki_input.txt"
            for row in chunks
        )
        manifest = {
            "enabled": True,
            "doc_count": len(manifest_files) + (1 if wiki_still_enabled else 0),
            "chunk_count": len(chunks),
            "files": manifest_files,
            "wiki_enabled": wiki_still_enabled,
            "wiki_uploaded_at": now if wiki_text else str(existing_manifest.get("wiki_uploaded_at", "") or ""),
            "wiki_uploaded_by": uploaded_by if wiki_text else str(existing_manifest.get("wiki_uploaded_by", "") or ""),
            "updated_at": now,
        }
        _safe_write_json(DOC_RAG_MANIFEST_PATH, manifest)
        _persist_doc_paths(DOC_RAG_CHUNKS_PATH, DOC_RAG_MANIFEST_PATH)
        if DOC_RAG_TFIDF_INDEX_PATH.exists():
            _persist_doc_paths(DOC_RAG_TFIDF_INDEX_PATH)
        if DOC_RAG_EMBEDDINGS_PATH.exists():
            _persist_doc_paths(DOC_RAG_EMBEDDINGS_PATH)
        for item in saved_files:
            _persist_doc_paths(Path(item["path"]))

        return {"ok": True, "message": f"{manifest['doc_count']}件の資料を取り込みました。", "chunk_count": len(chunks), "manifest": manifest}

    def _expand_document_search_query(query: str) -> str:
        """検索用に質問文を少しだけ展開する。

        Excelチェックシートでは「入室制限」のようなユーザー語と、
        資料側の「入退室管理」「入室可能者の制限」が一致しないことがある。
        汎用の質問語を弱め、業務語の言い換えを足して検索漏れを減らす。
        """
        clean = normalize_doc_text(query)
        if not clean:
            return ""
        core = clean
        core = re.sub(r"(について|に関して|とは|ですか|ますか|でしょうか|どのように|どのような|どうなっていますか|どうなってますか|教えてください|教えて)", " ", core)
        additions: list[str] = []
        if _detect_rag_intent(clean) == "explain":
            additions.append("とは 概要 定義 目的 趣旨 説明 基本方針 適用範囲 意味")
        if "36協定" in clean or "三六協定" in clean or "サブロク協定" in clean:
            additions.append("36協定 三六協定 時間外労働 休日労働 労使協定 労働基準監督署 届出 残業 協定")
        if any(token in clean for token in ("入室", "入退室", "入室制限", "入室者")):
            additions.append("入退室管理 入室可能者 入室者 制限 管理台帳 監視カメラ セキュリティカード 持ち込む機器 管理区域")
        if any(token in clean for token in ("パスワード", "password")):
            additions.append("パスワード 個人ID 管理 ルール 要領 基準 文字数 7桁 数字 アルファベット 推測されやすい 個人に関連する情報 秘密")
        if any(token in clean for token in ("アカウント", "ID", "ログイン", "アクセス権")):
            additions.append("アクセス制御 アカウント管理 発行 登録 削除 棚卸 権限 個人ID パスワード")
        if any(token in clean for token in ("廃棄", "消去", "破棄")):
            additions.append("機密情報の消去 廃棄 データ消去 物理的に破壊 廃棄証明 産業廃棄物業者")
        if any(token in clean for token in ("不正アクセス", "復旧", "復旧手順", "復旧手続", "被害時", "リカバリ", "障害発生")):
            additions.append("障害発生時 技術的対応 復旧手続 復旧手順 整備 不正アクセス 発生 対応 対策 コンピュータウイルス 被害時 リカバリ機能")
        if any(token in clean for token in ("持出", "持ち出", "持ち込み", "持込", "私有", "USB")):
            additions.append("持出し管理 持ち込む機器 私有機器 情報記憶媒体 USB 許可 禁止")
        return normalize_doc_text(" ".join([core, clean, *additions]))

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
        if not chunks:
            return []
        payload = _load_tfidf_index(chunks)
        if payload is None:
            # 旧データ互換: まだ保存indexが無い場合は一度だけ作成して保存する。
            _save_tfidf_index(chunks)
            payload = _load_tfidf_index(chunks)
        if payload is None:
            return []
        try:
            vectorizer = payload["vectorizer"]
            matrix = payload["matrix"]
            search_query = _expand_document_search_query(query) or query
            qv = vectorizer.transform([search_query])
            scores = cosine_similarity(qv, matrix).flatten()
            order = np.argsort(scores)[::-1][:top_k]
            hits: list[dict[str, Any]] = []
            for idx in order:
                item = dict(chunks[int(idx)])
                item["score"] = float(scores[int(idx)])
                hits.append(item)
            return hits
        except Exception:
            return []

    def _is_customer_area_form_query(query: str) -> bool:
        q = normalize_doc_text(query).lower()
        q_compact = re.sub(r"[\s\u3000、。,.!！?？…・･~〜ー\-＿_（）()「」『』【】\[\]]+", "", q)
        customer = ("顧客" in q or "お客様" in q or "客先" in q or "取引先" in q)
        area = any(t in q for t in ("領域", "環境", "スペース", "テナント", "エリア", "指定システム", "顧客システム"))
        action = any(t in q for t in ("作成", "作る", "利用", "申請", "申請書", "書式", "様式", "どれ", "どの"))
        compact_hit = any(t in q_compact for t in ("顧客領域作成", "顧客環境作成", "顧客指定システム", "顧客システム利用"))
        return bool((customer and area and action) or compact_hit)


    def _compact_for_match(text: str) -> str:
        """資料名・質問文の比較用に空白/記号を落とす。"""
        t = normalize_doc_text(text).lower()
        return re.sub(r"[\s\u3000、。,.!！?？…・･~〜ー\-＿_（）()「」『』【】\[\]\\/]+", "", t)

    def _extract_requested_document_keywords(user_q: str) -> list[str]:
        """質問に含まれる文書名らしい語を抽出する。

        固定の文言ではなく、「○○規程」「○○規定」「○○規則」「○○マニュアル」
        「○○申請書」などの構造から取得する。
        """
        q = normalize_doc_text(user_q)
        found: list[str] = []
        patterns = [
            r"[一-龥ぁ-んァ-ンA-Za-z0-9０-９]{2,}(?:規程|規定|規則|規約|要領|マニュアル|手順書|申請書|様式|書式)",
            r"[一-龥ぁ-んァ-ンA-Za-z0-9０-９]{2,}(?:pdf|docx|xlsx|xlsm)",
        ]
        for pat in patterns:
            for m in re.finditer(pat, q, flags=re.I):
                kw = normalize_doc_text(m.group(0))
                if kw and kw not in found:
                    found.append(kw)
        # 「情報システム管理規定」のような表記揺れは規程にも寄せる。
        more: list[str] = []
        for kw in found:
            if kw.endswith("規定"):
                more.append(kw[:-2] + "規程")
            if kw.endswith("規程"):
                more.append(kw[:-2] + "規定")
        for kw in more:
            if kw and kw not in found:
                found.append(kw)
        return found

    def _document_keyword_match_score(user_q: str, hit: dict[str, Any]) -> float:
        keywords = _extract_requested_document_keywords(user_q)
        if not keywords:
            return 0.0
        source = _compact_for_match(str(hit.get("source_name", "") or ""))
        loc = _compact_for_match(str(hit.get("location", "") or ""))
        text_head = _compact_for_match(str(hit.get("text", "") or "")[:500])
        score = 0.0
        for kw in keywords:
            ckw = _compact_for_match(kw)
            if not ckw:
                continue
            # 質問で指定された文書名が資料名に入る場合は最重要。
            if ckw in source:
                score += 1.0
            elif source and (source in ckw or ckw in source):
                score += 0.7
            elif ckw in loc:
                score += 0.35
            elif ckw in text_head:
                score += 0.20
        return score

    def _extract_article_block_from_text(text: str, article_no: str) -> tuple[str, str]:
        """本文から指定された条文ブロックだけを抜き出す。

        RAGの意味スコアではなく、文書構造としての「第◯条」を直接探す。
        目次の短い行は避け、本文らしい長さのブロックを優先する。
        """
        clean = normalize_doc_text(text)
        if not clean or not article_no:
            return "", ""
        num_pat = re.escape(str(article_no))
        # 第 13 条 / 第13条 / 13条 の表記揺れに対応
        pat = re.compile(rf"(?ms)(^\s*第\s*{num_pat}\s*条[^\n]*\n?.*?)(?=^\s*第\s*[0-9０-９]+\s*条|\Z)")
        candidates: list[str] = []
        for m in pat.finditer(clean):
            block = normalize_doc_text(m.group(1))
            if block:
                candidates.append(block)
        if not candidates:
            # 1行内に「第13条 保管場所 重要データ...」のように続く場合
            pat2 = re.compile(rf"(?s)(第\s*{num_pat}\s*条[^\n]{{0,120}}(?:\n|.){{0,900}}?)(?=第\s*[0-9０-９]+\s*条|\Z)")
            for m in pat2.finditer(clean):
                block = normalize_doc_text(m.group(1))
                if block:
                    candidates.append(block)
        if not candidates:
            return "", ""
        # 目次より本文を優先。本文は長めで句点や箇条書きを含みやすい。
        def rank_block(b: str) -> tuple[int, int]:
            is_toc = 1 if ("目次" in b[:120] or len(b) < 30) else 0
            content_score = len(re.findall(r"[。．\n]|しなければならない|ものとする|次の", b))
            return (-is_toc, content_score + min(len(b), 1200)//80)
        best = sorted(candidates, key=rank_block, reverse=True)[0]
        first = best.split("\n", 1)[0].strip()
        return first, best

    def _find_direct_article_hits(user_q: str, chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """第◯条などの明確指定は、RAGスコアではなく条文構造で直接取得する。"""
        article_no = _extract_article_number(user_q)
        if not article_no:
            return []
        direct: list[dict[str, Any]] = []
        for chunk in chunks:
            if not isinstance(chunk, dict):
                continue
            stype = str(chunk.get("source_type", "") or "").lower()
            if stype in {"xlsx", "xlsm"}:
                continue
            location = str(chunk.get("location", "") or "")
            text = str(chunk.get("text", "") or "")
            heading, block = _extract_article_block_from_text("\n".join([location, text]), article_no)
            if not block:
                continue
            new_hit = dict(chunk)
            new_hit["location"] = heading or location or f"第{article_no}条"
            new_hit["chunk_label"] = "article_direct"
            new_hit["text"] = block
            new_hit["score"] = 1.0 + _document_keyword_match_score(user_q, new_hit)
            new_hit["direct_match"] = "article"
            direct.append(new_hit)
        if not direct:
            return []
        # 質問内に文書名がある場合は、その文書名に合う資料を最優先。
        direct.sort(key=lambda h: (float(h.get("score", 0.0)), _document_keyword_match_score(user_q, h), len(str(h.get("text", "")))), reverse=True)
        return direct[:5]

    def _hit_contradiction_reason(user_q: str, hit: dict[str, Any]) -> str:
        """質問と候補が明確に矛盾している場合に理由を返す。"""
        q_article = _extract_article_number(user_q)
        if q_article:
            hay = normalize_doc_text("\n".join([
                str(hit.get("location", "") or ""),
                str(hit.get("chunk_label", "") or ""),
                str(hit.get("text", "") or "")[:500],
            ]))
            h_article = _extract_article_number(hay)
            if h_article and h_article != q_article:
                return f"質問は第{q_article}条ですが、候補は第{h_article}条です。"
            if not re.search(rf"第\s*{re.escape(q_article)}\s*条", hay):
                return f"質問は第{q_article}条ですが、候補内に第{q_article}条が確認できません。"
        intent = _detect_rag_intent(user_q)
        stype = str(hit.get("source_type", "") or "").lower()
        text = normalize_doc_text(str(hit.get("text", "") or ""))
        if intent == "form":
            hay_all = normalize_doc_text("\n".join([
                str(hit.get("source_name", "") or ""),
                str(hit.get("location", "") or ""),
                str(hit.get("chunk_label", "") or ""),
                str(hit.get("text", "") or ""),
            ]))
            if _is_customer_area_form_query(user_q) and _contains_customer_area_creation(user_q):
                # 「顧客の領域作成」の質問に、単なる「顧客指定システム利用」だけで答えない。
                if ("顧客指定システム利用申請" in hay_all
                    and not _contains_customer_area_creation(hay_all)
                    and not any(t in hay_all for t in ("システム作業申請書", "書式3", "責任者承認"))):
                    return "質問は顧客の領域作成ですが、候補は顧客指定システム利用申請のみで、領域作成または使用する申請書名が確認できません。"
            if stype in {"xlsx", "xlsm"}:
                # 申請書探しなのに判定だけの候補は回答にしない。
                if not any(t in text for t in ("申請書", "書式", "様式", "フォーム", "システム作業申請書", ".xlsx", ".docx", ".pdf")):
                    return "申請書・書式を尋ねていますが、候補内に申請書名や書式名が確認できません。"
        if intent in {"explain", "rule", "role"} and stype in {"xlsx", "xlsm"}:
            if re.search(r"判定結果\s*[:：]\s*[○〇×\-－ー]", text) and len(text) < 250:
                return "説明・規程内容を尋ねていますが、候補はExcelの判定行だけです。"
        return ""

    def _filter_contradictory_hits(user_q: str, hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not hits:
            return []
        good: list[dict[str, Any]] = []
        for h in hits:
            reason = _hit_contradiction_reason(user_q, h)
            if reason:
                h = dict(h)
                h["contradiction_reason"] = reason
                continue
            good.append(h)
        return good

    def _safe_no_confident_answer(user_q: str, hits: list[dict[str, Any]], reason: str = "") -> str:
        """怪しい候補で無理に回答せず、候補表示に留める安全回答。"""
        lines = [
            "社内資料内に関連しそうな候補は見つかりましたが、質問内容と根拠が完全には一致しないため、断定回答は控えます。",
        ]
        if reason:
            lines.extend(["", f"理由: {reason}"])
        if hits:
            lines.extend(["", "【参考候補】"])
            for h in hits[:3]:
                title = normalize_doc_text(str(h.get("location", "") or h.get("chunk_label", "") or ""))
                src = normalize_doc_text(str(h.get("source_name", "") or ""))
                excerpt = normalize_doc_text(str(h.get("text", "") or ""))[:140]
                lines.append(f"- {src} / {title}")
                if excerpt:
                    lines.append(f"  {excerpt}…")
        lines.extend(["", "資料名・条番号・申請書名などをもう少し具体的に入力するか、管理者に資料内容の確認を依頼してください。"])
        return "\n".join(lines).strip()

    def _expand_document_rag_query(query: str) -> str:
        """自然文の言い換えを社内資料・申請書名に寄せる。

        例: 「顧客の領域作成の申請書はどれですか？」
        → 顧客指定システム利用申請 / システム作業申請書 / 書式3 も検索語に加える。
        これにより、資料側の表現とユーザーの言い方が違っても拾いやすくする。
        """
        q = normalize_doc_text(query)
        additions: list[str] = []
        if _is_customer_area_form_query(q):
            additions.append(
                "顧客指定システム利用申請 顧客指定システム利用 顧客指定システム "
                "顧客システム利用 顧客領域作成 顧客環境作成 顧客用領域 領域作成 環境作成 "
                "システム作業申請書 書式3 書式3_システム作業申請書_責任者承認まで 申請書 書式 様式"
            )
        if any(t in q for t in ("申請書", "書式", "様式", "フォーム", "テンプレート", "どれですか", "どの申請書")):
            additions.append("申請書 書式 様式 フォーム テンプレート ファイル名 資料名")
        # 条番号・役割質問は、意味検索ではなく文書構造を強く使う。
        m_article = re.search(r"第\s*([0-9０-９]+)\s*条", q)
        if m_article:
            additions.append(f"第{m_article.group(1)}条 条文 見出し 本文")
        if any(t in q for t in ("どのようなこと", "何を行", "なにを行", "役割", "職務", "責務", "権限", "任務")):
            additions.append("役割 職務 責務 任務 権限 補佐 参画 遂行 責任")
        if not additions:
            return q
        return normalize_doc_text(q + " " + " ".join(additions))

    def _contains_customer_area_creation(text: str) -> bool:
        """顧客の領域/環境作成そのものを指す語があるかを見る。"""
        t = normalize_doc_text(text).lower()
        c = re.sub(r"[\s\u3000、。,.!！?？…・･~〜ー\-＿_（）()「」『』【】\[\]\\/]+", "", t)
        return any(x in c for x in (
            "顧客領域作成", "顧客の領域作成", "顧客環境作成", "顧客の環境作成",
            "顧客用領域", "顧客用環境", "領域作成", "環境作成",
        ))

    def _hit_text_for_exact_match(hit: dict[str, Any]) -> str:
        return normalize_doc_text("\n".join([
            str(hit.get("source_name", "") or ""),
            str(hit.get("location", "") or ""),
            str(hit.get("chunk_label", "") or ""),
            str(hit.get("text", "") or ""),
        ]))

    def _extract_exact_form_file_terms(user_q: str) -> list[str]:
        """書式名・申請書名・ファイル名らしい語を質問から抽出する。"""
        q = normalize_doc_text(user_q)
        terms: list[str] = []
        def add(term: str) -> None:
            term = normalize_doc_text(term).strip(" 　。．、,，:：;；「」『』【】[]()（）")
            if len(term) >= 2 and term not in terms:
                terms.append(term)
        for pat in (
            r"[A-Za-z0-9０-９_\-一-龥ぁ-んァ-ン ]{2,}\.(?:xlsx|xlsm|xls|docx|doc|pdf)",
            r"[A-Za-z0-9０-９_\-一-龥ぁ-んァ-ン ]{2,}(?:申請書|書式|様式|フォーム|テンプレート)",
            r"書式\s*[0-9０-９A-Za-z_-]+",
        ):
            for m in re.finditer(pat, q, flags=re.I):
                add(m.group(0))
        # 自然文の重要語。完全一致ではなく、後段の直接候補抽出用。
        if _is_customer_area_form_query(q):
            if _contains_customer_area_creation(q):
                add("領域作成")
                add("環境作成")
            add("システム作業申請書")
            add("書式3")
        return terms[:8]

    def _find_direct_form_or_file_hits(query: str, chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """書式名・ファイル名・明確な申請語はRAGスコアより先に直接一致で拾う。"""
        terms = _extract_exact_form_file_terms(query)
        if not terms:
            return []
        q_customer_area = _is_customer_area_form_query(query)
        q_area_creation = _contains_customer_area_creation(query)
        direct: list[dict[str, Any]] = []
        for chunk in chunks:
            if not isinstance(chunk, dict):
                continue
            hay = _hit_text_for_exact_match(chunk)
            hay_compact = _compact_for_match(hay)
            score = 0.0
            matched: list[str] = []
            for term in terms:
                cterm = _compact_for_match(term)
                if not cterm:
                    continue
                if cterm in hay_compact:
                    matched.append(term)
                    # ファイル名/書式名/申請書名の一致は強く見る。
                    if "." in term or "申請書" in term or "書式" in term or "様式" in term:
                        score += 1.2
                    else:
                        score += 0.7
            if q_customer_area:
                # 「顧客の領域作成」を尋ねている時は、単なる「顧客指定システム利用申請」だけでは確定にしない。
                # 領域/環境/作成 または実際の作業申請書・書式3がある候補を優先する。
                if any(x in hay for x in ("システム作業申請書", "書式3", "責任者承認")):
                    score += 1.0
                if _contains_customer_area_creation(hay):
                    score += 1.0
                if q_area_creation and "顧客指定システム利用申請" in hay and not (_contains_customer_area_creation(hay) or "システム作業申請書" in hay or "書式3" in hay):
                    score -= 1.3
            if score <= 0:
                continue
            h = dict(chunk)
            h["score"] = max(float(h.get("score", 0.0) or 0.0), min(score, 3.0))
            h["direct_match"] = "form_or_file"
            h["matched_terms"] = matched
            direct.append(h)
        direct.sort(key=lambda h: (float(h.get("score", 0.0)), len(str(h.get("text", "") or ""))), reverse=True)
        return direct[:8]

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

        # 第◯条のように明確な構造指定がある質問は、意味検索スコアで順位を決めず、
        # 条文インデックスとして直接探す。これにより「第13条」なのに「第6条」を返す事故を止める。
        direct_article_hits = _find_direct_article_hits(query, chunks)
        direct_form_file_hits = _find_direct_form_or_file_hits(query, chunks)
        search_query = _expand_document_rag_query(query)
        # Excelは行単位の明示語一致が重要なため、TF-IDF結果を優先する。
        # PDF/Word等はsentence-transformersが使える場合のみ意味検索を優先する。
        # 意図判定後に並べ替えられるよう、候補は少し多めに取得する。
        # 以前はTF-IDFの1位がExcelの場合にExcelだけを優先していたため、
        # 「マルウェア対策について教えて」のような説明要求でも
        # チェックシートの○/×行が回答になっていた。
        # ここではTF-IDFと意味検索の候補を統合し、後段の意図別rerankに渡す。
        fetch_k = max(top_k * 3, 12)
        tfidf_hits = _search_with_tfidf(search_query, chunks, top_k=fetch_k)
        embedding_hits = _search_with_embeddings(search_query, chunks, top_k=fetch_k)

        merged: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()
        for hit in list(direct_article_hits or []) + list(direct_form_file_hits or []) + list(tfidf_hits or []) + list(embedding_hits or []):
            key = (
                str(hit.get("source_name", "") or ""),
                str(hit.get("location", "") or ""),
                str(hit.get("chunk_label", "") or ""),
            )
            if key in seen:
                continue
            seen.add(key)
            merged.append(hit)
        # 明確指定の直接ヒットは必ず先頭に残す。以降の回答側で矛盾チェックも行う。
        # 回答前の矛盾チェックで、明確に質問語と合わない候補は落とす。
        merged = _filter_contradictory_hits(query, merged) or merged
        return merged[:fetch_k] or direct_article_hits or direct_form_file_hits or tfidf_hits or embedding_hits


    def _to_half_digits(text: str) -> str:
        return unicodedata.normalize("NFKC", str(text or ""))

    def _extract_article_number(text: str) -> str:
        m = re.search(r"(?:第\s*)?([0-9０-９]+)\s*条", normalize_doc_text(text))
        return _to_half_digits(m.group(1)) if m else ""

    def _canonical_article_no(text: str) -> str:
        n = _extract_article_number(text)
        return n

    def _first_line(text: str) -> str:
        clean = normalize_doc_text(text)
        return clean.split("\n", 1)[0].strip() if clean else ""

    def _looks_like_article_hit(hit: dict[str, Any]) -> bool:
        hay = normalize_doc_text(" ".join([
            str(hit.get("location", "") or ""),
            str(hit.get("chunk_label", "") or ""),
            str(hit.get("text", "") or "")[:200],
        ]))
        return bool(re.search(r"第\s*[0-9０-９]+\s*条", hay))

    def _strip_article_heading(line: str) -> str:
        return normalize_doc_text(re.sub(r"^第\s*[0-9０-９]+\s*条\s*", "", normalize_doc_text(line))).strip()

    def _extract_query_subject(user_q: str) -> str:
        """質問の主語らしい語を抽出する。固定辞書ではなく、助詞・質問語で切る。"""
        q = normalize_doc_text(user_q)
        if not q:
            return ""
        # 条番号指定の場合は主語より条番号を優先するため、ここでは文書名を除く。
        q2 = re.sub(r".*?第\s*[0-9０-９]+\s*条", "", q)
        q2 = re.sub(r"(について|とは|はどのようなことを行いますか|はどのようなことを行う|は何を行いますか|はなにを行いますか|は何を行う|はなにを行う|の役割|の職務|の責務|の権限|を教えてください|を教えて|ですか|ますか|ください|下さい|何ですか|なにですか)", " ", q2)
        q2 = re.sub(r"(情報システム管理規程|組織規程|規程|規定|社内資料|資料)", " ", q2)
        tokens = re.findall(r"[0-9A-Za-z一-龥ぁ-んァ-ン]{2,}", q2)
        stop = {"どのよう", "どんな", "こと", "行い", "行う", "行います", "内容", "場合", "対応", "方法", "ルール", "管理"}
        tokens = [t for t in tokens if t not in stop]
        if not tokens:
            return ""
        # 役職・条文見出しでは短めの名詞が主語になりやすい。
        return max(tokens, key=len)[:40]

    def _source_matches_query_document(user_q: str, hit: dict[str, Any]) -> float:
        q = normalize_doc_text(user_q)
        src = normalize_doc_text(str(hit.get("source_name", "") or ""))
        if not q or not src:
            return 0.0
        score = 0.0
        # 「情報システム管理規程第13条」のように文書名が入っている場合は、その資料を強く優先する。
        for key in re.findall(r"[一-龥ぁ-んァ-ンA-Za-z0-9]{2,}規程", q):
            if key and key in src:
                score += 0.45
        for key in re.findall(r"[一-龥ぁ-んァ-ンA-Za-z0-9]{2,}規則", q):
            if key and key in src:
                score += 0.35
        if "情報システム管理" in q and "情報システム管理" in src:
            score += 0.45
        if "組織" in q and "組織" in src:
            score += 0.35
        return score

    def _article_or_subject_structural_score(user_q: str, hit: dict[str, Any]) -> float:
        """条番号・見出し一致を強く評価し、本文中の偶然一致を弱くする。"""
        location = normalize_doc_text(str(hit.get("location", "") or ""))
        text = normalize_doc_text(str(hit.get("text", "") or ""))
        first = _first_line(text) or location
        score = 0.0
        q_article = _extract_article_number(user_q)
        h_article = _extract_article_number(location) or _extract_article_number(first)
        if q_article:
            if h_article == q_article:
                score += 1.20
            elif h_article:
                score -= 0.50
        subject = _extract_query_subject(user_q)
        if subject:
            title = normalize_doc_text(location + " " + first)
            title_no_article = _strip_article_heading(title)
            # 見出し名そのものが主語に一致する場合だけ強く上げる。
            if title_no_article == subject or re.fullmatch(rf".*第\s*[0-9０-９]+\s*条\s*{re.escape(subject)}(?:\s|$).*", title):
                score += 0.75
            elif subject in title:
                score += 0.35
            elif subject in text[:260]:
                score += 0.12
        score += _source_matches_query_document(user_q, hit)
        return score

    def _detect_rag_intent(user_q: str) -> str:
        """質問の意図をざっくり分類する。

        RAGで「一番近い文字列」をそのまま答えにすると、
        例: 「36協定について教えて」に対して申請書の
        「下記1から17の項目を記入してください」を返してしまう。
        そのため、質問意図ごとに優先する根拠を変える。
        """
        q = normalize_doc_text(user_q)
        if _is_customer_area_form_query(q) or any(t in q for t in ("どの申請書", "申請書はどれ", "申請書はどの", "どの書式", "書式はどれ", "様式はどれ", "様式", "テンプレート", "フォーマット", "書式", "用紙")):
            return "form"
        if _extract_article_number(q):
            return "article"
        if any(t in q for t in ("どのようなこと", "何を行", "なにを行", "役割", "職務", "責務", "権限", "任務")):
            return "role"
        if any(t in q for t in ("とは", "意味", "概要", "説明", "教えて", "について", "どんなもの", "何ですか", "なにですか")):
            return "explain"
        if any(t in q for t in ("手順", "方法", "やり方", "申請", "提出", "登録", "入力", "記入", "どうすれば", "どうやって")):
            return "procedure"
        # 「パスワードのルールはありますか？」のような質問は、単純な可否ではなく
        # 規程・基準・要件の説明を求めているため、ルール抽出として扱う。
        if any(t in q for t in ("ルール", "規程", "規定", "基準", "要件", "決まり", "ポリシー", "取扱", "取り扱", "管理要領", "何桁", "文字数", "桁以上")):
            return "rule"
        if any(t in q for t in ("ありますか", "できますか", "されていますか", "していますか", "可能", "可否", "必要ですか")):
            return "yes_no"
        if any(t in q for t in ("期限", "いつまで", "期間", "何日", "何時間", "締切")):
            return "deadline"
        if any(t in q for t in ("誰", "担当", "責任者", "窓口", "部署")):
            return "owner"
        if any(t in q for t in ("様式", "テンプレート", "フォーマット", "書式", "用紙")):
            return "form"
        return "general"

    def _looks_like_form_instruction(text: str) -> bool:
        """説明回答としては不適切な、入力案内・申請書の指示文を検出する。"""
        t = normalize_doc_text(text)
        if not t:
            return False
        patterns = (
            "下記", "以下の項目", "項目を記入", "記入してください", "入力してください",
            "必要事項", "再作成を依頼", "申請してください", "提出してください",
            "添付してください", "チェックしてください", "選択してください", "クリックしてください",
        )
        if any(p in t for p in patterns):
            return True
        if re.search(r"(1|１)\s*から\s*(17|１７)", t):
            return True
        return False

    def _looks_like_definition_text(text: str) -> bool:
        t = normalize_doc_text(text)
        if not t:
            return False
        return any(p in t for p in (
            "とは", "定義", "概要", "目的", "趣旨", "は、", "とは、", "をいう", "について",
            "対象", "適用範囲", "基本方針", "目的とする",
        ))

    def _rag_hit_intent_score(user_q: str, hit: dict[str, Any]) -> float:
        intent = _detect_rag_intent(user_q)
        text = normalize_doc_text(str(hit.get("text", "") or ""))
        location = normalize_doc_text(str(hit.get("location", "") or ""))
        source_name = normalize_doc_text(str(hit.get("source_name", "") or ""))
        source_type = str(hit.get("source_type", "") or "").lower()
        base = float(hit.get("score", 0.0) or 0.0)
        score = base
        score += _article_or_subject_structural_score(user_q, hit)

        if intent in {"article", "role"}:
            if _looks_like_article_hit(hit):
                score += 0.25
            if source_type in {"pdf", "docx", "doc", "txt", "md"}:
                score += 0.12
            if source_type in {"xlsx", "xlsm"}:
                score -= 0.30

        if intent == "explain":
            if _looks_like_definition_text(text) or _looks_like_definition_text(location):
                score += 0.18
            # 規程・手順書・Word/PDFの本文は、説明要求ではExcelチェック表より優先しやすくする。
            if source_type in {"docx", "doc", "pdf", "txt", "md"}:
                score += 0.16
            # Excelチェックシートの「○/×判定」は、ありますか系では有効だが、
            # 「教えてください」「について」の説明要求では詳細説明として弱い。
            if source_type in {"xlsx", "xlsm"}:
                if any(p in text for p in ("○", "〇", "×", "講じていますか", "確認事項", "判定")):
                    score -= 0.28
            if any(p in text for p in ("申請", "届出", "様式", "フォーム", "チェックリスト")) and not _looks_like_definition_text(text):
                score -= 0.08
            if _looks_like_form_instruction(text):
                score -= 0.25
            if len(text) < 40:
                score -= 0.05
        elif intent == "procedure":
            if any(p in text for p in ("手順", "方法", "申請", "提出", "記入", "入力", "届出", "流れ", "フォーム")):
                score += 0.12
        elif intent == "rule":
            if any(p in text + location for p in ("第", "条", "規程", "規定", "ルール", "要領", "基準", "管理", "取り扱", "取扱", "設定", "してはならない", "しなければならない")):
                score += 0.18
            if any(p in text for p in ("7桁", "文字数", "数字", "アルファベット", "推測", "個人に関連", "他人に知られない", "非表示")):
                score += 0.18
            if _looks_like_form_instruction(text):
                score -= 0.10
        elif intent == "yes_no":
            if any(p in text for p in ("○", "〇", "×", "可", "不可", "必要", "不要", "できます", "できません", "対応済", "未対応")):
                score += 0.10
        elif intent == "deadline":
            if any(p in text for p in ("期限", "期間", "日以内", "日前", "時間", "締切", "まで")):
                score += 0.14
        elif intent == "owner":
            if any(p in text for p in ("担当", "責任者", "部署", "部門", "窓口", "管理者")):
                score += 0.14
        elif intent == "form":
            form_zone = text + source_name + location
            if any(p in form_zone for p in ("様式", "テンプレート", "書式", "フォーム", "申請書", "届", "作業申請書")):
                score += 0.22
            if _is_customer_area_form_query(user_q):
                if _contains_customer_area_creation(user_q):
                    # 領域/環境作成の質問では、実際の作成語または作業申請書・書式3を強く優先。
                    if _contains_customer_area_creation(form_zone):
                        score += 0.55
                    if any(p in form_zone for p in ("システム作業申請書", "書式3", "責任者承認")):
                        score += 0.55
                    # 単なる「顧客指定システム利用申請」だけの候補は、領域作成の答えとしては弱める。
                    if "顧客指定システム利用申請" in form_zone and not (_contains_customer_area_creation(form_zone) or any(p in form_zone for p in ("システム作業申請書", "書式3", "責任者承認"))):
                        score -= 0.45
                else:
                    if any(p in form_zone for p in ("顧客指定システム", "顧客システム", "顧客領域", "顧客環境", "領域作成", "環境作成")):
                        score += 0.38
                    if any(p in form_zone for p in ("システム作業申請書", "書式3", "責任者承認")):
                        score += 0.34
                # Microsoft 365等の一般FAQ/一般資料へ流れないように弱める。
                if any(p in form_zone.lower() for p in ("microsoft", "office 365", "teams", "outlook")) and not any(p in form_zone for p in ("顧客指定システム", "システム作業申請書")):
                    score -= 0.35

        return score

    def _rerank_hits_by_intent(user_q: str, hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not hits:
            return []
        intent = _detect_rag_intent(user_q)
        # Excelチェックシートは「ありますか」「できていますか」の判定質問では強いが、
        # 説明要求・規程確認ではWord/PDFの条文や本文を優先できるよう必ずrerankする。
        ranked = []
        for i, hit in enumerate(hits):
            h = dict(hit)
            h["intent_score"] = _rag_hit_intent_score(user_q, h)
            h["original_rank"] = i
            ranked.append(h)
        ranked.sort(key=lambda x: (float(x.get("intent_score", 0.0)), -int(x.get("original_rank", 0))), reverse=True)
        return ranked

    def _select_hits_for_answer(hits: list[dict[str, Any]], user_q: str = "") -> list[dict[str, Any]]:
        if not hits:
            return []
        ranked_hits = _rerank_hits_by_intent(user_q, hits) if user_q else hits
        intent = _detect_rag_intent(user_q) if user_q else "general"

        # 最終回答に使う前に、質問と明確に矛盾する候補を捨てる。
        # RAGスコアは「候補集め」にだけ使い、回答決定権は持たせない。
        filtered_hits = _filter_contradictory_hits(user_q, ranked_hits) if user_q else ranked_hits
        if not filtered_hits:
            return []
        ranked_hits = filtered_hits

        # 説明要求・規程確認では、Excelチェックシートの○/×行だけでなく、
        # Word/PDFの条文・本文を候補に残す。
        if intent in {"article", "role", "explain", "rule", "procedure"}:
            non_excel = [h for h in ranked_hits if str(h.get("source_type", "") or "").lower() not in {"xlsx", "xlsm"}]
            if non_excel:
                return non_excel[:4]

        top = ranked_hits[0]
        top_type = str(top.get("source_type", "") or "").lower()
        # Excelは1行が1つの答えになりやすい。複数行をLLMへ渡すと、
        # 近くの行（例: 廃棄行）まで混ざるため、最上位1行だけを使う。
        if top_type in {"xlsx", "xlsm"}:
            return [top]
        return ranked_hits[:4]

    def _extract_labeled_line(text: str, label: str) -> str:
        pattern = re.compile(rf"(?m)^{re.escape(label)}\s*:\s*(.*?)(?=\n[^\n:：]{{1,30}}[:：]|\Z)", re.S)
        match = pattern.search(normalize_doc_text(text))
        return normalize_doc_text(match.group(1)) if match else ""

    def _looks_like_excel_note(value: str) -> bool:
        v = normalize_doc_text(value)
        if not v:
            return True
        if len(v) <= 14 and (v.endswith("?") or v.endswith("？")):
            return True
        if v in {"システム", "システム?", "システム？", "運用", "体制", "対象外", "確認中"}:
            return True
        return False

    def _excel_display_score(value: str) -> int:
        v = normalize_doc_text(value)
        if not v or _looks_like_excel_note(v):
            return -10_000
        if re.fullmatch(r"[0-9０-９]+|[0-9０-９]+[-－][0-9０-９]+|[①-⑳◎○〇×△・－ー-]", v):
            return -10_000
        if v in {"○", "〇", "×", "-", "－", "ー", "対応済", "未対応", "該当無", "該当なし"}:
            return -10_000
        score = len(v)
        if any(token in v for token in ("ますか", "ですか", "していますか", "講じていますか", "確認", "管理", "体制", "規程", "ルール")):
            score += 70
        if any(token in v for token in ("整備", "対策", "手続", "対応", "制限", "防止", "管理", "確認", "復旧", "不正アクセス")):
            score += 45
        return score

    def _normalize_judgement_label(value: str) -> str:
        v = normalize_doc_text(value)
        if v == "〇":
            return "○"
        if v in {"ー", "-"}:
            return "－"
        return v

    def _parse_excel_hit_location(location: str) -> tuple[str, int]:
        """`sheet シート名 row 149` 形式からシート名と行番号を取り出す。"""
        loc = normalize_doc_text(location)
        m = re.search(r"sheet\s+(.+?)\s+row\s+(\d+)", loc, flags=re.I)
        if not m:
            return "", 0
        return m.group(1).strip(), int(m.group(2))

    def _extract_saved_excel_row(hit: dict[str, Any]) -> dict[str, str]:
        """保存済みExcel本体から該当行を読み直して、判定列を確実に復元する。

        過去バージョンで作られたチャンクでは、正規化時に `○` が落ちて
        `判定結果` が残っていないことがある。その場合でも、RAG管理で保存した
        元Excelファイルを参照して `AF: ○` のような判定セルを読み直す。
        """
        source_name = str(hit.get("source_name", "") or "").strip()
        source_type = str(hit.get("source_type", "") or "").lower()
        if source_type not in {"xlsx", "xlsm"} or not source_name:
            return {}
        sheet_name, row_idx = _parse_excel_hit_location(str(hit.get("location", "") or hit.get("chunk_label", "") or ""))
        if not sheet_name or row_idx <= 0:
            return {}

        candidates: list[Path] = [DOC_RAG_FILES_DIR / source_name]
        try:
            manifest = get_document_rag_manifest()
            for f in manifest.get("files", []) or []:
                if str(f.get("name", "")) == source_name and str(f.get("path", "")):
                    candidates.append(Path(str(f.get("path"))))
        except Exception:
            pass
        xlsx_path = next((p for p in candidates if p.exists()), None)
        if xlsx_path is None:
            return {}

        try:
            wb = load_workbook(xlsx_path, data_only=True, read_only=True)
            ws = wb[sheet_name] if sheet_name in wb.sheetnames else wb.active
            row = next(ws.iter_rows(min_row=row_idx, max_row=row_idx, values_only=False))
        except Exception:
            return {}

        cells: list[tuple[int, str]] = []
        for cell in row:
            cell_text = normalize_doc_text(cell.value)
            if cell_text:
                cells.append((int(cell.column), cell_text))
        if not cells:
            return {}

        judgement_marks = {"○", "〇", "×", "-", "－", "ー", "対応済", "未対応", "該当無", "該当なし"}
        judgement_pos = -1
        judgement = ""
        for i, (_col, val) in enumerate(cells):
            if re.fullmatch(r"[0-9０-９]+[-－][0-9０-９]+", val):
                continue
            if val in judgement_marks:
                judgement_pos = i
                judgement = _normalize_judgement_label(val)
                break

        id_text = ""
        if cells and re.fullmatch(r"[0-9０-９]+|[①-⑳]", cells[0][1]):
            id_text = cells[0][1]

        before_cells = cells[:judgement_pos] if judgement_pos >= 0 else cells
        item_candidates: list[tuple[int, str]] = []
        topic_values: list[str] = []
        for i, (_col, val) in enumerate(before_cells):
            if i == 0 and id_text:
                continue
            score = _excel_display_score(val)
            if score > 0:
                item_candidates.append((score, val))
        item = sorted(item_candidates, key=lambda x: x[0], reverse=True)[0][1] if item_candidates else ""
        for i, (_col, val) in enumerate(before_cells):
            if i == 0 and id_text:
                continue
            if val == item or _looks_like_excel_note(val):
                continue
            if 1 < len(val) <= 60 and _excel_display_score(val) > 0:
                topic_values.append(val)

        reason_values: list[str] = []
        note_values: list[str] = []
        if judgement_pos >= 0:
            for _col, val in cells[judgement_pos + 1:]:
                if _looks_like_excel_note(val):
                    note_values.append(val)
                else:
                    reason_values.append(val)

        parent = ""
        try:
            # 直近の親設問を上方向に探索。row149 のような ①②③ 明細の親を補足に出す。
            for r in range(row_idx - 1, max(0, row_idx - 12), -1):
                vals = [normalize_doc_text(c.value) for c in next(ws.iter_rows(min_row=r, max_row=r, values_only=False))]
                vals = [v for v in vals if v]
                if not vals:
                    continue
                joined = " / ".join(vals)
                if any(tok in joined for tok in ("以下の措置", "以下の項目", "として、以下", "講じていますか")):
                    pcands = [( _excel_display_score(v) + (120 if any(tok in v for tok in ("以下", "講じていますか", "として")) else 0), v) for v in vals if _excel_display_score(v) > 0]
                    if pcands:
                        parent = sorted(pcands, key=lambda x: x[0], reverse=True)[0][1]
                        break
        except Exception:
            pass

        return {
            "parent": parent,
            "topic": " / ".join(dict.fromkeys(topic_values)),
            "item": item,
            "question": item,
            "judgement": judgement,
            "reason": " / ".join(reason_values),
            "note": " / ".join(note_values),
        }

    def _parse_excel_raw_parts(text: str) -> dict[str, str]:
        """Excel行テキストから、親項目・該当項目・判定・理由を安全に推定する。

        重要: 右端の「システム？」のような分類欄は、回答や該当項目にしない。
        """
        clean = normalize_doc_text(text)
        raw = _extract_labeled_line(clean, "元データ") or clean
        raw = re.sub(r"^row\s+\d+\s*:\s*", "", raw.strip(), flags=re.I)
        def _strip_excel_col_prefix(value: str) -> str:
            # 旧チャンク互換: 「F: 文章」「AF: ○」のようなExcel列名を表示/判定から除去する。
            return normalize_doc_text(re.sub(r"^[A-Z]{1,3}:\s*", "", str(value or "")).strip())

        parts = [_strip_excel_col_prefix(p) for p in raw.split(" / ")]
        parts = [p for p in parts if p]

        judgement_marks = {"○", "〇", "×", "-", "－", "ー", "対応済", "未対応", "該当無", "該当なし"}
        judgement_idx = -1
        for i, part in enumerate(parts):
            if re.fullmatch(r"[0-9０-９]+[-－][0-9０-９]+", part):
                continue
            if part in judgement_marks:
                judgement_idx = i
                break

        parent = _extract_labeled_line(clean, "親項目")
        item = _strip_excel_col_prefix(_extract_labeled_line(clean, "該当項目"))
        question = _strip_excel_col_prefix(_extract_labeled_line(clean, "確認事項"))
        topic = _strip_excel_col_prefix(_extract_labeled_line(clean, "項目") or _extract_labeled_line(clean, "分類・補助項目"))
        judgement = _normalize_judgement_label(_strip_excel_col_prefix(_extract_labeled_line(clean, "判定結果")))
        reason = _strip_excel_col_prefix(_extract_labeled_line(clean, "回答・理由"))
        note = _strip_excel_col_prefix(_extract_labeled_line(clean, "備考"))

        # 旧データ互換: ラベルが無い/弱い場合は、判定列より左の最良セルを該当項目にする。
        if not item or _looks_like_excel_note(item):
            candidates: list[tuple[int, str]] = []
            search_parts = parts[:judgement_idx] if judgement_idx >= 0 else parts
            for p in search_parts:
                score = _excel_display_score(p)
                if score > 0:
                    candidates.append((score, p))
            if candidates:
                item = sorted(candidates, key=lambda x: x[0], reverse=True)[0][1]

        if not question or _looks_like_excel_note(question):
            question = item

        if not judgement and judgement_idx >= 0:
            judgement = _normalize_judgement_label(parts[judgement_idx])
        if not judgement:
            # 判定結果ラベルや raw の `AF: ○` / `F: ×` から判定を復元する。
            mark_re = r"(○|〇|×|－|ー|-)"
            patterns = [
                rf"(?:判定結果|判定|回答結果)\s*[:：]\s*{mark_re}",
                rf"(?:^|[ /\n])(?:[A-Z]{{1,3}}\s*[:：]\s*){mark_re}(?=$|[ /\n])",
                rf"(?:^|[ /\n]){mark_re}(?=$|[ /\n])",
            ]
            for pat in patterns:
                m = re.search(pat, clean)
                if m:
                    judgement = _normalize_judgement_label(m.group(1))
                    break

        # 旧データ互換: 判定列より右の値を理由にする。ただし短い分類欄は備考扱い。
        if not reason and judgement_idx >= 0 and judgement_idx + 1 < len(parts):
            reasons = [p for p in parts[judgement_idx + 1:] if not _looks_like_excel_note(p)]
            notes = [p for p in parts[judgement_idx + 1:] if _looks_like_excel_note(p)]
            reason = " / ".join(reasons)
            if not note:
                note = " / ".join(notes)
        elif reason and _looks_like_excel_note(reason):
            # 「回答・理由: システム？」のような既存チャンクを救済。
            note = note or reason
            reason = ""

        # 旧データで「項目: システム？」になっている場合は破棄。
        if _looks_like_excel_note(topic):
            topic = ""

        return {
            "parent": parent,
            "topic": topic,
            "item": item,
            "question": question,
            "judgement": judgement,
            "reason": reason,
            "note": note,
        }

    def _is_yes_no_question(user_q: str) -> bool:
        q = normalize_doc_text(user_q)
        return any(token in q for token in (
            "ありますか", "していますか", "されていますか", "されてますか", "できていますか",
            "できてますか", "講じていますか", "講じてますか", "対策は", "手順は",
            "整備されていますか", "整備されてますか", "制限されていますか", "制限されてますか",
        ))

    def _judgement_answer_sentence(user_q: str, judgement: str, reason: str = "") -> str:
        j = _normalize_judgement_label(judgement)
        if not j:
            return ""
        yes_no = _is_yes_no_question(user_q)
        if j == "○":
            return "はい、あります。判定は「○」です。" if yes_no else "資料上の判定は「○」です。"
        if j == "×":
            if yes_no:
                return "いいえ、判定は「×」です。"
            return "資料上の判定は「×」です。"
        if j in {"－", "該当無", "該当なし"}:
            return f"判定は「{j}」です。対象外または未判定の可能性があります。"
        if j == "対応済":
            return "はい、対応済です。" if yes_no else "資料上の判定は「対応済」です。"
        if j == "未対応":
            return "いいえ、未対応です。" if yes_no else "資料上の判定は「未対応」です。"
        return f"資料上の判定は「{j}」です。"

    def _format_excel_row_answer(user_q: str, hit: dict[str, Any]) -> str:
        parsed = _parse_excel_raw_parts(str(hit.get("text", "") or ""))
        saved = _extract_saved_excel_row(hit)
        # 保存済みExcel本体から読み取れた場合は、それを最優先にする。
        # 旧チャンクに判定「○」が残っていない場合でも正しく回答できる。
        if saved:
            for key in ("parent", "topic", "item", "question", "judgement", "reason", "note"):
                sv = normalize_doc_text(saved.get(key, ""))
                if sv and (key == "judgement" or not normalize_doc_text(parsed.get(key, "")) or _looks_like_excel_note(str(parsed.get(key, "")))):
                    parsed[key] = sv
        parent = parsed.get("parent", "")
        topic = parsed.get("topic", "")
        item = parsed.get("item", "") or parsed.get("question", "")
        question = parsed.get("question", "")
        judgement = parsed.get("judgement", "")
        reason = parsed.get("reason", "")
        source_name = str(hit.get("source_name", "") or "")
        location = str(hit.get("location", "") or hit.get("chunk_label", "") or "")

        lines = ["社内資料から該当箇所が見つかりました。", "", "【回答】"]

        judgement_sentence = _judgement_answer_sentence(user_q, judgement, reason)
        if judgement_sentence:
            lines.append(judgement_sentence)
            if reason:
                lines.append("")
                lines.append(reason)
        elif reason:
            lines.append(reason)
        elif item:
            lines.append(item)
        else:
            excerpt = str(hit.get("text", "") or "").strip()
            if len(excerpt) > 360:
                excerpt = excerpt[:360].rstrip() + "…"
            lines.append(excerpt)

        if item:
            lines.extend(["", "【該当項目】", item])
        if parent or topic or (reason and judgement):
            lines.extend(["", "【補足・根拠】"])
            if parent and item and judgement:
                parent_label = parent.replace("「", "").replace("」", "")
                lines.append(f"「{parent_label}」の中で、「{item}」が「{_normalize_judgement_label(judgement)}」になっています。")
            elif parent:
                lines.append(parent)
            if topic and topic != item:
                lines.append(topic)

        lines.extend(["", "【参照元】", f"- {source_name} / {location}".strip()])
        return "\n".join(lines).strip()


    def _query_content_tokens(user_q: str) -> list[str]:
        q = normalize_doc_text(user_q)
        # 一般的な質問語を除き、資料本文と照合しやすい語を残す。
        stop = {
            "について", "教えて", "ください", "下さい", "とは", "ですか", "ますか", "ありますか",
            "ルール", "規程", "規定", "基準", "要件", "決まり", "ポリシー", "方法", "手順",
            "どの", "よう", "どんな", "内容", "社内", "資料", "ください。",
        }
        tokens = re.findall(r"[0-9a-zA-Z一-龥ぁ-んァ-ン]{2,}", q)
        return [t for t in tokens if t not in stop]

    def _clean_policy_line(line: str) -> str:
        line = normalize_doc_text(line)
        # PDF抽出では日本語の文字間に空白が入ることがあるため、表示前に詰める。
        line = re.sub(r"(?<=[一-龥ぁ-んァ-ン、。，．])\s+(?=[一-龥ぁ-んァ-ン、。，．])", "", line)
        # 箇条書き番号だけを除去する。ただし「7桁」のように数値自体が意味を持つ場合は残す。
        line = re.sub(r"^(?:[0-9０-９]+[.．、)]|[①-⑳]|\([0-9０-９]+\))\s*", "", line).strip()
        return line


    def _clean_article_body_lines(text: str) -> tuple[str, list[str]]:
        clean = normalize_doc_text(text)
        lines = [ln.strip() for ln in clean.split("\n") if normalize_doc_text(ln)]
        if not lines:
            return "", []
        heading = ""
        body: list[str] = []
        for i, ln in enumerate(lines):
            if not heading and re.match(r"^第\s*[0-9０-９]+\s*条", ln):
                heading = ln
                body = lines[i + 1:]
                break
        if not heading:
            heading = lines[0]
            body = lines[1:]
        cleaned: list[str] = []
        for ln in body:
            c = normalize_doc_text(ln)
            if not c:
                continue
            # ヘッダー・フッター・ページ番号・目次断片を除外
            if re.fullmatch(r"[0-9０-９]+/[0-9０-９]+|[0-9０-９]+", c):
                continue
            if re.search(r"^(情報|[0-9０-９]{2}-[0-9０-９]{2}-[0-9０-９]{2})", c) and len(c) < 40:
                continue
            if c in {"第1版", "改訂", "主管", "部門"}:
                continue
            cleaned.append(_clean_policy_line(c))
        # 条文回答では、次条以降は混ぜない。
        final: list[str] = []
        for c in cleaned:
            if re.match(r"^第\s*[0-9０-９]+\s*条", c):
                break
            if c:
                final.append(c)

        # PDF抽出で1文が改行分断される場合があるため、文末記号が無い行は次行と結合する。
        merged: list[str] = []
        for c in final:
            if not merged:
                merged.append(c)
                continue
            prev = merged[-1]
            prev_ends = bool(re.search(r"[。.!！?？)]$", prev))
            current_starts_item = bool(re.match(r"^(?:[0-9０-９]+[.．、)]|[①-⑳]|\([0-9０-９]+\)|・|-)", c))
            if (not prev_ends) and (not current_starts_item):
                merged[-1] = normalize_doc_text(prev + c)
            else:
                merged.append(c)

        unique: list[str] = []
        for c in merged:
            if c and c not in unique:
                unique.append(c)
        return heading, unique

    def _try_format_structured_article_answer(user_q: str, hits: list[dict[str, Any]]) -> str:
        """第◯条・役割・規程説明は、最上位条文の本文だけで矛盾なく回答する。"""
        if not hits:
            return ""
        intent = _detect_rag_intent(user_q)
        if intent not in {"article", "role", "explain", "rule"}:
            return ""
        ranked = _rerank_hits_by_intent(user_q, hits)
        # 条番号指定がある場合は、該当条番号以外を回答にしない。
        q_article = _extract_article_number(user_q)
        candidates: list[dict[str, Any]] = []
        for h in ranked:
            stype = str(h.get("source_type", "") or "").lower()
            if stype in {"xlsx", "xlsm"}:
                continue
            if not _looks_like_article_hit(h):
                continue
            if q_article:
                h_article = _extract_article_number(str(h.get("location", "") or "")) or _extract_article_number(str(h.get("text", "") or ""))
                if h_article != q_article:
                    continue
            candidates.append(h)
        if not candidates:
            return ""
        top = candidates[0]
        heading, body_lines = _clean_article_body_lines(str(top.get("text", "") or ""))
        if not heading or not body_lines:
            return ""

        # 役割質問では、短すぎる断片ではなく条文本文を要約風にそのまま出す。
        intro = "社内資料の該当箇所は以下です。"
        if intent == "article":
            intro = f"{heading}の内容は以下です。"
        elif intent == "role":
            subj = _extract_query_subject(user_q)
            intro = f"{subj}の役割・職務は以下のとおりです。" if subj else "役割・職務は以下のとおりです。"
        elif intent in {"explain", "rule"}:
            intro = "社内資料に、以下の内容が記載されています。"

        # 条文本文は、番号付き/箇条書きを維持しつつ、長すぎる場合だけ抑える。
        selected = body_lines[:10]
        bullet_lines = []
        for ln in selected:
            if re.match(r"^(?:[0-9０-９]+[.．、)]|[①-⑳]|\([0-9０-９]+\))", ln):
                bullet_lines.append(ln)
            else:
                bullet_lines.append(f"- {ln}")
        refs = f"- {top.get('source_name', '')} / {top.get('location', '')}".strip()
        return "\n".join([intro, "", "【回答】", *bullet_lines, "", "【該当箇所】", heading, "", "参照資料:", refs]).strip()

    def _try_format_policy_rule_answer(user_q: str, hits: list[dict[str, Any]]) -> str:
        """規程・手順書の『ルール/基準/要件』質問は、LLM任せにせず根拠行を抽出する。

        例: 「パスワードのルールはありますか？」では、FAQの再設定手順ではなく、
        Word規程の『第10条 個人IDとパスワードの管理』にある
        7桁以上・英数字組み合わせ等を直接回答に出す。
        """
        if not hits:
            return ""
        intent = _detect_rag_intent(user_q)
        if intent not in {"article", "role", "rule", "explain", "yes_no"}:
            return ""
        q = normalize_doc_text(user_q)
        q_tokens = _query_content_tokens(q)
        top = hits[0]
        source_type = str(top.get("source_type", "") or "").lower()
        if source_type in {"xlsx", "xlsm"}:
            return ""
        text = normalize_doc_text(str(top.get("text", "") or ""))
        if not text:
            return ""

        # ルール質問では、質問の主要語が本文/見出しにある場合だけ抽出回答にする。
        hay = normalize_doc_text(" ".join([str(top.get("source_name", "")), str(top.get("location", "")), text]))
        if q_tokens and not any(t in hay for t in q_tokens):
            return ""

        password_rule = any(t in q for t in ("パスワード", "password")) and any(t in q for t in ("ルール", "規程", "規定", "基準", "要件", "何桁", "文字数", "管理", "取扱", "取り扱"))

        lines = [ln.strip() for ln in text.split("\n") if normalize_doc_text(ln)]
        # 見出しは第◯条などを優先。
        heading = str(top.get("location", "") or "").strip()
        for ln in lines[:4]:
            if re.match(r"^第\s*[0-9０-９]+\s*条", ln):
                heading = ln
                break

        selected: list[str] = []
        if password_rule:
            capture = False
            for ln in lines:
                c = _clean_policy_line(ln)
                if not c:
                    continue
                if "パスワード" in c and any(k in c for k in ("取り扱", "要領", "管理", "設定", "運営")):
                    capture = True
                    continue
                if capture:
                    # 次条に入ったら終了
                    if re.match(r"^第\s*[0-9０-９]+\s*条", c):
                        break
                    if any(k in c for k in ("7桁", "文字数", "数字", "アルファベット", "個人に関連", "推測", "各個人", "他人", "非表示")):
                        selected.append(c)
                elif any(k in c for k in ("7桁", "文字数", "数字", "アルファベット", "個人に関連", "推測", "各個人", "他人", "非表示")):
                    selected.append(c)
        else:
            for ln in lines:
                c = _clean_policy_line(ln)
                if not c or _looks_like_form_instruction(c):
                    continue
                if any(t in c for t in q_tokens) or any(k in c for k in ("しなければならない", "してはならない", "講じる", "設定する", "管理する", "承認")):
                    selected.append(c)

        # 重複除去・多すぎる場合は上位だけ
        unique: list[str] = []
        for item in selected:
            if item and item not in unique:
                unique.append(item)
        unique = unique[:8]
        if not unique:
            return ""

        if password_rule:
            intro = "はい、社内資料にパスワードのルールが記載されています。"
        elif _is_yes_no_question(user_q):
            intro = "はい、社内資料に関連する記載があります。"
        else:
            intro = "社内資料の該当箇所は以下です。"

        bullet_text = "\n".join(f"- {x}" for x in unique)
        refs = f"- {top.get('source_name', '')} / {top.get('location', '')}".strip()
        parts = [intro, "", "【回答】", bullet_text]
        if heading:
            parts.extend(["", "【該当箇所】", heading])
        parts.extend(["", "参照資料:", refs])
        return "\n".join(parts).strip()

    def _clean_application_form_name(name: str) -> str:
        """申請書名候補をユーザーに見せやすい形へ整える。

        Excelのセルには //svfl.../【試運転中】 システム作業申請書_責任者承認まで.xlsx
        のようなフルパスが入ることがある。回答ではファイル名だけを見せる。
        """
        n = normalize_doc_text(name)
        if not n:
            return ""
        n = n.replace("\\", "/")
        # パスを含む場合は末尾のファイル名だけ残す。
        if "/" in n:
            n = n.split("/")[-1]
        n = re.sub(r"^[・\-\s]+", "", n).strip()
        # 行テキストや列名の混入を除去。
        n = re.sub(r"^(?:資料名|元データ|回答|該当項目|補足|根拠)\s*[:：]\s*", "", n).strip()
        n = re.sub(r"^row\s*\d+\s*[:：]\s*", "", n, flags=re.I).strip()
        # 申請書ファイル名の後ろに説明文が続く場合は拡張子までで止める。
        m = re.search(r"([^\s、。/]+(?:システム作業申請書|申請書|書式)[^\s、。/]*?\.(?:xlsx|xlsm|xls|docx|doc|pdf))", n, flags=re.I)
        if m:
            n = m.group(1)
        return n.strip(" /、。")

    def _is_reference_form_catalog_name(name: str) -> bool:
        """申請書そのものではなく、申請書の説明資料・一覧表らしい名前を判定する。

        例: 「書式別システム作業申請書の説明.xlsx」は参照資料であり、
        ユーザーへ「使用する申請書」として出してはいけない。
        """
        n = normalize_doc_text(name).lower()
        if not n:
            return False
        if any(k in n for k in ("説明", "一覧", "対応表", "リスト", "台帳", "項目一覧", "マスタ", "早見表")):
            # ただし、実際の申請書ファイル名に近いものは除外しない。
            if "責任者承認" in n or "申請書_" in n or "申請書-" in n:
                return False
            return True
        return False

    def _extract_form_names_from_text(text: str, *, include_reference_materials: bool = False) -> list[str]:
        clean = normalize_doc_text(text)
        found: list[str] = []

        def _append_candidate(raw: str) -> None:
            name = _clean_application_form_name(raw)
            if not (3 <= len(name) <= 120):
                return
            if not include_reference_materials and _is_reference_form_catalog_name(name):
                return
            if name not in found:
                found.append(name)

        # まずファイル名らしい候補を優先して拾う。
        file_patterns = [
            r"[^\\/\s、。\n\r]*システム作業申請書[^\\/\s、。\n\r]*\.(?:xlsx|xlsm|xls|docx|doc|pdf)",
            r"[^\\/\s、。\n\r]*申請書[^\\/\s、。\n\r]*\.(?:xlsx|xlsm|xls|docx|doc|pdf)",
            r"[^\\/\s、。\n\r]*書式[^\\/\s、。\n\r]*\.(?:xlsx|xlsm|xls|docx|doc|pdf)",
        ]
        for pat in file_patterns:
            for m in re.finditer(pat, clean, flags=re.I):
                _append_candidate(m.group(0))

        # 次に申請名・書式名の候補を拾う。
        patterns = [
            r"書式\s*[0-9０-９A-Za-z_-]*[^\n\r、。]{0,80}?(?:申請書|承認|届|様式)[^\n\r、。]{0,80}?(?:\.xlsx|\.xlsm|\.xls|\.docx|\.doc|\.pdf)?",
            r"[^\n\r、。\s]{0,40}?(?:システム作業申請書|顧客指定システム利用申請|顧客指定システム利用|申請書|書式)[^\n\r、。\s]{0,80}?(?:\.xlsx|\.xlsm|\.xls|\.docx|\.doc|\.pdf)?",
        ]
        for pat in patterns:
            for m in re.finditer(pat, clean):
                _append_candidate(m.group(0))
        return found[:5]

    def _try_format_application_form_answer(user_q: str, hits: list[dict[str, Any]]) -> str:
        """申請書・書式探しは、本文要約より『どの申請書か』を先に答える。"""
        if not hits:
            return ""
        if _detect_rag_intent(user_q) != "form":
            return ""
        answer_hits = _rerank_hits_by_intent(user_q, hits)
        top = answer_hits[0]
        # 回答候補の抽出では、参照資料名（例: 「書式別...説明.xlsx」）を
        # 「使用する申請書」と誤認しないよう、まず本文・行データだけを見る。
        combined_body = "\n".join(
            " ".join([
                str(h.get("chunk_label", "") or ""),
                str(h.get("text", "") or ""),
            ])
            for h in answer_hits[:4]
        )
        combined_refs = "\n".join(
            " ".join([
                str(h.get("source_name", "") or ""),
                str(h.get("location", "") or ""),
            ])
            for h in answer_hits[:4]
        )
        combined = combined_body + "\n" + combined_refs
        names = _extract_form_names_from_text(combined_body)
        # 本文側にファイル名が無い場合のみ、参照資料名も補助的に見る。
        # ただし「説明.xlsx」「一覧.xlsx」等は _extract_form_names_from_text 側で除外する。
        if not names:
            names = _extract_form_names_from_text(combined_refs)
        is_customer_area = _is_customer_area_form_query(user_q)

        # 顧客領域/顧客環境の作成では、「顧客指定システム利用申請」とだけ出すと
        # ユーザーの質問（どの申請書/どこ）に対して不正確に見えるため、
        # 実際の作業申請書・書式名を優先し、単なる利用申請名は補助扱いにする。
        likely_application = ""
        area_creation_query = is_customer_area and _contains_customer_area_creation(user_q)
        if is_customer_area and not area_creation_query:
            if "顧客指定システム利用申請" in combined:
                likely_application = "顧客指定システム利用申請"
            elif "顧客指定システム利用" in combined or "顧客指定システム" in combined:
                likely_application = "顧客指定システム利用申請"

        preferred_file = ""
        real_names = [n for n in names if not _is_reference_form_catalog_name(n)]
        for n in real_names:
            if "システム作業申請書" in n or "書式3" in n or "責任者承認" in n:
                preferred_file = n
                break
        if not preferred_file and real_names:
            preferred_file = real_names[0]

        # 顧客領域/顧客環境作成は、実際に使う書式名が本文・参照にある場合のみ回答する。
        # 見つからない場合に「顧客指定システム利用申請」と断定しない。
        if is_customer_area and not preferred_file and ("書式3" in combined or "システム作業申請書" in combined or "責任者承認" in combined):
            if "書式3" in combined or "3_" in combined:
                preferred_file = "書式3_システム作業申請書_責任者承認まで.xlsx"
            else:
                preferred_file = "システム作業申請書_責任者承認まで.xlsx"

        if not likely_application and not preferred_file and not names:
            return ""

        lines = ["社内資料から該当する申請書・書式が見つかりました。", "", "【回答】"]
        if preferred_file:
            lines.append(f"使用する申請書は「{preferred_file}」です。")
        elif likely_application:
            # 書式名が取れない場合のみ、申請区分として案内する。
            lines.append(f"資料上では「{likely_application}」に関連する可能性がありますが、使用する申請書名まではこの候補だけでは断定できません。")
        elif real_names:
            lines.append("関連する申請書・書式候補は以下です。")
            lines.extend(f"- {n}" for n in real_names)
        if is_customer_area:
            lines.extend(["", "【補足】", "顧客領域作成/顧客環境作成の質問では、単なる『顧客指定システム利用』だけで断定せず、領域作成または使用書式名が根拠にある候補を優先しています。"])
        refs = "\n".join(
            f"- {h.get('source_name', '')} / {h.get('location', '')}".strip()
            for h in answer_hits[:3]
        )
        lines.extend(["", "参照資料:", refs])
        return "\n".join(lines).strip()


    def build_document_rag_prompt(user_q: str, hits: list[dict[str, Any]]) -> str:
        answer_hits = _select_hits_for_answer(hits, user_q)
        contexts: list[str] = []
        for i, hit in enumerate(answer_hits, start=1):
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
            "複数の根拠がある場合でも、質問に最も近い根拠1を最優先し、別項目の内容を混ぜないでください。"
            "Excel資料の場合は、提示されたExcel行だけを回答根拠にしてください。"
            "『〇〇について教えて』『〇〇とは』のような説明要求では、定義・概要・目的を優先し、申請書の入力案内だけを回答本文にしないでください。"
            "『下記を記入してください』『以下の項目を入力してください』などは、質問が入力方法を尋ねている場合を除き、関連資料の案内として扱ってください。"
            "資料内に定義や概要が見つからない場合は、無理に説明を作らず『詳しい説明は見つかりませんでした。ただし関連する記入案内があります』と明示してください。"
            "回答の最後に '参照資料:' を付けて、資料名と場所を箇条書きで並べてください。\n\n"
            f"[質問]\n{user_q}\n\n"
            f"[社内資料]\n{context_text}"
        )

    def answer_with_document_rag(user_q: str, hits: list[dict[str, Any]]) -> str:
        answer_hits = _select_hits_for_answer(hits, user_q)
        if not answer_hits:
            # 候補はあっても第◯条違い等で矛盾する場合は、無理に回答しない。
            first_reason = ""
            for h in hits or []:
                first_reason = _hit_contradiction_reason(user_q, h)
                if first_reason:
                    break
            return _safe_no_confident_answer(user_q, hits or [], first_reason)
        top = answer_hits[0] if answer_hits else {}
        top_type = str(top.get("source_type", "") or "").lower()

        # 申請書・書式探しの質問では、Excelの○/×判定よりも
        # 「どの申請書・書式を使うか」を最優先にする。
        # 例: 「顧客の領域作成の申請書はどれですか？」では、
        # row上の判定「○」ではなく「顧客指定システム利用申請」や
        # 「システム作業申請書_責任者承認まで.xlsx」を回答する。
        if _detect_rag_intent(user_q) == "form":
            form_answer = _try_format_application_form_answer(user_q, hits or answer_hits)
            if form_answer:
                return form_answer

        # 第◯条指定・役割/責務/規程説明では、条文単位の根拠だけで回答する。
        structured_article_answer = _try_format_structured_article_answer(user_q, answer_hits)
        if structured_article_answer:
            return structured_article_answer

        # 規程・マニュアルの説明要求では、Excelの○/×判定よりも
        # Word/PDF本文から条文・箇条書きを抽出した回答を優先する。
        policy_answer = _try_format_policy_rule_answer(user_q, answer_hits)
        if policy_answer:
            return policy_answer

        # Excelチェックシートは、LLMに複数行を渡すよりも、
        # 最上位1行から決定的に整形した方が混入事故が起きにくい。
        # ただし上の form / policy 分岐に該当しない場合だけ判定優先にする。
        if top_type in {"xlsx", "xlsm"}:
            return _format_excel_row_answer(user_q, top)

        intent = _detect_rag_intent(user_q)
        top_text = normalize_doc_text(str(top.get("text", "") or ""))
        # 説明要求に対して、申請書の入力案内しかヒットしていない場合は、
        # その案内文を「説明」として断定しない。
        if intent == "explain" and _looks_like_form_instruction(top_text) and not _looks_like_definition_text(top_text):
            refs = "\n".join(
                f"- {x.get('source_name', '')} / {x.get('location', '')}".strip()
                for x in answer_hits[:3]
            )
            excerpt = top_text[:220].rstrip() + ("…" if len(top_text) > 220 else "")
            return (
                "社内資料内には、この用語の詳しい定義・概要説明は見つかりませんでした。\n\n"
                "ただし、関連する申請・記入案内として以下の記載が見つかりました。\n\n"
                f"【関連記載】\n{excerpt}\n\n"
                f"参照資料:\n{refs}"
            ).strip()

        prompt = build_document_rag_prompt(user_q, answer_hits)
        try:
            messages = [
                {"role": "system", "content": "あなたは情シス担当です。資料に基づいて日本語で回答してください。別項目の内容を混ぜないでください。"},
                {"role": "user", "content": prompt},
            ]
            answer = str(llm_chat(messages) or "").strip()
            if answer:
                return answer
        except Exception:
            pass
        excerpt = str(top.get("text", "")).strip()
        if len(excerpt) > 260:
            excerpt = excerpt[:260].rstrip() + "…"
        refs = "\n".join(
            f"- {x.get('source_name', '')} / {x.get('location', '')}".strip()
            for x in answer_hits[:3]
        )
        return f"社内資料から該当箇所が見つかりました。\n\n{excerpt}\n\n参照資料:\n{refs}"

    return SimpleNamespace(
        DOC_RAG_DIR=DOC_RAG_DIR,
        DOC_RAG_FILES_DIR=DOC_RAG_FILES_DIR,
        DOC_RAG_MANIFEST_PATH=DOC_RAG_MANIFEST_PATH,
        DOC_RAG_CHUNKS_PATH=DOC_RAG_CHUNKS_PATH,
        DOC_RAG_TFIDF_INDEX_PATH=DOC_RAG_TFIDF_INDEX_PATH,
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
