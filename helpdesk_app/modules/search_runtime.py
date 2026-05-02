
from __future__ import annotations

from types import SimpleNamespace
import re
import csv
import numpy as np


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
        split_hints = ["できない", "つながらない", "起動しない", "ログイン", "パスワード", "電源", "ディスプレイ", "モニター", "画面", "映らない", "印刷", "メール", "アカウント", "vpn", "wifi", "アプリ", "ソフト", "インストール", "導入", "申請"]
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
        repeats = max(1, min(12, int(round(weight * 2))))
        return " ".join([norm] * repeats)

    def _weighted_search_text_norm(row) -> str:
        weights = _field_weight_settings()
        parts = []
        for field in ["question", "intent", "keywords", "category", "answer"]:
            parts.append(_repeat_weighted_norm(str(row.get(field, "")), weights.get(field, 1.0)))
        return " / ".join([p for p in parts if p]).strip()

    def load_faq_df():
        try:
            return _filter_enabled_faq_rows(normalize_faq_columns(read_csv_flexible(FAQ_PATH)))
        except Exception:
            return pd.DataFrame(columns=["question", "answer", "intent", "keywords", "category", "answer_format"])

    def prepare_faq_dataframe(src_df: pd.DataFrame) -> pd.DataFrame:
        try:
            df = _filter_enabled_faq_rows(normalize_faq_columns(src_df))
        except Exception:
            df = src_df.copy() if src_df is not None else pd.DataFrame(columns=["question", "answer", "intent", "keywords", "category", "answer_format"])
        if df is None or len(df) == 0:
            return pd.DataFrame(columns=["question", "answer", "intent", "keywords", "category", "answer_format"])
        df = df.copy()
        for col in ["question", "answer", "intent", "keywords", "category", "answer_format"]:
            if col not in df.columns:
                df[col] = "markdown" if col == "answer_format" else ""
            df[col] = df[col].fillna("").astype(str)
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
        current_search_settings=current_search_settings,
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
        i = normalize_search_text(str(row.get("intent", "")))
        k = normalize_search_text(str(row.get("keywords", "")))
        c = normalize_search_text(str(row.get("category", "")))
        whole = f"{q} {i} {k} {c} {a}"
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
        intent_norm = str(row.get("intent_norm", ""))
        keywords_norm = str(row.get("keywords_norm", ""))
        category_norm = str(row.get("category_norm", ""))
        faq_norm_all = f"{question_norm} {intent_norm} {keywords_norm} {category_norm} {answer_norm}"
        search_tokens = set(row.get("search_tokens", [])) if hasattr(row, "get") else set()
        score = 0.0
        if question_norm == query_norm:
            score += 1.2
        if query_norm and (query_norm in question_norm or question_norm in query_norm):
            score += 0.45
        overlap = len(q_tokens & search_tokens) / max(1, len(q_tokens)) if q_tokens else 0.0
        score += overlap * 0.55
        if "パスワード" in query_norm and "パスワード" in faq_norm_all:
            score += 0.25
        if any(k in query_norm for k in ["忘れ", "わから", "リセット", "再設定", "失念"]):
            if any(k in faq_norm_all for k in ["リセット", "再設定", "初期化", "忘れ"]):
                score += 0.22
        if any(k in query_norm for k in ["アプリ", "アプリケーション", "ソフト", "ソフトウェア", "ツール"]):
            if any(k in faq_norm_all for k in ["アプリ", "アプリケーション", "ソフト", "ソフトウェア", "ツール"]):
                score += 0.18
        if any(k in query_norm for k in ["インストール", "導入", "追加", "申請"]):
            if any(k in faq_norm_all for k in ["インストール", "導入", "追加", "申請"]):
                score += 0.20
        if any(k in query_norm for k in ["ディスプレイ", "モニター", "モニタ", "画面"]):
            if any(k in faq_norm_all for k in ["ディスプレイ", "モニター", "モニタ", "画面", "外部ディスプレイ"]):
                score += 0.34
        if any(k in query_norm for k in ["映らない", "表示されない", "真っ暗", "ブラックアウト", "入らない"]):
            if any(k in faq_norm_all for k in ["映らない", "表示されない", "真っ暗", "画面", "ディスプレイ", "モニター"]):
                score += 0.28
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
            row_i = normalize_search_text(str(row.get("intent", "")))
            row_k = normalize_search_text(str(row.get("keywords", "")))
            row_c = normalize_search_text(str(row.get("category", "")))
            row_text = f"{row_q} / {row_i} / {row_k} / {row_c}"
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
            if "display" in q_concepts:
                if "display" not in row_concepts and ({"vpn", "mail", "office_app", "browser_app", "software_install"} & row_concepts):
                    penalty -= 0.35
                elif "display" not in row_concepts:
                    penalty -= 0.12
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

    def _sparse_tfidf_scores(query_vector, matrix):
        """TF-IDFはL2正規化済みなので、cosine_similarityより内積の方が軽い。"""
        try:
            return np.asarray(query_vector @ matrix.T).ravel()
        except Exception:
            try:
                return cosine_similarity(query_vector, matrix).flatten()
            except Exception:
                return np.array([], dtype=float)

    def _top_indices(scores, count: int):
        """全件sortを避け、上位候補だけを高速抽出する。"""
        if scores is None or len(scores) == 0 or count <= 0:
            return np.array([], dtype=int)
        n = len(scores)
        count = min(int(count), n)
        if count >= n:
            return np.argsort(scores)[::-1]
        idx = np.argpartition(scores, -count)[-count:]
        return idx[np.argsort(scores[idx])[::-1]]

    @st.cache_data(show_spinner=False, ttl=60)
    def _load_candidate_learning_rows(cache_key: str = "candidate_learning"):
        """候補クリック学習ログを軽量に読む。

        優先順位:
        1. SQLite: 本番用の永続学習ログ
        2. CSV: 既存ログ・確認用ログとの互換
        """
        rows = []

        # 1) SQLiteから取得（再起動後も残る本命の学習ログ）
        try:
            from helpdesk_app.faq_db import load_candidate_learning_from_db
            rows.extend(load_candidate_learning_from_db(FAQ_PATH, limit=500))
        except Exception:
            pass

        # 2) CSVからも取得（過去ログ互換・ダウンロード用）
        seen_paths = set()
        candidate_dirs = [Path("logs")]
        try:
            candidate_dirs.append(Path(FAQ_PATH).parent / "logs")
            candidate_dirs.append(Path(FAQ_PATH).parent.parent / "logs")
        except Exception:
            pass
        for log_dir in candidate_dirs:
            try:
                if not log_dir.exists() or not log_dir.is_dir():
                    continue
                files = sorted(log_dir.glob("candidate_learning_*.csv"), reverse=True)[:14]
                for path in files:
                    key = str(path.resolve())
                    if key in seen_paths:
                        continue
                    seen_paths.add(key)
                    with path.open("r", encoding="utf-8-sig", newline="") as f:
                        for row in csv.DictReader(f):
                            uq = str(row.get("user_question", "")).strip()
                            sq = str(row.get("selected_question", "")).strip()
                            fid = str(row.get("selected_faq_id", "")).strip()
                            if uq and (sq or fid):
                                rows.append({
                                    "user_question": uq,
                                    "selected_question": sq,
                                    "selected_faq_id": fid,
                                    "source": "csv",
                                })
            except Exception:
                continue
        return rows[-800:]

    def _iter_candidate_learning_events():
        events = []
        try:
            events.extend(list(st.session_state.get("faq_candidate_learning_events", [])))
        except Exception:
            pass
        try:
            events.extend(_load_candidate_learning_rows())
        except Exception:
            pass
        return events[-600:]

    def _apply_candidate_learning_bonus(*, query_norm: str, local_df, sims, candidate_idxs: set[int]) -> None:
        """候補クリック学習を安全に反映する。

        学習は「正解を決め打ちする機能」ではなく、順位を少しだけ後押しする機能にする。
        1回の誤クリックで高スコア化しないよう、元スコア・概念一致・上限を必ず確認する。
        """
        if not query_norm or local_df is None or sims is None:
            return
        try:
            n_rows = int(len(local_df))
            if n_rows <= 0:
                return

            question_norm_arr = local_df["question_norm"].fillna("").astype(str).to_numpy() if "question_norm" in local_df.columns else np.array([""] * n_rows)
            faq_id_arr = local_df["faq_id"].fillna("").astype(str).to_numpy() if "faq_id" in local_df.columns else np.array([""] * n_rows)
            concept_values = local_df["search_concepts"].tolist() if "search_concepts" in local_df.columns else [[] for _ in range(n_rows)]
            q_concepts = extract_concepts(query_norm)

            # セッションログとCSVログの二重カウントを避ける
            # key: (正規化済みユーザー質問, FAQ_ID or 正規化済み質問)
            seen_event_keys: set[tuple[str, str]] = set()
            boost_counts: dict[int, int] = {}

            for ev in _iter_candidate_learning_events():
                ev_query = normalize_search_text(ev.get("user_question", ""))
                if not ev_query or ev_query != query_norm:
                    continue

                selected_id = str(ev.get("selected_faq_id", "")).strip()
                selected_q_norm = normalize_search_text(ev.get("selected_question", ""))
                selected_key = selected_id or selected_q_norm
                if not selected_key:
                    continue
                event_key = (ev_query, selected_key)
                if event_key in seen_event_keys:
                    continue
                seen_event_keys.add(event_key)

                for i in range(n_rows):
                    if selected_id and selected_id == str(faq_id_arr[i]).strip():
                        boost_counts[i] = boost_counts.get(i, 0) + 1
                        break
                    if selected_q_norm and selected_q_norm == str(question_norm_arr[i]):
                        boost_counts[i] = boost_counts.get(i, 0) + 1
                        break

            if not boost_counts:
                return

            # 学習補正は弱めにする。元スコアが低すぎる候補は補正しない。
            min_base_score = 0.18
            per_click_bonus = 0.02
            max_learning_bonus = 0.08

            for i, count in boost_counts.items():
                if i < 0 or i >= n_rows:
                    continue

                base_score = float(sims[int(i)])
                try:
                    row_concepts = set(concept_values[int(i)] or [])
                except Exception:
                    row_concepts = set()
                concept_overlap = bool(q_concepts and row_concepts and (set(q_concepts) & row_concepts))

                # 元スコアが低く、概念も合っていないものは誤学習として扱う
                if base_score < min_base_score and not concept_overlap:
                    continue

                candidate_idxs.add(int(i))
                sims[int(i)] += min(max_learning_bonus, per_click_bonus * max(1, int(count)))
        except Exception:
            return

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

            search_cfg = current_search_settings()
            top_k = max(1, int(search_cfg.get("top_k", 3)))
            n_rows = int(len(local_df))

            qv_word = local_vectorizer.transform([query_norm])
            qv_char = local_char_vectorizer.transform([query_norm])
            sims_word = _sparse_tfidf_scores(qv_word, local_X)
            sims_char = _sparse_tfidf_scores(qv_char, local_X_char)
            if sims_word.size == 0 or sims_char.size == 0:
                return []

            sims = (sims_word * float(search_cfg.get("word_weight", 0.54))) + (sims_char * float(search_cfg.get("char_weight", 0.46)))

            # 精度補正は全件にapplyしない。TF-IDF上位＋完全一致候補だけに絞って補正する。
            candidate_count = min(n_rows, max(top_k * 12, int(search_cfg.get("candidate_pool", 80))))
            candidate_idxs = set(int(i) for i in _top_indices(sims, candidate_count))

            try:
                maps = faq_index_ctx._build_fast_lookup_maps(_faq_cache_token())
                candidate_idxs.update(int(i) for i in maps.get("exact", {}).get(query_norm, []))
            except Exception:
                pass

            # ユーザー語正規化で拾える領域は、該当領域のFAQを候補プールに必ず入れる
            # 例: 「モニター死んだ」→「ディスプレイ 映らない 不具合」
            try:
                q_tmp_concepts = extract_concepts(query_norm)
                if "display" in q_tmp_concepts:
                    for j, row in local_df.iterrows():
                        row_text = str(row.get("search_text_norm", ""))
                        if any(w in row_text for w in ["ディスプレイ", "モニター", "モニタ", "画面", "映らない", "表示されない"]):
                            candidate_idxs.add(int(j))
            except Exception:
                pass

            _apply_candidate_learning_bonus(query_norm=query_norm, local_df=local_df, sims=sims, candidate_idxs=candidate_idxs)

            q_tokens = extract_search_tokens(query_norm)
            q_concepts = extract_concepts(query_norm)
            question_norm_arr = local_df["question_norm"].fillna("").astype(str).to_numpy() if "question_norm" in local_df.columns else np.array([""] * n_rows)
            search_text_arr = local_df["search_text_norm"].fillna("").astype(str).to_numpy() if "search_text_norm" in local_df.columns else np.array([""] * n_rows)
            token_values = local_df["search_tokens"].tolist() if "search_tokens" in local_df.columns else [[] for _ in range(n_rows)]
            concept_values = local_df["search_concepts"].tolist() if "search_concepts" in local_df.columns else [[] for _ in range(n_rows)]

            exact_bonus_value = float(search_cfg.get("exact_bonus", 0.28))
            contains_bonus_value = float(search_cfg.get("contains_bonus", 0.14))
            token_bonus_max = float(search_cfg.get("token_bonus_max", 0.24))
            concept_bonus_max = float(search_cfg.get("concept_bonus_max", 0.24))
            prefix_bonus_value = float(search_cfg.get("prefix_bonus", 0.07))
            prefix = query_norm[: min(8, len(query_norm))]

            for i in candidate_idxs:
                if i < 0 or i >= n_rows:
                    continue
                qn = question_norm_arr[i]
                stxt = search_text_arr[i]
                if qn == query_norm:
                    sims[i] += exact_bonus_value
                if query_norm and (query_norm in stxt or stxt in query_norm):
                    sims[i] += contains_bonus_value
                if q_tokens:
                    try:
                        sims[i] += token_bonus_max * (len(q_tokens & set(token_values[i])) / max(1, len(q_tokens)))
                    except Exception:
                        pass
                if q_concepts:
                    try:
                        sims[i] += concept_bonus_max * (len(q_concepts & set(concept_values[i])) / max(1, len(q_concepts)))
                    except Exception:
                        pass
                if prefix and str(qn).startswith(prefix):
                    sims[i] += prefix_bonus_value
                try:
                    sims[i] += _domain_penalty(query_norm, local_df.iloc[i])
                except Exception:
                    pass

            is_fastlane = _is_fastlane_query_text(query_norm)
            preliminary_top = float(np.max(sims)) if len(sims) else 0.0
            query_len = len(query_norm)
            need_semantic = (
                bool(search_cfg.get("semantic_enabled", True))
                and (not is_fastlane or not bool(search_cfg.get("semantic_skip_fastlane", True)))
                and SENTENCE_TRANSFORMERS_AVAILABLE
                and query_len >= int(search_cfg.get("semantic_min_query_len", 8))
                and float(search_cfg.get("semantic_trigger_min", 0.24)) <= preliminary_top <= float(search_cfg.get("semantic_trigger_max", 0.48))
            )
            if need_semantic:
                sem_count = min(int(search_cfg.get("semantic_candidate_count", 8)), len(sims))
                sem_candidate_idxs = _top_indices(sims, sem_count)
                if local_faq_embeddings is None and local_df is not None and len(local_df) > 0 and "qa_text_norm" in local_df.columns:
                    try:
                        local_faq_embeddings = faq_index_ctx._get_sentence_embeddings_cached(tuple(local_df["qa_text_norm"].tolist()))
                    except Exception:
                        local_faq_embeddings = None
                sims_sem = faq_index_ctx._search_with_sentence_transformers(query_norm, local_faq_embeddings)
                if sims_sem is not None and len(sims_sem) == len(sims):
                    sem_arr = pd.Series(sims_sem).fillna(0.0).to_numpy()
                    sims[sem_candidate_idxs] = sims[sem_candidate_idxs] + (sem_arr[sem_candidate_idxs] * float(search_cfg.get("semantic_boost", 0.28)))

            idxs = _top_indices(sims, top_k)
            return [(local_df.iloc[int(i)], float(sims[int(i)])) for i in idxs if float(sims[int(i)]) > 0]
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
            intent = str(row.get("intent", ""))
            keywords = str(row.get("keywords", ""))
            category = str(row.get("category", ""))
            meta = " / ".join([x for x in [f"カテゴリ:{category}" if category else "", f"意図:{intent}" if intent else "", f"言い換え:{keywords}" if keywords else ""] if x])
            context_parts.append(f"\n[FAQ{i}]\nQ:{q}\n{meta}\nA:{a}\n")
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
