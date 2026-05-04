from __future__ import annotations

from types import SimpleNamespace

from helpdesk_app.search_engine import create_faq_index_runtime, create_search_runtime


FULLWIDTH_TRANS = str.maketrans({
    "０": "0", "１": "1", "２": "2", "３": "3", "４": "4",
    "５": "5", "６": "6", "７": "7", "８": "8", "９": "9",
    "ａ": "a", "ｂ": "b", "ｃ": "c", "ｄ": "d", "ｅ": "e", "ｆ": "f", "ｇ": "g",
    "ｈ": "h", "ｉ": "i", "ｊ": "j", "ｋ": "k", "ｌ": "l", "ｍ": "m", "ｎ": "n",
    "ｏ": "o", "ｐ": "p", "ｑ": "q", "ｒ": "r", "ｓ": "s", "ｔ": "t", "ｕ": "u",
    "ｖ": "v", "ｗ": "w", "ｘ": "x", "ｙ": "y", "ｚ": "z",
    "Ａ": "a", "Ｂ": "b", "Ｃ": "c", "Ｄ": "d", "Ｅ": "e", "Ｆ": "f", "Ｇ": "g",
    "Ｈ": "h", "Ｉ": "i", "Ｊ": "j", "Ｋ": "k", "Ｌ": "l", "Ｍ": "m", "Ｎ": "n",
    "Ｏ": "o", "Ｐ": "p", "Ｑ": "q", "Ｒ": "r", "Ｓ": "s", "Ｔ": "t", "Ｕ": "u",
    "Ｖ": "v", "Ｗ": "w", "Ｘ": "x", "Ｙ": "y", "Ｚ": "z",
})

CANONICAL_PATTERNS = [
    (r"デスクトップパソコン|デスクトップｐｃ|desktop\s*pc", "デスクトップpc"),
    (r"ノートパソコン|ラップトップ", "ノートpc"),
    (r"パーソナルコンピュータ|パソコン|ピーシー|ｐｃ|pc端末", "pc"),
    (r"コンピューター", "コンピュータ"),
    (r"無線lan|wi-?fi|wifi|ワイファイ", "wifi"),
    (r"ｖｐｎ|ぶいぴーえぬ|vpn接続", "vpn"),
    (r"サインイン", "ログイン"),
    (r"サインアウト", "ログアウト"),
    (r"パスコード|passcode", "パスワード"),
    (r"pw", "パスワード"),
    (r"パスワードを忘れました|パスワードを忘れた|パスワード忘れた|パスワードがわからない|password forgotten|forgot password", "パスワード リセット"),
    (r"パスワード再発行|パスワード初期化", "パスワード リセット"),
    (r"立ち上がらない|起ち上がらない|立ちあがらない|起ちあがらない", "起動しない"),
    (r"電源がつかない|電源が付かない|電源がはいらない", "電源が入らない"),
    # ユーザー語・スラングをFAQにヒットしやすい正式表現へ寄せる
    (r"モニター|モニタ|画面|ディスプレー", "ディスプレイ"),
    (r"真っ暗|まっくら|黒い|ブラックアウト|映らん|うつらない|表示されない|表示しない", "映らない"),
    (r"死んだ|壊れた|壊れてる|故障した|故障|反応しない", "映らない 不具合"),
    (r"つかない|付かない|点かない", "入らない"),
    (r"ディスプレイ\s*入らない|ディスプレイ\s*映らない 不具合|ディスプレイ\s*映らない", "ディスプレイ 映らない"),
    (r"ログイン出来ない|ログインできません", "ログインできない"),
    (r"接続できない|接続できません|接続出来ない|接続出来ません|接続しない|接続されない|つながりません|繋がりません|繋がらない|繋げない|つなげない", "つながらない"),
    (r"利用できない|使用できない", "使えない"),
    (r"開けない", "起動しない"),
    (r"印字できない|プリントできない", "印刷できない"),
    (r"メール送れない", "メールが送信できない"),
    (r"メール受け取れない", "メールが受信できない"),
    (r"認証に失敗|認証エラー", "認証できない"),
    (r"ロックされました|ロックされた|凍結された|ロックしてしまった|ロックがかかった", "ロックされた"),
    (r"pcがロック|pc ロック|パソコンがロック|パソコン ロック|端末がロック|端末 ロック", "pc ロックされた"),
    # 申請書・書式系の自然文をFAQ検索しやすい語へ寄せる
    (r"システムを?導入するための|システムを?導入したい|システム導入したい", "システム導入"),
    (r"申請書はどれですか|申請書はどれ|申請書はどの書式|どの申請書|どれの申請書", "申請書 書式"),
    (r"どの書式を使えばいい|どの書式を使用|どの書式ですか|書式はどれ", "書式"),
]

