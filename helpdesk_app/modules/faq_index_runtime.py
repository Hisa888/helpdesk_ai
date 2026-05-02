
from types import SimpleNamespace


def create_faq_index_runtime(
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
    normalize_search_text,
    extract_search_tokens,
    extract_concepts,
    load_faq_df,
    prepare_faq_dataframe,
    SENTENCE_TRANSFORMERS_AVAILABLE,
    SentenceTransformer,
    FASTLANE_INTENT_RULES,
):
    """FAQインデックス生成とキャッシュ系をまとめて返す。"""

    state = {
        "df": None,
        "vectorizer": None,
        "X": None,
        "char_vectorizer": None,
        "X_char": None,
        "faq_embeddings": None,
    }

    WORD_VECTORIZER = TfidfVectorizer(ngram_range=(1, 2))
    CHAR_VECTORIZER = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4))
    SENTENCE_MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

    def _filter_enabled_faq_rows(df):
        if df is None or len(df) == 0 or "enabled" not in df.columns:
            return df
        false_like = {"false", "0", "no", "n", "off", "disabled", "disable", "無効", "削除", "停止", "×", "✕"}
        mask = ~df["enabled"].fillna("TRUE").astype(str).str.strip().str.lower().isin(false_like)
        return df[mask].reset_index(drop=True)

    DEFAULT_FIELD_WEIGHTS = {
        "question": 3.0,
        "answer": 0.5,
        "intent": 2.5,
        "keywords": 2.0,
        "category": 1.0,
    }

    def _field_weight_settings() -> dict[str, float]:
        cfg = current_search_settings() if callable(current_search_settings) else {}
        out: dict[str, float] = {}
        for field, default in DEFAULT_FIELD_WEIGHTS.items():
            try:
                value = float(cfg.get(f"{field}_weight", default))
            except Exception:
                value = default
            out[field] = max(0.0, min(5.0, value))
        return out

    def _repeat_weighted_norm(text: str, weight: float) -> str:
        norm = normalize_search_text(text)
        if not norm or weight <= 0:
            return ""
        # TF-IDFで項目別重みを反映するため、重みに応じて検索テキスト内で反復する。
        # 0.5でも補助情報として1回、3.0なら6回程度入る。
        repeats = max(1, min(12, int(round(weight * 2))))
        return " ".join([norm] * repeats)

    def _weighted_search_text_norm(row) -> str:
        weights = _field_weight_settings()
        parts: list[str] = []
        for field in ["question", "intent", "keywords", "category", "answer"]:
            parts.append(_repeat_weighted_norm(str(row.get(field, "")), weights.get(field, 1.0)))
        return " / ".join([p for p in parts if p]).strip()

    @st.cache_resource
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

    @st.cache_resource
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

    def _empty_index():
        empty = pd.DataFrame(columns=["question", "answer", "intent", "keywords", "category", "answer_format"])
        return empty, None, None, None, None, None

    def _build_faq_index_from_df(src_df):
        """DataFrameから検索用インデックスをメモリ上に作る。"""
        try:
            df = _filter_enabled_faq_rows(normalize_faq_columns(src_df))
        except Exception:
            df = src_df.copy() if src_df is not None else pd.DataFrame()
            df = _filter_enabled_faq_rows(df)

        if df is None:
            return _empty_index()

        df = df.copy()
        for col in ["question", "answer", "intent", "keywords", "category", "answer_format"]:
            if col not in df.columns:
                df[col] = "markdown" if col == "answer_format" else ""
            df[col] = df[col].fillna("").astype(str)

        if len(df) == 0:
            return df, None, None, None, None, None

        df["question_norm"] = df["question"].apply(normalize_search_text)
        df["answer_norm"] = df["answer"].apply(normalize_search_text)
        df["intent_norm"] = df["intent"].apply(normalize_search_text)
        df["keywords_norm"] = df["keywords"].apply(normalize_search_text)
        df["category_norm"] = df["category"].apply(normalize_search_text)
        df["qa_text"] = (df["question"] + " / " + df["intent"] + " / " + df["keywords"] + " / " + df["category"] + " / " + df["answer"]).astype(str)
        df["qa_text_norm"] = (df["question_norm"] + " / " + df["intent_norm"] + " / " + df["keywords_norm"] + " / " + df["category_norm"] + " / " + df["answer_norm"]).astype(str)
        df["search_text_norm"] = df.apply(_weighted_search_text_norm, axis=1).astype(str)
        df["search_tokens"] = df["search_text_norm"].apply(extract_search_tokens)
        df["search_concepts"] = df["search_text_norm"].apply(extract_concepts)

        try:
            word_vectorizer = TfidfVectorizer(ngram_range=(1, 2))
            char_vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4))
            X_word = word_vectorizer.fit_transform(df["search_text_norm"])
            X_char = char_vectorizer.fit_transform(df["search_text_norm"])
        except Exception:
            return df, None, None, None, None, None

        faq_embeddings = None
        return df, word_vectorizer, X_word, char_vectorizer, X_char, faq_embeddings

    @st.cache_resource
    def load_faq_index(faq_path_str: str):
        faq_path = Path(faq_path_str)
        if not faq_path.exists():
            return _empty_index()

        try:
            df = read_csv_flexible(faq_path)
        except Exception:
            return _empty_index()
        return _build_faq_index_from_df(df)

    @st.cache_resource
    def get_faq_index_state(faq_path_str: str):
        return load_faq_index(faq_path_str)

    def reset_faq_index_runtime():
        state["df"] = None
        state["vectorizer"] = None
        state["X"] = None
        state["char_vectorizer"] = None
        state["X_char"] = None
        state["faq_embeddings"] = None

    def prime_faq_index_from_df(src_df):
        """保存直後のFAQ DataFrameをそのまま検索メモリへ反映する。"""
        built = _build_faq_index_from_df(src_df)
        state["df"] = built[0]
        state["vectorizer"] = built[1]
        state["X"] = built[2]
        state["char_vectorizer"] = built[3]
        state["X_char"] = built[4]
        state["faq_embeddings"] = built[5] if len(built) >= 6 else None
        try:
            _build_fast_lookup_maps.clear()
        except Exception:
            pass
        return built

    def ensure_faq_index_loaded():
        if (
            state["df"] is not None
            and state["vectorizer"] is not None
            and state["X"] is not None
            and state["char_vectorizer"] is not None
            and state["X_char"] is not None
        ):
            return (
                state["df"],
                state["vectorizer"],
                state["X"],
                state["char_vectorizer"],
                state["X_char"],
                state["faq_embeddings"],
            )

        local_df = None
        local_vectorizer = None
        local_X = None
        local_char_vectorizer = None
        local_X_char = None
        local_faq_embeddings = None

        try:
            loaded = get_faq_index_state(str(FAQ_PATH))
            if isinstance(loaded, tuple) and len(loaded) >= 5:
                local_df = loaded[0]
                local_vectorizer = loaded[1]
                local_X = loaded[2]
                local_char_vectorizer = loaded[3]
                local_X_char = loaded[4]
                local_faq_embeddings = loaded[5] if len(loaded) >= 6 else None
        except Exception:
            pass

        if local_df is None:
            try:
                loaded_df = load_faq_df()
            except Exception:
                loaded_df = None

            if loaded_df is not None and len(loaded_df) > 0:
                try:
                    local_df = prepare_faq_dataframe(loaded_df)
                except Exception:
                    local_df = loaded_df

                try:
                    questions = local_df["search_text_norm"].fillna("").astype(str).tolist() if "search_text_norm" in local_df.columns else local_df["question"].fillna("").astype(str).tolist()
                except Exception:
                    questions = []

                if questions:
                    try:
                        local_vectorizer = TfidfVectorizer(analyzer="word", ngram_range=(1, 2))
                        local_X = local_vectorizer.fit_transform(questions)
                    except Exception:
                        local_vectorizer = None
                        local_X = None

                    try:
                        local_char_vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4))
                        local_X_char = local_char_vectorizer.fit_transform(questions)
                    except Exception:
                        local_char_vectorizer = None
                        local_X_char = None

                    try:
                        qa_texts = local_df["qa_text_norm"].tolist() if "qa_text_norm" in local_df.columns else questions
                        local_faq_embeddings = _get_sentence_embeddings_cached(tuple(qa_texts)) if qa_texts else None
                    except Exception:
                        local_faq_embeddings = None

        state["df"] = local_df
        state["vectorizer"] = local_vectorizer
        state["X"] = local_X
        state["char_vectorizer"] = local_char_vectorizer
        state["X_char"] = local_X_char
        state["faq_embeddings"] = local_faq_embeddings

        return (
            state["df"],
            state["vectorizer"],
            state["X"],
            state["char_vectorizer"],
            state["X_char"],
            state["faq_embeddings"],
        )

    def get_faq_index_cached():
        return ensure_faq_index_loaded()

    def warmup_faq_search_index(faq_token: str = "") -> dict:
        """Pre-build FAQ search index before the first user question."""
        info = {"ok": False, "rows": 0, "word_ready": False, "char_ready": False, "fastmap_ready": False}
        try:
            local_df, local_vectorizer, local_X, local_char_vectorizer, local_X_char, _ = ensure_faq_index_loaded()
            row_count = int(len(local_df)) if local_df is not None else 0
            info["rows"] = row_count
            info["word_ready"] = local_vectorizer is not None and local_X is not None
            info["char_ready"] = local_char_vectorizer is not None and local_X_char is not None
            if row_count > 0:
                _build_fast_lookup_maps(str(faq_token or "warmup"))
                info["fastmap_ready"] = True
                try:
                    sample_query = "password login vpn"
                    if local_vectorizer is not None:
                        local_vectorizer.transform([sample_query])
                    if local_char_vectorizer is not None:
                        local_char_vectorizer.transform([sample_query])
                except Exception:
                    pass
            info["ok"] = bool(info["word_ready"] and info["char_ready"])
        except Exception as e:
            info["error"] = str(e)
        return info

    @st.cache_data(show_spinner=False, ttl=1800)
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
            i_text = normalize_search_text(str(row.get("intent", "")))
            k_text = normalize_search_text(str(row.get("keywords", "")))
            c_text = normalize_search_text(str(row.get("category", "")))
            whole = f"{q_text} {i_text} {k_text} {c_text} {a_text}"
            if any(w in whole for w in ["パスワード", "password", "pw", "リセット", "再設定", "初期化"]):
                password_rows.append(int(idx))
            for i, rule in enumerate(FASTLANE_INTENT_RULES):
                rule_name = rule.get("name", f"rule_{i}")
                faq_words = [normalize_search_text(w) for w in rule.get("faq_any", []) if w]
                if any(w and w in whole for w in faq_words):
                    rule_rows.setdefault(rule_name, []).append(int(idx))

        return {"exact": exact, "password_rows": password_rows, "rule_rows": rule_rows}

    return SimpleNamespace(
        WORD_VECTORIZER=WORD_VECTORIZER,
        CHAR_VECTORIZER=CHAR_VECTORIZER,
        SENTENCE_MODEL_NAME=SENTENCE_MODEL_NAME,
        _load_sentence_transformer_model=_load_sentence_transformer_model,
        _build_sentence_embeddings=_build_sentence_embeddings,
        _get_sentence_embeddings_cached=_get_sentence_embeddings_cached,
        _search_with_sentence_transformers=_search_with_sentence_transformers,
        _build_faq_index_from_df=_build_faq_index_from_df,
        prime_faq_index_from_df=prime_faq_index_from_df,
        load_faq_index=load_faq_index,
        get_faq_index_state=get_faq_index_state,
        reset_faq_index_runtime=reset_faq_index_runtime,
        ensure_faq_index_loaded=ensure_faq_index_loaded,
        get_faq_index_cached=get_faq_index_cached,
        warmup_faq_search_index=warmup_faq_search_index,
        _build_fast_lookup_maps=_build_fast_lookup_maps,
    )
