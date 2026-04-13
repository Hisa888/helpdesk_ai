from __future__ import annotations

import csv
import json
from pathlib import Path

import pandas as pd

from helpdesk_app.log_service import normalize_question



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
        return pd.DataFrame(columns=["category", "question", "answer"])

    max_in = min(len(nohit_questions), 80)
    sample = nohit_questions[:max_in]
    examples = "\n".join([f"- {q}" for q in sample])

    prompt = f"""あなたは社内情シスのベテラン担当です。
以下は『FAQに該当なし』として蓄積された、社員からの問い合わせ例です。

【目的】
この問い合わせ例から、社内で使えるFAQ（Q&A）を {n_items} 件作成してください。

【要件】
- 日本語のみ
- 1件ごとに category / question / answer を作る
- answer は手順を箇条書きで（3〜7行）
- 個人情報や会社固有の秘密情報は作らない
- できるだけ汎用的（どの会社でも通用）に
- 出力は必ずJSONのみ（前後に説明文を入れない）
- コードブロック ``` は使わない

【出力JSON形式】
[
  {{"category":"VPN", "question":"...", "answer":"- ...\n- ..."}},
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
        return pd.DataFrame(columns=["category", "question", "answer"])

    rows = []
    for item in data:
        if not isinstance(item, dict):
            continue
        cat = str(item.get("category", "")).strip()
        q = str(item.get("question", "")).strip()
        a = str(item.get("answer", "")).strip()
        if not q or not a:
            continue
        rows.append({"category": cat, "question": q, "answer": a})

    return pd.DataFrame(rows, columns=["category", "question", "answer"])



def append_faq_csv(*, faq_path: Path, new_df: pd.DataFrame, normalize_faq_columns, read_csv_flexible, persist_faq_now) -> int:
    """Append FAQ rows to faq.csv while skipping rough duplicates by question."""
    if new_df is None or len(new_df) == 0:
        return 0

    for col in ["question", "answer", "category"]:
        if col not in new_df.columns:
            new_df[col] = ""

    new_df = new_df[["question", "answer", "category"]].copy()
    new_df["question"] = new_df["question"].fillna("").astype(str).str.strip()
    new_df["answer"] = new_df["answer"].fillna("").astype(str).str.strip()
    new_df["category"] = new_df["category"].fillna("").astype(str).str.strip()
    new_df = new_df[(new_df["question"] != "") & (new_df["answer"] != "")]
    if len(new_df) == 0:
        return 0

    if faq_path.exists():
        try:
            exist = normalize_faq_columns(read_csv_flexible(faq_path))
        except Exception:
            exist = pd.DataFrame(columns=["question", "answer", "category"])
    else:
        exist = pd.DataFrame(columns=["question", "answer", "category"])

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
        rows.append([record["question"], record["answer"], record.get("category", "")])

    if not rows:
        return 0

    is_new = not faq_path.exists()
    with faq_path.open("a", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow(["question", "answer", "category"])
        writer.writerows(rows)

    persist_faq_now()
    return len(rows)
