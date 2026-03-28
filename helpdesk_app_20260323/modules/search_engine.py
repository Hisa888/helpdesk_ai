from pathlib import Path
from datetime import datetime, timedelta
import base64
import csv
import io
import json
import os
import re
import threading
import zipfile

import pandas as pd
import requests
import streamlit as st
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

def normalize_search_text(text: str) -> str:
    """FAQ検索用の正規化。表記ゆれ・同義表現を寄せて意味検索を強化する。"""
    s = str(text or "").strip().lower()
    if not s:
        return ""

    s = s.translate(FULLWIDTH_TRANS)
    for pattern, repl in CANONICAL_PATTERNS:
        s = re.sub(pattern, repl, s)

    s = re.sub(r"([^a-z0-9])pc([^a-z0-9])", r"\1 pc \2", f" {s} ")
    s = re.sub(r"[\/／・,、。．・:：;；\-ー_（）()\[\]{}『』「」\"'`]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def extract_search_tokens(text: str) -> set[str]:
    """日本語FAQ検索向けの軽量トークン抽出。"""
    s = normalize_search_text(text)
    if not s:
        return set()

    tokens = set()
    for part in s.split():
        part = part.strip()
        if part:
            tokens.add(part)

    for tok in re.findall(r"[a-z0-9]+|[\u3040-\u30ff\u4e00-\u9fff]{2,}", s):
        tokens.add(tok)

    split_hints = ["できない", "つながらない", "起動しない", "ログイン", "パスワード", "電源", "印刷", "メール", "アカウント", "vpn", "wifi"]
    for tok in list(tokens):
        for hint in split_hints:
            if hint in tok and tok != hint:
                tokens.add(hint)
                remain = tok.replace(hint, " ").strip()
                if len(remain) >= 2:
                    tokens.add(remain)

    return {t for t in tokens if t}

def extract_concepts(text: str) -> set[str]:
    s = normalize_search_text(text)
    found = set()
    for concept, aliases in CONCEPT_ALIASES.items():
        if any(alias in s for alias in aliases):
            found.add(concept)
    return found

def _load_sentence_transformer_model():
    if not SENTENCE_TRANSFORMERS_AVAILABLE or SentenceTransformer is None:
        return None
    try:
        return SentenceTransformer(SENTENCE_MODEL_NAME)
    except Exception:
        return None

def _build_sentence_embeddings(model, texts: list[str]):
    if model is None or not texts:
        return None
    try:
        return model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    except Exception:
        return None

def _get_sentence_embeddings_cached(texts: tuple[str, ...]):
    model = _load_sentence_transformer_model()
    if model is None or not texts:
        return None
    return _build_sentence_embeddings(model, list(texts))

def _search_with_sentence_transformers(query_norm: str, faq_embeddings) -> list[float] | None:
    if not query_norm or faq_embeddings is None:
        return None
    model = _load_sentence_transformer_model()
    if model is None:
        return None
    try:
        q_emb = model.encode([query_norm], normalize_embeddings=True, show_progress_bar=False)
        sims_sem = cosine_similarity(q_emb, faq_embeddings).flatten()
        return sims_sem.tolist()
    except Exception:
        return None

def load_faq_index(faq_path_str: str):
    faq_path = Path(faq_path_str)
    if not faq_path.exists():
        empty = pd.DataFrame(columns=["question", "answer", "category"])
        return empty, None, None, None, None, None

    try:
        df = normalize_faq_columns(read_csv_flexible(faq_path))
    except Exception:
        empty = pd.DataFrame(columns=["question", "answer", "category"])
        return empty, None, None, None, None, None

    df["question"] = df["question"].fillna("").astype(str)
    df["answer"] = df["answer"].fillna("").astype(str)
    df["category"] = df["category"].fillna("").astype(str)

    if len(df) == 0:
        return df, None, None, None, None, None

    df["question_norm"] = df["question"].apply(normalize_search_text)
    df["answer_norm"] = df["answer"].apply(normalize_search_text)
    df["qa_text"] = (df["question"] + " / " + df["answer"]).astype(str)
    df["qa_text_norm"] = (df["question_norm"] + " / " + df["answer_norm"]).astype(str)
    df["search_tokens"] = df["qa_text_norm"].apply(extract_search_tokens)
    df["search_concepts"] = df["qa_text_norm"].apply(extract_concepts)

    try:
        word_vectorizer = WORD_VECTORIZER
        char_vectorizer = CHAR_VECTORIZER
        X_word = word_vectorizer.fit_transform(df["qa_text_norm"])
        X_char = char_vectorizer.fit_transform(df["qa_text_norm"])
    except Exception:
        return df, None, None, None, None, None

    # sentence-transformers は起動時に埋め込みを全件生成せず、検索時に遅延ロードする
    faq_embeddings = None

    return df, word_vectorizer, X_word, char_vectorizer, X_char, faq_embeddings

def get_faq_index_state(faq_path_str: str):
    return load_faq_index(faq_path_str)

def reset_faq_index_runtime():
    global df, vectorizer, X, char_vectorizer, X_char, faq_embeddings
    df = None
    vectorizer = None
    X = None
    char_vectorizer = None
    X_char = None
    faq_embeddings = None

def ensure_faq_index_loaded():
    global df, vectorizer, X, char_vectorizer, X_char, faq_embeddings
    if df is not None and vectorizer is not None and X is not None and char_vectorizer is not None and X_char is not None:
        return df, vectorizer, X, char_vectorizer, X_char, faq_embeddings
    try:
        df, vectorizer, X, char_vectorizer, X_char, faq_embeddings = get_faq_index_state(str(FAQ_PATH))
    except Exception:
        reset_faq_index_runtime()
    return df, vectorizer, X, char_vectorizer, X_char, faq_embeddings

def get_faq_index_cached():
    """互換ラッパー: 旧修正で参照された名前を既存の遅延ロード実装へ接続する。"""
    return ensure_faq_index_loaded()

def _is_fastlane_query_text(query: str) -> bool:
    q = normalize_search_text(query)
    if not q:
        return False
    for rule in FASTLANE_INTENT_RULES:
        try:
            if _contains_any(q, rule.get("query_any", [])) and _contains_any(q, rule.get("query_any2", [])):
                return True
        except Exception:
            continue
    return False

def _build_fast_lookup_maps(_faq_token: str):
    local_df, *_ = ensure_faq_index_loaded()
    if local_df is None or len(local_df) == 0:
        return {"exact": {}, "password_rows": [], "rule_rows": {}}

    exact = {}
    password_rows = []
    rule_rows = {rule.get("name", f"rule_{i}"): [] for i, rule in enumerate(FASTLANE_INTENT_RULES)}

    for idx, row in local_df.iterrows():
        qn = str(row.get("question_norm", "")).strip()
        if qn:
            exact.setdefault(qn, []).append(int(idx))
        q_text = normalize_search_text(str(row.get("question", "")))
        a_text = normalize_search_text(str(row.get("answer", "")))
        whole = f"{q_text} {a_text}"
        if any(w in whole for w in ["パスワード", "password", "pw", "リセット", "再設定", "初期化"]):
            password_rows.append(int(idx))
        for i, rule in enumerate(FASTLANE_INTENT_RULES):
            rule_name = rule.get("name", f"rule_{i}")
            faq_words = [normalize_search_text(w) for w in rule.get("faq_any", []) if w]
            if any(w and w in whole for w in faq_words):
                rule_rows.setdefault(rule_name, []).append(int(idx))

    return {"exact": exact, "password_rows": password_rows, "rule_rows": rule_rows}

def _score_fast_candidate(query_norm: str, q_tokens: set[str], row) -> float:
    question_norm = str(row.get("question_norm", ""))
    answer_norm = str(row.get("answer_norm", ""))
    search_tokens = set(row.get("search_tokens", [])) if hasattr(row, "get") else set()
    score = 0.0
    if question_norm == query_norm:
        score += 1.2
    if query_norm and (query_norm in question_norm or question_norm in query_norm):
        score += 0.45
    overlap = len(q_tokens & search_tokens) / max(1, len(q_tokens)) if q_tokens else 0.0
    score += overlap * 0.55
    if "パスワード" in query_norm and "パスワード" in f"{question_norm} {answer_norm}":
        score += 0.25
    if any(k in query_norm for k in ["忘れ", "わから", "リセット", "再設定", "失念"]):
        if any(k in f"{question_norm} {answer_norm}" for k in ["リセット", "再設定", "初期化", "忘れ"]):
            score += 0.22
    return float(score)

def try_ultrafast_answer(query: str):
    local_df, *_ = ensure_faq_index_loaded()
    if local_df is None or len(local_df) == 0:
        return None

    query_norm = normalize_search_text(query)
    if not query_norm:
        return None

    maps = _build_fast_lookup_maps(_faq_cache_token())
    exact_idxs = maps.get("exact", {}).get(query_norm, [])
    if exact_idxs:
        idx = int(exact_idxs[0])
        row = local_df.iloc[idx]
        ans = str(row.get("answer", "")).strip()
        if ans:
            return {"answer": ans, "hits": [(row, 0.99)], "best_score": 0.99, "mode": "exact"}

    q_tokens = extract_search_tokens(query_norm)

    # パスワード忘れ系は最優先で超高速レーン
    if _contains_any(query, ["パスワード", "password", "pw", "認証情報"]) and _contains_any(query, ["忘れ", "わから", "不明", "リセット", "再設定", "失念", "変更"]):
        best = None
        for idx in maps.get("password_rows", []):
            row = local_df.iloc[int(idx)]
            score = _score_fast_candidate(query_norm, q_tokens, row)
            if best is None or score > best[0]:
                best = (score, row)
        if best and best[0] >= 0.42:
            return {"answer": str(best[1].get("answer", "")).strip(), "hits": [(best[1], min(0.98, best[0]))], "best_score": min(0.98, best[0]), "mode": "password_fastlane"}

    # 他の頻出系も軽量ルートで先に拾う
    for i, rule in enumerate(FASTLANE_INTENT_RULES):
        if not (_contains_any(query, rule.get("query_any", [])) and _contains_any(query, rule.get("query_any2", []))):
            continue
        best = None
        for idx in maps.get("rule_rows", {}).get(rule.get("name", f"rule_{i}"), []):
            row = local_df.iloc[int(idx)]
            score = _score_fast_candidate(query_norm, q_tokens, row)
            if best is None or score > best[0]:
                best = (score, row)
        if best and best[0] >= 0.46:
            return {"answer": str(best[1].get("answer", "")).strip(), "hits": [(best[1], min(0.96, best[0]))], "best_score": min(0.96, best[0]), "mode": "rule_fastlane"}

    return None

def retrieve_faq_cached(query: str, faq_token: str):
    results = retrieve_faq(query)
    packed = []
    for row, score in results:
        try:
            idx = int(getattr(row, "name", -1))
        except Exception:
            idx = -1
        packed.append((idx, float(score)))
    return packed

def retrieve_faq(query: str):
    if not query:
        return []
    local_df, local_vectorizer, local_X, local_char_vectorizer, local_X_char, local_faq_embeddings = ensure_faq_index_loaded()
    if local_vectorizer is None or local_X is None or local_char_vectorizer is None or local_X_char is None or local_df is None or len(local_df) == 0:
        return []
    try:
        query_norm = normalize_search_text(query)
        if not query_norm:
            return []

        qv_word = local_vectorizer.transform([query_norm])
        qv_char = local_char_vectorizer.transform([query_norm])
        sims_word = cosine_similarity(qv_word, local_X).flatten()
        sims_char = cosine_similarity(qv_char, local_X_char).flatten()
        if sims_word.size == 0 or sims_char.size == 0:
            return []

        search_cfg = current_search_settings()

        # まずは軽量検索だけで候補を絞る
        sims_base = (sims_word * float(search_cfg.get("word_weight", 0.54))) + (sims_char * float(search_cfg.get("char_weight", 0.46)))

        q_tokens = extract_search_tokens(query_norm)
        q_concepts = extract_concepts(query_norm)

        exact_bonus = (local_df["question_norm"] == query_norm).astype(float).to_numpy() * float(search_cfg.get("exact_bonus", 0.28))
        contains_bonus = local_df["question_norm"].apply(
            lambda x: float(search_cfg.get("contains_bonus", 0.14)) if query_norm and (query_norm in x or x in query_norm) else 0.0
        ).to_numpy()

        token_bonus = local_df["search_tokens"].apply(
            lambda toks: (float(search_cfg.get("token_bonus_max", 0.24)) * len(q_tokens & set(toks)) / max(1, len(q_tokens))) if q_tokens else 0.0
        ).to_numpy()

        concept_bonus = local_df["search_concepts"].apply(
            lambda cs: (float(search_cfg.get("concept_bonus_max", 0.24)) * len(q_concepts & set(cs)) / max(1, len(q_concepts))) if q_concepts else 0.0
        ).to_numpy()

        prefix_bonus = local_df["question_norm"].apply(
            lambda x: float(search_cfg.get("prefix_bonus", 0.07)) if query_norm and str(x).startswith(query_norm[: min(8, len(query_norm))]) else 0.0
        ).to_numpy()

        sims = sims_base + exact_bonus + contains_bonus + token_bonus + concept_bonus + prefix_bonus

        # 頻出問い合わせ（パスワード等）はここで十分。重い意味検索は使わない
        is_fastlane = _is_fastlane_query_text(query_norm)

        preliminary_top = float(sims.max()) if len(sims) else 0.0
        query_len = len(query_norm)
        need_semantic = (
            bool(search_cfg.get("semantic_enabled", True))
            and (not is_fastlane or not bool(search_cfg.get("semantic_skip_fastlane", True)))
            and SENTENCE_TRANSFORMERS_AVAILABLE
            and query_len >= int(search_cfg.get("semantic_min_query_len", 8))
            and float(search_cfg.get("semantic_trigger_min", 0.24)) <= preliminary_top <= float(search_cfg.get("semantic_trigger_max", 0.48))
        )

        # 意味検索は「あいまいで軽量検索だけでは微妙」な時だけ
        if need_semantic:
            candidate_count = min(int(search_cfg.get("semantic_candidate_count", 8)), len(sims))
            candidate_idxs = sims.argsort()[::-1][:candidate_count]
            if local_faq_embeddings is None and local_df is not None and len(local_df) > 0 and "qa_text_norm" in local_df.columns:
                try:
                    local_faq_embeddings = _get_sentence_embeddings_cached(tuple(local_df["qa_text_norm"].tolist()))
                except Exception:
                    local_faq_embeddings = None

            sims_sem = _search_with_sentence_transformers(query_norm, local_faq_embeddings)
            if sims_sem is not None and len(sims_sem) == len(sims):
                sem_arr = pd.Series(sims_sem).fillna(0.0).to_numpy()
                boosted = sims.copy()
                boosted[candidate_idxs] = boosted[candidate_idxs] + (sem_arr[candidate_idxs] * float(search_cfg.get("semantic_boost", 0.28)))
                sims = boosted

        idxs = sims.argsort()[::-1][:int(search_cfg.get("top_k", 3))]
        return [(local_df.iloc[i], float(sims[i])) for i in idxs if float(sims[i]) > 0]
    except Exception:
        return []

def _contains_any(text: str, words: list[str]) -> bool:
    s = normalize_search_text(text)
    return any(normalize_search_text(w) in s for w in words if w)

def _faq_row_matches_words(row, words: list[str]) -> bool:
    q = normalize_search_text(str(row.get("question", "")))
    a = normalize_search_text(str(row.get("answer", "")))
    whole = f"{q} {a}"
    return any(normalize_search_text(w) in whole for w in words if w)

def _fastlane_direct_answer(user_q: str, hits, best_score: float, answer_threshold: float, suggest_threshold: float):
    """FAQで十分答えられる問い合わせは、LLMを呼ばずに高速返答する。"""
    if not hits:
        return None

    top_row, _ = hits[0]
    faq_answer = str(top_row.get("answer", "")).strip()
    if not faq_answer:
        return None

    q_norm = normalize_search_text(user_q)
    top_q_norm = normalize_search_text(str(top_row.get("question", "")))
    q_tokens = extract_search_tokens(q_norm)
    top_tokens = set(top_row.get("search_tokens", [])) if hasattr(top_row, "get") else set()
    token_overlap = (len(q_tokens & top_tokens) / max(1, len(q_tokens))) if q_tokens else 0.0
    q_concepts = extract_concepts(q_norm)
    top_concepts = set(top_row.get("search_concepts", [])) if hasattr(top_row, "get") else set()
    concept_overlap = (len(q_concepts & top_concepts) / max(1, len(q_concepts))) if q_concepts else 0.0
    exact_like = bool(top_q_norm and (q_norm == top_q_norm or q_norm in top_q_norm or top_q_norm in q_norm))

    FAQ_DIRECT_SCORE = max(answer_threshold, 0.35)
    FAST_DIRECT_SCORE = max(suggest_threshold + 0.10, min(answer_threshold, 0.68))

    if best_score >= FAQ_DIRECT_SCORE:
        return faq_answer
    if exact_like and best_score >= FAST_DIRECT_SCORE:
        return faq_answer
    if token_overlap >= 0.70 and best_score >= max(suggest_threshold + 0.06, 0.42):
        return faq_answer
    if concept_overlap >= 0.80 and best_score >= max(suggest_threshold + 0.04, 0.36):
        return faq_answer

    # 頻出系（パスワード忘れなど）は、候補が十分寄っていれば LLM に行かず即答する
    for rule in FASTLANE_INTENT_RULES:
        if not _contains_any(user_q, rule["query_any"]):
            continue
        if not _contains_any(user_q, rule["query_any2"]):
            continue

        if _faq_row_matches_words(top_row, rule["faq_any"]) and best_score >= max(suggest_threshold + 0.02, 0.28):
            return faq_answer

        for row, score in hits[:3]:
            answer = str(row.get("answer", "")).strip()
            if not answer:
                continue
            if _faq_row_matches_words(row, rule["faq_any"]) and float(score) >= max(suggest_threshold, 0.26):
                return answer

    return None

def llm_answer_cached(user_q: str, prompt: str, faq_token: str, top_question: str):
    try:
        answer = llm_chat(
            [
                {"role": "system", "content": "あなたは情シス担当です。FAQの内容を優先し、必ず日本語で簡潔に回答してください。"},
                {"role": "user", "content": prompt},
            ]
        )
        return str(answer or "").strip()
    except Exception:
        return ""

def build_prompt(user_q: str, hits):
    context_parts = []
    for i, (row, score) in enumerate(hits, 1):
        q = str(row.get("question", ""))
        a = str(row.get("answer", ""))
        context_parts.append(f"\n[FAQ{i}]\nQ:{q}\nA:{a}\n")
    context = "".join(context_parts)

    return f"""
あなたは社内の情シス担当です。
必ず日本語のみで回答してください。
丁寧で簡潔に、手順は箇条書きで書いてください。

参照FAQ:
{context}

質問:
{user_q}
"""

def nohit_template():
    return """
FAQに該当がありませんでした。

情シスへお問い合わせの際は、以下の情報を添えてください：

・何ができないか（具体的な操作）
・エラー画面のスクリーンショット
・発生時刻
・利用場所（社内 / 社外）
・ネットワーク（Wi-Fi / VPN）
・端末（Windows / Mac）
・影響範囲（自分のみ / 他の人も）

※これらを共有いただくと対応が早くなります。
※このAIは御社の運用に合わせてカスタマイズ可能です。
""".strip()

def _ensure_nohit_schema(path: Path):
    """既存nohit CSVが旧形式（timestamp,questionのみ）でも、新スキーマに移行する。"""
    cols = ["timestamp", "question", "device", "location", "network", "error_text", "impact", "channel"]
    if not path.exists():
        return cols

    try:
        # 先頭行だけ見る（軽量）
        with path.open("r", encoding="utf-8", errors="ignore") as f:
            header = f.readline().strip()
        header_cols = [h.strip() for h in header.split(",")] if header else []
    except Exception:
        header_cols = []

    # すでに新スキーマなら何もしない
    if set(cols).issubset(set(header_cols)):
        return header_cols

    # 移行：既存を読み取り→新ヘッダで書き直し
    try:
        old_df = read_csv_flexible(path)
        if old_df is None:
            old_df = pd.DataFrame()
    except Exception:
        old_df = pd.DataFrame()

    if len(old_df) == 0:
        # 空なら新ヘッダで作り直す
        with path.open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(cols)
        return cols

    qcol = pick_question_column(old_df.columns) or ("question" if "question" in old_df.columns else None)
    tcol = "timestamp" if "timestamp" in old_df.columns else None

    rows = []
    for _, r in old_df.iterrows():
        ts = str(r.get(tcol, "")).strip() if tcol else ""
        q = str(r.get(qcol, "")).strip() if qcol else ""
        if not q:
            continue
        rows.append([ts, q, "", "", "", "", "", ""])

    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        w.writerows(rows)

    return cols

def log_nohit(question: str, extra: dict | None = None) -> str:
    """該当なしログを追記して、記録したtimestamp（秒）を返す。"""
    if not question:
        return ""
    extra = extra or {}
    day = datetime.now().strftime("%Y%m%d")
    path = LOG_DIR / f"nohit_{day}.csv"
    cols = _ensure_nohit_schema(path)

    ts = datetime.now().isoformat(timespec="seconds")
    row = {
        "timestamp": ts,
        "question": question,
        "device": extra.get("device", ""),
        "location": extra.get("location", ""),
        "network": extra.get("network", ""),
        "error_text": extra.get("error_text", ""),
        "impact": extra.get("impact", ""),
        "channel": extra.get("channel", "web"),
    }

    try:
        is_new = not path.exists()
        with path.open("a", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            if is_new:
                w.writerow(cols)
            w.writerow([row.get(c, "") for c in cols])
        persist_log_now(path)
    except Exception:
        pass
    return ts

def update_nohit_record(day: str, timestamp: str, question: str, extra: dict) -> bool:
    """同じday/timestamp/question の行があれば更新。無ければ追記。"""
    if not day or not timestamp or not question:
        return False
    path = LOG_DIR / f"nohit_{day}.csv"
    cols = _ensure_nohit_schema(path)

    try:
        df_log = read_csv_flexible(path)
        if df_log is None:
            df_log = pd.DataFrame(columns=cols)
    except Exception:
        df_log = pd.DataFrame(columns=cols)

    # 必須列を揃える
    for c in cols:
        if c not in df_log.columns:
            df_log[c] = ""

    # 既存行を更新（最初の一致）
    mask = (df_log["timestamp"].astype(str) == str(timestamp)) & (df_log["question"].astype(str) == str(question))
    idxs = df_log.index[mask].tolist()
    if idxs:
        i = idxs[0]
        for k, v in (extra or {}).items():
            if k in df_log.columns:
                df_log.at[i, k] = v
        df_log.at[i, "channel"] = extra.get("channel", df_log.at[i, "channel"] or "web")
    else:
        # 無ければ追記
        row = {c: "" for c in cols}
        row["timestamp"] = timestamp
        row["question"] = question
        for k, v in (extra or {}).items():
            if k in row:
                row[k] = v
        if not row.get("channel"):
            row["channel"] = "web"
        df_log = pd.concat([df_log, pd.DataFrame([row])], ignore_index=True)

    # UTF-8で書き戻す（Excel対応ならutf-8-sigでもOK）
    try:
        with path.open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(cols)
            for _, r in df_log[cols].iterrows():
                w.writerow([str(r.get(c, "")) for c in cols])
        persist_log_now(path)
        return True
    except Exception:
        return False

def seed_nohit_questions(n: int = 20) -> int:
    """本番前のデモ用：情シス定番のnohit質問を今日のログに追加する。"""
    seeds = [
        "VPNにつながらない", "Outlookの送受信ができない", "Teamsにログインできない", "パスワードを忘れた",
        "アカウントがロックされた", "共有フォルダにアクセスできない", "プリンタが印刷できない", "Wi-Fiが頻繁に切れる",
        "PCが重い", "PCが固まる", "Excelが起動しない", "Excelがフリーズする", "OneDriveが同期しない",
        "メール添付ファイルが開けない", "二段階認証が通らない", "カメラが映らない", "マイクが認識されない",
        "ソフトのインストール申請方法が分からない", "Windows更新が終わらない", "画面が真っ黒になる",
    ]
    added = 0
    for q in seeds[:n]:
        ts = log_nohit(q, {"channel": "seed"})
        if ts:
            added += 1
    return added

def log_interaction(question: str, matched: bool, best_score: float, category: str):
    """全ての質問をログ化（削減時間の見える化用）: logs/interactions_YYYYMMDD.csv"""
    if not question:
        return
    day = datetime.now().strftime("%Y%m%d")
    path = LOG_DIR / f"interactions_{day}.csv"
    try:
        is_new = not path.exists()
        with path.open("a", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            if is_new:
                w.writerow(["timestamp", "question", "matched", "best_score", "category"])
            w.writerow([datetime.now().isoformat(timespec="seconds"), question, int(bool(matched)), float(best_score), category or ""])
        persist_log_now(path)
    except Exception:
        pass

def normalize_question(q: str) -> str:
    q = (q or "").strip().lower()
    q = re.sub(r"\s+", " ", q)
    # 日本語も含めて記号類をざっくり除去
    q = re.sub(r"[\u3000\s\t\r\n]+", " ", q)
    q = re.sub(r"[!！?？。、,.，:：;；\-_=+~`'\"()（）\[\]{}<>＜＞/\\|@#%^&*]", "", q)
    return q.strip()

def load_nohit_questions_from_logs(files, max_questions: int = 100) -> list[str]:
    """nohit_*.csv から質問を収集（新しいログから優先）。文字コード/カラム揺れに強く読む。"""
    questions: list[str] = []
    seen: set[str] = set()
    for p in files:
        try:
            _df = read_csv_flexible(Path(p))
            if _df is None or len(_df) == 0:
                continue

            qcol = pick_question_column(_df.columns)
            if not qcol:
                continue

            for q in _df[qcol].fillna("").astype(str).tolist():
                nq = normalize_question(q)
                if not nq:
                    continue
                if nq in seen:
                    continue
                seen.add(nq)
                questions.append(q.strip())
                if len(questions) >= max_questions:
                    return questions
        except Exception:
            continue
    return questions

def generate_faq_candidates(nohit_questions: list[str], n_items: int = 8) -> pd.DataFrame:
    """該当なしログからFAQ案を生成してDataFrameで返す（category/question/answer）。"""
    if not nohit_questions:
        return pd.DataFrame(columns=["category", "question", "answer"])

    # 入力が長すぎると落ちるので上限
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

def append_faq_csv(faq_path: Path, new_df: pd.DataFrame) -> int:
    """faq.csv に追記。重複（question）をざっくり除外して追記件数を返す。"""
    if new_df is None or len(new_df) == 0:
        return 0

    # 必須列を揃える
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

    # 既存読み込み
    if faq_path.exists():
        try:
            exist = normalize_faq_columns(read_csv_flexible(faq_path))
        except Exception:
            exist = pd.DataFrame(columns=["question", "answer", "category"])
    else:
        exist = pd.DataFrame(columns=["question", "answer", "category"])

    exist_q = set(normalize_question(x) for x in exist.get("question", pd.Series(dtype=str)).fillna("").astype(str).tolist())

    rows = []
    for _, r in new_df.iterrows():
        nq = normalize_question(str(r.get("question", "")))
        if not nq:
            continue
        if nq in exist_q:
            continue
        exist_q.add(nq)
        rows.append([r["question"], r["answer"], r.get("category", "")])

    if not rows:
        return 0

    is_new = not faq_path.exists()
    with faq_path.open("a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if is_new:
            w.writerow(["question", "answer", "category"])
        w.writerows(rows)

    persist_faq_now()
    return len(rows)

def generate_slack_bot_zip_bytes():
    """Slack Bot 完全版コード一式をZIPで返す。既存アプリ本体とは分離し、Render等に別サービスとして配置する想定。"""
    import textwrap

    render_base = "https://your-render-url.onrender.com"

    slack_bot_py = textwrap.dedent("""    import os
    import hmac
    import hashlib
    import time
    import json
    from typing import Any

    import requests
    from flask import Flask, request, jsonify

    app = Flask(__name__)

    HELP_DESK_ASK_URL = os.getenv("HELPDESK_ASK_URL", "https://your-streamlit-or-api-url/ask")
    SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET", "")
    REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "30"))


    def verify_slack_request(req) -> bool:
        if not SLACK_SIGNING_SECRET:
            return True

        timestamp = req.headers.get("X-Slack-Request-Timestamp", "")
        slack_signature = req.headers.get("X-Slack-Signature", "")
        if not timestamp or not slack_signature:
            return False

        try:
            if abs(time.time() - int(timestamp)) > 60 * 5:
                return False
        except Exception:
            return False

        body = req.get_data(as_text=True)
        basestring = f"v0:{timestamp}:{body}"
        my_signature = "v0=" + hmac.new(
            SLACK_SIGNING_SECRET.encode("utf-8"),
            basestring.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(my_signature, slack_signature)


    def ask_helpdesk(question: str, user_name: str = "", channel_name: str = "") -> str:
        payload: dict[str, Any] = {
            "question": question,
            "source": "slack",
            "user_name": user_name,
            "channel_name": channel_name,
        }

        r = requests.post(
            HELP_DESK_ASK_URL,
            json=payload,
            timeout=REQUEST_TIMEOUT,
        )
        r.raise_for_status()

        data = r.json()
        answer = data.get("answer") or data.get("message") or "回答を取得できませんでした。"
        return str(answer)


    @app.get("/")
    def health() -> tuple[str, int]:
        return "ok", 200


    @app.post("/slack/command")
    def slack_command():
        if not verify_slack_request(request):
            return jsonify({"text": "署名検証に失敗しました。"}), 403

        question = (request.form.get("text") or "").strip()
        user_name = request.form.get("user_name", "")
        channel_name = request.form.get("channel_name", "")

        if not question:
            return jsonify({
                "response_type": "ephemeral",
                "text": "質問文を入れてください。例: /helpdesk VPNがつながらない",
            })

        try:
            answer = ask_helpdesk(question, user_name=user_name, channel_name=channel_name)
            return jsonify({
                "response_type": "in_channel",
                "text": f"*質問:* {question}\n*回答:* {answer}",
            })
        except Exception as e:
            return jsonify({
                "response_type": "ephemeral",
                "text": f"問い合わせAIへの接続に失敗しました: {e}",
            }), 500


    @app.post("/slack/events")
    def slack_events():
        if not verify_slack_request(request):
            return jsonify({"error": "invalid signature"}), 403

        data = request.get_json(silent=True) or {}

        if data.get("type") == "url_verification":
            return jsonify({"challenge": data.get("challenge", "")})

        event = data.get("event", {})
        if event.get("type") == "app_mention":
            text = event.get("text", "")
            return jsonify({"ok": True, "note": f"mention received: {text}"})

        return jsonify({"ok": True})


    if __name__ == "__main__":
        port = int(os.getenv("PORT", "3000"))
        app.run(host="0.0.0.0", port=port)
    """).strip() + "\n"

    requirements_txt = textwrap.dedent("""    flask==3.0.3
    requests==2.32.3
    gunicorn==22.0.0
    """).strip() + "\n"

    render_yaml = textwrap.dedent("""    services:
      - type: web
        name: slack-helpdesk-bot
        env: python
        plan: free
        buildCommand: pip install -r requirements.txt
        startCommand: gunicorn slack_bot:app
        autoDeploy: true
    """).strip() + "\n"

    env_example = textwrap.dedent(f"""    HELPDESK_ASK_URL={render_base}/ask
    SLACK_SIGNING_SECRET=your_signing_secret
    REQUEST_TIMEOUT=30
    """).strip() + "\n"

    readme_md = textwrap.dedent("""    # Slack Helpdesk Bot 完全版

    このZIPは、既存の Streamlit アプリ本体とは別サービスとして Render に配置する想定です。

    ## 含まれるファイル
    - `slack_bot.py` : Slack Slash Command / Events 受信用 Flask アプリ
    - `requirements.txt` : 必要ライブラリ
    - `render.yaml` : Render デプロイ設定例
    - `.env.example` : 環境変数の雛形

    ## Slack 側設定
    1. Slack API で App を作成
    2. Slash Commands に `/helpdesk` を追加
    3. Request URL に `https://あなたのRenderURL/slack/command` を設定
    4. Event Subscriptions を使う場合は `https://あなたのRenderURL/slack/events` を設定
    5. Signing Secret を Render の環境変数 `SLACK_SIGNING_SECRET` に設定

    ## Render 側設定
    1. このZIPを GitHub リポジトリに配置
    2. Render で New + → Web Service
    3. Build Command: `pip install -r requirements.txt`
    4. Start Command: `gunicorn slack_bot:app`
    5. `HELPDESK_ASK_URL` に既存問い合わせAIの API URL を設定

    ## 重要
    既存の Streamlit アプリに `/ask` API が無い場合は、別途 API 追加が必要です。
    まずは Slack Bot コード一式を先に配布し、後から API 側を接続しても構いません。
    """).strip() + "\n"

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("slack_bot.py", slack_bot_py)
        zf.writestr("requirements.txt", requirements_txt)
        zf.writestr("render.yaml", render_yaml)
        zf.writestr(".env.example", env_example)
        zf.writestr("README.md", readme_md)

    buf.seek(0)
    return buf.getvalue()

def build_suggest_answer(user_q: str, hits) -> str:
    if not hits:
        return nohit_template()
    row, score = hits[0]
    q = str(row.get("question", "")).strip()
    a = str(row.get("answer", "")).strip()
    cat = str(row.get("category", "")).strip()
    parts = [
        "入力内容に近いFAQ候補が見つかりました。完全一致ではありませんが、まずはこちらを確認してください。",
    ]
    if q:
        parts.append(f"【候補FAQ】{q}")
    if cat:
        parts.append(f"【カテゴリ】{cat}")
    if a:
        parts.append(f"【回答】\n{a}")
    parts.append("解決しない場合は、下の『追加情報を記録』から状況を補足してください。")
    return "\n\n".join(parts)

def render_nohit_extra_form(info: dict | None = None, expanded: bool = True):
    """『該当なし』直後に表示する追加情報フォーム（端末/利用場所/ネットワーク等）。"""
    info = info or (st.session_state.get("pending_nohit", {}) or {})
    with st.expander("📝 追加情報を記録（任意）", expanded=expanded):
        st.caption("解決しない場合は、状況を少し補足するとFAQ改善に役立ちます。")
        with st.form("nohit_extra_form", clear_on_submit=False):
            c1, c2, c3 = st.columns(3)
            with c1:
                device = st.selectbox(
                    "端末",
                    ["", "Windows", "Mac", "iPhone/iPad", "Android", "不明"],
                    index=0,
                    key="nohit_device",
                )
            with c2:
                location = st.selectbox(
                    "利用場所",
                    ["", "社内", "社外", "不明"],
                    index=0,
                    key="nohit_location",
                )
            with c3:
                network = st.selectbox(
                    "ネットワーク",
                    ["", "Wi-Fi", "有線", "VPN", "モバイル回線", "不明"],
                    index=0,
                    key="nohit_network",
                )

            impact = st.selectbox(
                "影響範囲",
                ["", "自分のみ", "他の人も", "不明"],
                index=0,
                key="nohit_impact",
            )
            error_text = st.text_area(
                "エラー内容（任意）",
                placeholder="例：0x80190001 / '資格情報が無効です' など",
                key="nohit_error_text",
            )

            submitted = st.form_submit_button("✅ この内容で記録")
            if submitted:
                ok = update_nohit_record(
                    day=str(info.get("day", "")),
                    timestamp=str(info.get("timestamp", "")),
                    question=str(info.get("question", "")),
                    extra={
                        "device": device,
                        "location": location,
                        "network": network,
                        "impact": impact,
                        "error_text": error_text,
                        "channel": "web",
                    },
                )
                if ok:
                    st.success("追加情報をログに保存しました。ありがとうございます！")
                    # 次回以降はフォームを閉じる（保持は消す）
                    st.session_state["pending_nohit_active"] = False
                else:
                    st.warning("保存に失敗しました（もう一度お試しください）。")
