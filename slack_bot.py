import os
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
                "text": f"*質問:* {question}
*回答:* {answer}",
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