CONCEPT_ALIASES = {
    "vpn": ["vpn", "リモートアクセス", "社外接続"],
    "network": ["ネットワーク", "wifi", "lan", "通信", "internet", "インターネット"],
    "login": ["ログイン", "サインイン", "認証", "アカウント"],
    "password": ["パスワード", "password", "pw", "リセット", "再設定", "初期化"],
    "boot": ["起動", "立ち上が", "立上", "電源", "シャットダウン", "再起動"],
    "display": ["ディスプレイ", "モニター", "モニタ", "画面", "映らない", "真っ暗", "ブラックアウト", "表示されない"],
    "mail": ["メール", "outlook", "受信", "送信"],
    "print": ["印刷", "プリンタ", "printer", "print"],
    "lock": ["ロック", "ロックされた", "アカウントロック", "凍結", "無効", "停止"],
    "error": ["エラー", "失敗", "不具合", "異常", "障害"],
    "cannot": ["できない", "できません", "使えない", "つながらない", "入らない", "起動しない"],
    "pc_device": ["pc", "パソコン", "ノートpc", "デスクトップpc", "端末", "windows"],
    "office_app": ["excel", "word", "powerpoint", "access", "onenote", "office"],
    "browser_app": ["chrome", "edge", "firefox", "ブラウザ", "web", "sso"],
    "mail_app": ["outlook", "exchange", "共有メール", "メーリングリスト", "メールアプリ"],
    "software_install": ["アプリ", "アプリケーション", "ソフト", "ソフトウェア", "インストール", "導入", "追加", "利用したい", "使いたい"],
    "application_form": ["申請書", "書式", "申請方法", "申請", "どの書式", "どれ"],
    "system_introduction": ["システム導入", "外部システム", "新規アプリケーション", "導入申請", "新規アプリ"],
    "trial": ["トライアル", "試用", "お試し", "検証", "検討", "poc"],
}

FASTLANE_INTENT_RULES = [
    {
        "name": "password_reset",
        "query_any": ["パスワード", "password", "pw", "認証情報"],
        "query_any2": ["忘れ", "わから", "不明", "リセット", "再設定", "変更", "思い出せ", "失念"],
        "faq_any": ["パスワード", "password", "pw", "リセット", "再設定", "初期化"],
    },
    {
        "name": "account_lock",
        "query_any": ["アカウント", "ログイン", "認証"],
        "query_any2": ["ロック", "凍結", "無効", "停止"],
        "faq_any": ["ロック", "凍結", "無効", "停止", "アカウント"],
    },
    {
        "name": "display_no_signal",
        "query_any": ["ディスプレイ", "モニター", "モニタ", "画面"],
        "query_any2": ["映らない", "真っ暗", "黒い", "ブラックアウト", "死んだ", "壊れた", "表示されない", "つかない", "付かない"],
        "faq_any": ["ディスプレイ", "モニター", "モニタ", "画面", "映らない", "表示されない", "外部ディスプレイ"],
    },
    {
        "name": "vpn_connect",
        "query_any": ["vpn", "リモートアクセス", "社外接続"],
        "query_any2": ["つながらない", "接続", "入らない", "失敗", "できない"],
        "faq_any": ["vpn", "リモートアクセス", "接続"],
    },
    {
        "name": "software_install",
        "query_any": ["アプリ", "アプリケーション", "ソフト", "ソフトウェア", "ツール"],
        "query_any2": ["インストール", "導入", "追加", "利用したい", "使いたい", "申請"],
        "faq_any": ["アプリ", "アプリケーション", "ソフト", "ソフトウェア", "インストール", "導入", "追加", "申請"],
    },
    {
        "name": "system_introduction_form",
        "query_any": ["システム導入", "外部システム", "新規アプリケーション", "導入"],
        "query_any2": ["申請書", "書式", "どれ", "どの", "申請"],
        "faq_any": ["システム導入", "外部システム", "新規アプリケーション", "導入申請", "申請書", "書式"],
    },
]


