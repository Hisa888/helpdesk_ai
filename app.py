import os
import re
import io
import csv
import uuid
import textwrap
from pathlib import Path
from datetime import datetime, timedelta

import streamlit as st
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from services.auth import check_password
from services.llm_router import chat as llm_chat

# PDF (運用マニュアル)
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont

# =========================================================
# 設定
# =========================================================
FAQ_PATH = Path("faq.csv")
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

TOP_K = 3
MIN_SCORE = 0.15

APP_TITLE = "🧑‍💻 情シス問い合わせAI"
st.set_page_config(page_title="情シス問い合わせAI", layout="wide")

# =========================================================
# 見た目（CSS）
# =========================================================
st.markdown(
    """
<style>
.block-container {padding-top: 1.6rem; padding-bottom: 3rem; max-width: 1200px;}
.hero{
  padding: 18px 20px; border-radius: 14px;
  background: linear-gradient(135deg, #0ea5e9 0%, #22c55e 100%);
  color: white; margin-bottom: 14px;
}
.hero h1{font-size: 34px; margin: 0 0 6px 0; line-height: 1.2;}
.hero p{margin:0; font-size: 14px; opacity: 0.95;}
.badges{margin-top: 12px; display:flex; gap:8px; flex-wrap:wrap;}
.badge{
  background: rgba(255,255,255,0.18);
  border: 1px solid rgba(255,255,255,0.25);
  padding: 6px 10px; border-radius: 999px; font-size: 12px;
}
.refbox{
  border-left: 4px solid #0ea5e9;
  background: #f8fafc;
  padding: 10px 12px;
  border-radius: 10px;
  margin-bottom: 10px;
}
.answerbox{
  border-left: 4px solid #22c55e;
  background: #f0fdf4;
  padding: 12px 14px;
  border-radius: 12px;
}
.small{font-size: 12px; color:#6b7280;}
.kpi{
  background:#ffffff; border:1px solid #e5e7eb; border-radius:12px;
  padding:10px 12px; box-shadow: 0 6px 20px rgba(0,0,0,0.05);
}
.kpi .label{font-size:12px; color:#6b7280;}
.kpi .value{font-size:24px; font-weight:700; margin-top:2px;}
</style>
""",
    unsafe_allow_html=True,
)

# =========================================================
# ヘッダー
# =========================================================
st.markdown(
    f"""
<div class="hero">
  <h1>{APP_TITLE}</h1>
  <p>FAQ根拠付きで回答し、問い合わせ対応を削減する社内ヘルプデスクAI（RAG + LLM）</p>
  <div class="badges">
    <span class="badge">✅ FAQ参照（根拠表示）</span>
    <span class="badge">⚡ Groq / LLM</span>
    <span class="badge">📝 ログ（該当なし蓄積）</span>
    <span class="badge">🔐 管理者で運用</span>
    <span class="badge">⏱ 削減時間シミュレーター</span>
  </div>
</div>
""",
    unsafe_allow_html=True,
)

# =========================================================
# セッション初期化
# =========================================================
if "messages" not in st.session_state:
    st.session_state.messages = []
if "used_hits" not in st.session_state:
    st.session_state.used_hits = []
if "is_admin" not in st.session_state:
    st.session_state.is_admin = False
if "pending_question" not in st.session_state:
    st.session_state.pending_question = None

# =========================================================
# FAQロード / インデックス
# =========================================================
@st.cache_resource
def load_faq_index():
    if not FAQ_PATH.exists():
        # 最低限のダミー
        df = pd.DataFrame(
            [
                {"category": "アカウント", "question": "パスワードを忘れました", "answer": "社内ポータルの「パスワードリセット」から再設定してください。"},
                {"category": "アカウント", "question": "アカウントがロックされました", "answer": "10分待って再試行してください。解除されない場合は情シスへ連絡してください。"},
                {"category": "ネットワーク", "question": "VPNに接続できません", "answer": "ID/PW、端末時刻、エラー画面を確認し改善しない場合は情シスへ連絡してください。"},
            ]
        )
        df.to_csv(FAQ_PATH, index=False, encoding="utf-8")
    df = pd.read_csv(FAQ_PATH, encoding="utf-8", engine="python", on_bad_lines="skip")
    for col in ["category", "question", "answer"]:
        if col not in df.columns:
            df[col] = ""
    df["qa_text"] = (df["question"].fillna("") + " / " + df["answer"].fillna("")).astype(str)

    vectorizer = TfidfVectorizer(ngram_range=(1, 2))
    X = vectorizer.fit_transform(df["qa_text"])
    return df, vectorizer, X

