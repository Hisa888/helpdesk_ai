from __future__ import annotations

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
import io
import json
import os
import textwrap
import zipfile

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from helpdesk_app.faq_io import (
    faq_df_to_excel_bytes,
    normalize_faq_columns,
    read_csv_flexible,
    read_faq_uploaded_file,
    save_faq_csv_full,
)
from helpdesk_app.llm_service import create_llm_runtime
from helpdesk_app.modules.admin_faq_generation_utils import (
    append_faq_csv as build_append_faq_csv,
    generate_faq_candidates as build_generate_faq_candidates,
)
from helpdesk_app.modules.admin_log_runtime import create_admin_log_runtime
from helpdesk_app.modules.faq_answer_flow_runtime import create_faq_answer_flow_runtime
from helpdesk_app.modules.pdf_runtime import (
    REPORTLAB_AVAILABLE,
    generate_effect_report_pdf,
    generate_ops_manual_pdf,
    generate_sales_proposal_pdf,
)
from helpdesk_app.modules.settings_and_persistence import create_runtime_context


try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except Exception:
    SentenceTransformer = None
    SENTENCE_TRANSFORMERS_AVAILABLE = False


def build_slack_bot_zip_bytes(render_base: str = "https://your-render-url.onrender.com") -> bytes:
    """Slack Bot 完全版コード一式をZIPで返す。"""
    slack_bot_py = textwrap.dedent("""\
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
    """).strip() + "\n"

    requirements_txt = textwrap.dedent("""\
    flask==3.0.3
    requests==2.32.3
    gunicorn==22.0.0
    """).strip() + "\n"

    render_yaml = textwrap.dedent("""\
    services:
      - type: web
        name: slack-helpdesk-bot
        env: python
        plan: free
        buildCommand: pip install -r requirements.txt
        startCommand: gunicorn slack_bot:app
        autoDeploy: true
    """).strip() + "\n"

    env_example = textwrap.dedent(f"""\
    HELPDESK_ASK_URL={render_base}/ask
    SLACK_SIGNING_SECRET=your_signing_secret
    REQUEST_TIMEOUT=30
    """).strip() + "\n"

    readme_md = textwrap.dedent("""\
    # Slack Helpdesk Bot 完全版

    このZIPは、既存の Streamlit アプリ本体とは別サービスとして Render に配置する想定です。

    ## 含まれるファイル
    - `slack_bot.py` : Slack Slash Command / Events 受信用 Flask アプリ
    - `requirements.txt` : 必要ライブラリ
    - `render.yaml` : Render デプロイ設定例
    - `.env.example` : 環境変数の雛形

    ## Slack 側設定
    1. Slack API で App を作成
    2. Slash Commands に `/helpdesk` を追加
    3. Request URL に `https://あなたのRenderURL/slack/command` を設定
    4. Event Subscriptions を使う場合は `https://あなたのRenderURL/slack/events` を設定
    5. Signing Secret を Render の環境変数 `SLACK_SIGNING_SECRET` に設定

    ## Render 側設定
    1. このZIPを GitHub リポジトリに配置
    2. Render で New + → Web Service
    3. Build Command: `pip install -r requirements.txt`
    4. Start Command: `gunicorn slack_bot:app`
    5. `HELPDESK_ASK_URL` に既存問い合わせAIの API URL を設定

    ## 重要
    既存の Streamlit アプリに `/ask` API が無い場合は、別途 API 追加が必要です。
    まずは Slack Bot コード一式を先に配布し、後から API 側を接続しても構いません。
    """).strip() + "\n"

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("slack_bot.py", slack_bot_py)
        zf.writestr("requirements.txt", requirements_txt)
        zf.writestr("render.yaml", render_yaml)
        zf.writestr(".env.example", env_example)
        zf.writestr("README.md", readme_md)

    buf.seek(0)
    return buf.getvalue()



