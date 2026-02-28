import os
import re
import uuid
import csv
import io
import zipfile
from pathlib import Path
from datetime import datetime, timedelta

import streamlit as st
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from services.auth import check_password
from services.llm_router import chat as llm_chat

# ======================
# 基本設定
# ======================
FAQ_PATH = Path("faq.csv")
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)


def list_log_files():
    """logsフォルダ内のCSV（nohit_*.csv）を新しい順に返す"""
    try:
        files = sorted(LOG_DIR.glob("nohit_*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
        return files
    except Exception:
        return []


def make_logs_zip(files):
    """指定されたCSVをZIP化してbytesで返す"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for p in files:
            try:
                zf.write(p, arcname=p.name)
            except Exception:
                pass
    buf.seek(0)
    return buf.getvalue()


def render_match_bar(score: float):
    """一致度（0-1）をバーで表示"""
    try:
        v = float(score)
    except Exception:
        v = 0.0
    v = max(0.0, min(1.0, v))
    st.progress(v, text=f"一致度：{int(v
def count_nohit_logs(days: int = 7):
    """該当なしログ件数を集計（今日 / 過去N日 / 累計）"""
    files = list_log_files()
    if not files:
        return 0, 0, 0

    today_str = datetime.now().strftime("%Y%m%d")
    today_count = 0
    total_count = 0
    recent_count = 0

    # 過去N日の日付セット
    today = datetime.now().date()
    recent_days = { (today - timedelta(days=i)).strftime("%Y%m%d") for i in range(days) }

    for p in files:
        name = p.name
        # nohit_YYYYMMDD.csv
        m = re.match(r"nohit_(\d{8})\.csv$", name)
        day = m.group(1) if m else ""
        try:
            # CSVの行数（ヘッダ除外）
            with p.open("r", encoding="utf-8") as f:
                lines = f.readlines()
            cnt = max(0, len(lines) - 1)
        except Exception:
            cnt = 0

        total_count += cnt
        if day == today_str:
            today_count += cnt
        if day in recent_days:
            recent_count += cnt

    return today_count, recent_count, total_count
*100)}%")


TOP_K = 3
MIN_SCORE = 0.15

st.set_page_config(page_title="情シス問い合わせAI", layout="centered")
st.title("🧑‍💻 情シス問い合わせAI")

# ===== プロっぽい見た目（CSS）=====
st.markdown(
    """
<style>
.block-container {padding-top: 2.0rem; padding-bottom: 3rem; max-width: 1100px;}
.hero {padding: 18px 20px; border-radius: 14px; background: linear-gradient(135deg, #0ea5e9 0%, #22c55e 100%); color: white; margin-bottom: 18px;}
.hero h1 {font-size: 34px; margin: 0 0 6px 0;}
.hero p {margin: 0; font-size: 15px; opacity: 0.95;}
.badges {margin-top: 12px; display:flex; gap:8px; flex-wrap:wrap;}
.badge {background: rgba(255,255,255,0.18); border: 1px solid rgba(255,255,255,0.25); padding: 6px 10px; border-radius: 999px; font-size: 12px;}
.card {background: #ffffff; border: 1px solid #e5e7eb; border-radius: 14px; padding: 14px 14px; box-shadow: 0 6px 20px rgba(0,0,0,0.06);}
.card h3 {margin: 0 0 8px 0; font-size: 16px;}
.small {font-size: 12px; color:#6b7280;}
.refbox {border-left: 4px solid #0ea5e9; background: #f8fafc; padding: 10px 12px; border-radius: 10px;}
.answerbox {border-left: 4px solid #22c55e; background: #f0fdf4; padding: 12px 14px; border-radius: 12px; line-height: 1.6;}
</style>
""",
    unsafe_allow_html=True,
)

# ===== ヒーローヘッダー =====
st.markdown(
    """
<div class="hero">
  <h1>情シス問い合わせAI</h1>
  <p>FAQ根拠付きで回答し、問い合わせ対応を削減する社内ヘルプデスクAI（RAG + LLM）</p>
  <div class="badges">
    <span class="badge">✅ FAQ参照（根拠表示）</span>
    <span class="badge">⚡ Groq高速推論</span>
    <span class="badge">📝 ログ / 該当なし蓄積</span>
    <span class="badge">🔐 管理者でFAQ育成</span>
  </div>
</div>
""",
    unsafe_allow_html=True,
)

# ==== サイドバー ========
with st.sidebar:
    st.markdown("### 📌 このAIでできること")
    st.markdown(
        """
- FAQから最も近い回答を提示（根拠表示）
- 低一致は「該当なし」へ誘導＋必要情報テンプレ
- 問い合わせ文の統一（必要情報を自動ガイド）
"""
    )

    st.markdown("### 📈 想定効果（例）")
    st.markdown(
        """
- 繰り返し質問の削減
- 対応品質の平準化
- 新人でも同じ回答ができる
"""
    )

    st.markdown("### 🧭 使い方")
    st.markdown(
        """
1. 質問を入力（またはおすすめボタン）  
2. 回答＋参照FAQ（根拠）を確認  
3. 該当なしはテンプレを使って情シスへ連絡  
"""
    )

    # ======================
    # ログ（該当なし）状況＆ダウンロード
    # ======================
    st.markdown("### 📊 問い合わせログ状況（該当なし）")
    t_cnt, w_cnt, total_cnt = count_nohit_logs(days=7)
    cA, cB, cC = st.columns(3)
    cA.metric("今日", t_cnt)
    cB.metric("過去7日", w_cnt)
    cC.metric("累計", total_cnt)

    st.markdown("### 📥 ログ（該当なし）ダウンロード")
    log_files = list_log_files()
    if not log_files:
        st.caption("まだログはありません。")
    else:
        latest = log_files[0]
        try:
            latest_bytes = latest.read_bytes()
        except Exception:
            latest_bytes = b""
        st.download_button(
            "⬇ 最新ログCSVをダウンロード",
            data=latest_bytes,
            file_name=latest.name,
            mime="text/csv",
            use_container_width=True,
        )

        zip_bytes = make_logs_zip(log_files)
        st.download_button(
            "⬇ ログをZIPでまとめてDL",
            data=zip_bytes,
            file_name="nohit_logs.zip",
            mime="application/zip",
            use_container_width=True,
        )

        with st.expander("ログ一覧を見る"):
            for p in log_files[:20]:
                st.write(f"• {p.name}")


# ======================
# FAQロード（落ちやすい箇所を全てガード）
# ======================
@st.cache_resource(show_spinner=False)
def load_faq_index(faq_path: Path):
    if not faq_path.exists():
        empty = pd.DataFrame(columns=["question", "answer", "category"])
        return empty, None, None

    try:
        df = pd.read_csv(faq_path, encoding="utf-8", engine="python", on_bad_lines="skip")
    except Exception:
        empty = pd.DataFrame(columns=["question", "answer", "category"])
        return empty, None, None

    for col in ["question", "answer", "category"]:
        if col not in df.columns:
            df[col] = ""

    df["question"] = df["question"].fillna("").astype(str)
    df["answer"] = df["answer"].fillna("").astype(str)
    df["category"] = df["category"].fillna("").astype(str)

    if len(df) == 0:
        return df, None, None

    df["qa_text"] = (df["question"] + " / " + df["answer"]).astype(str)

    try:
        vectorizer = TfidfVectorizer(ngram_range=(1, 2))
        X = vectorizer.fit_transform(df["qa_text"])
    except Exception:
        return df, None, None

    return df, vectorizer, X


df, vectorizer, X = load_faq_index(FAQ_PATH)

if df is None or len(df) == 0 or vectorizer is None or X is None:
    st.warning("faq.csv が未配置/空/不正のため、FAQ検索は無効です。まず faq.csv を配置してください。")


def retrieve_faq(query: str):
    if not query:
        return []
    if vectorizer is None or X is None or df is None or len(df) == 0:
        return []
    try:
        qv = vectorizer.transform([query])
        sims = cosine_similarity(qv, X).flatten()
        if sims.size == 0:
            return []
        idxs = sims.argsort()[::-1][:3]
        return [(df.iloc[i], float(sims[i])) for i in idxs]
    except Exception:
        return []


def build_prompt(user_q: str, hits):
    context_parts = []
    for i, (row, score) in enumerate(hits, 1):
        q = str(row.get("question", ""))
        a = str(row.get("answer", ""))
        context_parts.append(f"\n[FAQ{i}]\nQ:{q}\nA:{a}\n")
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


def nohit_template():
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


def log_nohit(question: str):
    if not question:
        return
    day = datetime.now().strftime("%Y%m%d")
    path = LOG_DIR / f"nohit_{day}.csv"
    try:
        is_new = not path.exists()
        with path.open("a", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            if is_new:
                w.writerow(["timestamp", "question"])
            w.writerow([datetime.now().isoformat(timespec="seconds"), question])
    except Exception:
        pass


# ======================
# 管理者ログイン
# ======================
if "is_admin" not in st.session_state:
    st.session_state.is_admin = False

with st.sidebar:
    st.markdown("## 🛠 管理者")
    if not st.session_state.is_admin:
        pwd = st.text_input("管理者パスワード", type="password")
        if st.button("ログイン"):
            if check_password(pwd):
                st.session_state.is_admin = True
                st.success("ログイン成功")
                st.rerun()
            else:
                st.error("パスワードが違います")
    else:
        st.success("ログイン中")
        if st.button("ログアウト"):
            st.session_state.is_admin = False
            st.rerun()


# ======================
# セッション初期化
# ======================
if "used_hits" not in st.session_state:
    st.session_state.used_hits = []

if "messages" not in st.session_state:
    st.session_state.messages = []

if "pending_q" not in st.session_state:
    st.session_state.pending_q = ""


# ======================
# チャット履歴表示
# ======================
for m in st.session_state.messages:
    with st.chat_message(m.get("role", "assistant")):
        st.markdown(m.get("content", ""))


# ======================
# 「参照FAQ」表示
# ======================
with st.expander("参照したFAQ（根拠）を見る"):
    used_hits = st.session_state.used_hits
    if not used_hits:
        st.markdown('<div class="refbox">該当なし（スコアが低いため問い合わせ誘導）</div>', unsafe_allow_html=True)
    else:
        for i, (row, score) in enumerate(used_hits, 1):
            render_match_bar(score)
            q_html = str(row.get("question", "")).replace("\n", "<br>")
            a_html = str(row.get("answer", "")).replace("\n", "<br>")
            cat = str(row.get("category", ""))
            match_pct = int(max(0.0, min(1.0, float(score))) * 100)
            st.markdown(
                f"""
<div class="refbox">
<b>FAQ{i}</b>（一致度：{match_pct}% / category={cat}）<br>
<b>Q:</b> {q_html}<br>
<b>A:</b> {a_html}
</div>
""",
                unsafe_allow_html=True,
            )


# ======================
# おすすめ質問ボタン（3つ）
# ======================
st.markdown("### 💡 おすすめ質問（クリックで送信）")
c1, c2, c3 = st.columns(3)

if c1.button("🔐 パスワードを忘れた"):
    st.session_state.pending_q = "パスワードを忘れました"
    st.rerun()

if c2.button("🧩 アカウントがロックされた"):
    st.session_state.pending_q = "アカウントがロックされました"
    st.rerun()

if c3.button("🌐 VPNに接続できない"):
    st.session_state.pending_q = "VPNに接続できません"
    st.rerun()


# ======================
# 入力 → 検索 → 回答
# ======================
user_q = st.session_state.pending_q or st.chat_input("質問を入力してください")

if user_q:
    st.session_state.pending_q = ""

    st.session_state.messages.append({"role": "user", "content": user_q})
    with st.chat_message("user"):
        st.markdown(user_q)

    hits = retrieve_faq(user_q)
    best_score = hits[0][1] if hits else 0.0

    if hits:
        render_match_bar(best_score)

    if best_score < MIN_SCORE:
        used_hits = []
        answer = nohit_template()
        log_nohit(user_q)
    else:
        used_hits = hits
        prompt = build_prompt(user_q, hits)
        try:
            answer = llm_chat(
                [
                    {"role": "system", "content": "あなたは情シス担当です。"},
                    {"role": "user", "content": prompt},
                ]
            )
        except Exception:
            answer = "現在AIの回答機能でエラーが発生しています。しばらくしてから再度お試しください。"

    st.session_state.used_hits = used_hits

    with st.chat_message("assistant"):
        answer_html = str(answer).replace("\n", "<br>")
        st.markdown(f'<div class="answerbox">{answer_html}</div>', unsafe_allow_html=True)

    st.session_state.messages.append({"role": "assistant", "content": str(answer)})