df, vectorizer, X = load_faq_index()

def retrieve_faq(query: str):
    qv = vectorizer.transform([query])
    sims = cosine_similarity(qv, X).flatten()
    idxs = sims.argsort()[::-1][:TOP_K]
    hits = []
    for i in idxs:
        row = df.iloc[int(i)]
        hits.append((row, float(sims[int(i)])))
    return hits

def build_prompt(user_q: str, hits):
    context = ""
    for i, (row, score) in enumerate(hits, 1):
        context += f"\n[FAQ{i}]\nQ:{row.get('question','')}\nA:{row.get('answer','')}\n(一致度:{score:.3f})\n"
    return f"""あなたは社内の情シス担当です。
必ず日本語のみで、丁寧で短めに回答してください。
FAQに根拠がある場合は、その内容を優先してください。

参照FAQ:
{context}

質問:
{user_q}
"""

def render_match_bar(score: float):
    v = max(0.0, min(1.0, float(score)))
    st.progress(v, text=f"一致度：{int(v*100)}%")

def nohit_template() -> str:
    return """FAQに該当がありませんでした。

情シスへお問い合わせの際は、以下の情報を添えてください：

- 何ができないか（具体的な操作）
- エラー画面のスクリーンショット
- 発生時刻
- 利用場所（社内 / 社外）
- ネットワーク（Wi‑Fi / VPN）
- 端末（Windows / Mac）
- 影響範囲（自分のみ / 他の人も）

※これらを共有いただくと対応が早くなります。"""

# =========================================================
# ログ（該当なし）
# =========================================================
def _today_str():
    return datetime.now().strftime("%Y-%m-%d")

def log_nohit(user_q: str, best_score: float):
    # キーや個人情報が入っても最低限に抑える（長文は切る）
    safe_q = str(user_q).strip()
    safe_q = re.sub(r"\s+", " ", safe_q)
    safe_q = safe_q[:500]

    path = LOG_DIR / f"nohit_{_today_str()}.csv"
    is_new = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if is_new:
            w.writerow(["ts", "id", "query", "best_score"])
        w.writerow([datetime.now().isoformat(timespec="seconds"), str(uuid.uuid4())[:8], safe_q, f"{best_score:.4f}"])

def list_log_files():
    return sorted(LOG_DIR.glob("nohit_*.csv"))

def read_logs_df() -> pd.DataFrame:
    files = list_log_files()
    rows = []
    for fp in files:
        try:
            df0 = pd.read_csv(fp, encoding="utf-8")
            if "date" not in df0.columns:
                # nohit_YYYY-MM-DD.csv を日付として補完
                m = re.search(r"nohit_(\d{4}-\d{2}-\d{2})\.csv", fp.name)
                if m:
                    df0["date"] = m.group(1)
                else:
                    df0["date"] = ""
            rows.append(df0)
        except Exception:
            continue
    if not rows:
        return pd.DataFrame(columns=["ts", "id", "query", "best_score", "date"])
    out = pd.concat(rows, ignore_index=True)
    # best_score をfloatに
    try:
        out["best_score"] = out["best_score"].astype(float)
    except Exception:
        pass
    return out

def log_kpis():
    logs = read_logs_df()
    if logs.empty:
        return 0, 0, 0, logs

    today = _today_str()
    week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

    # date列がない場合はtsから作る
    if "date" not in logs.columns or logs["date"].isna().all():
        logs["date"] = logs["ts"].astype(str).str.slice(0, 10)

    today_cnt = int((logs["date"] == today).sum())
    last7_cnt = int((logs["date"] >= week_ago).sum())
    total_cnt = int(len(logs))
    return today_cnt, last7_cnt, total_cnt, logs

