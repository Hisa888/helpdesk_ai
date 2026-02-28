import os
import re
import uuid
import csv
import io
import zipfile
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont

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
    st.progress(v, text=f"一致度：{int(v*100)}%")

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


def read_interactions(days: int = 7) -> pd.DataFrame:
    """直近days日分のinteractionsログを結合して返す（無ければ空DF）"""
    frames = []
    for i in range(days):
        d = (datetime.now() - timedelta(days=i)).strftime("%Y%m%d")
        p = LOG_DIR / f"interactions_{d}.csv"
        if p.exists():
            try:
                frames.append(pd.read_csv(p, encoding="utf-8"))
            except Exception:
                try:
                    frames.append(pd.read_csv(p, encoding="utf-8", engine="python", on_bad_lines="skip"))
                except Exception:
                    pass
    if not frames:
        return pd.DataFrame(columns=["timestamp", "question", "matched", "best_score", "category"])

    df_all = pd.concat(frames, ignore_index=True)

    # 型整形
    if "matched" in df_all.columns:
        df_all["matched"] = pd.to_numeric(df_all["matched"], errors="coerce").fillna(0).astype(int)
    else:
        df_all["matched"] = 0
    if "best_score" in df_all.columns:
        df_all["best_score"] = pd.to_numeric(df_all["best_score"], errors="coerce").fillna(0.0)
    else:
        df_all["best_score"] = 0.0
    if "category" not in df_all.columns:
        df_all["category"] = ""

    return df_all

def format_minutes_to_hours(minutes: float) -> str:
    """分→表示用（xx分 / x.x時間）"""
    try:
        m = float(minutes)
    except Exception:
        m = 0.0
    h = m / 60.0
    if h < 1:
        return f"{int(round(m))}分"
    return f"{h:.1f}時間"
def register_jp_font():
    """ReportLabで日本語を表示できるフォントを登録"""
    try:
        pdfmetrics.registerFont(UnicodeCIDFont("HeiseiKakuGo-W5"))
        return "HeiseiKakuGo-W5"
    except Exception:
        return "Helvetica"


