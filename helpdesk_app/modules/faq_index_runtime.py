
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

    @st.cache_resource
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
        df["search_text_norm"] = (
            df["question_norm"].fillna("").astype(str)
            + " / "
            + df["category"].fillna("").astype(str).apply(normalize_search_text)
        ).astype(str)
        df["search_tokens"] = df["search_text_norm"].apply(extract_search_tokens)
        df["search_concepts"] = df["search_text_norm"].apply(extract_concepts)

        try:
            word_vectorizer = WORD_VECTORIZER
            char_vectorizer = CHAR_VECTORIZER
            X_word = word_vectorizer.fit_transform(df["search_text_norm"])
            X_char = char_vectorizer.fit_transform(df["search_text_norm"])
        except Exception:
            return df, None, None, None, None, None

        faq_embeddings = None
        return df, word_vectorizer, X_word, char_vectorizer, X_char, faq_embeddings

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
                    questions = local_df["question_norm"].fillna("").astype(str).tolist() if "question_norm" in local_df.columns else local_df["question"].fillna("").astype(str).tolist()
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
            whole = f"{q_text} {a_text}"
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
        load_faq_index=load_faq_index,
        get_faq_index_state=get_faq_index_state,
        reset_faq_index_runtime=reset_faq_index_runtime,
        ensure_faq_index_loaded=ensure_faq_index_loaded,
        get_faq_index_cached=get_faq_index_cached,
        _build_fast_lookup_maps=_build_fast_lookup_maps,
    )