def build_nohit_template() -> str:
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


def create_faq_answer_flow_runtime(
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
    faq_cache_token_getter,
    SENTENCE_TRANSFORMERS_AVAILABLE,
    SentenceTransformer,
):
    search_ctx = create_search_runtime(
        st=st,
        pd=pd,
        Path=Path,
        FAQ_PATH=FAQ_PATH,
        TfidfVectorizer=TfidfVectorizer,
        cosine_similarity=cosine_similarity,
        normalize_faq_columns=normalize_faq_columns,
        read_csv_flexible=read_csv_flexible,
        current_search_settings=current_search_settings,
        llm_chat=llm_chat,
        _faq_cache_token=faq_cache_token_getter,
        SENTENCE_TRANSFORMERS_AVAILABLE=SENTENCE_TRANSFORMERS_AVAILABLE,
        SentenceTransformer=SentenceTransformer,
        FULLWIDTH_TRANS=FULLWIDTH_TRANS,
        CANONICAL_PATTERNS=CANONICAL_PATTERNS,
        CONCEPT_ALIASES=CONCEPT_ALIASES,
        FASTLANE_INTENT_RULES=FASTLANE_INTENT_RULES,
        create_faq_index_runtime=create_faq_index_runtime,
    )

    faq_index_ctx = search_ctx.faq_index_ctx

    return SimpleNamespace(
        search_ctx=search_ctx,
        faq_index_ctx=faq_index_ctx,
        FULLWIDTH_TRANS=FULLWIDTH_TRANS,
        CANONICAL_PATTERNS=CANONICAL_PATTERNS,
        CONCEPT_ALIASES=CONCEPT_ALIASES,
        FASTLANE_INTENT_RULES=FASTLANE_INTENT_RULES,
        normalize_search_text=search_ctx.normalize_search_text,
        extract_search_tokens=search_ctx.extract_search_tokens,
        extract_concepts=search_ctx.extract_concepts,
        load_faq_df=search_ctx.load_faq_df,
        prepare_faq_dataframe=search_ctx.prepare_faq_dataframe,
        _contains_any=search_ctx._contains_any,
        _faq_row_matches_words=search_ctx._faq_row_matches_words,
        _is_fastlane_query_text=search_ctx._is_fastlane_query_text,
        _score_fast_candidate=search_ctx._score_fast_candidate,
        _domain_penalty=search_ctx._domain_penalty,
        extract_specific_search_terms=getattr(search_ctx, "extract_specific_search_terms", None),
        _top_hit_is_ambiguous=getattr(search_ctx, "_top_hit_is_ambiguous", None),
        try_ultrafast_answer=search_ctx.try_ultrafast_answer,
        retrieve_faq_cached=search_ctx.retrieve_faq_cached,
        retrieve_faq=search_ctx.retrieve_faq,
        _fastlane_direct_answer=search_ctx._fastlane_direct_answer,
        llm_answer_cached=search_ctx.llm_answer_cached,
        build_prompt=search_ctx.build_prompt,
        WORD_VECTORIZER=faq_index_ctx.WORD_VECTORIZER,
        CHAR_VECTORIZER=faq_index_ctx.CHAR_VECTORIZER,
        SENTENCE_MODEL_NAME=faq_index_ctx.SENTENCE_MODEL_NAME,
        _load_sentence_transformer_model=faq_index_ctx._load_sentence_transformer_model,
        _build_sentence_embeddings=faq_index_ctx._build_sentence_embeddings,
        _get_sentence_embeddings_cached=faq_index_ctx._get_sentence_embeddings_cached,
        _search_with_sentence_transformers=faq_index_ctx._search_with_sentence_transformers,
        prime_faq_index_from_df=faq_index_ctx.prime_faq_index_from_df,
        load_faq_index=faq_index_ctx.load_faq_index,
        get_faq_index_state=faq_index_ctx.get_faq_index_state,
        reset_faq_index_runtime=faq_index_ctx.reset_faq_index_runtime,
        ensure_faq_index_loaded=faq_index_ctx.ensure_faq_index_loaded,
        get_faq_index_cached=faq_index_ctx.get_faq_index_cached,
        warmup_faq_search_index=faq_index_ctx.warmup_faq_search_index,
        _build_fast_lookup_maps=faq_index_ctx._build_fast_lookup_maps,
        nohit_template=build_nohit_template,
    )
