import os
import re
import uuid
import csv
from pathlib import Path
from datetime import datetime

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

TOP_K = 3
MIN_SCORE = 0.15

st.set_page_config(page_title="情シス問い合わせAI", layout="centered")
st.title("🧑‍💻 情シス問い合わせAI")

# ===== プロっぽい見た目（CSS）=====
st.markdown("""
<style>
/* 全体幅 */
.block-container {padding-top: 2.0rem; padding-bottom: 3rem; max-width: 1100px;}
/* タイトル周り */
.hero {
  padding: 18px 20px;
  border-radius: 14px;
  background: linear-gradient(135deg, #0ea5e9 0%, #22c55e 100%);
  color: white;
  margin-bottom: 18px;
}
.hero h1 {font-size: 34px; margin: 0 0 6px 0;}
.hero p {margin: 0; font-size: 15px; opacity: 0.95;}
.badges {margin-top: 12px; display:flex; gap:8px; flex-wrap:wrap;}
.badge {
  background: rgba(255,255,255,0.18);
  border: 1px solid rgba(255,255,255,0.25);
  padding: 6px 10px; border-radius: 999px; font-size: 12px;
}
/* カード */
.card {
  background: #ffffff;
  border: 1px solid #e5e7eb;
  border-radius: 14px;
  padding: 14px 14px;
  box-shadow: 0 6px 20px rgba(0,0,0,0.06);
}
.card h3 {margin: 0 0 8px 0; font-size: 16px;}
.small {font-size: 12px; color:#6b7280;}
/* 参照FAQの枠 */
.refbox {
  border-left: 4px solid #0ea5e9;
  background: #f8fafc;
  padding: 10px 12px;
  border-radius: 10px;
}
</style>
""", unsafe_allow_html=True)

# ===== ヒーローヘッダー =====
st.markdown("""
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
""", unsafe_allow_html=True)


# ====サイドバー ========
with st.sidebar:
    st.markdown("### 📌 このAIでできること")
    st.markdown("""
- FAQから最も近い回答を提示（根拠表示）
- 低一致は「該当なし」へ蓄積 → 管理者がFAQ化
- 問い合わせ文の統一（必要情報を自動ガイド）
""")

    st.markdown("### 📈 想定効果（例）")
    st.markdown("""
- 繰り返し質問の削減
- 対応品質の平準化
- 新人でも同じ回答ができる
""")

    st.markdown("### 🧭 使い方")
    st.markdown("""
1. 質問を入力  
2. 回答＋参照FAQを確認  
3. 該当なしは管理者がFAQ化  
""")
    

# ======================
# FAQロード
# ======================
@st.cache_resource
def load_faq_index():
    df = pd.read_csv(FAQ_PATH, encoding="utf-8", engine="python", on_bad_lines="skip")
    df["qa_text"] = (df["question"].fillna("") + " / " + df["answer"].fillna("")).astype(str)
    vectorizer = TfidfVectorizer(ngram_range=(1, 2))
    X = vectorizer.fit_transform(df["qa_text"])
    return df, vectorizer, X

df, vectorizer, X = load_faq_index()

# ======================
# 補助関数
# ======================
def retrieve_faq(query):
    qv = vectorizer.transform([query])
    sims = cosine_similarity(qv, X).flatten()
    idxs = sims.argsort()[::-1][:TOP_K]
    return [(df.iloc[i], float(sims[i])) for i in idxs]

def build_prompt(user_q, hits):
    context = ""
    for i, (row, score) in enumerate(hits, 1):
        context += f"\n[FAQ{i}]\nQ:{row['question']}\nA:{row['answer']}\n"

    return f"""
あなたは社内の情シス担当です。
必ず日本語のみで回答してください。

参照FAQ:
{context}

質問:
{user_q}
"""

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
# チャット
# ======================
if "messages" not in st.session_state:
    st.session_state.messages = []

for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])

# ======================
# 「参照FAQ」も見た目を整える
# ======================
with st.expander("参照したFAQ（根拠）を見る"):
    if not used_hits:
        st.markdown('<div class="refbox">該当なし（スコアが低いため問い合わせ誘導）</div>', unsafe_allow_html=True)
    else:
        for i, (row, score) in enumerate(used_hits, 1):
            st.markdown(f"""
<div class="refbox">
<b>FAQ{i}</b>（score={score:.3f} / category={row.get('category','')}）<br>
<b>Q:</b> {row['question']}<br>
<b>A:</b> {row['answer']}
</div>
""", unsafe_allow_html=True)
            st.write("")


user_q = st.chat_input("質問を入力してください")

if user_q:
    st.session_state.messages.append({"role": "user", "content": user_q})
    with st.chat_message("user"):
        st.markdown(user_q)

    hits = retrieve_faq(user_q)
    best_score = hits[0][1] if hits else 0

    if best_score < MIN_SCORE:
        answer = "FAQに該当がありません。情シスへお問い合わせください。"
    else:
        prompt = build_prompt(user_q, hits)
        answer = llm_chat([
            {"role": "system", "content": "あなたは情シス担当です。"},
            {"role": "user", "content": prompt}
        ])

    with st.chat_message("assistant"):
        formatted_text = user_text.replace("\n", "<br>")

        st.markdown(f"""
        <div>
        {formatted_text}
        </div>
        """, unsafe_allow_html=True)

        st.markdown(answer)

    st.session_state.messages.append({"role": "assistant", "content": answer})