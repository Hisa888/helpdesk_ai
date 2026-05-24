from __future__ import annotations

import io
import re
import unicodedata
from pathlib import Path
from typing import Any, Iterable

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter
from pypdf import PdfReader
from docx import Document

SUPPORTED_DOC_RAG_EXTENSIONS = ("pdf", "docx", "xlsx", "xlsm", "txt", "md")

_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_BOX_RE = re.compile(r"[\u25A0-\u25FF\u2580-\u259F\uE000-\uF8FF]+")
_SPACE_RE = re.compile(r"[ \t　]+")


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
    # PDFフォント抽出で混入しやすい黒四角・私用領域文字を除去。
    # ただしExcelチェックシートでは「○」「◎」「△」が判定結果そのものなので保護する。
    mark_placeholders = {
        "○": "__KEEP_JUDGE_MARU__",
        "〇": "__KEEP_JUDGE_MARU_KANJI__",
        "◎": "__KEEP_JUDGE_DOUBLE_MARU__",
        "△": "__KEEP_JUDGE_TRIANGLE__",
    }
    for mark, placeholder in mark_placeholders.items():
        s = s.replace(mark, placeholder)
    s = _BOX_RE.sub("", s).replace("□", "").replace("■", "")
    for mark, placeholder in mark_placeholders.items():
        s = s.replace(placeholder, mark)
    s = _SPACE_RE.sub(" ", s)
    # 行末の余分な空白を除去
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
    # 文字化け・記号ばかりのページを除外
    jp_alnum = re.findall(r"[A-Za-z0-9ぁ-んァ-ン一-龥]", clean)
    return len(jp_alnum) < max(8, len(clean) * 0.18)


def extract_pdf_sections(file_bytes: bytes, filename: str) -> list[dict[str, str]]:
    """PDFをページ単位で抽出。

    画像スキャンPDFはOCRなしでは本文抽出できないため、その場合は空になります。
    """
    results: list[dict[str, str]] = []
    try:
        reader = PdfReader(io.BytesIO(file_bytes))
    except Exception:
        return results

    for idx, page in enumerate(reader.pages, start=1):
        texts: list[str] = []
        # extraction_mode が使える pypdf では layout を優先。古い版では通常抽出へフォールバック。
        for mode in ("layout", None):
            try:
                if mode:
                    t = page.extract_text(extraction_mode=mode) or ""
                else:
                    t = page.extract_text() or ""
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
        if not text:
            continue
        results.append({
            "source_name": filename,
            "source_type": "pdf",
            "location": f"page {idx}",
            "text": text,
        })
    return results


def _iter_docx_table_text(doc: Document) -> list[str]:
    blocks: list[str] = []
    for t_idx, table in enumerate(doc.tables, start=1):
        rows: list[str] = []
        for r_idx, row in enumerate(table.rows, start=1):
            cells = [normalize_doc_text(cell.text) for cell in row.cells]
            cells = [c for c in cells if c]
            if cells:
                rows.append(f"row {r_idx}: " + " / ".join(cells))
        if rows:
            blocks.append(f"[表 {t_idx}]\n" + "\n".join(rows))
    return blocks


def extract_docx_sections(file_bytes: bytes, filename: str) -> list[dict[str, str]]:
    """Word(docx)を見出し・段落・表まで含めて抽出。"""
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
                "text": text,
            })
        current_lines = []

    for p in doc.paragraphs:
        raw = normalize_doc_text(p.text)
        if not raw:
            continue
        style_name = (getattr(getattr(p, "style", None), "name", "") or "").lower()
        # 見出しでセクションを分割。日本語スタイル名も考慮。
        if "heading" in style_name or "見出し" in style_name:
            flush()
            current_title = raw[:80]
            current_lines.append(raw)
        else:
            current_lines.append(raw)
    flush()

    # Word内の表もFAQ生成では重要なので別セクションとして追加
    for idx, table_text in enumerate(_iter_docx_table_text(doc), start=1):
        if table_text:
            results.append({
                "source_name": filename,
                "source_type": "docx",
                "location": f"table {idx}",
                "text": table_text,
            })

    # 段落なし・表だけの文書対策
    if not results:
        table_blocks = _iter_docx_table_text(doc)
        text = normalize_doc_text("\n\n".join(table_blocks))
        if text:
            results.append({
                "source_name": filename,
                "source_type": "docx",
                "location": "document",
                "text": text,
            })
    return results


