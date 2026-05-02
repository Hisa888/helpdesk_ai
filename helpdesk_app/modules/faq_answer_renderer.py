from __future__ import annotations

import html
import re
from typing import Any


FAQ_ANSWER_FORMAT_COLUMN = "answer_format"
FAQ_ANSWER_FORMATS = {"text", "markdown", "html"}
FAQ_ANSWER_FORMAT_LABELS = {
    "text": "テキスト",
    "markdown": "Markdown",
    "html": "HTML",
}


def normalize_answer_format(value: Any, default: str = "markdown") -> str:
    """FAQ行単位の回答表示形式を正規化する。

    Excel/CSVでは以下を許可する。
    - text / テキスト / 文字
    - markdown / md / マークダウン / リンク
    - html / HTML
    """
    default = default if default in FAQ_ANSWER_FORMATS else "markdown"
    raw = "" if value is None else str(value).strip()
    raw = raw.replace("　", " ").strip().lower()
    if raw in {"", "nan", "none", "null"}:
        return default

    mapping = {
        "text": "text",
        "plain": "text",
        "plaintext": "text",
        "plain_text": "text",
        "テキスト": "text",
        "通常": "text",
        "文字": "text",
        "markdown": "markdown",
        "mark down": "markdown",
        "md": "markdown",
        "マークダウン": "markdown",
        "リンク": "markdown",
        "html": "html",
        "htm": "html",
    }
    return mapping.get(raw, default)


def get_row_answer_format(row: Any, default: str = "markdown") -> str:
    """pandas.Series / dict のどちらでも answer_format を取得する。"""
    try:
        if hasattr(row, "get"):
            # 日本語列のまま渡ってきた場合も吸収
            for key in ("answer_format", "表示形式", "回答表示形式", "回答形式"):
                try:
                    val = row.get(key, None)
                    if val is not None and str(val).strip() not in {"", "nan", "None"}:
                        return normalize_answer_format(val, default=default)
                except Exception:
                    pass
        return normalize_answer_format(default)
    except Exception:
        return normalize_answer_format(default)


def _safe_url(url: str) -> str:
    url = str(url or "").strip()
    if re.match(r"^(https?://|mailto:|tel:)", url, flags=re.IGNORECASE):
        return html.escape(url, quote=True)
    return "#"


def _has_markdown_link(text: str) -> bool:
    return bool(re.search(r"\[[^\]\n]+\]\((https?://[^)\s]+|mailto:[^)\s]+|tel:[^)\s]+)\)", str(text or "")))


def markdown_links_to_safe_html(text: str) -> str:
    """FAQ回答用の軽量Markdown変換。

    既存の緑枠HTMLデザインの中でもクリックできるよう、
    [表示名](https://...) を安全な <a> タグへ変換する。
    """
    escaped = html.escape("" if text is None else str(text), quote=False)

    def repl_link(match: re.Match) -> str:
        label = html.escape(match.group(1).strip(), quote=False)
        url = match.group(2).strip()
        return f'<a href="{_safe_url(url)}" target="_blank" rel="noopener noreferrer">{label}</a>'

    # [表示名](https://example.com) / [表示名](mailto:xxx) / [表示名](tel:xxx)
    escaped = re.sub(
        r"\[([^\]\n]+)\]\((https?://[^)\s]+|mailto:[^)\s]+|tel:[^)\s]+)\)",
        repl_link,
        escaped,
        flags=re.IGNORECASE,
    )
    escaped = re.sub(r"\*\*([^*\n]+)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"__([^_\n]+)__", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"`([^`\n]+)`", r"<code>\1</code>", escaped)
    return escaped.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br>")


def answer_to_html(answer: str, answer_format: str = "markdown") -> str:
    fmt = normalize_answer_format(answer_format)
    text = "" if answer is None else str(answer)
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # 実運用対策:
    # 表示形式の列が読み込まれていない/古いキャッシュが残っている場合でも、
    # 回答文に [表示名](https://...) が含まれていればリンク化する。
    # これにより、既存FAQのリンクが「ただの文字」になる事故を防ぐ。
    if fmt == "html":
        return text.replace("\n", "<br>")
    if fmt == "markdown" or _has_markdown_link(text):
        return markdown_links_to_safe_html(text)
    return html.escape(text, quote=False).replace("\n", "<br>")


def render_answer_box(st, *, answer: str, answer_format: str = "markdown", css_class: str = "answerbox") -> None:
    body_html = answer_to_html(answer, answer_format)
    fmt = normalize_answer_format(answer_format)
    st.markdown(
        f'<div class="{css_class}" data-answer-format="{fmt}">{body_html}</div>',
        unsafe_allow_html=True,
    )


def render_ref_answer_html(answer: str, answer_format: str = "markdown") -> str:
    return answer_to_html(answer, answer_format)