def create_runtime_services(*, st, requests, root_dir: str | Path = ".") -> SimpleNamespace:
    settings_ctx = create_runtime_context(
        st=st,
        requests=requests,
        base_llm_chat=lambda messages: "",
        root_dir=Path(root_dir),
    )

    llm_runtime = create_llm_runtime(
        st=st,
        requests=requests,
        current_llm_settings=settings_ctx.current_llm_settings,
        base_llm_chat=lambda messages: settings_ctx.llm_chat(messages),
    )
    llm_chat = llm_runtime.llm_chat

    admin_log_runtime = create_admin_log_runtime(
        log_dir=settings_ctx.LOG_DIR,
        persist_log_now=settings_ctx.persist_log_now,
    )

    def faq_cache_token() -> str:
        try:
            if settings_ctx.FAQ_PATH.exists():
                stat = settings_ctx.FAQ_PATH.stat()
                return f"{settings_ctx.FAQ_PATH}:{stat.st_mtime_ns}:{stat.st_size}"
        except Exception:
            pass
        return str(settings_ctx.FAQ_PATH)

    answer_flow_ctx = create_faq_answer_flow_runtime(
        st=st,
        pd=pd,
        Path=Path,
        FAQ_PATH=settings_ctx.FAQ_PATH,
        TfidfVectorizer=TfidfVectorizer,
        cosine_similarity=cosine_similarity,
        normalize_faq_columns=normalize_faq_columns,
        read_csv_flexible=read_csv_flexible,
        current_search_settings=settings_ctx.current_search_settings,
        llm_chat=llm_chat,
        faq_cache_token_getter=faq_cache_token,
        SENTENCE_TRANSFORMERS_AVAILABLE=SENTENCE_TRANSFORMERS_AVAILABLE,
        SentenceTransformer=SentenceTransformer,
    )

    def generate_faq_candidates(nohit_questions: list[str], n_items: int = 8) -> pd.DataFrame:
        return build_generate_faq_candidates(
            nohit_questions=nohit_questions,
            n_items=n_items,
            llm_chat=llm_chat,
        )

    def append_faq_csv(faq_path: Path, new_df: pd.DataFrame) -> int:
        return build_append_faq_csv(
            faq_path=faq_path,
            new_df=new_df,
            normalize_faq_columns=normalize_faq_columns,
            read_csv_flexible=read_csv_flexible,
            persist_faq_now=settings_ctx.persist_faq_now,
        )

    def check_password(pwd: str) -> bool:
        expected = str(st.secrets.get("ADMIN_PASSWORD", os.environ.get("ADMIN_PASSWORD", "admin")))
        return str(pwd or "") == expected

    contact_link = settings_ctx.build_contact_link()

    return SimpleNamespace(
        pd=pd,
        datetime=datetime,
        settings_ctx=settings_ctx,
        llm_chat=llm_chat,
        contact_link=contact_link,
        check_password=check_password,
        faq_cache_token_getter=faq_cache_token,
        generate_faq_candidates=generate_faq_candidates,
        append_faq_csv=append_faq_csv,
        build_slack_bot_zip_bytes=build_slack_bot_zip_bytes,
        faq_df_to_excel_bytes=faq_df_to_excel_bytes,
        normalize_faq_columns=normalize_faq_columns,
        read_csv_flexible=read_csv_flexible,
        read_faq_uploaded_file=read_faq_uploaded_file,
        save_faq_csv_full=save_faq_csv_full,
        REPORTLAB_AVAILABLE=REPORTLAB_AVAILABLE,
        generate_effect_report_pdf=generate_effect_report_pdf,
        generate_ops_manual_pdf=generate_ops_manual_pdf,
        generate_sales_proposal_pdf=generate_sales_proposal_pdf,
        SENTENCE_TRANSFORMERS_AVAILABLE=SENTENCE_TRANSFORMERS_AVAILABLE,
        SentenceTransformer=SentenceTransformer,
        FAQ_PATH=settings_ctx.FAQ_PATH,
        COMPANY_NAME=settings_ctx.COMPANY_NAME,
        LOGO_PATH=settings_ctx.LOGO_PATH,
        SEARCH_SETTINGS=settings_ctx.SEARCH_SETTINGS,
        DEFAULT_SEARCH_THRESHOLD=settings_ctx.DEFAULT_SEARCH_THRESHOLD,
        DEFAULT_SUGGEST_THRESHOLD=settings_ctx.DEFAULT_SUGGEST_THRESHOLD,
        default_ui_theme_settings=settings_ctx.default_ui_theme_settings,
        default_ui_layout_settings=settings_ctx.default_ui_layout_settings,
        sanitize_ui_theme_settings=settings_ctx.sanitize_ui_theme_settings,
        sanitize_ui_layout_settings=settings_ctx.sanitize_ui_layout_settings,
        default_llm_settings=settings_ctx.default_llm_settings,
        sanitize_llm_settings=settings_ctx.sanitize_llm_settings,
        current_llm_settings=settings_ctx.current_llm_settings,
        save_llm_settings=settings_ctx.save_llm_settings,
        default_search_settings=settings_ctx.default_search_settings,
        _sanitize_search_settings=settings_ctx._sanitize_search_settings,
        current_search_settings=settings_ctx.current_search_settings,
        save_search_settings=settings_ctx.save_search_settings,
        current_search_threshold=settings_ctx.current_search_threshold,
        current_suggest_threshold=settings_ctx.current_suggest_threshold,
        current_ui_theme_settings=settings_ctx.current_ui_theme_settings,
        current_ui_layout_settings=settings_ctx.current_ui_layout_settings,
        save_ui_theme_settings=settings_ctx.save_ui_theme_settings,
        save_ui_layout_settings=settings_ctx.save_ui_layout_settings,
        persist_faq_now=settings_ctx.persist_faq_now,
        persist_log_now=settings_ctx.persist_log_now,
        read_interactions=admin_log_runtime.read_interactions,
        list_log_files=admin_log_runtime.list_log_files,
        make_logs_zip=admin_log_runtime.make_logs_zip,
        count_nohit_logs=admin_log_runtime.count_nohit_logs,
        log_nohit=admin_log_runtime.log_nohit,
        update_nohit_record=admin_log_runtime.update_nohit_record,
        seed_nohit_questions=admin_log_runtime.seed_nohit_questions,
        log_interaction=admin_log_runtime.log_interaction,
        load_nohit_questions_from_logs=admin_log_runtime.load_nohit_questions_from_logs,
        format_minutes_to_hours=admin_log_runtime.format_minutes_to_hours,
        csv_bytes_as_utf8_sig=admin_log_runtime.csv_bytes_as_utf8_sig,
        retrieve_faq_cached=answer_flow_ctx.retrieve_faq_cached,
        try_ultrafast_answer=answer_flow_ctx.try_ultrafast_answer,
        ensure_faq_index_loaded=answer_flow_ctx.ensure_faq_index_loaded,
        nohit_template=answer_flow_ctx.nohit_template,
        _fastlane_direct_answer=answer_flow_ctx._fastlane_direct_answer,
        build_prompt=answer_flow_ctx.build_prompt,
        llm_answer_cached=answer_flow_ctx.llm_answer_cached,
        load_faq_index=answer_flow_ctx.load_faq_index,
        get_faq_index_state=answer_flow_ctx.get_faq_index_state,
        reset_faq_index_runtime=answer_flow_ctx.reset_faq_index_runtime,
    )
