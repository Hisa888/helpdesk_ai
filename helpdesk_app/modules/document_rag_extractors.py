from __future__ import annotations

import io
import re
import unicodedata
from pathlib import Path
from typing import Any, Iterable

from openpyxl import load_workbook
from pypdf import PdfReader
from docx import Document

SUPPORTED_DOC_RAG_EXTENSIONS = ("pdf", "docx", "xlsx", "xlsm", "txt", "md")

_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_BOX_RE = re.compile(r"[\u25A0-\u25FF\u2580-\u259F\uE000-\uF8FF]+")
_SPACE_RE = re.compile(r"[ \t　]+")
_HEADER_HINT_RE = re.compile(r"(項目|内容|回答|説明|質問|問合せ|問い合わせ|q|a|answer|question|区分|分類|カテゴリ|category|対象|有無|対応|対策|手順|方法|確認事項|概要)", re.I)

# Excel RAGでは、管理番号・連番・更新日などを検索に混ぜると誤ヒットの原因になります。
_IGNORE_COLUMN_RE = re.compile(
    r"^(no|no\.|№|番号|連番|id|管理id|管理番号|faq[_-]?id|行番号|更新日|登録日|作成日|日時|日付|"
    r"契約番号|顧客番号|コード|cd|備考のみ|メモ)$",
    re.I,
)
_IMPORTANT_COLUMN_RE = re.compile(
    r"(項目|質問|問合せ|問い合わせ|確認事項|内容|回答|説明|手順|方法|対応|対策|概要|タイトル|見出し|件名|事象|原因|結論)",
    re.I,
)
_WEAK_CELL_RE = re.compile(r"^[○〇×✕△▲◎\-ー―/\\|・.．,，:：;；_\s0-9A-Za-z]{1,4}$")


def normalize_doc_text(text: Any) -> str:
    """PDF/Word/Excel/TXT から取り出した文字列を検索・FAQ生成向けに整える。"""
    if text is None:
        return ""
    s = str(text)
    if s.lower().strip() in {"nan", "none", "null"}:
        return ""
    s = unicodedata.normalize("NFKC", s)
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = _CONTROL_RE.sub("", s)
    s = _BOX_RE.sub("", s).replace("□", "").replace("■", "")
    s = _SPACE_RE.sub(" ", s)
    s = "\n".join(line.strip() for line in s.split("\n"))
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def _decode_text_bytes(file_bytes: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "cp932", "shift_jis", "euc_jp"):
        try:
            return file_bytes.decode(enc)
        except Exception:
            continue
    return file_bytes.decode("utf-8", errors="ignore")


def iter_text_chunks(text: str, *, chunk_size: int = 700, overlap: int = 120) -> Iterable[str]:
    clean = normalize_doc_text(text)
    if not clean:
        return
    start = 0
    text_len = len(clean)
    while start < text_len:
        end = min(text_len, start + chunk_size)
        if end < text_len:
            cut = clean.rfind("\n", start, end)
            if cut <= start + 120:
                cut = clean.rfind("。", start, end)
            if cut <= start + 120:
                cut = clean.rfind(" ", start, end)
            if cut > start + 120:
                end = cut + 1
        piece = clean[start:end].strip()
        if piece:
            yield piece
        if end >= text_len:
            break
        start = max(end - overlap, start + 1)


def _looks_like_noise(text: str) -> bool:
    clean = normalize_doc_text(text)
    if not clean:
        return True
    jp_alnum = re.findall(r"[A-Za-z0-9ぁ-んァ-ン一-龥]", clean)
    return len(jp_alnum) < max(8, len(clean) * 0.18)


def extract_pdf_sections(file_bytes: bytes, filename: str) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    try:
        reader = PdfReader(io.BytesIO(file_bytes))
    except Exception:
        return results

    for idx, page in enumerate(reader.pages, start=1):
        texts: list[str] = []
        for mode in ("layout", None):
            try:
                t = page.extract_text(extraction_mode=mode) if mode else page.extract_text()
                t = t or ""
            except TypeError:
                try:
                    t = page.extract_text() or ""
                except Exception:
                    t = ""
            except Exception:
                t = ""
            t = normalize_doc_text(t)
            if t and not _looks_like_noise(t):
                texts.append(t)
                break
        text = normalize_doc_text("\n".join(texts))
        if text:
            results.append({
                "source_name": filename,
                "source_type": "pdf",
                "location": f"page {idx}",
                "heading": f"page {idx}",
                "text": text,
            })
    return results