def logs_to_csv_bytes(df_logs: pd.DataFrame) -> bytes:
    buf = io.StringIO()
    df_logs.to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8")

# =========================================================
# 削減時間シミュレーター
# =========================================================
def calc_time_savings(monthly_inquiries: int, avg_minutes: float, self_service_rate: float):
    # self_service_rate: 0..1
    monthly_saved = monthly_inquiries * avg_minutes * self_service_rate
    hours = monthly_saved / 60.0
    return max(0.0, hours)

def generate_effect_report_pdf(company: str, monthly_inquiries: int, avg_minutes: float, self_service_rate: float, hourly_cost_yen: int) -> bytes:
    # 日本語フォント
    try:
        pdfmetrics.registerFont(UnicodeCIDFont("HeiseiKakuGo-W5"))
        font_name = "HeiseiKakuGo-W5"
    except Exception:
        font_name = "Helvetica"

    hours_saved = calc_time_savings(monthly_inquiries, avg_minutes, self_service_rate)
    monthly_yen = int(hours_saved * hourly_cost_yen)
    annual_yen = monthly_yen * 12

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4
    c.setTitle("情シス問い合わせAI 効果レポート")

    c.setFont(font_name, 16)
    c.drawString(40, h - 60, "情シス問い合わせAI：削減効果レポート（概算）")

    c.setFont(font_name, 11)
    y = h - 95
    lines = [
        f"会社名：{company}",
        f"前提：月間問い合わせ {monthly_inquiries} 件 / 1件あたり {avg_minutes:.1f} 分 / 自己解決率 {int(self_service_rate*100)}%",
        f"人件費換算：{hourly_cost_yen:,} 円 / 時間（概算）",
        "",
        f"削減時間（概算）：{hours_saved:.1f} 時間 / 月",
        f"削減金額（概算）：{monthly_yen:,} 円 / 月（年間 {annual_yen:,} 円）",
        "",
        "※本レポートは入力値に基づく概算です。実測値により調整してください。",
    ]
    for ln in lines:
        c.drawString(40, y, ln)
        y -= 18

    c.showPage()
    c.save()
    return buf.getvalue()

# =========================================================
# 運用マニュアルPDF（管理者ログインでDL）
# =========================================================
def _wrap_lines(text: str, max_chars: int):
    out = []
    for para in str(text).split("\n"):
        if not para.strip():
            out.append("")
            continue
        out.extend(textwrap.wrap(para, width=max_chars, replace_whitespace=False))
    return out

