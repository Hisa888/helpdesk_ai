
from __future__ import annotations

from types import SimpleNamespace
import re


def create_search_runtime(
    *,
    st,
    pd,
    Path,
    FAQ_PATH,
    TfidfVectorizer,
    cosine_similarity,
    normalize_faq_columns,
    read_csv_flexible,
    current_search_settings,
    llm_chat,
    _faq_cache_token,
    SENTENCE_TRANSFORMERS_AVAILABLE,
    SentenceTransformer,
    FULLWIDTH_TRANS,
    CANONICAL_PATTERNS,
    CONCEPT_ALIASES,
    FASTLANE_INTENT_RULES,
    create_faq_index_runtime,
):
    def normalize_search_text(text: str) -> str:
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
        s = normalize_search_text(text)
        if not s:
            return set()
        tokens = set()
        for part in s.split():
            part = part.strip()
            if part:
                tokens.add(part)
        for tok in re.findall(r"[a-z0-9]+|[぀-ヿ一-鿿]{2,}", s):
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

    def load_faq_df():
        try:
            return normalize_faq_columns(read_csv_flexible(FAQ_PATH))
        except Exception:
            return pd.DataFrame(columns=["question", "answer", "category"])

    def prepare_faq_dataframe(src_df: pd.DataFrame) -> pd.DataFrame:
        try:
            df = normalize_faq_columns(src_df)
        except Exception:
            df = src_df.copy() if src_df is not None else pd.DataFrame(columns=["question", "answer", "category"])
        if df is None or len(df) == 0:
            return pd.DataFrame(columns=["question", "answer", "category"])
        df = df.copy()
        df["question"] = df["question"].fillna("").astype(str)
        df["answer"] = df["answer"].fillna("").astype(str)
        df["category"] = df["category"].fillna("").astype(str)
        df["question_norm"] = df["question"].apply(normalize_search_text)
        df["answer_norm"] = df["answer"].apply(normalize_search_text)
        df["qa_text"] = (df["question"] + " / " + df["answer"]).astype(str)
        df["qa_text_norm"] = (df["question_norm"] + " / " + df["answer_norm"]).astype(str)
        df["search_text_norm"] = (
            df["question_norm"].fillna("").astype(str) + " / " + df["category"].fillna("").astype(str).apply(normalize_search_text)
        ).astype(str)
        df["search_tokens"] = df["search_text_norm"].apply(extract_search_tokens)
        df["search_concepts"] = df["search_text_norm"].apply(extract_concepts)
        return df

    faq_index_ctx = create_faq_index_runtime(
        st=st,
        pd=pd,
        Path=Path,
        FAQ_PATH=FAQ_PATH,
        TfidfVectorizer=TfidfVectorizer,
        cosine_similarity=cosine_similarity,
        normalize_faq_columns=normalize_faq_columns,
        read_csv_flexible=read_csv_flexible,
        normalize_search_text=normalize_search_text,
        extract_search_tokens=extract_search_tokens,
        extract_concepts=extract_concepts,
        load_faq_df=load_faq_df,
        prepare_faq_dataframe=prepare_faq_dataframe,
        SENTENCE_TRANSFORMERS_AVAILABLE=SENTENCE_TRANSFORMERS_AVAILABLE,
        SentenceTransformer=SentenceTransformer,
        FASTLANE_INTENT_RULES=FASTLANE_INTENT_RULES,
    )

    def _contains_any(text: str, words: list[str]) -> bool:
        s = normalize_search_text(text)
        return any(normalize_search_text(w) in s for w in words if w)

    def _faq_row_matches_words(row, words: list[str]) -> bool:
        q = normalize_search_text(str(row.get("question", "")))
        a = normalize_search_text(str(row.get("answer", "")))
        whole = f"{q} {a}"
        return any(normalize_search_text(w) in whole for w in words if w)

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
        local_df, *_ = faq_index_ctx.ensure_faq_index_loaded()
        if local_df is None or len(local_df) == 0:
            return None
        query_norm = normalize_search_text(query)
        if not query_norm:
            return None
        maps = faq_index_ctx._build_fast_lookup_maps(_faq_cache_token())
        exact_idxs = maps.get("exact", {}).get(query_norm, [])
        if exact_idxs:
            idx = int(exact_idxs[0])
            row = local_df.iloc[idx]
            ans = str(row.get("answer", "")).strip()
            if ans:
                return {"answer": ans, "hits": [(row, 0.99)], "best_score": 0.99, "mode": "exact"}
        q_tokens = extract_search_tokens(query_norm)
        if _contains_any(query, ["パスワード", "password", "pw", "認証情報"]) and _contains_any(query, ["忘れ", "わから", "不明", "リセット", "再設定", "失念", "変更"]):
            best = None
            for idx in maps.get("password_rows", []):
                row = local_df.iloc[int(idx)]
                score = _score_fast_candidate(query_norm, q_tokens, row)
                if best is None or score > best[0]:
                    best = (score, row)
            if best and best[0] >= 0.42:
                return {"answer": str(best[1].get("answer", "")).strip(), "hits": [(best[1], min(0.98, best[0]))], "best_score": min(0.98, best[0]), "mode": "password_fastlane"}
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

    def _domain_penalty(query_norm: str, row) -> float:
        try:
            q_concepts = extract_concepts(query_norm)
            row_q = normalize_search_text(str(row.get("question", "")))
            row_c = normalize_search_text(str(row.get("category", "")))
            row_text = f"{row_q} / {row_c}"
            row_concepts = extract_concepts(row_text)
            penalty = 0.0
            if "pc_device" in q_concepts:
                if "pc_device" not in row_concepts:
                    penalty -= 0.22
                if "boot" in q_concepts and ({"office_app", "browser_app", "mail_app"} & row_concepts):
                    penalty -= 0.35
            if "boot" in q_concepts and not ({"office_app", "browser_app", "mail_app"} & q_concepts):
                if {"office_app", "browser_app", "mail_app"} & row_concepts and "pc_device" not in row_concepts:
                    penalty -= 0.18
            return float(penalty)
        except Exception:
            return 0.0

    @st.cache_data(show_spinner=False, ttl=1800)
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
        local_df, local_vectorizer, local_X, local_char_vectorizer, local_X_char, local_faq_embeddings = faq_index_ctx.ensure_faq_index_loaded()
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
            sims_base = (sims_word * float(search_cfg.get("word_weight", 0.54))) + (sims_char * float(search_cfg.get("char_weight", 0.46)))
            q_tokens = extract_search_tokens(query_norm)
            q_concepts = extract_concepts(query_norm)
            exact_bonus = (local_df["question_norm"] == query_norm).astype(float).to_numpy() * float(search_cfg.get("exact_bonus", 0.28))
            contains_bonus = local_df["question_norm"].apply(lambda x: float(search_cfg.get("contains_bonus", 0.14)) if query_norm and (query_norm in x or x in query_norm) else 0.0).to_numpy()
            token_bonus = local_df["search_tokens"].apply(lambda toks: (float(search_cfg.get("token_bonus_max", 0.24)) * len(q_tokens & set(toks)) / max(1, len(q_tokens))) if q_tokens else 0.0).to_numpy()
            concept_bonus = local_df["search_concepts"].apply(lambda cs: (float(search_cfg.get("concept_bonus_max", 0.24)) * len(q_concepts & set(cs)) / max(1, len(q_concepts))) if q_concepts else 0.0).to_numpy()
            prefix_bonus = local_df["question_norm"].apply(lambda x: float(search_cfg.get("prefix_bonus", 0.07)) if query_norm and str(x).startswith(query_norm[: min(8, len(query_norm))]) else 0.0).to_numpy()
            sims = sims_base + exact_bonus + contains_bonus + token_bonus + concept_bonus + prefix_bonus
            domain_penalty = local_df.apply(lambda row: _domain_penalty(query_norm, row), axis=1).to_numpy()
            sims = sims + domain_penalty
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
            if need_semantic:
                candidate_count = min(int(search_cfg.get("semantic_candidate_count", 8)), len(sims))
                candidate_idxs = sims.argsort()[::-1][:candidate_count]
                if local_faq_embeddings is None and local_df is not None and len(local_df) > 0 and "qa_text_norm" in local_df.columns:
                    try:
                        local_faq_embeddings = faq_index_ctx._get_sentence_embeddings_cached(tuple(local_df["qa_text_norm"].tolist()))
                    except Exception:
                        local_faq_embeddings = None
                sims_sem = faq_index_ctx._search_with_sentence_transformers(query_norm, local_faq_embeddings)
                if sims_sem is not None and len(sims_sem) == len(sims):
                    sem_arr = pd.Series(sims_sem).fillna(0.0).to_numpy()
                    boosted = sims.copy()
                    boosted[candidate_idxs] = boosted[candidate_idxs] + (sem_arr[candidate_idxs] * float(search_cfg.get("semantic_boost", 0.28)))
                    sims = boosted
            idxs = sims.argsort()[::-1][:int(search_cfg.get("top_k", 3))]
            return [(local_df.iloc[i], float(sims[i])) for i in idxs if float(sims[i]) > 0]
        except Exception:
            return []

    def _fastlane_direct_answer(user_q: str, hits, best_score: float, answer_threshold: float, suggest_threshold: float):
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

    @st.cache_data(show_spinner=False, ttl=1800)
    def llm_answer_cached(user_q: str, prompt: str, faq_token: str, top_question: str):
        try:
            answer = llm_chat([
                {"role": "system", "content": "あなたは情シス担当です。FAQの内容を優先し、必ず日本語で簡潔に回答してください。"},
                {"role": "user", "content": prompt},
            ])
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

    return SimpleNamespace(
        faq_index_ctx=faq_index_ctx,
        normalize_search_text=normalize_search_text,
        extract_search_tokens=extract_search_tokens,
        extract_concepts=extract_concepts,
        load_faq_df=load_faq_df,
        prepare_faq_dataframe=prepare_faq_dataframe,
        _contains_any=_contains_any,
        _faq_row_matches_words=_faq_row_matches_words,
        _is_fastlane_query_text=_is_fastlane_query_text,
        _score_fast_candidate=_score_fast_candidate,
        _domain_penalty=_domain_penalty,
        try_ultrafast_answer=try_ultrafast_answer,
        retrieve_faq_cached=retrieve_faq_cached,
        retrieve_faq=retrieve_faq,
        _fastlane_direct_answer=_fastlane_direct_answer,
        llm_answer_cached=llm_answer_cached,
        build_prompt=build_prompt,
    )
