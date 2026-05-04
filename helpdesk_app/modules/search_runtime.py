
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
        # 「〜するための」「どれですか」などの質問文の飾りは、検索ノイズになりやすいので落とす。
        # 例: 「システム導入するための申請書はどれですか？」→「システム導入 申請書 書式」
        s = re.sub(r"(してください|お願いします|教えてください|教えて|ですか|でしょうか|ますか)", " ", s)
        s = re.sub(r"(するための|するため|のための|のため)", " ", s)
        s = re.sub(r"(どれ|どの|どちら|どれを|どのような|なに|何)", " ", s)
        s = re.sub(r"([^a-z0-9])pc([^a-z0-9])", r"\1 pc \2", f" {s} ")
        s = re.sub(r"[\/／・,、。．・:：;；\-ー_（）()\[\]{}『』「」\"'`？?！!]+", " ", s)
        s = re.sub(r"\s+", " ", s).strip()
        return s

    def extract_search_tokens(text: str) -> set[str]:
        s = normalize_search_text(text)
        if not s:
            return set()
        # 検索安全性には先頭の質問/意図/キーワードが重要。長文回答まで全て
        # トークン化すると1000件超FAQで遅くなるため上限を設ける。
        if len(s) > 4000:
            s = s[:4000]
        tokens = set()
        for part in s.split():
            part = part.strip()
            if part:
                tokens.add(part)
        for tok in re.findall(r"[a-z0-9]+|[぀-ヿ一-鿿]{2,}", s):
            tokens.add(tok)
        split_hints = [
            "できない", "つながらない", "起動しない", "ログイン", "パスワード", "電源",
            "ロック", "ロックされた", "アカウントロック", "ロック解除",
            "ディスプレイ", "モニター", "画面", "映らない", "印刷", "メール", "アカウント",
            "vpn", "wifi", "アプリ", "ソフト", "インストール", "導入", "申請",
            "申請書", "書式", "システム導入", "導入申請", "外部システム", "新規アプリケーション",
            "トライアル", "試用", "検証", "権限付与", "アクセス許可",
            # 申請書・書式の個別名称。これが無いと「書式」「申請書」だけが強くなり、
            # 別の申請書FAQを誤採用しやすくなる。
            "起案書", "念書", "承諾書", "管理簿", "アクセスログ", "ログ確認管理簿",
            "テレワーク", "テレワーク勤務", "テレワーク機器受領書",
            "情報システム責任者", "情報システム権限者", "受諾書",
            "セキュリティチェックシート", "顧客指定システム",
            "マイナンバー室", "サーバルーム", "サイトアクセス許可",
        ]
        for phrase in split_hints:
            if phrase and phrase in s:
                tokens.add(phrase)
        for tok in list(tokens)[:200]:
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

    # 「申請書」「書式」のような汎用語だけで自動回答すると誤回答になりやすい。
    # 重要なのは「起案書」「サイトアクセス許可」「システム導入」などの個別業務語なので、
    # その語が候補FAQに入っているかを強く見ます。
    GENERIC_QUERY_TERMS = {
        "申請", "申請書", "書式", "資料", "書類", "ファイル", "テンプレート",
        "どれ", "どの", "どこ", "あります", "ありますか", "ある", "教えて",
        "方法", "手順", "使用", "利用", "使う", "使い", "確認", "ため",
        "あり", "ある", "は", "の", "を", "に", "で", "と", "から", "まで",
    }

    FORM_SPECIFIC_TERMS = [
        "システム導入", "外部システム", "新規アプリケーション", "導入申請",
        "サイトアクセス許可", "url許可", "webアクセス", "アクセス許可",
        "起案書", "念書", "承諾書", "管理簿", "it資産管理表",
        "アクセスログ", "ログ確認管理簿",
        "テレワーク勤務許可申請書", "テレワーク機器受領書", "テレワーク",
        "情報システム責任者", "情報システム権限者", "受諾書",
        "セキュリティチェックシート", "顧客指定システム",
        "マイナンバー室", "サーバルーム", "アプリインストール",
        "機器貸与", "tel", "回線", "回線機器",
    ]

    # 同じ「申請書」「書式」でも業務語が違うと別FAQです。
    # ここにある語は、TF-IDFのスコアより優先して「合っている/違う」を判断します。
    BUSINESS_TERM_ALIASES = {
        "起案書": ["起案書", "起案", "稟議", "りんぎ"],
        "念書": ["念書"],
        "承諾書": ["承諾書", "同意書"],
        "システム導入": ["システム導入", "外部システム", "新規アプリケーション", "新規アプリ", "導入申請"],
        "サイトアクセス許可": ["サイトアクセス許可", "url許可", "webアクセス", "アクセス許可", "サイト閲覧", "ブロック解除", "ホワイトリスト"],
        "アプリインストール": ["アプリインストール", "ソフトインストール", "インストール依頼", "ソフト追加", "アプリ追加"],
        "アカウント権限": ["アカウント権限", "権限付与", "権限設定", "権限解除", "id作成", "id削除", "アクセス権"],
        "管理者権限": ["管理者権限", "管理者権限付与"],
        "機器貸与": ["機器貸与", "貸与", "貸出", "pc貸与", "端末貸与"],
        "回線機器": ["回線", "回線機器", "ネットワーク機器", "ルーター", "スイッチ"],
        "pc設置": ["pc/tel", "pc設置", "pc移動", "pc撤去", "電話", "電話機", "tel"],
        "セキュリティチェックシート": ["セキュリティチェックシート", "チェックシート"],
        "顧客指定システム": ["顧客指定システム", "顧客システム", "指定システム"],
        "情報システム責任者": ["情報システム責任者", "責任者指名"],
        "情報システム権限者": ["情報システム権限者", "権限者指名", "受諾書"],
        "アクセスログ": ["アクセスログ", "ログ確認管理簿", "ログ台帳"],
        "テレワーク": ["テレワーク", "在宅勤務", "勤務許可", "機器受領"],
        "マイナンバー室": ["マイナンバー室", "個人番号室"],
        "サーバルーム": ["サーバルーム", "サーバ室"],
        "ロック": ["ロック", "ロックされた", "アカウントロック", "ロック解除"],
        "bitlocker": ["bitlocker", "回復キー", "ビットロッカー"],
    }

    BUSINESS_TERM_ALIASES_NORM = {
        normalize_search_text(canonical): [normalize_search_text(a) for a in aliases if normalize_search_text(a)]
        for canonical, aliases in BUSINESS_TERM_ALIASES.items()
    }

    LOW_VALUE_SPECIFIC_TERMS = {"pc", "パソコン", "端末", "windows", "tel", "電話", "ロックされた"}

    FALSE_WORDS = {"false", "0", "no", "n", "off", "ng", "不可", "禁止", "無効", "しない", "いいえ"}
    TRUE_WORDS = {"true", "1", "yes", "y", "on", "ok", "可", "有効", "する", "はい"}

    def _safe_bool_text(value, default: bool = False) -> bool:
        s = str(value or "").strip().lower()
        if not s:
            return default
        if s in TRUE_WORDS:
            return True
        if s in FALSE_WORDS:
            return False
        return default

    def _split_rule_terms(value) -> set[str]:
        text = str(value or "").strip()
        if not text:
            return set()
        # Excelで入力しやすい区切りを許可する。
        text = re.sub(r"[\r\n、，,;；|｜/／]+", " ", text)
        terms = set()
        for part in text.split():
            n = normalize_search_text(part)
            if n:
                terms.add(n)
        return terms

    def _row_full_norm(row) -> str:
        return " ".join([
            str(row.get("question_norm", "")),
            str(row.get("intent_norm", "")),
            str(row.get("keywords_norm", "")),
            str(row.get("category_norm", "")),
            str(row.get("answer_norm", "")),
            normalize_search_text(str(row.get("required_keywords", ""))),
            normalize_search_text(str(row.get("exclude_keywords", ""))),
            normalize_search_text(str(row.get("ambiguity_keywords", ""))),
        ]).strip()

    def _business_terms_in_text(text: str) -> set[str]:
        s = normalize_search_text(text)
        found: set[str] = set()
        if not s:
            return found
        for canonical_norm, aliases_norm in BUSINESS_TERM_ALIASES_NORM.items():
            if any(alias and alias in s for alias in aliases_norm):
                found.add(canonical_norm)
        return found

    def extract_specific_search_terms(text: str) -> set[str]:
        """検索の決め手になる個別語を抽出する。

        例: 「起案書の書式はありますか？」 -> {"起案書"}
            「サイトアクセス許可の申請書はどれ？」 -> {"サイトアクセス許可", "アクセス許可"}

        「申請書」「書式」だけでは汎用語なので、自動回答の根拠にはしない。
        """
        s = normalize_search_text(text)
        if not s:
            return set()

        terms: set[str] = set()
        for term in FORM_SPECIFIC_TERMS:
            nt = normalize_search_text(term)
            if nt and nt in s:
                terms.add(nt)

        # 正規表現で拾える語も候補化。ただし汎用語・短すぎる語は除外。
        raw_tokens = set()
        for part in s.split():
            if part:
                raw_tokens.add(part.strip())
        for tok in re.findall(r"[a-z0-9]+|[぀-ヿ一-鿿]{2,}", s):
            raw_tokens.add(tok.strip())

        generic = {normalize_search_text(x) for x in GENERIC_QUERY_TERMS}
        for tok in raw_tokens:
            if not tok or tok in generic:
                continue
            # 「起案書の書式はあり」のような助詞込みの長い自然文を個別語にしてしまうと、
            # 正しいFAQまで不一致扱いになるため、業務語辞書で拾えない短い固有語だけを採用する。
            if re.search(r"(です|ます|ください|どれ|どこ|あります|あり|の|は|を|に|で)", tok) and not re.search(r"[a-z0-9]", tok):
                continue
            if len(tok) >= 2 and len(tok) <= 12:
                terms.add(tok)

        # 業務語辞書で拾えたものを最優先で返す。
        terms.update(_business_terms_in_text(s))
        return {t for t in terms if t and t not in generic and t not in LOW_VALUE_SPECIFIC_TERMS}

    def _specific_term_bonus(query_norm: str, faq_norm_all: str, question_norm: str = "") -> float:
        terms = extract_specific_search_terms(query_norm)
        if not terms:
            return 0.0
        matched = [t for t in terms if t and t in faq_norm_all]
        score = 0.0
        if matched:
            # 個別語が一致したFAQを強く優先する。
            score += 0.34 * len(matched)
            if any(t in question_norm for t in matched):
                score += 0.28
            # 「起案書」＋「書式/資料/申請書」などは、該当FAQがあれば自動回答してよい。
            if any(g in query_norm for g in ["申請書", "書式", "資料", "書類", "どこ", "どれ"]):
                score += 0.24
        else:
            # 個別語を含む質問なのに候補側に無い場合、汎用的な申請書FAQの誤回答を抑える。
            if any(g in faq_norm_all for g in ["申請書", "書式", "資料"]):
                score -= 0.30
        return float(score)

    def _safety_adjustment(query_norm: str, row, search_cfg: dict | None = None) -> tuple[float, list[str]]:
        """業務用語一致・除外条件・行別ルールでスコア補正する。

        戻り値: (加減点, 理由リスト)
        理由リストは自動回答可否判定にも使う。
        """
        cfg = search_cfg or {}
        row_text = _row_full_norm(row)
        reasons: list[str] = []
        adjust = 0.0

        specific_terms = extract_specific_search_terms(query_norm) | _business_terms_in_text(query_norm)

        if specific_terms:
            matched_specific = set()
            for t in specific_terms:
                if not t:
                    continue
                if t in row_text:
                    matched_specific.add(t)
                    continue
                # t が「起案書」などの正規業務語なら、その別名がFAQ側にあるかだけ確認する。
                # FAQ本文全体を毎回正規化すると重くなるため、row_text は既に正規化済みの文字列だけを見る。
                aliases = BUSINESS_TERM_ALIASES_NORM.get(t, [])
                if any(a and a in row_text for a in aliases):
                    matched_specific.add(t)
            if matched_specific:
                adjust += float(cfg.get("specific_term_bonus", 0.70)) * min(3, len(matched_specific))
                reasons.append("specific_match")
            else:
                # 質問に「起案書」などの個別語があるのにFAQ側に無い場合は、
                # 「書式」「申請書」だけ合っていても誤回答になりやすい。
                adjust -= float(cfg.get("specific_mismatch_penalty", 0.70))
                reasons.append("specific_mismatch")

        required_terms = set(row.get("required_terms_norm", set()) or set())
        if not required_terms:
            required_terms = _split_rule_terms(row.get("required_keywords", ""))
        if required_terms:
            if any(t and t in query_norm for t in required_terms):
                adjust += 0.25
                reasons.append("required_match")
            else:
                adjust -= float(cfg.get("required_keyword_mismatch_penalty", 0.90))
                reasons.append("required_mismatch")

        exclude_terms = set(row.get("exclude_terms_norm", set()) or set())
        if not exclude_terms:
            exclude_terms = _split_rule_terms(row.get("exclude_keywords", ""))
        if exclude_terms and any(t and t in query_norm for t in exclude_terms):
            adjust -= float(cfg.get("exclude_keyword_penalty", 1.00))
            reasons.append("exclude_match")

        ambiguity_terms = set(row.get("ambiguity_terms_norm", set()) or set())
        if not ambiguity_terms:
            ambiguity_terms = _split_rule_terms(row.get("ambiguity_keywords", ""))
        if ambiguity_terms and any(t and t in query_norm for t in ambiguity_terms):
            reasons.append("ambiguity_rule")

        if _safe_bool_text(row.get("prefer_candidate", ""), default=False):
            reasons.append("prefer_candidate")

        if str(row.get("auto_answer_allowed", "")).strip() and not _safe_bool_text(row.get("auto_answer_allowed", ""), default=True):
            reasons.append("auto_disabled")

        return float(adjust), reasons

    def _top_row_allows_auto(query_norm: str, row, search_cfg: dict | None = None) -> tuple[bool, list[str]]:
        cfg = search_cfg or {}
        _adj, reasons = _safety_adjustment(query_norm, row, cfg)
        if any(r in reasons for r in ["specific_mismatch", "required_mismatch", "exclude_match", "ambiguity_rule", "prefer_candidate", "auto_disabled"]):
            return False, reasons
        return True, reasons

    def _top_hit_is_ambiguous(query_norm: str, hits, *, answer_threshold: float, search_cfg: dict) -> bool:
        """高スコアでも自動回答せず「もしかしてこれ？」に回すべきか判定する。"""
        query_norm = normalize_search_text(query_norm)
        if not hits:
            return False
        try:
            best_score = float(hits[0][1])
        except Exception:
            return False
        if best_score < float(answer_threshold):
            return False

        top_row = hits[0][0]
        top_text = _row_full_norm(top_row)

        # 共通安全検索ガード。
        # 業務用語不一致・必須語不一致・除外語一致・候補優先・自動回答禁止がある場合は、
        # 高スコアでも自動回答せず「もしかしてこれ？」に回す。
        if bool(search_cfg.get("strict_safety_mode", True)):
            try:
                allow_auto, _reasons = _top_row_allows_auto(query_norm, top_row, search_cfg)
                if not allow_auto:
                    return True
            except Exception:
                pass

        q_concepts = extract_concepts(query_norm)
        # 「パソコンがロックされた」は、画面ロック・Windowsサインイン・AD/M365アカウントロック・BitLockerなど
        # 意味が分かれるため、十分な確信がない限り自動回答せず候補表示に回す。
        if "lock" in q_concepts and "pc_device" in q_concepts:
            account_hint_words = ["アカウント", "ログイン", "サインイン", "ad", "microsoft", "365", "パスワード"]
            has_account_hint = any(w in query_norm for w in account_hint_words)
            if not has_account_hint:
                return True
            if "lock" not in top_text:
                return True

        specific_terms = extract_specific_search_terms(query_norm)
        if specific_terms:
            top_has_specific = any(t in top_text for t in specific_terms)
            other_has_specific = False
            for row, _score in hits[1:5]:
                row_text = _row_full_norm(row)
                if any(t in row_text for t in specific_terms):
                    other_has_specific = True
                    break
            if (not top_has_specific) and other_has_specific:
                return True

        try:
            gap = best_score - float(hits[1][1]) if len(hits) >= 2 else 1.0
            min_gap = float(search_cfg.get("auto_answer_min_gap", 0.08))
            high_conf = float(search_cfg.get("high_confidence_score", 0.82))
            if best_score < high_conf and gap < min_gap:
                return True
        except Exception:
            pass
        return False

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
        # 長すぎる回答本文をそのまま検索テキストへ入れると、
        # トークン抽出とTF-IDF作成が極端に遅くなるため上限を設ける。
        if len(norm) > 1800:
            norm = norm[:1800]
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
        for col in [
            "question", "answer", "intent", "keywords", "category", "answer_format",
            "required_keywords", "exclude_keywords", "ambiguity_keywords",
            "prefer_candidate", "auto_answer_allowed",
        ]:
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
        df["required_terms_norm"] = df["required_keywords"].apply(_split_rule_terms) if "required_keywords" in df.columns else [set() for _ in range(len(df))]
        df["exclude_terms_norm"] = df["exclude_keywords"].apply(_split_rule_terms) if "exclude_keywords" in df.columns else [set() for _ in range(len(df))]
        df["ambiguity_terms_norm"] = df["ambiguity_keywords"].apply(_split_rule_terms) if "ambiguity_keywords" in df.columns else [set() for _ in range(len(df))]
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
        if any(k in query_norm for k in ["申請書", "書式"]):
            if any(k in faq_norm_all for k in ["申請書", "書式"]):
                score += 0.26
        if "システム導入" in query_norm and "システム導入" in faq_norm_all:
            score += 0.34
        if "システム導入" in query_norm and any(k in faq_norm_all for k in ["外部システム", "新規アプリケーション", "導入申請"]):
            score += 0.18
        if "システム導入" in query_norm and not any(k in query_norm for k in ["トライアル", "試用", "検討", "検証", "poc"]):
            if any(k in faq_norm_all for k in ["トライアル", "試用", "検討", "検証", "poc"]):
                score -= 0.14
        score += _specific_term_bonus(query_norm, faq_norm_all, question_norm)
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
            if "lock" in q_concepts:
                # 「パソコンがロックされた」で、起動遅延/フリーズ系FAQへ誤爆するのを防ぐ。
                if "lock" not in row_concepts:
                    penalty -= 0.55
                if "lock" in row_concepts:
                    penalty += 0.18
                if ("pc_device" in q_concepts) and ("lock" not in row_concepts):
                    penalty -= 0.25
                if ({"boot", "office_app", "browser_app", "mail_app", "display"} & row_concepts) and ("lock" not in row_concepts):
                    penalty -= 0.18
                if "pc_device" in q_concepts:
                    mobile_words = ["iphone", "ipad", "android", "スマホ", "ガラホ", "モバイル", "モバイルル", "スマートフォン", "携帯"]
                    if any(w in row_text for w in mobile_words):
                        penalty -= 3.00
                    # PCロックは、Windows/AD/M365アカウントロックの可能性が高いので候補に上げる。
                    if any(w in row_text for w in ["アカウント", "ad", "windows", "microsoft", "365", "ログイン", "サインイン"]):
                        penalty += 2.00
            if "boot" in q_concepts and not ({"office_app", "browser_app", "mail_app"} & q_concepts):
                if {"office_app", "browser_app", "mail_app"} & row_concepts and "pc_device" not in row_concepts:
                    penalty -= 0.18
            if "display" in q_concepts:
                if "display" not in row_concepts and ({"vpn", "mail", "office_app", "browser_app", "software_install"} & row_concepts):
                    penalty -= 0.35
                elif "display" not in row_concepts:
                    penalty -= 0.12
            if "system_introduction" in q_concepts:
                if "system_introduction" not in row_concepts:
                    penalty -= 0.18
                if "trial" in row_concepts and "trial" not in q_concepts:
                    # 「システム導入するための申請書」ではトライアル/検証用を優先しない
                    penalty -= 0.16
            if "application_form" in q_concepts and "application_form" not in row_concepts:
                penalty -= 0.10
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
        """TF-IDFはL2正規化済みなので、cosine_similarityより内積の方が軽い。

        SciPyの疎行列は np.asarray(sparse_matrix) だけでは数値配列にならず、
        object配列化して後続のargpartitionやmax判定が壊れる環境がある。
        必ず toarray() で dense な1次元float配列へ変換する。
        """
        try:
            prod = query_vector @ matrix.T
            if hasattr(prod, "toarray"):
                return np.asarray(prod.toarray()).ravel().astype(float)
            return np.asarray(prod).ravel().astype(float)
        except Exception:
            try:
                return np.asarray(cosine_similarity(query_vector, matrix)).flatten().astype(float)
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

    def _confidence_score(raw_score: float) -> float:
        """内部補正後スコアを、画面用の0〜0.99の一致度へ単調変換する。

        0.99で単純カットすると上位候補が全部99%に見えてしまうため、
        0.99を超えた分は90〜99%の範囲に圧縮する。
        """
        try:
            raw = max(0.0, float(raw_score))
        except Exception:
            return 0.0
        if raw <= 0.99:
            return raw
        compressed = 0.90 + (0.09 * min(1.0, (raw - 0.99) / 2.5))
        return float(min(0.99, max(0.0, compressed)))

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
                if "lock" in q_tmp_concepts:
                    for j, row in local_df.iterrows():
                        row_text = " ".join([
                            str(row.get("question_norm", "")),
                            str(row.get("intent_norm", "")),
                            str(row.get("keywords_norm", "")),
                            str(row.get("category_norm", "")),
                            str(row.get("answer_norm", "")),
                            str(row.get("search_text_norm", "")),
                        ])
                        if any(w in row_text for w in ["ロック", "ロックされた", "アカウントロック", "ロック解除", "ログイン不可"]):
                            candidate_idxs.add(int(j))
                if "application_form" in q_tmp_concepts:
                    for j, row in local_df.iterrows():
                        row_text = str(row.get("search_text_norm", ""))
                        if any(w in row_text for w in ["申請書", "書式", "申請方法"]):
                            candidate_idxs.add(int(j))
                if "system_introduction" in q_tmp_concepts:
                    for j, row in local_df.iterrows():
                        row_text = str(row.get("search_text_norm", ""))
                        if any(w in row_text for w in ["システム導入", "外部システム", "新規アプリケーション", "導入申請"]):
                            candidate_idxs.add(int(j))

                # 「起案書」「念書」「サイトアクセス許可」などの個別語がある場合は、
                # TF-IDF上位に入っていなくても候補プールへ必ず入れる。
                specific_terms = extract_specific_search_terms(query_norm)
                if specific_terms:
                    for j, row in local_df.iterrows():
                        row_text = " ".join([
                            str(row.get("question_norm", "")),
                            str(row.get("intent_norm", "")),
                            str(row.get("keywords_norm", "")),
                            str(row.get("category_norm", "")),
                            str(row.get("answer_norm", "")),
                            str(row.get("search_text_norm", "")),
                        ])
                        if any(t in row_text for t in specific_terms):
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
                        row_concepts = set(concept_values[i])
                        sims[i] += concept_bonus_max * (len(q_concepts & row_concepts) / max(1, len(q_concepts)))
                    except Exception:
                        row_concepts = set()
                else:
                    row_concepts = set()

                # 申請書・書式系は、一般的な自然文だとTF-IDFだけでは低スコアになりやすい。
                # 業務語（システム導入＋申請書）を明示的に後押しする。
                try:
                    if any(k in query_norm for k in ["申請書", "書式"]) and any(k in stxt for k in ["申請書", "書式"]):
                        sims[i] += float(search_cfg.get("application_form_bonus", 0.24))
                    if "システム導入" in query_norm and "システム導入" in stxt:
                        sims[i] += float(search_cfg.get("system_intro_bonus", 0.34))
                    if "system_introduction" in q_concepts and "system_introduction" in row_concepts:
                        sims[i] += float(search_cfg.get("system_intro_concept_bonus", 0.22))
                    if "application_form" in q_concepts and "application_form" in row_concepts:
                        sims[i] += float(search_cfg.get("application_form_concept_bonus", 0.18))
                    if "lock" in q_concepts and "lock" in row_concepts:
                        sims[i] += float(search_cfg.get("lock_concept_bonus", 0.34))
                    if "lock" in q_concepts and "lock" not in row_concepts:
                        sims[i] -= float(search_cfg.get("lock_mismatch_penalty", 0.45))
                    if "system_introduction" in q_concepts and "trial" in row_concepts and "trial" not in q_concepts:
                        sims[i] -= float(search_cfg.get("trial_mismatch_penalty", 0.18))

                    # 個別語一致補正：
                    # 例「起案書の書式はありますか？」では「書式」より「起案書」を最優先する。
                    sims[i] += _specific_term_bonus(query_norm, stxt, qn)
                except Exception:
                    pass

                if prefix and str(qn).startswith(prefix):
                    sims[i] += prefix_bonus_value
                try:
                    # 共通安全検索ガード。
                    # 業務用語不一致・除外語一致・必須語不一致をスコアに反映する。
                    safe_adj, _safe_reasons = _safety_adjustment(query_norm, local_df.iloc[i], search_cfg)
                    sims[i] += safe_adj
                except Exception:
                    pass
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
            # 画面表示・ログでは一致度として扱うため、最終スコアは0〜0.99に丸める。
            return [
                (local_df.iloc[int(i)], _confidence_score(float(sims[int(i)])))
                for i in idxs
                if float(sims[int(i)]) > 0
            ]
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
        _safety_adjustment=_safety_adjustment,
        _top_row_allows_auto=_top_row_allows_auto,
        extract_specific_search_terms=extract_specific_search_terms,
        _top_hit_is_ambiguous=_top_hit_is_ambiguous,
        try_ultrafast_answer=try_ultrafast_answer,
        retrieve_faq_cached=retrieve_faq_cached,
        retrieve_faq=retrieve_faq,
        _fastlane_direct_answer=_fastlane_direct_answer,
        llm_answer_cached=llm_answer_cached,
        build_prompt=build_prompt,
    )
