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
st.markdown(
    """
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
/* 回答の枠（未定義だと見た目が崩れるので追加） */
.answerbox {
  border-left: 4px solid #22c55e;
  background: #f0fdf4;
  padding: 12px 14px;
  border-radius: 12px;
  line-height: 1.6;
}
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

# ====サイドバー ========
with st.sidebar:
    st.markdown("### 📌 このAIでできること")
    st.markdown(
        """
- FAQから最も近い回答を提示（根拠表示）
- 低一致は「該当なし」へ蓄積 → 管理者がFAQ化
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
1. 質問を入力  
2. 回答＋参照FAQを確認  
3. 該当なしは管理者がFAQ化  
"""
    )


# ======================
# FAQロード（落ちやすい箇所を全てガード）
# ======================
@st.cache_resource(show_spinner=False)
def load_faq_index(faq_path: Path):
    """
    - faq.csv が無い/空/列欠け でもアプリが落ちないように防御
    - vectorizer は df が空のときは None を返す
    """
    if not faq_path.exists():
        # 空のDFを返し、画面側で注意表示
        empty = pd.DataFrame(columns=["question", "answer", "category"])
        return empty, None, None

    try:
        df = pd.read_csv(
            faq_path,
            encoding="utf-8",
            engine="python",
            on_bad_lines="skip",
        )
    except Exception as e:
        # CSVが壊れている/エンコード違い等
        empty = pd.DataFrame(columns=["question", "answer", "category"])
        return empty, None, None

    # 列の欠けを補完
    for col in ["question", "answer", "category"]:
        if col not in df.columns:
            df[col] = ""

    # 文字列化
    df["question"] = df["question"].fillna("").astype(str)
    df["answer"] = df["answer"].fillna("").astype(str)
    df["category"] = df["category"].fillna("").astype(str)

    # 空チェック
    if len(df) == 0:
        return df, None, None

    df["qa_text"] = (df["question"] + " / " + df["answer"]).astype(str)

    try:
        vectorizer = TfidfVectorizer(ngram_range=(1, 2))
        X = vectorizer.fit_transform(df["qa_text"])
    except Exception:
        # 学習に失敗（極端に短い/異常なデータなど）
        return df, None, None

    return df, vectorizer, X


df, vectorizer, X = load_faq_index(FAQ_PATH)

if df is None or len(df) == 0 or vectorizer is None or X is None:
    st.warning("faq.csv が未配置/空/不正のため、FAQ検索は無効です。まず faq.csv を配置してください。")

# ======================
# 補助関数（例外を潰して落ちないように）
# ======================
def retrieve_faq(query: str):
    """
    戻り値: [(row(dict-like), score(float)), ...]
    """
    if not query:
        return []

    if vectorizer is None or X is None or df is None or len(df) == 0:
        return []

    try:
        qv = vectorizer.transform([query])
        sims = cosine_similarity(qv, X).flatten()
        if sims.size == 0:
            return []
        idxs = sims.argsort()[::-1][:TOP_K]
        return [(df.iloc[i], float(sims[i])) for i in idxs]
    except Exception:
        return []


def build_prompt(user_q: str, hits):
    context_parts = []
    for i, (row, score) in enumerate(hits, 1):
        # row は Series の可能性があるので get を使う
        q = str(row.get("question", ""))
        a = str(row.get("answer", ""))
        context_parts.append(f"\n[FAQ{i}]\nQ:{q}\nA:{a}\n")
    context = "".join(context_parts)

    return f"""
あなたは社内の情シス担当です。
必ず日本語のみで回答してください。

参照FAQ:
{context}

質問:
{user_q}
"""


def log_nohit(question: str):
    """
    該当なしを logs/nohit_YYYYMMDD.csv に蓄積（CSV壊れやすい箇所を防御）
    """
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
        # ログ失敗してもアプリは落とさない
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
            try:
                if check_password(pwd):
                    st.session_state.is_admin = True
                    st.success("ログイン成功")
                    st.rerun()
                else:
                    st.error("パスワードが違います")
            except Exception:
                st.error("認証処理でエラーが発生しました（設定/サービスを確認してください）。")
    else:
        st.success("ログイン中")
        if st.button("ログアウト"):
            st.session_state.is_admin = False
            st.rerun()


# ======================
# セッション初期化（NameError/KeyError防止）
# ======================
if "used_hits" not in st.session_state:
    st.session_state.used_hits = []

if "messages" not in st.session_state:
    st.session_state.messages = []


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
        st.markdown(
            '<div class="refbox">該当なし（スコアが低いため問い合わせ誘導）</div>',
            unsafe_allow_html=True,
        )
    else:
        for i, (row, score) in enumerate(used_hits, 1):
            q_html = str(row.get("question", "")).replace("\n", "<br>")
            a_html = str(row.get("answer", "")).replace("\n", "<br>")
            cat = str(row.get("category", ""))

            st.markdown(
                f"""
<div class="refbox">
<b>FAQ{i}</b>（score={score:.3f} / category={cat}）<br>
<b>Q:</b> {q_html}<br>
<b>A:</b> {a_html}
</div>
""",
                unsafe_allow_html=True,
            )


# ======================
# 入力 → 検索 → 回答
# ======================
user_q = st.chat_input("質問を入力してください")

if user_q:
    # 1) ユーザー発言を保存＆表示
    st.session_state.messages.append({"role": "user", "content": user_q})
    with st.chat_message("user"):
        st.markdown(user_q)

    # 2) FAQ検索
    hits = retrieve_faq(user_q)  # 例: [(row, score), ...]
    best_score = hits[0][1] if hits else 0.0

    # 3) 根拠表示用 used_hits / 回答の確定
    if best_score < MIN_SCORE:
        used_hits = []
        answer = "FAQに該当がありません。情シスへお問い合わせください。"
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
            # LLM側の設定漏れ/API障害でも落とさない
            answer = "現在AIの回答機能でエラーが発生しています。しばらくしてから再度お試しください。"

    st.session_state.used_hits = used_hits  # 根拠の保存

    # 4) アシスタント発言を表示（HTML整形）
    with st.chat_message("assistant"):
        answer_html = str(answer).replace("\n", "<br>")
        st.markdown(
            f"""
<div class="answerbox">
{answer_html}
</div>
""",
            unsafe_allow_html=True,
        )

    # 5) 履歴に保存
    st.session_state.messages.append({"role": "assistant", "content": str(answer)})