def generate_ops_manual_pdf() -> bytes:
    try:
        pdfmetrics.registerFont(UnicodeCIDFont("HeiseiKakuGo-W5"))
        font_name = "HeiseiKakuGo-W5"
    except Exception:
        font_name = "Helvetica"

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4
    c.setTitle("情シス問い合わせAI 操作説明書")

    def draw_block(title, body_lines, y):
        c.setFont(font_name, 13)
        c.drawString(40, y, title)
        y -= 18
        c.setFont(font_name, 10.5)
        for ln in body_lines:
            if y < 60:
                c.showPage()
                y = h - 60
                c.setFont(font_name, 10.5)
            c.drawString(48, y, ln)
            y -= 14
        y -= 8
        return y

    y = h - 60
    c.setFont(font_name, 16)
    c.drawString(40, y, "情シス問い合わせAI（デモ） 操作説明書")
    y -= 26
    c.setFont(font_name, 10.5)
    c.drawString(40, y, f"出力日：{datetime.now().strftime('%Y-%m-%d %H:%M')}")
    y -= 20

    # 1. 機能一覧
    features = [
        "① FAQ検索（TF‑IDF）で最も近いQ&Aを上位3件参照",
        "② 回答時に『参照したFAQ（根拠）』を表示（透明性）",
        "③ 一致度バー（%）表示",
        "④ 低一致は『該当なし』として問い合わせテンプレを表示",
        "⑤ 『該当なし』の質問をログ（CSV）に蓄積",
        "⑥ ログ状況（今日 / 過去7日 / 累計）をサイドバーに表示",
        "⑦ ログ（該当なし）CSVをダウンロード可能",
        "⑧ おすすめ質問ボタン（3つ）で初見でも迷わず利用",
        "⑨ LLM連携（Groq等）：FAQを根拠に自然文で回答（失敗時はエラーメッセージ）",
        "⑩ 削減時間シミュレーター（概算）＋効果レポートPDF出力",
        "⑪ 管理者ログインで、上記の運用資料/レポートをダウンロード可能",
    ]
    y = draw_block("1. 機能一覧", _wrap_lines("\n".join([f"- {x}" for x in features]), 60), y)

    # 2. 一般ユーザー操作
    user_steps = [
        "1) 画面下の入力欄に質問を入力して送信します。",
        "2) 回答が表示されます。必要に応じて『参照したFAQ（根拠）を見る』を開き、根拠を確認します。",
        "3) 一致度が低い場合は『該当なし』テンプレが表示されます。テンプレの必要情報を添えて情シスへ連絡します。",
        "4) 初見の人は『おすすめ質問（クリックで送信）』の3つのボタンから試せます。",
    ]
    y = draw_block("2. 利用者の操作手順", _wrap_lines("\n".join([f"- {x}" for x in user_steps]), 60), y)

    # 3. 管理者運用（ログ→FAQ育成）
    admin_ops = [
        "1) サイドバー『管理者』でログインします。",
        "2) サイドバーに『問い合わせログ状況（該当なし）』が表示されます。",
        "3) 『ログ（該当なし）ダウンロード』からCSVを取得します。",
        "4) ログ内で頻出の質問を抽出し、faq.csvにQ&Aとして追記します。",
        "   - category, question, answer の3列を推奨",
        "5) faq.csvを更新してデプロイすると、次回からFAQにヒットしやすくなります。",
        "",
        "※運用イメージ：『該当なし』ログ → 頻出をFAQ化 → 対応がどんどん自動化される（ナレッジ育成）",
    ]
    y = draw_block("3. 管理者の運用（ログ → FAQ育成）", _wrap_lines("\n".join([f"{x}" for x in admin_ops]), 60), y)

    # 4. 注意事項
    notes = [
        "・APIキーはソースに直書きせず、StreamlitのSecrets（または環境変数）で管理してください。",
        "・個人情報を含む質問ログは取り扱いルールに従い、必要に応じてマスキング/保管期間を設定してください。",
        "・一致度（%）は“文章の近さ”の指標です。FAQが増えるほど改善します。",
    ]
    y = draw_block("4. 注意事項", _wrap_lines("\n".join([f"- {x}" for x in notes]), 60), y)

    c.showPage()
    c.save()
    return buf.getvalue()