_JUDGEMENT_MARKS = {"○", "〇", "×", "-", "－", "ー", "該当無", "対応済", "未対応"}


def _is_short_number_like(text: str) -> bool:
    t = normalize_doc_text(text)
    return bool(re.fullmatch(r"[0-9０-９]+|[0-9０-９]+[-－][0-9０-９]+|[①-⑳◎○〇×△・－ー-]", t))


def _looks_like_judgement(text: str) -> bool:
    t = normalize_doc_text(text).strip()
    if not t:
        return False
    # 「4-1」「27-3」のような設問番号を判定結果と誤認しない。
    if re.fullmatch(r"[0-9０-９]+[-－][0-9０-９]+", t):
        return False
    # 判定欄は基本的に単独の ○/〇/×/－/ー/-。
    # ヘッダー文や設問番号に含まれる記号までは判定扱いしない。
    if t in _JUDGEMENT_MARKS:
        return True
    if t in {"対応済", "未対応", "該当無", "該当なし"}:
        return True
    return False


def _excel_value_quality_score(value: str) -> int:
    """Excel行内で「回答対象の項目」にしやすい文字列ほど高スコアにする。"""
    v = normalize_doc_text(value)
    if not v or _is_short_number_like(v) or _looks_like_judgement(v):
        return -10_000
    # 右端の分類・担当欄に入りやすい短い値は、項目/回答にしない。
    if len(v) <= 12 and (v.endswith("?") or v.endswith("？") or v in {"システム", "システム?", "システム？", "運用", "体制"}):
        return -5_000
    score = len(v)
    if any(token in v for token in ("ますか", "ですか", "していますか", "講じていますか", "確認", "管理", "規程", "ルール", "体制")):
        score += 70
    if any(token in v for token in ("整備", "対策", "手続", "対応", "制限", "防止", "管理", "確認", "復旧", "不正アクセス")):
        score += 45
    # カタカナ読みが末尾に付いた長文は検索には有効だが、表示項目としては少し弱める。
    if re.search(r"[ァ-ン]{8,}$", v):
        score -= 10
    return score


def _is_excel_note_like(value: str) -> bool:
    """右側の分類・備考欄らしい短い値を回答本文から除外する。"""
    v = normalize_doc_text(value)
    if not v:
        return True
    if len(v) <= 14 and (v.endswith("?") or v.endswith("？")):
        return True
    if v in {"システム", "システム?", "システム？", "運用", "体制", "対象外", "確認中"}:
        return True
    return False


def _is_parent_context_row(cells: list[tuple[int, str]], formatted_text: str) -> bool:
    """Excelチェックシートの親設問行かどうかを推定する。"""
    values = [value for _, value in cells]
    if not values:
        return False
    text = normalize_doc_text(" / ".join(values))
    judgement = ""
    for value in values:
        if _looks_like_judgement(value):
            judgement = value
            break
    if any(token in text for token in ("以下の措置", "以下の項目", "として、以下", "講じていますか")):
        return True
    # 親行は No + 長い確認事項 + － の形が多い。
    if judgement in {"-", "－", "ー"} and any(len(v) >= 24 for v in values):
        return True
    return False