def _iter_docx_table_text(doc: Document) -> list[str]:
    blocks: list[str] = []
    for t_idx, table in enumerate(doc.tables, start=1):
        rows: list[str] = []
        headers: list[str] = []
        for r_idx, row in enumerate(table.rows, start=1):
            cells = [normalize_doc_text(cell.text) for cell in row.cells]
            cells = [c for c in cells if c]
            if not cells:
                continue
            if r_idx == 1:
                headers = cells
                rows.append(f"ヘッダー: " + " / ".join(cells))
                continue
            if headers and len(headers) == len(cells):
                pairs = [f"{headers[i]}: {cells[i]}" for i in range(len(cells))]
                rows.append(f"row {r_idx}: " + " / ".join(pairs))
            else:
                rows.append(f"row {r_idx}: " + " / ".join(cells))
        if rows:
            blocks.append(f"[表 {t_idx}]\n" + "\n".join(rows))
    return blocks


def extract_docx_sections(file_bytes: bytes, filename: str) -> list[dict[str, str]]:
    try:
        doc = Document(io.BytesIO(file_bytes))
    except Exception:
        return []

    results: list[dict[str, str]] = []
    current_title = "document"
    current_lines: list[str] = []

    def flush() -> None:
        nonlocal current_lines, current_title
        text = normalize_doc_text("\n".join(current_lines))
        if text:
            results.append({
                "source_name": filename,
                "source_type": "docx",
                "location": current_title or "document",
                "heading": current_title or "document",
                "text": text,
            })
        current_lines = []

    for p in doc.paragraphs:
        raw = normalize_doc_text(p.text)
        if not raw:
            continue
        style_name = (getattr(getattr(p, "style", None), "name", "") or "").lower()
        if "heading" in style_name or "見出し" in style_name:
            flush()
            current_title = raw[:80]
            current_lines.append(raw)
        else:
            current_lines.append(raw)
    flush()

    for idx, table_text in enumerate(_iter_docx_table_text(doc), start=1):
        if table_text:
            results.append({
                "source_name": filename,
                "source_type": "docx",
                "location": f"table {idx}",
                "heading": f"table {idx}",
                "text": table_text,
            })

    if not results:
        table_blocks = _iter_docx_table_text(doc)
        text = normalize_doc_text("\n\n".join(table_blocks))
        if text:
            results.append({
                "source_name": filename,
                "source_type": "docx",
                "location": "document",
                "heading": "document",
                "text": text,
            })
    return results


def _row_values(row: tuple[Any, ...]) -> list[str]:
    return [normalize_doc_text(v) for v in row]


def _nonempty_cells(values: list[str]) -> list[str]:
    return [v for v in values if v]


def _is_probable_header(values: list[str]) -> bool:
    cells = _nonempty_cells(values)
    if not cells:
        return False
    joined = " ".join(cells)
    if _HEADER_HINT_RE.search(joined):
        return True
    # 表の先頭行は文字列中心ならヘッダーとして扱う
    alpha_like = sum(1 for c in cells if re.search(r"[A-Za-zぁ-んァ-ン一-龥]", c))
    return alpha_like >= max(1, len(cells) * 0.7)



def _norm_col_name(name: str) -> str:
    return normalize_doc_text(name).replace(" ", "").strip()


def _is_ignored_column(col_name: str) -> bool:
    c = _norm_col_name(col_name)
    if not c:
        return False
    return bool(_IGNORE_COLUMN_RE.search(c))


def _is_important_column(col_name: str) -> bool:
    c = _norm_col_name(col_name)
    return bool(c and _IMPORTANT_COLUMN_RE.search(c))


