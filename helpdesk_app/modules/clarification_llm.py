from __future__ import annotations


def _fallback_prompt(user_q: str) -> str:
    q = str(user_q or "").lower()
    if any(x in q for x in ["アプリ", "アプリケーション", "ソフト", "ソフトウェア", "ツール"]):
        return "状況を特定するため、次を教えてください。\n- インストール、起動できない、更新、削除など何をしたいですか？\n- 対象のアプリ名やソフト名\n- エラーメッセージや申請理由があれば教えてください"
    if "vpn" in q:
        return "状況を特定するため、次を教えてください。\n- 社内と社外のどちらから接続していますか？\n- いつから発生していますか？\n- エラーメッセージは表示されていますか？"
    if "outlook" in q or "メール" in q:
        return "状況を特定するため、次を教えてください。\n- 送信・受信・起動のどれで困っていますか？\n- PCとスマホのどちらですか？\n- エラーメッセージは表示されていますか？"
    if "印刷" in q or "プリンタ" in q:
        return "状況を特定するため、次を教えてください。\n- プリンタ名を教えてください。\n- 他のファイルでも同じですか？\n- エラーメッセージは表示されていますか？"
    return "状況を特定するため、次を教えてください。\n- 対象のシステム名や機器名\n- いつから発生しているか\n- エラーメッセージや具体的な症状"


def build_clarification_messages(user_q: str):
    prompt = f"""
あなたは社内ヘルプデスクAIです。
ユーザーの質問は情報が不足しており、そのままでは原因特定が難しい可能性があります。
問題特定のために、追加で確認したいことを日本語で作成してください。

条件:
- 丁寧で短く
- 回答はまだしない
- 確認項目は最大3つ
- 箇条書きで出す
- 必ず「状況を特定するため、次を教えてください。」で始める
- 業務ヘルプデスクとして実用的な確認だけを聞く
- 余計な前置きや結論は書かない

ユーザー質問:
{user_q}
""".strip()
    return [
        {"role": "system", "content": "あなたは社内ITヘルプデスク担当です。必ず日本語で、短く実務的に質問を返してください。"},
        {"role": "user", "content": prompt},
    ]


def generate_clarification_prompt(*, user_q: str, llm_chat) -> str:
    try:
        answer = str(llm_chat(build_clarification_messages(user_q)) or "").strip()
        if answer:
            return answer
    except Exception:
        pass
    return _fallback_prompt(user_q)