def _best_parent_context(cells: list[tuple[int, str]]) -> str:
    values = [value for _, value in cells]
    candidates: list[tuple[int, str]] = []
    for value in values:
        if _is_short_number_like(value) or _looks_like_judgement(value):
            continue
        score = _excel_value_quality_score(value)
        if any(token in value for token in ("以下の措置", "以下の項目", "講じていますか", "として")):
            score += 100
        if score > 0:
            candidates.append((score, value))
    if not candidates:
        return ""
    return sorted(candidates, key=lambda x: x[0], reverse=True)[0][1]


def _should_apply_parent_context(cells: list[tuple[int, str]], parent_context: str) -> bool:
    """親設問は、直下の①②③などの明細行にだけ付与する。

    通常のNo列（例: B列の23）まで親項目を引き継ぐと、
    入退室管理など独立した行に別セクションの親文言が混ざるため、
    先頭非空セルが右寄り（E列以降）にある明細行だけを対象にする。
    """
    if not parent_context or not cells:
        return False
    first_col, first_value = cells[0]
    return first_col >= 5 and _is_short_number_like(first_value)


def _format_excel_row_text(sheet_title: str, row_idx: int, cells: list[tuple[int, str]], parent_context: str = "") -> str:
    """Excel RAG用に、1行だけを意味のあるラベル付きテキストへ変換する。

    チェックシート型Excelでは「1シート＝1チャンク」にすると、前後行の
    廃棄・入退室管理などが混ざって回答される。
    そのため、Excelは必ず「1行＝1チャンク」で扱う。

    また、チェックシートの右端にある「システム？」などの分類列を
    回答や該当項目として誤表示しないよう、判定列の前後で役割を分ける。
    """
    raw_parts = [f"{get_column_letter(col_idx)}: {value}" for col_idx, value in cells]
    values = [value for _, value in cells]

    id_text = ""
    topic_values: list[str] = []
    item_text = ""
    judgement_text = ""
    reason_values: list[str] = []
    note_values: list[str] = []

    if values and _is_short_number_like(values[0]):
        id_text = values[0]

    judgement_pos = -1
    for i, value in enumerate(values):
        if _looks_like_judgement(value):
            judgement_pos = i
            judgement_text = value
            break

    before_values = values[:judgement_pos] if judgement_pos >= 0 else values
    item_candidates: list[tuple[int, str]] = []
    for i, value in enumerate(before_values):
        if i == 0 and id_text:
            continue
        score = _excel_value_quality_score(value)
        if score > 0:
            item_candidates.append((score, value))
    if item_candidates:
        item_text = sorted(item_candidates, key=lambda x: x[0], reverse=True)[0][1]

    for i, value in enumerate(values):
        if i == 0 and id_text:
            continue
        if value == item_text or (judgement_pos >= 0 and i == judgement_pos):
            continue
        if judgement_pos >= 0 and i > judgement_pos:
            if _is_excel_note_like(value):
                note_values.append(value)
            else:
                reason_values.append(value)
        else:
            # 判定より左側の短い分類は項目補助として保持する。
            if 1 < len(value) <= 60 and not _is_excel_note_like(value) and not _looks_like_judgement(value):
                topic_values.append(value)

    lines = [f"シート: {sheet_title}", f"Excel行: {row_idx}"]
    if parent_context:
        lines.append(f"親項目: {parent_context}")
    if id_text:
        lines.append(f"No: {id_text}")
    # 「該当項目」は、ユーザーへ出す主項目。右端の「システム？」は入れない。
    if item_text:
        lines.append(f"該当項目: {item_text}")
    if topic_values:
        lines.append("分類・補助項目: " + " / ".join(topic_values))
    if item_text:
        lines.append(f"確認事項: {item_text}")
    if judgement_text:
        lines.append(f"判定結果: {judgement_text}")
    if reason_values:
        lines.append("回答・理由: " + " / ".join(reason_values))
    if note_values:
        lines.append("備考: " + " / ".join(note_values))
    lines.append("元データ: " + " / ".join(raw_parts))
    return normalize_doc_text("\n".join(lines))



