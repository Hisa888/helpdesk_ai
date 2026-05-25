from __future__ import annotations

import hashlib
import json
import pickle
import re
import shutil
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
        """社内ドキュメントRAGを追加・更新する。

        重要:
        以前の実装は「この内容でRAGへ反映」を押すたびに chunks.json と
        manifest.json を新規作成していたため、後から別資料を追加すると
        管理一覧にも検索対象にも最後の1件しか残らなかった。

        この実装では、既存のRAGデータを読み込んだうえで、
        - 新しくアップロードされたファイルは追加
        - 同名ファイルは差し替え
        - アップロードしていない既存ファイルは保持
        - Wiki本文は入力された場合だけ差し替え
        として、複数資料を継続して保持する。
        """
        uploaded_files = list(uploaded_files or [])
        wiki_text = normalize_doc_text(wiki_text)
        now = _now_iso()
        uploaded_by = str(uploaded_by or "不明").strip() or "不明"

        if not uploaded_files and not wiki_text:
            return {"ok": False, "message": "取り込むファイルまたはWiki本文を指定してください。", "chunk_count": 0}

        DOC_RAG_FILES_DIR.mkdir(parents=True, exist_ok=True)

        existing_manifest = get_document_rag_manifest()
        existing_chunks = load_document_chunks()
        existing_files = [x for x in (existing_manifest.get("files", []) or []) if isinstance(x, dict)]

        new_sections: list[dict[str, Any]] = []
        saved_files: list[dict[str, Any]] = []
        replace_keys: set[tuple[str, str]] = set()
        failed_files: list[str] = []

        for uploaded in uploaded_files:
            original_name = str(getattr(uploaded, "name", "document")).strip() or "document"
            filename = _safe_source_filename(original_name)
            source_type = Path(filename).suffix.lower().lstrip(".") or "file"
            key = (filename, source_type)
            try:
                raw_bytes = uploaded.getvalue() if hasattr(uploaded, "getvalue") else uploaded.read()

                # Streamlit UploadedFile は getvalue() で繰り返し読めるが、
                # 念のため抽出関数側でも読めるようそのまま渡す。
                sections = extract_sections_from_uploaded_file(uploaded)
                if not sections:
                    failed_files.append(filename)
                    continue

                for section in sections:
                    section["source_name"] = filename
                    section["source_type"] = str(section.get("source_type") or source_type).lower()
                new_sections.extend(sections)

                save_path = DOC_RAG_FILES_DIR / filename
                save_path.write_bytes(raw_bytes)
                replace_keys.add(key)
                saved_files.append({
                    "name": filename,
                    "type": source_type,
                    "path": str(save_path),
                    "uploaded_at": now,
                    "uploaded_by": uploaded_by,
                    "chunk_count": 0,
                })
            except Exception as exc:
                failed_files.append(filename)
                try:
                    st.warning(f"ドキュメント取込に失敗しました: {filename} / {exc}")
                except Exception:
                    pass

        replace_wiki = bool(wiki_text)
        if wiki_text:
            new_sections.append({
                "source_name": "wiki_input.txt",
                "source_type": "wiki",
                "location": "wiki",
                "chunk_label": "wiki",
                "text": wiki_text,
            })

        new_chunks = build_chunks_from_sections(new_sections)
        for row in new_chunks:
            row["chunk_id"] = _hash_chunk(row)

        if not new_chunks:
            msg = "取り込める本文がありませんでした。"
            if failed_files:
                msg += " 失敗: " + ", ".join(failed_files[:5])
            return {"ok": False, "message": msg, "chunk_count": 0}

        def _is_replaced_chunk(row: dict[str, Any]) -> bool:
            name = str(row.get("source_name", "") or "").strip()
            source_type = str(row.get("source_type", "") or Path(name).suffix.lower().lstrip(".") or "file").strip().lower()
            if replace_wiki and (source_type == "wiki" or name == "wiki_input.txt"):
                return True
            return (name, source_type) in replace_keys

        kept_chunks = [row for row in existing_chunks if isinstance(row, dict) and not _is_replaced_chunk(row)]
        chunks = kept_chunks + new_chunks

        # 同名・同種の既存manifest行は差し替え、それ以外は保持する。
        kept_files: list[dict[str, Any]] = []
        seen_files: set[tuple[str, str]] = set()
        for item in existing_files:
            name = str(item.get("name", "") or "").strip()
            if not name:
                continue
            source_type = str(item.get("type", "") or Path(name).suffix.lower().lstrip(".") or "file").strip().lower()
            key = (name, source_type)
            if key in replace_keys or key in seen_files:
                continue
            seen_files.add(key)
            # チャンク数は現在のchunksから再計算し、一覧と実データのズレを防ぐ。
            clean_item = dict(item)
            clean_item["name"] = name
            clean_item["type"] = source_type
            clean_item["chunk_count"] = _chunk_count_for(chunks, name, source_type)
            kept_files.append(clean_item)

        files = kept_files + saved_files
        for item in files:
            item["chunk_count"] = _chunk_count_for(chunks, item.get("name", ""), item.get("type", ""))

        wiki_enabled = bool(existing_manifest.get("wiki_enabled"))
        wiki_uploaded_at = str(existing_manifest.get("wiki_uploaded_at", "") or "")
        wiki_uploaded_by = str(existing_manifest.get("wiki_uploaded_by", "") or "")
        if replace_wiki:
            wiki_enabled = True
            wiki_uploaded_at = now
            wiki_uploaded_by = uploaded_by
        elif not any(str(c.get("source_type", "") or "").lower() == "wiki" or str(c.get("source_name", "") or "") == "wiki_input.txt" for c in chunks):
            wiki_enabled = False
            wiki_uploaded_at = ""
            wiki_uploaded_by = ""

        embeddings = None
        if SENTENCE_TRANSFORMERS_AVAILABLE:
            try:
                model = _load_sentence_model(SentenceTransformer)
                if model is not None:
                    texts = [f"passage: {str(x.get('text', ''))}" for x in chunks]
                    emb = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
                    embeddings = np.asarray(emb, dtype=np.float32)
            except Exception as exc:
                try:
                    st.warning(f"sentence-transformers での索引化に失敗したため通常検索に切り替えます: {exc}")
                except Exception:
                    pass
                embeddings = None

        _safe_write_json(DOC_RAG_CHUNKS_PATH, chunks)
        _save_tfidf_index(chunks)
        if embeddings is not None:
            np.save(DOC_RAG_EMBEDDINGS_PATH, embeddings)
        elif DOC_RAG_EMBEDDINGS_PATH.exists():
            DOC_RAG_EMBEDDINGS_PATH.unlink()

        manifest = {
            "enabled": bool(files or wiki_enabled or chunks),
            "doc_count": len(files) + (1 if wiki_enabled else 0),
            "chunk_count": len(chunks),
            "files": files,
            "wiki_enabled": wiki_enabled,
            "wiki_uploaded_at": wiki_uploaded_at,
            "wiki_uploaded_by": wiki_uploaded_by,
            "updated_at": now,
            "last_import": {
                "uploaded_by": uploaded_by,
                "uploaded_at": now,
                "added_or_updated_files": [f.get("name", "") for f in saved_files],
                "failed_files": failed_files,
                "new_chunk_count": len(new_chunks),
            },
        }
        _safe_write_json(DOC_RAG_MANIFEST_PATH, manifest)
        _persist_doc_paths(DOC_RAG_CHUNKS_PATH, DOC_RAG_MANIFEST_PATH)
        if DOC_RAG_TFIDF_INDEX_PATH.exists():
            _persist_doc_paths(DOC_RAG_TFIDF_INDEX_PATH)
        if DOC_RAG_EMBEDDINGS_PATH.exists():
            _persist_doc_paths(DOC_RAG_EMBEDDINGS_PATH)
        for item in saved_files:
            _persist_doc_paths(Path(item["path"]))

        action = "追加・更新しました"
        message = f"{len(saved_files) + (1 if replace_wiki else 0)}件の資料を{action}。登録資料: {manifest['doc_count']}件 / 総チャンク数: {len(chunks)}"
        if failed_files:
            message += " / 取込失敗: " + ", ".join(failed_files[:5])
        return {"ok": True, "message": message, "chunk_count": len(chunks), "manifest": manifest}

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
        if any(token in clean for token in ("入室", "入退室", "入室制限", "入室者")):
            additions.append("入退室管理 入室可能者 入室者 制限 管理台帳 監視カメラ セキュリティカード 持ち込む機器 管理区域")
        if any(token in clean for token in ("アカウント", "ID", "ログイン", "アクセス権")):
            additions.append("アクセス制御 アカウント管理 発行 登録 削除 棚卸 権限")
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
        # Excelは行単位の明示語一致が重要なため、TF-IDF結果を優先する。
        # PDF/Word等はsentence-transformersが使える場合のみ意味検索を優先する。
        tfidf_hits = _search_with_tfidf(query, chunks, top_k=top_k)
        embedding_hits = _search_with_embeddings(query, chunks, top_k=top_k)
        if tfidf_hits and str(tfidf_hits[0].get("source_type", "") or "").lower() in {"xlsx", "xlsm"}:
            return tfidf_hits
        return embedding_hits or tfidf_hits

    def _select_hits_for_answer(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not hits:
            return []
        top = hits[0]
        top_type = str(top.get("source_type", "") or "").lower()
        # Excelは1行が1つの答えになりやすい。複数行をLLMへ渡すと、
        # 近くの行（例: 廃棄行）まで混ざるため、最上位1行だけを使う。
        if top_type in {"xlsx", "xlsm"}:
            return [top]
        return hits[:4]

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

    def build_document_rag_prompt(user_q: str, hits: list[dict[str, Any]]) -> str:
        answer_hits = _select_hits_for_answer(hits)
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
            "回答の最後に '参照資料:' を付けて、資料名と場所を箇条書きで並べてください。\n\n"
            f"[質問]\n{user_q}\n\n"
            f"[社内資料]\n{context_text}"
        )

    def answer_with_document_rag(user_q: str, hits: list[dict[str, Any]]) -> str:
        answer_hits = _select_hits_for_answer(hits)
        top = answer_hits[0] if answer_hits else {}
        top_type = str(top.get("source_type", "") or "").lower()

        # Excelチェックシートは、LLMに複数行を渡すよりも、
        # 最上位1行から決定的に整形した方が混入事故が起きにくい。
        if top_type in {"xlsx", "xlsm"}:
            return _format_excel_row_answer(user_q, top)

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