# =========================================================
# サイドバー：案内 / KPI / 管理者
# =========================================================
with st.sidebar:
    st.markdown("### 📌 このAIでできること")
    st.markdown(
        """
- FAQから最も近い回答を提示（根拠表示）
- 低一致は「該当なし」へ誘導＋必要情報テンプレ
- 該当なしログを蓄積してFAQ育成
"""
    )

    st.markdown("### 🧭 使い方")
    st.markdown(
        """
1. 質問を入力（またはおすすめボタン）  
2. 回答＋参照FAQ（根拠）を確認  
3. 該当なしはテンプレで情シスへ連絡  
"""
    )

    # ログKPI
    st.markdown("### 📊 問い合わせログ状況（該当なし）")
    today_cnt, last7_cnt, total_cnt, logs_df = log_kpis()
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(f'<div class="kpi"><div class="label">今日</div><div class="value">{today_cnt}</div></div>', unsafe_allow_html=True)
    with c2:
        st.markdown(f'<div class="kpi"><div class="label">過去7日</div><div class="value">{last7_cnt}</div></div>', unsafe_allow_html=True)
    with c3:
        st.markdown(f'<div class="kpi"><div class="label">累計</div><div class="value">{total_cnt}</div></div>', unsafe_allow_html=True)

    st.markdown("### 📥 ログ（該当なし）ダウンロード")
    if logs_df.empty:
        st.caption("まだログはありません。")
    else:
        st.download_button(
            "CSVをダウンロード",
            data=logs_to_csv_bytes(logs_df),
            file_name=f"nohit_logs_{_today_str()}.csv",
            mime="text/csv",
            use_container_width=True,
        )

    st.markdown("---")
    st.markdown("## 🛠 管理者")
    if not st.session_state.is_admin:
        pwd = st.text_input("管理者パスワード", type="password")
        if st.button("ログイン", use_container_width=True):
            if check_password(pwd):
                st.session_state.is_admin = True
                st.success("ログイン成功")
                st.rerun()
            else:
                st.error("パスワードが違います")
    else:
        st.success("ログイン中")
        if st.button("ログアウト", use_container_width=True):
            st.session_state.is_admin = False
            st.rerun()

        st.markdown("### 📘 操作説明書（PDF）")
        st.download_button(
            "操作説明書PDFをダウンロード",
            data=generate_ops_manual_pdf(),
            file_name="情シス問い合わせAI_操作説明書.pdf",
            mime="application/pdf",
            use_container_width=True,
        )

        st.markdown("### ⏱ 効果レポート（PDF）")
        company = st.text_input("会社名（レポート用）", value="デモ企業")
        monthly_inquiries = st.number_input("月間問い合わせ件数", min_value=0, value=200, step=10)
        avg_minutes = st.number_input("1件あたり対応分数（分）", min_value=0.0, value=8.0, step=0.5)
        self_rate = st.slider("自己解決率（想定）", min_value=0, max_value=100, value=30, step=5)
        hourly_cost = st.number_input("人件費換算（円/時間）", min_value=0, value=4000, step=500)

        hours_saved = calc_time_savings(int(monthly_inquiries), float(avg_minutes), float(self_rate) / 100.0)
        st.caption(f"概算：{hours_saved:.1f} 時間 / 月 の削減見込み")

        st.download_button(
            "効果レポートPDFをダウンロード",
            data=generate_effect_report_pdf(company, int(monthly_inquiries), float(avg_minutes), float(self_rate) / 100.0, int(hourly_cost)),
            file_name="情シス問い合わせAI_効果レポート.pdf",
            mime="application/pdf",
            use_container_width=True,
        )

# =========================================================
# 参照FAQ（根拠）表示
# =========================================================
with st.expander("参照したFAQ（根拠）を見る"):
    used_hits = st.session_state.used_hits
    if not used_hits:
        st.markdown('<div class="refbox">該当なし（スコアが低いため問い合わせ誘導）</div>', unsafe_allow_html=True)
    else:
        for i, (row, score) in enumerate(used_hits, 1):
            q_html = str(row.get("question", "")).replace("\n", "<br>")
            a_html = str(row.get("answer", "")).replace("\n", "<br>")
            cat = str(row.get("category", ""))
            st.markdown(
                f"""
<div class="refbox">
<b>FAQ{i}</b>（一致度={score:.3f} / category={cat}）<br>
<b>Q:</b> {q_html}<br>
<b>A:</b> {a_html}
</div>
""",
                unsafe_allow_html=True,
            )

# =========================================================
# おすすめ質問ボタン（3つ）
# =========================================================
st.markdown("## 💡 おすすめ質問（クリックで送信）")
b1, b2, b3 = st.columns(3)
with b1:
    if st.button("🔐 パスワードを忘れた", use_container_width=True):
        st.session_state.pending_question = "パスワードを忘れました"
        st.rerun()
with b2:
    if st.button("🧩 アカウントがロックされた", use_container_width=True):
        st.session_state.pending_question = "アカウントがロックされました"
        st.rerun()
with b3:
    if st.button("🌐 VPNに接続できない", use_container_width=True):
        st.session_state.pending_question = "VPNに接続できません"
        st.rerun()

# =========================================================
# チャット履歴表示
# =========================================================
for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])

# =========================================================
# 入力（常に最下部）
# =========================================================
user_q = st.chat_input("質問を入力してください")
if not user_q and st.session_state.pending_question:
    user_q = st.session_state.pending_question
    st.session_state.pending_question = None

# =========================================================
# メイン処理
# =========================================================
if user_q:
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
        log_nohit(user_q, best_score)
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