def _is_weak_cell_value(value: str) -> bool:
    v = normalize_doc_text(value)
    if not v:
        return True
    # 「○」「×」「43」などは単独では意味が弱い。根拠表示には残すが検索重みには使いすぎない。
    return bool(_WEAK_CELL_RE.fullmatch(v))


def _repeat_text(text: str, times: int) -> list[str]:
    text = normalize_doc_text(text)
    return [text] * max(0, times) if text else []


def extract_xlsx_sections(file_bytes: bytes, filename: str) -> list[dict[str, str]]:
    """Excelを列の意味で分解して、検索用テキストと表示用テキストを分離する。

    重要ポイント:
    - No/ID/更新日/契約番号などの管理列は検索対象から外す
    - 項目/質問/確認事項/内容/回答/手順などの意味列を強く検索対象にする
    - Excelは行単位でチャンク化し、別行の内容が混ざらないようにする
    """
    wb = load_workbook(io.BytesIO(file_bytes), data_only=True, read_only=True)
    results: list[dict[str, str]] = []
    for ws in wb.worksheets:
        header: list[str] = []
        title_context: list[str] = []
        sheet_title = normalize_doc_text(ws.title)

        for r_idx, row in enumerate(ws.iter_rows(values_only=True), start=1):
            values = _row_values(row)
            cells = _nonempty_cells(values)
            if not cells:
                continue

            # 1セルだけの行は章・見出しとして扱う
            if len(cells) == 1 and len(cells[0]) <= 90 and not re.search(r"[:：]", cells[0]):
                title_context = [cells[0]]
                results.append({
                    "source_name": filename,
                    "source_type": "xlsx",
                    "location": f"sheet {sheet_title} row {r_idx}",
                    "sheet_name": sheet_title,
                    "heading": cells[0],
                    "keywords": " ".join([sheet_title, cells[0]]),
                    "text": f"シート名: {sheet_title}\n見出し: {cells[0]}",
                    "search_text": "\n".join(_repeat_text(sheet_title, 2) + _repeat_text(cells[0], 5)),
                })
                continue

            # ヘッダーは2セル以上で判定。1セル見出しをヘッダー誤認しない。
            if not header and len(cells) >= 2 and _is_probable_header(values):
                header = values
                important_headers = [h for h in header if h and not _is_ignored_column(h)]
                results.append({
                    "source_name": filename,
                    "source_type": "xlsx",
                    "location": f"sheet {sheet_title} row {r_idx}",
                    "sheet_name": sheet_title,
                    "heading": "ヘッダー",
                    "keywords": " ".join([sheet_title] + important_headers),
                    "text": f"シート名: {sheet_title}\nヘッダー: " + " / ".join(cells),
                    "search_text": "\n".join(_repeat_text(sheet_title, 2) + _repeat_text(" ".join(important_headers), 4)),
                })
                continue

            display_pairs: list[str] = []
            search_parts: list[str] = []
            keyword_parts: list[str] = [sheet_title] + title_context
            heading_candidates: list[str] = []

            if header:
                for i, cell in enumerate(values):
                    if not cell:
                        continue
                    col_name = normalize_doc_text(header[i]) if i < len(header) and header[i] else f"列{i + 1}"
                    display_pairs.append(f"{col_name}: {cell}")

                    if _is_ignored_column(col_name):
                        # 表示根拠には残すが、検索には使わない
                        continue

                    important = _is_important_column(col_name)
                    weak_value = _is_weak_cell_value(cell)
                    keyword_parts.append(col_name)
                    if not weak_value:
                        keyword_parts.append(cell)

                    if important:
                        heading_candidates.append(cell if not weak_value else col_name)
                        search_parts.extend(_repeat_text(col_name, 5))
                        search_parts.extend(_repeat_text(cell, 8 if not weak_value else 2))
                    else:
                        search_parts.extend(_repeat_text(col_name, 2))
                        if not weak_value:
                            search_parts.extend(_repeat_text(cell, 3))
            else:
                # ヘッダーがない表は、管理値らしき短い値の重みを下げる
                for i, cell in enumerate(values):
                    if not cell:
                        continue
                    display_pairs.append(f"列{i + 1}: {cell}")
                    if not _is_weak_cell_value(cell):
                        keyword_parts.append(cell)
                        search_parts.extend(_repeat_text(cell, 3))
                heading_candidates = [c for c in cells if not _is_weak_cell_value(c)][:2]

            if not display_pairs:
                continue

            heading = " / ".join((title_context[-1:] + heading_candidates[:2]) or ["明細"])
            text = normalize_doc_text("\n".join([
                f"シート名: {sheet_title}",
                *(f"見出し: {x}" for x in title_context[-2:]),
                f"Excel行: {r_idx}",
                "内容: " + " / ".join(display_pairs),
            ]))
            search_text = normalize_doc_text("\n".join(
                _repeat_text(sheet_title, 2)
                + _repeat_text(" ".join(title_context[-2:]), 4)
                + _repeat_text(heading, 5)
                + search_parts
            ))
            results.append({
                "source_name": filename,
                "source_type": "xlsx",
                "location": f"sheet {sheet_title} row {r_idx}",
                "sheet_name": sheet_title,
                "heading": heading,
                "keywords": " ".join(keyword_parts),
                "text": text,
                "search_text": search_text or text,
            })
    return results