def generate_effect_report_pdf(
    df: pd.DataFrame,
    avg_min: float,
    deflect: float,
    hourly_cost_yen: int,
    title: str = "導入効果レポート（情シス問い合わせAI）",
) -> bytes:
    """導入効果レポートPDFを生成してbytesで返す"""
    buf = io.BytesIO()
    font = register_jp_font()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4

    # ヘッダー
    c.setFont(font, 16)
    c.drawString(20 * mm, height - 20 * mm, title)
    c.setFont(font, 10)
    c.drawString(20 * mm, height - 27 * mm, f"作成日時: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    # KPI計算
    total = int(len(df))
    matched = int(df["matched"].sum()) if total and "matched" in df.columns else 0
    auto_rate = (matched / total * 100.0) if total else 0.0
    saved_min = matched * float(avg_min) * float(deflect)
    saved_hours = saved_min / 60.0
    saved_yen = int(round(saved_hours * int(hourly_cost_yen))) if hourly_cost_yen else 0

    # 本文
    y = height - 45 * mm
    c.setFont(font, 12)
    c.drawString(20 * mm, y, "サマリー（今月）")
    y -= 8 * mm

    c.setFont(font, 11)
    lines = [
        f"・問い合わせ件数：{total} 件",
        f"・自動対応率：{auto_rate:.1f} %",
        f"・削減時間（推定）：{saved_hours:.1f} 時間（{int(round(saved_min))} 分）",
        f"・想定人件費削減：{saved_yen:,} 円（{hourly_cost_yen:,} 円/時間で試算）",
        f"・前提：1件あたり平均対応時間 {avg_min:.0f} 分、AIで解決できる割合 {deflect*100:.0f} %",
    ]
    for line in lines:
        c.drawString(22 * mm, y, line)
        y -= 7 * mm

    y -= 5 * mm
    c.setFont(font, 12)
    c.drawString(20 * mm, y, "補足")
    y -= 8 * mm
    c.setFont(font, 10)
    notes = [
        "・本レポートは、アプリが自動記録する利用ログ（interactions）から集計しています。",
        "・自動対応はFAQヒット（matched=1）を基準に計算しています。",
        "・削減時間／削減額は推定値です（実運用に合わせて係数調整できます）。",
    ]
    for line in notes:
        c.drawString(22 * mm, y, line)
        y -= 6 * mm

    c.showPage()
    c.save()
    return buf.getvalue()



TOP_K = 3
MIN_SCORE = 0.15

st.set_page_config(page_title="情シス問い合わせAI", layout="centered")
st.title("🧑‍💻 情シス問い合わせAI")


# ===== プロっぽい見た目（CSS）=====
st.markdown(
    """
<style>
/* タイトル上部の余白を確保 */
.block-container {
    padding-top: 3rem !important;
}

/* h1の高さを確保 */
h1 {
    padding-top: 0.5rem;
    line-height: 1.3 !important;
}

/* スマホ対応 */
@media (max-width: 768px) {
    .block-container {
        padding-top: 2.5rem !important;
    }
}

.block-container {padding-top: 2.0rem; padding-bottom: 10rem; max-width: 1100px;}
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

# ===== KPI（直近7日）=====
try:
    _df7 = read_interactions(days=7)
    if _df7 is not None and len(_df7) > 0:
        _total7 = int(len(_df7))
        _matched7 = int(_df7["matched"].sum()) if "matched" in _df7.columns else 0
        _rate7 = (_matched7 / _total7 * 100.0) if _total7 else 0.0
        _today_prefix = datetime.now().strftime("%Y-%m-%d")
        _today = _df7[_df7["timestamp"].astype(str).str.startswith(_today_prefix)]
        _total_today = int(len(_today))

        k1, k2, k3 = st.columns(3)
        k1.metric("直近7日 問い合わせ", _total7)
        k2.metric("直近7日 自動対応率", f"{_rate7:.1f}%")
        k3.metric("今日の問い合わせ", _total_today)
    else:
        st.caption("（利用ログがまだありません。質問するとKPIが表示されます）")
except Exception:
    pass


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


    # ======================
    # 削減時間シミュレーター（営業用）
    # ======================
    st.markdown("### ⏱ 削減時間シミュレーター")
    avg_min = st.slider("1件あたりの平均対応時間（分）", 1, 20, 5, help="情シスが1件対応する平均時間の目安")
    deflect = st.slider("AIで解決できる割合（推定）", 30, 100, 70, help="AI回答で自己解決に至る割合の推定") / 100.0

    df_int = read_interactions(days=7)
    if df_int is None or len(df_int) == 0:
        st.caption("まだ利用ログがありません（質問すると自動で蓄積します）。")
    else:
        matched_7d = int(df_int["matched"].sum()) if "matched" in df_int.columns else 0
        total_7d = int(len(df_int))
        nohit_7d = total_7d - matched_7d
        saved_min_7d = matched_7d * float(avg_min) * float(deflect)
        st.metric("推定削減（過去7日）", format_minutes_to_hours(saved_min_7d))
        st.caption(f"内訳：自動対応 {matched_7d} 件 / 該当なし {nohit_7d} 件（合計 {total_7d} 件）")

        # 今日分（timestamp先頭が YYYY-MM-DD の想定）
        try:
            today_prefix = datetime.now().strftime("%Y-%m-%d")
            df_today = df_int[df_int["timestamp"].astype(str).str.startswith(today_prefix)]
            matched_today = int(df_today["matched"].sum()) if len(df_today) else 0
            saved_min_today = matched_today * float(avg_min) * float(deflect)
            st.metric("推定削減（今日）", format_minutes_to_hours(saved_min_today))
        except Exception:
            pass

    
    # ======================
    # 見える化（グラフ）
    # ======================
    if df_int is not None and len(df_int) > 0:
        st.markdown("### 📈 見える化（直近7日）")

        df_plot = df_int.copy()
        df_plot["date"] = pd.to_datetime(df_plot["timestamp"], errors="coerce").dt.date
        daily = (
            df_plot.groupby("date", dropna=True)
            .agg(total=("question", "count"), matched=("matched", "sum"))
            .reset_index()
            .sort_values("date")
        )
        daily["auto_rate"] = (daily["matched"] / daily["total"]).replace([pd.NA, float("inf")], 0.0) * 100.0
        daily["saved_min"] = daily["matched"] * float(avg_min) * float(deflect)
        daily["saved_min_cum"] = daily["saved_min"].cumsum()

        # 1) 問い合わせ件数
        st.caption("📈 7日間の問い合わせ件数推移")
        st.line_chart(daily.set_index("date")[["total"]])

        # 2) 自動対応率
        st.caption("🧠 AI自動対応率の推移（FAQヒット率）")
        st.line_chart(daily.set_index("date")[["auto_rate"]])

        # 3) 削減時間（累計）
        st.caption("⏱ 削減時間の累計（推定）")
        st.line_chart(daily.set_index("date")[["saved_min_cum"]])

    # ======================
    # 効果レポートPDF出力（今月）
    # ======================
    st.markdown("### 📄 効果レポート（PDF）")
    hourly_cost = st.number_input("想定人件費（円/時間）", min_value=0, max_value=20000, value=4000, step=500)

    # 今月のログを集計（最大60日読み込み→今月分だけ抽出）
    df_month_all = read_interactions(days=60)
    if df_month_all is None or len(df_month_all) == 0:
        st.caption("今月の利用ログがまだありません。質問すると自動で蓄積します。")
    else:
        try:
            ts = pd.to_datetime(df_month_all["timestamp"], errors="coerce")
            month_start = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            df_month = df_month_all[ts >= month_start]
        except Exception:
            df_month = df_month_all

        pdf_bytes = generate_effect_report_pdf(
            df=df_month,
            avg_min=float(avg_min),
            deflect=float(deflect),
            hourly_cost_yen=int(hourly_cost),
        )
        st.download_button(
            "📄 今月の導入効果レポートをダウンロード",
            data=pdf_bytes,
            file_name=f"effect_report_{datetime.now().strftime('%Y%m')}.pdf",
            mime="application/pdf",
            use_container_width=True,
        )
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



def log_interaction(question: str, matched: bool, best_score: float, category: str):
    """全ての質問をログ化（削減時間の見える化用）: logs/interactions_YYYYMMDD.csv"""
    if not question:
        return
    day = datetime.now().strftime("%Y%m%d")
    path = LOG_DIR / f"interactions_{day}.csv"
    try:
        is_new = not path.exists()
        with path.open("a", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            if is_new:
                w.writerow(["timestamp", "question", "matched", "best_score", "category"])
            w.writerow([datetime.now().isoformat(timespec="seconds"), question, int(bool(matched)), float(best_score), category or ""])
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
# 先に chat_input を必ず描画（pending_q があっても入力欄が消えないようにする）
chat_typed = st.chat_input("質問を入力してください")
user_q = chat_typed or st.session_state.pending_q
used_pending = (not chat_typed) and bool(st.session_state.pending_q)

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

    # 利用ログ（削減時間の見える化用）
    top_cat = ""
    if used_hits:
        try:
            top_cat = str(used_hits[0][0].get("category", ""))
        except Exception:
            top_cat = ""
    log_interaction(user_q, matched=(best_score >= MIN_SCORE), best_score=best_score, category=top_cat)

    with st.chat_message("assistant"):
        answer_html = str(answer).replace("\n", "<br>")
        st.markdown(f'<div class="answerbox">{answer_html}</div>', unsafe_allow_html=True)

    st.session_state.messages.append({"role": "assistant", "content": str(answer)})

    # おすすめ質問ボタンから自動送信した場合は、もう一度 rerun して入力欄を確実に表示
    if used_pending:
        st.rerun()