_BUSINESS_HEADER_ALIASES = {
    "overview": {"概要", "内容", "説明", "確認事項"},
    "sheet": {"シート名", "書式", "使用書式", "申請書"},
    "application_item": {"申請項目", "項目", "申請内容"},
    "path": {"パス", "申請書", "フォルダ", "結合パス"},
}


def _normalize_header_name(value: str) -> str:
    return normalize_doc_text(value).replace(" ", "").replace("　", "")


def _detect_business_header_map(cells: list[tuple[int, str]]) -> dict[int, str]:
    """Excelの業務一覧表で、概要/シート名/申請項目などの列を検出する。"""
    header_map: dict[int, str] = {}
    for col_idx, value in cells:
        h = _normalize_header_name(value)
        if not h:
            continue
        if h in {"概要", "内容", "説明"}:
            header_map[col_idx] = "overview"
        elif h in {"シート名", "書式", "使用書式"}:
            header_map[col_idx] = "sheet"
        elif h in {"申請項目", "項目", "申請内容"}:
            header_map[col_idx] = "application_item"
        elif h in {"申請書", "パス", "フォルダ", "結合パス"}:
            header_map[col_idx] = "path"
    # 少なくとも2種類以上の業務ヘッダーがある場合のみ採用する。
    if len(set(header_map.values())) >= 2:
        return header_map
    return {}