def extract_text_sections(file_bytes: bytes, filename: str, source_type: str) -> list[dict[str, str]]:
    text = normalize_doc_text(_decode_text_bytes(file_bytes))
    if not text:
        return []
    return [{
        "source_name": filename,
        "source_type": source_type,
        "location": "document",
        "heading": "document",
        "text": text,
    }]


def extract_sections_from_uploaded_file(uploaded_file: Any) -> list[dict[str, str]]:
    filename = str(getattr(uploaded_file, "name", "document")).strip() or "document"
    ext = Path(filename).suffix.lower().lstrip(".")
    file_bytes = uploaded_file.getvalue() if hasattr(uploaded_file, "getvalue") else uploaded_file.read()

    if ext == "pdf":
        return extract_pdf_sections(file_bytes, filename)
    if ext == "docx":
        return extract_docx_sections(file_bytes, filename)
    if ext in {"xlsx", "xlsm"}:
        return extract_xlsx_sections(file_bytes, filename)
    if ext in {"txt", "md"}:
        return extract_text_sections(file_bytes, filename, ext)
    return []


def build_chunks_from_sections(sections: list[dict[str, str]], *, chunk_size: int = 700, overlap: int = 120) -> list[dict[str, str]]:
    chunks: list[dict[str, str]] = []
    for sec in sections:
        source_type = sec.get("source_type", "text")
        # Excelは行単位で既に意味分割済みなので、原則そのまま1チャンクにする
        if source_type in {"xlsx", "xlsm"}:
            pieces = [normalize_doc_text(sec.get("text", ""))]
        else:
            pieces = list(iter_text_chunks(sec.get("text", ""), chunk_size=chunk_size, overlap=overlap))
        for i, piece in enumerate(pieces, start=1):
            if not piece:
                continue
            metadata_text = normalize_doc_text("\n".join([
                f"資料名: {sec.get('source_name', 'document')}",
                f"種類: {source_type}",
                f"場所: {sec.get('location', 'document')}",
                f"シート名: {sec.get('sheet_name', '')}",
                f"見出し: {sec.get('heading', '')}",
                f"キーワード: {sec.get('keywords', '')}",
                f"検索用: {sec.get('search_text', '')}",
                f"本文: {piece}",
            ]))
            chunks.append({
                "source_name": sec.get("source_name", "document"),
                "source_type": source_type,
                "location": sec.get("location", "document"),
                "sheet_name": sec.get("sheet_name", ""),
                "heading": sec.get("heading", ""),
                "keywords": sec.get("keywords", ""),
                "chunk_label": f"chunk {i}",
                "text": piece,
                "search_text": normalize_doc_text(sec.get("search_text", "")) or metadata_text,
            })
    return chunks


__all__ = [
    "SUPPORTED_DOC_RAG_EXTENSIONS",
    "normalize_doc_text",
    "extract_pdf_sections",
    "extract_docx_sections",
    "extract_xlsx_sections",
    "extract_sections_from_uploaded_file",
    "build_chunks_from_sections",
]
