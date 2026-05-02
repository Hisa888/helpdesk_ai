from __future__ import annotations

import csv
import json
from pathlib import Path

import pandas as pd

from helpdesk_app.faq_io import save_faq_csv_full

from helpdesk_app.log_service import normalize_question


FAQ_GENERATION_COLUMNS = ["question", "answer", "intent", "keywords", "category", "answer_format"]


def _auto_intent(question: str, category: str = "") -> str:
    q = str(question or "").strip().rstrip("？?")
    cat = str(category or "").strip()
    if cat and q:
        return f"{cat}について、{q}内容を解決したい"
    return f"{q}内容を解決したい" if q else ""


def _auto_keywords(question: str, category: str = "") -> str:
    text = f"{category} {question}"
    keywords = []
    synonym_sets = [
        ("パスワード", ["ログインできない", "サインインできない", "忘れた", "再設定", "リセット", "アカウントロック"]),
        ("VPN", ["つながらない", "接続できない", "在宅", "社外", "認証エラー"]),
        ("メール", ["Outlook", "受信できない", "送信できない", "見れない", "共有メールボックス"]),
        ("プリンタ", ["印刷できない", "紙詰まり", "プリンター", "出力できない"]),
        ("PC", ["パソコン", "起動しない", "重い", "遅い", "固まる"]),
    ]
    for trigger, words in synonym_sets:
        if trigger.lower() in text.lower() or any(w in text for w in words):
            keywords.extend([trigger, *words])
    for token in str(text).replace("/", " ").replace("、", " ").split():
        if token and token not in keywords:
            keywords.append(token)
    return ", ".join(dict.fromkeys(keywords))


def extract_json_array(text: str) -> str | None:
    """Extract the first top-level JSON array from mixed LLM output."""
    if not text:
        return None
    start = text.find('[')
    if start < 0:
        return None

    depth = 0
    in_string = False
    escape = False
    for i, ch in enumerate(text[start:], start=start):
        if in_string:
            if escape:
                escape = False
            elif ch == '\\':
                escape = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
        elif ch == '[':
            depth += 1
        elif ch == ']':
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None



def generate_faq_candidates(*, nohit_questions: list[str], n_items: int, llm_chat) -> pd.DataFrame:
    """Generate FAQ candidates from accumulated nohit questions."""
    if not nohit_questions:
        return pd.DataFrame(columns=FAQ_GENERATION_COLUMNS)

    try:
        target_items = max(0, int(n_items))
    except Exception:
        target_items = 0

    max_in = min(len(nohit_questions), 500)
    sample = nohit_questions[:max_in]
    examples = "\n".join([f"- {q}" for q in sample])
    target_text = f"{target_items} 件" if target_items > 0 else "可能な範囲で最大件数"

    prompt = f"""あなたは社内情シスのベテラン担当です。
以下は『FAQに該当なし』として蓄積された、社員からの問い合わせ例です。

【目的】
この問い合わせ例から、社内で使えるFAQ（Q&A）を {target_text} 作成してください。

【要件】
- 日本語のみ
- 1件ごとに question / answer / intent / keywords / category を作る
- question は社員が実際に入力しそうな言葉にする
- answer は短く結論→手順の順番で、手順は箇条書き（3〜7行）
- intent は質問の意味・目的を1文で書く
- keywords は言い換え・表記ゆれをカンマ区切りで書く
- 個人情報や会社固有の秘密情報は作らない
- できるだけ汎用的（どの会社でも通用）に
- 出力は必ずJSONのみ（前後に説明文を入れない）
- コードブロック ``` は使わない

【出力JSON形式】
[
  {{"question":"...", "answer":"- ...\n- ...", "intent":"...", "keywords":"...", "category":"VPN"}},
  ...
]

【問い合わせ例】
{examples}
"""

    out = llm_chat(
        [
            {"role": "system", "content": "あなたは情シスのFAQ作成者です。出力はJSONのみ。"},
            {"role": "user", "content": prompt},
        ]
    )

    out_text = out if isinstance(out, str) else str(out)
    json_text = extract_json_array(out_text) or out_text.strip()

    try:
        data = json.loads(json_text)
        if not isinstance(data, list):
            raise ValueError("JSON is not a list")
    except Exception:
        return pd.DataFrame(columns=FAQ_GENERATION_COLUMNS)

    rows = []
    for item in data:
        if not isinstance(item, dict):
            continue
        cat = str(item.get("category", "")).strip()
        q = str(item.get("question", "")).strip()
        a = str(item.get("answer", "")).strip()
        intent = str(item.get("intent", "")).strip() or _auto_intent(q, cat)
        keywords = str(item.get("keywords", "")).strip() or _auto_keywords(q, cat)
        if not q or not a:
            continue
        rows.append({"question": q, "answer": a, "intent": intent, "keywords": keywords, "category": cat, "answer_format": "markdown"})

    return pd.DataFrame(rows, columns=FAQ_GENERATION_COLUMNS)



