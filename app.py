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
        st.markdown(answer)

    st.session_state.messages.append({"role": "assistant", "content": answer})