def _business_value_map(cells: list[tuple[int, str]], header_map: dict[int, str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for col_idx, value in cells:
        key = header_map.get(col_idx)
        if not key:
            continue
        v = normalize_doc_text(value)
        if not v:
            continue
        values[key] = v
    return values


def _format_business_excel_row_text(sheet_title: str, row_idx: int, cells: list[tuple[int, str]], business: dict[str, str]) -> str:
    """申請書一覧・MEMO系のExcel行を、回答しやすい業務形式に整形する。"""
    raw_parts = [f"{get_column_letter(col_idx)}: {value}" for col_idx, value in cells]
    overview = business.get("overview", "")
    form_sheet = business.get("sheet", "")
    application_item = business.get("application_item", "")
    path_text = business.get("path", "")

    lines = [f"シート: {sheet_title}", f"Excel行: {row_idx}"]
    if form_sheet:
        lines.append(f"使用書式: {form_sheet}")
    if application_item:
        lines.append(f"申請項目: {application_item}")
        lines.append(f"該当項目: {application_item}")
    if overview:
        lines.append(f"概要: {overview}")
        lines.append(f"確認事項: {overview}")
    if path_text:
        lines.append(f"申請書パス: {path_text}")
    # 検索時に「どの申請書」「書式」「申請項目」が強く効くように重複重み付けする。
    weighted = []
    if application_item:
        weighted.extend([application_item] * 6)
    if form_sheet:
        weighted.extend([form_sheet] * 5)
    if overview:
        weighted.extend([overview] * 3)
    if path_text:
        weighted.append(path_text)
    if weighted:
        lines.append("検索用重要語: " + " / ".join(weighted))
    lines.append("元データ: " + " / ".join(raw_parts))
    return normalize_doc_text("\n".join(lines))

def extract_xlsx_sections(file_bytes: bytes, filename: str) -> list[dict[str, Any]]:
    wb = load_workbook(io.BytesIO(file_bytes), data_only=True, read_only=True)
    results: list[dict[str, Any]] = []
    for ws in wb.worksheets:
        parent_context = ""
        business_header_map: dict[int, str] = {}
        for r_idx, row in enumerate(ws.iter_rows(values_only=True), start=1):
            cells: list[tuple[int, str]] = []
            for c_idx, value in enumerate(row, start=1):
                cell_text = normalize_doc_text(value)
                if cell_text:
                    cells.append((c_idx, cell_text))
            if not cells:
                continue
            # 業務一覧表（概要/シート名/申請項目など）のヘッダーを検出。
            detected_header = _detect_business_header_map(cells)
            if detected_header:
                business_header_map = detected_header
                continue
            # 連番だけの空行テンプレートは検索ノイズになるため除外する。
            if len(cells) == 1 and _is_short_number_like(cells[0][1]):
                continue

            business_values = _business_value_map(cells, business_header_map) if business_header_map else {}
            if business_values and (business_values.get("application_item") or business_values.get("sheet") or business_values.get("overview")):
                text = _format_business_excel_row_text(ws.title, r_idx, cells, business_values)
                source_meta = {
                    "business_overview": business_values.get("overview", ""),
                    "business_sheet": business_values.get("sheet", ""),
                    "business_application_item": business_values.get("application_item", ""),
                    "business_path": business_values.get("path", ""),
                }
                search_text = normalize_doc_text("\n".join([
                    " ".join([business_values.get("application_item", "")] * 8),
                    " ".join([business_values.get("sheet", "")] * 6),
                    " ".join([business_values.get("overview", "")] * 4),
                    business_values.get("path", ""),
                    text,
                ]))
            else:
                # 親設問行の文言を保持し、直後の①②③などの明細行に付与する。
                # これにより「不正アクセスの復旧対策はありますか？」の回答で
                # 「障害発生時の技術的対応・復旧手続の整備」の配下であることを示せる。
                row_parent_context = parent_context if _should_apply_parent_context(cells, parent_context) else ""
                text = _format_excel_row_text(ws.title, r_idx, cells, parent_context=row_parent_context)
                source_meta = {}
                search_text = text

            if text:
                row_payload = {
                    "source_name": filename,
                    "source_type": "xlsx",
                    "location": f"sheet {ws.title} row {r_idx}",
                    "chunk_label": f"row {r_idx}",
                    "text": text,
                    "search_text": search_text,
                    "no_split": True,
                }
                row_payload.update(source_meta)
                results.append(row_payload)
            if _is_parent_context_row(cells, text):
                parent_context = _best_parent_context(cells) or parent_context
    return results

def extract_text_sections(file_bytes: bytes, filename: str, source_type: str) -> list[dict[str, str]]:
    text = normalize_doc_text(_decode_text_bytes(file_bytes))
    if not text:
        return []
    return [{
        "source_name": filename,
        "source_type": source_type,
        "location": "document",
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


def build_chunks_from_sections(sections: list[dict[str, Any]], *, chunk_size: int = 700, overlap: int = 120) -> list[dict[str, str]]:
    chunks: list[dict[str, str]] = []
    for sec in sections:
        source_type = str(sec.get("source_type", "text") or "text").lower()
        # Excelは「1行＝1チャンク」を厳守する。ここで再分割すると、
        # 隣の行の内容が回答に混ざる原因になる。
        if bool(sec.get("no_split")) or source_type in {"xlsx", "xlsm"}:
            piece = normalize_doc_text(sec.get("text", ""))
            if piece:
                payload = {
                    "source_name": sec.get("source_name", "document"),
                    "source_type": sec.get("source_type", "text"),
                    "location": sec.get("location", "document"),
                    "chunk_label": str(sec.get("chunk_label") or "row"),
                    "text": piece,
                    "search_text": normalize_doc_text(sec.get("search_text", "") or piece),
                }
                for key in ("business_overview", "business_sheet", "business_application_item", "business_path"):
                    if sec.get(key):
                        payload[key] = normalize_doc_text(sec.get(key, ""))
                chunks.append(payload)
            continue

        pieces = list(iter_text_chunks(sec.get("text", ""), chunk_size=chunk_size, overlap=overlap))
        for i, piece in enumerate(pieces, start=1):
            chunks.append({
                "source_name": sec.get("source_name", "document"),
                "source_type": sec.get("source_type", "text"),
                "location": sec.get("location", "document"),
                "chunk_label": f"chunk {i}",
                "text": piece,
                "search_text": piece,
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