def append_faq_csv(*, faq_path: Path, new_df: pd.DataFrame, normalize_faq_columns, read_csv_flexible, persist_faq_now) -> int:
    """Append FAQ rows to faq.csv while skipping rough duplicates by question."""
    if new_df is None or len(new_df) == 0:
        return 0

    for col in FAQ_GENERATION_COLUMNS:
        if col not in new_df.columns:
            new_df[col] = "markdown" if col == "answer_format" else ""

    new_df = new_df[FAQ_GENERATION_COLUMNS].copy()
    new_df["question"] = new_df["question"].fillna("").astype(str).str.strip()
    new_df["answer"] = new_df["answer"].fillna("").astype(str).str.strip()
    new_df["intent"] = new_df["intent"].fillna("").astype(str).str.strip()
    new_df["keywords"] = new_df["keywords"].fillna("").astype(str).str.strip()
    new_df["category"] = new_df["category"].fillna("").astype(str).str.strip()
    new_df["answer_format"] = new_df["answer_format"].fillna("markdown").astype(str).str.strip().replace("", "markdown")
    for idx, record in new_df.iterrows():
        if not str(record.get("intent", "")).strip():
            new_df.at[idx, "intent"] = _auto_intent(record.get("question", ""), record.get("category", ""))
        if not str(record.get("keywords", "")).strip():
            new_df.at[idx, "keywords"] = _auto_keywords(record.get("question", ""), record.get("category", ""))
    new_df = new_df[(new_df["question"] != "") & (new_df["answer"] != "")]
    if len(new_df) == 0:
        return 0

    if faq_path.exists():
        try:
            exist = normalize_faq_columns(read_csv_flexible(faq_path))
        except Exception:
            exist = pd.DataFrame(columns=FAQ_GENERATION_COLUMNS)
    else:
        exist = pd.DataFrame(columns=FAQ_GENERATION_COLUMNS)

    exist_q = set(
        normalize_question(x)
        for x in exist.get("question", pd.Series(dtype=str)).fillna("").astype(str).tolist()
    )

    rows: list[list[str]] = []
    for _, record in new_df.iterrows():
        normalized_q = normalize_question(str(record.get("question", "")))
        if not normalized_q or normalized_q in exist_q:
            continue
        exist_q.add(normalized_q)
        rows.append([record["question"], record["answer"], record.get("intent", ""), record.get("keywords", ""), record.get("category", ""), record.get("answer_format", "markdown")])

    if not rows:
        return 0

    add_df = pd.DataFrame(rows, columns=FAQ_GENERATION_COLUMNS)
    combined = pd.concat([exist, add_df], ignore_index=True)

    # DB化対応: runtime_data/faq.csv は直接追記せず、save_faq_csv_full 経由で
    # SQLite正本 + CSVキャッシュの両方を更新する。
    save_faq_csv_full(faq_path, combined, persist_callback=persist_faq_now)
    return len(rows)
