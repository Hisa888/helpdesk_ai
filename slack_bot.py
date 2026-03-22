import os
import hmac
import hashlib
import time
from typing import Any

import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

HELP_DESK_ASK_URL = os.getenv("HELPDESK_ASK_URL", "https://your-streamlit-or-api-url/ask")
SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET", "")
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")
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


def post_message_to_slack(channel: str, text: str) -> None:
    if not SLACK_BOT_TOKEN:
        raise RuntimeError("SLACK_BOT_TOKEN が未設定です。")

    resp = requests.post(
        "https://slack.com/api/chat.postMessage",
        headers={
            "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
            "Content-Type": "application/json; charset=utf-8",
        },
        json={
            "channel": channel,
            "text": text,
        },
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    payload = resp.json()
    if not payload.get("ok"):
        raise RuntimeError(payload.get("error", "chat.postMessage failed"))


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

    # SlackのURL検証に必須
    if data.get("type") == "url_verification":
        return jsonify({"challenge": data.get("challenge", "")})

    event = data.get("event", {})
    event_type = event.get("type")

    # Slack再送やbot自身の投稿は無視
    if event.get("subtype") == "bot_message" or event.get("bot_id"):
        return jsonify({"ok": True})

    # DM / チャンネルメンションの両方に対応
    if event_type in {"app_mention", "message"}:
        channel = event.get("channel", "")
        user = event.get("user", "")
        text = (event.get("text") or "").strip()
        channel_type = event.get("channel_type", "")

        # チャンネル投稿はメンション時だけ処理、DMはそのまま処理
        if event_type == "message" and channel_type != "im":
            return jsonify({"ok": True})

        if event_type == "app_mention":
            bot_user_id = data.get("authorizations", [{}])[0].get("user_id", "")
            if bot_user_id:
                text = text.replace(f"<@{bot_user_id}>", "").strip()

        if not text:
            post_message_to_slack(channel, "質問文を入れてください。例: VPNがつながらない")
            return jsonify({"ok": True})

        try:
            answer = ask_helpdesk(text, user_name=user, channel_name=channel)
            post_message_to_slack(channel, f"*質問:* {text}\n*回答:* {answer}")
        except Exception as e:
            post_message_to_slack(channel, f"問い合わせAIへの接続に失敗しました: {e}")

    return jsonify({"ok": True})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

