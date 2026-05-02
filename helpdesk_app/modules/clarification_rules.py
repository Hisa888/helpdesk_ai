from __future__ import annotations

import re

VAGUE_WORDS = [
    "できない", "つながらない", "繋がらない", "開かない", "動かない", "見れない", "見られない",
    "使えない", "エラー", "遅い", "だめ", "不具合", "おかしい", "失敗", "困っている",
]

TARGET_HINTS = [
    "vpn", "outlook", "teams", "slack", "excel", "word", "printer", "pc", "wifi", "wi-fi",
    "メール", "印刷", "プリンタ", "ログイン", "パスワード", "端末", "社内", "mfa", "onedrive",
    "sharepoint", "ブラウザ", "ネットワーク", "office",
    "ソフト", "ソフトウェア", "アプリ", "アプリケーション", "インストール", "導入",
]

# これだけだと「何をしたいのか」が不足しやすい単語。
# 例: 「アプリ」だけで自動回答すると、インストールなのか、起動エラーなのか、削除なのか判定できない。
GENERIC_TARGET_WORDS = [
    "アプリ", "アプリケーション", "ソフト", "ソフトウェア", "ツール", "システム", "サービス",
    "pc", "パソコン", "端末", "メール", "outlook", "vpn", "プリンタ", "印刷",
    "excel", "word", "office", "teams", "ブラウザ", "ネットワーク", "wifi", "wi-fi",
]

# これだけだと「対象」が不足しやすい単語。
# ただし、追加質問の回答として入力された場合は query_flow_runtime 側で skip_clarification=True になるため、
# 「アプリ」→「インストール」は結合後に検索される。
GENERIC_ACTION_WORDS = [
    "インストール", "導入", "追加", "申請", "設定", "変更", "削除", "更新", "利用", "使いたい",
]

ACTION_OR_PROBLEM_WORDS = [
    "インストール", "導入", "追加", "申請", "設定", "変更", "削除", "更新", "利用", "使いたい", "したい",
    "できない", "できません", "使えない", "つながらない", "繋がらない", "開かない", "動かない",
    "見れない", "見られない", "エラー", "失敗", "遅い", "忘れ", "ロック", "起動", "表示", "印刷",
]

QUESTION_WORDS = ["いつ", "どこ", "どの", "なに", "何", "誰", "どうして"]


def _normalize(text: str) -> str:
    return re.sub(r"\s+", "", str(text or "").lower())


def has_vague_word(question: str) -> bool:
    q = _normalize(question)
    return any(word in q for word in VAGUE_WORDS)


def has_target_hint(question: str) -> bool:
    q = _normalize(question)
    return any(word in q for word in TARGET_HINTS)


def is_too_short(question: str, min_len: int = 10) -> bool:
    q = _normalize(question)
    return len(q) < min_len


def looks_like_question_word_only(question: str) -> bool:
    q = _normalize(question)
    return any(q.startswith(word) for word in QUESTION_WORDS) and len(q) <= 12


def looks_like_generic_target_only(question: str) -> bool:
    """対象名だけで、操作・症状が不足している質問を検出する。"""
    q = _normalize(question)
    if not q:
        return False
    has_generic_target = any(word in q for word in GENERIC_TARGET_WORDS)
    if not has_generic_target:
        return False
    has_action_or_problem = any(word in q for word in ACTION_OR_PROBLEM_WORDS)
    if has_action_or_problem:
        return False
    # 「アプリ」「メール」「VPN」などの単語だけ、または非常に短い対象名だけなら追加質問へ回す。
    return len(q) <= 12


def looks_like_generic_action_only(question: str) -> bool:
    """操作語だけで、対象システム・対象アプリが不足している質問を検出する。"""
    q = _normalize(question)
    if not q:
        return False
    has_generic_action = any(word in q for word in GENERIC_ACTION_WORDS)
    if not has_generic_action:
        return False
    has_target = any(word in q for word in GENERIC_TARGET_WORDS)
    if has_target:
        return False
    return len(q) <= 12


def should_request_clarification(*, question: str, best_score: float, answer_threshold: float, suggest_threshold: float) -> tuple[bool, str]:
    q = str(question or "").strip()
    if not q:
        return False, "empty"

    # 重要: 強いFAQ一致があっても、「アプリ」などの対象名だけでは回答を確定しない。
    # ここを best_score 判定より前に置くことで、「アプリ」→即回答を防ぐ。
    if looks_like_generic_target_only(q):
        return True, "generic_target_only"
    if looks_like_generic_action_only(q):
        return True, "generic_action_only"

    if best_score >= answer_threshold:
        return False, "strong_match"

    too_short = is_too_short(q)
    vague = has_vague_word(q)
    target = has_target_hint(q)
    qword_only = looks_like_question_word_only(q)

    if qword_only:
        return True, "question_word_only"
    if too_short and not target:
        return True, "short_without_target"
    if vague and best_score < max(suggest_threshold, 0.28):
        return True, "vague_low_score"
    if vague and too_short:
        return True, "vague_and_short"
    return False, "clear_enough"
