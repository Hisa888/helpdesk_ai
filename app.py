from pathlib import Path
import pandas as pd
import io
import re
import json

import os
import re
import uuid
import csv
import io
import zipfile

# ===== CSV読み込みを頑丈にする（文字コード/区切り/カラム揺れ対策）=====
def read_csv_flexible(path: Path) -> pd.DataFrame:
    """CSVをできる限り失敗しないで読む（UTF-8/UTF-8-SIG/CP932等 + delimiter推定）。"""
    # まずは生bytesを読む
    raw = path.read_bytes()
    # 文字コード候補
    encs = ["utf-8", "utf-8-sig", "cp932", "shift_jis"]
    last_err = None
    text = None
    for enc in encs:
        try:
            text = raw.decode(enc)
            break
        except Exception as e:
            last_err = e
            continue
    if text is None:
        # 最終手段：latin1で無理やり
        text = raw.decode("latin1", errors="ignore")

    # delimiter推定（csv.Snifferが失敗する場合もあるのでガード）
    import csv as _csv
    sample = text[:5000]
    delim = ","
    try:
        dialect = _csv.Sniffer().sniff(sample, delimiters=[",", "\t", ";", "|"])
        delim = dialect.delimiter
    except Exception:
        # 行にタブが多ければタブ、それ以外はカンマ
        if sample.count("\t") > sample.count(","):
            delim = "\t"

    # pandasで読む（on_bad_linesはpandas2系で有効）
    try:
        return pd.read_csv(io.StringIO(text), sep=delim, engine="python", on_bad_lines="skip")
    except Exception:
        try:
            return pd.read_csv(io.StringIO(text), sep=delim, engine="python")
        except Exception:
            # それでもダメなら空
            return pd.DataFrame()

def pick_question_column(cols) -> str | None:
    """質問カラム名の揺れを吸収"""
    cand = [
        "question", "質問", "問い合わせ", "問合せ", "query", "user_question",
        "content", "text"
    ]
    for c in cand:
        if c in cols:
            return c
    # 大文字小文字無視
    lower_map = {str(c).lower(): c for c in cols}
    for c in cand:
        if c.lower() in lower_map:
            return lower_map[c.lower()]
    return None

def extract_json_array(text: str) -> str | None:
    """LLM出力から最初のJSON配列（[...]）を抜き出す。"""
    if not text:
        return None
    s = str(text).strip()
    # ```json ... ``` を除去
    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", s.strip(), flags=re.IGNORECASE)
    # 先頭から最初の [ ... ] を抽出（DOTALL）
    m = re.search(r"\[[\s\S]*\]", s)
    return m.group(0).strip() if m else None

# ===== PDF生成（ReportLab）===== 
REPORTLAB_AVAILABLE = False
try:
    from reportlab.pdfgen import canvas  # type: ignore
    from reportlab.lib.pagesizes import A4  # type: ignore
    from reportlab.lib.units import mm  # type: ignore
    from reportlab.lib.colors import HexColor  # type: ignore
    from reportlab.pdfbase import pdfmetrics  # type: ignore
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont  # type: ignore
    REPORTLAB_AVAILABLE = True
except ModuleNotFoundError:
    # Streamlit Cloudでは requirements.txt に reportlab を追加してください
    REPORTLAB_AVAILABLE = False


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

# ======================
# 営業用UI設定（secrets / 環境変数で上書き可）
# ======================
def _get_setting(key: str, default: str = "") -> str:
    # secrets.toml → 環境変数 → デフォルト の順で参照
    try:
        v = st.secrets.get(key, None)  # type: ignore[attr-defined]
    except Exception:
        v = None
    if v is None:
        v = os.environ.get(key)
    return str(v) if v is not None else default

COMPANY_NAME = _get_setting("COMPANY_NAME", "株式会社〇〇（デモ）")
LOGO_PATH = _get_setting("LOGO_PATH", "assets/logo.png")
CONTACT_URL = _get_setting("CONTACT_URL", "")
CONTACT_EMAIL = _get_setting("CONTACT_EMAIL", "")

def build_contact_link() -> str:
    if CONTACT_URL:
        return CONTACT_URL
    if CONTACT_EMAIL:
        # 件名などは最低限。必要なら後で増やせます。
        return f"mailto:{CONTACT_EMAIL}?subject=情シス問い合わせAI%20導入相談"
    return ""


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

# =========================
# 管理者向けPDF（操作説明書 / 提案資料）
# =========================
def _wrap_lines_for_pdf(text: str, font_name: str, font_size: int, max_width_pt: float):
    """日本語を含む文章を、指定幅に収まるようにざっくり折り返す（ReportLab用）"""
    if not REPORTLAB_AVAILABLE:
        return [text]
    # 改行は保持しつつ、各行を折り返す
    lines = []
    for raw in str(text).splitlines() or [""]:
        buf = ""
        for ch in raw:
            if ch == "\t":
                ch = "  "
            trial = buf + ch
            try:
                w = pdfmetrics.stringWidth(trial, font_name, font_size)
            except Exception:
                # 万一フォント計測に失敗したら文字数で折る
                w = len(trial) * font_size
            if w <= max_width_pt:
                buf = trial
            else:
                if buf:
                    lines.append(buf)
                buf = ch
        lines.append(buf)
    return lines


def _pdf_draw_paragraph(c, x, y, text, font_name, font_size, max_width_pt, leading=None):
    if leading is None:
        leading = font_size * 1.35
    c.setFont(font_name, font_size)
    for line in _wrap_lines_for_pdf(text, font_name, font_size, max_width_pt):
        c.drawString(x, y, line)
        y -= leading
    return y


def _pdf_draw_title(c, title: str, subtitle: str | None = None):
    w, h = A4
    c.setFont("HeiseiKakuGo-W5", 20)
    c.drawString(20 * mm, h - 25 * mm, title)
    if subtitle:
        c.setFont("HeiseiKakuGo-W5", 11)
        c.drawString(20 * mm, h - 33 * mm, subtitle)
    # line
    c.setLineWidth(1)
    c.line(20 * mm, h - 36 * mm, w - 20 * mm, h - 36 * mm)


def _pdf_draw_flow(c, x0, y0):
    """簡易運用フロー図（箱 + 矢印）"""
    # box helper
    def box(x, y, w, h, label):
        c.setStrokeColor(HexColor("#0F172A"))
        c.roundRect(x, y, w, h, 6, stroke=1, fill=0)
        c.setFillColor(HexColor("#0F172A"))
        c.setFont("HeiseiKakuGo-W5", 10)
        # center-ish
        lines = _wrap_lines_for_pdf(label, "HeiseiKakuGo-W5", 10, w - 10)
        yy = y + h - 14
        for ln in lines[:3]:
            c.drawString(x + 6, yy, ln)
            yy -= 12

    def arrow(x1, y1, x2, y2):
        c.line(x1, y1, x2, y2)
        # arrow head
        import math
        ang = math.atan2(y2 - y1, x2 - x1)
        ah = 6
        a1 = ang + math.pi * 0.85
        a2 = ang - math.pi * 0.85
        c.line(x2, y2, x2 + ah * math.cos(a1), y2 + ah * math.sin(a1))
        c.line(x2, y2, x2 + ah * math.cos(a2), y2 + ah * math.sin(a2))

    w_box, h_box = 55 * mm, 16 * mm
    gap_y = 10 * mm

    x = x0
    y = y0
    box(x, y, w_box, h_box, "① ユーザーが質問\n（チャット/おすすめ）")
    arrow(x + w_box/2, y, x + w_box/2, y - gap_y + 2)
    y2 = y - gap_y - h_box
    box(x, y2, w_box, h_box, "② FAQ検索（TF-IDF）\n一致度を表示")
    arrow(x + w_box/2, y2, x + w_box/2, y2 - gap_y + 2)
    y3 = y2 - gap_y - h_box
    box(x, y3, w_box, h_box, "③ 低一致なら\n『問い合わせテンプレ』")
    arrow(x + w_box + 8, y2 + h_box/2, x + w_box + 28, y2 + h_box/2)
    box(x + w_box + 32, y2, w_box, h_box, "④ 高一致なら\nAI回答（Groq等）")
    arrow(x + w_box + 8, y3 + h_box/2, x + w_box + 28, y3 + h_box/2)
    box(x + w_box + 32, y3, w_box, h_box, "⑤ 該当なしログ\n蓄積・集計")
    return y3 - 10 * mm


def generate_ops_manual_pdf() -> bytes:
    """機能一覧 + 操作説明書PDF（管理者向け）"""
    if not REPORTLAB_AVAILABLE:
        return b""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    pdfmetrics.registerFont(UnicodeCIDFont("HeiseiKakuGo-W5"))

    w, h = A4
    margin = 20 * mm
    maxw = w - margin * 2

    # --- Page 1: cover
    _pdf_draw_title(c, "情シス問い合わせAI 操作説明書", "管理者向け / デモ用（Streamlit）")
    y = h - 55 * mm
    y = _pdf_draw_paragraph(
        c,
        margin,
        y,
        "本資料は『情シス問い合わせAI』の機能一覧と、管理者・利用者の操作手順をまとめたものです。\n運用時は自社ルール（連絡先、受付時間、SLA、個人情報ポリシー）に合わせて調整してください。",
        "HeiseiKakuGo-W5",
        11,
        maxw,
    )
    c.setFont("HeiseiKakuGo-W5", 10)
    c.drawString(margin, 20 * mm, f"生成日: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    c.showPage()

    # --- Page 2: feature list
    _pdf_draw_title(c, "1. 機能一覧", "このアプリでできること")
    y = h - 55 * mm
    features = [
        "FAQ検索（TF-IDF）: faq.csv から近いQ/Aを抽出し、根拠として表示",
        "一致度（スコア）表示: 上位候補の一致度をバーで可視化",
        "低一致時の問い合わせテンプレ: 必要情報を自動で提示し、問い合わせ品質を平準化",
        "おすすめ質問ボタン: 初見ユーザーでも迷わず入力できる導線",
        "該当なしログ蓄積: 低一致/未該当の質問をログ保存（運用改善の材料）",
        "ログ状況ダッシュボード: 今日/過去7日/累計の件数を表示",
        "ログCSVダウンロード: 管理者がログを取得してFAQ改善に活用",
        "管理者ログイン: 管理者機能（ログ確認/FAQ育成/資料DL）を保護",
        "削減時間シミュレーター: 問い合わせ削減効果（時間/金額）を試算",
        "効果レポートPDF出力: 試算結果をPDFで出力（営業・社内説明用）",
    ]
    for i, f in enumerate(features, 1):
        y = _pdf_draw_paragraph(c, margin, y, f"・{f}", "HeiseiKakuGo-W5", 11, maxw)
        y -= 2
        if y < 30 * mm:
            c.showPage()
            _pdf_draw_title(c, "1. 機能一覧（続き）", None)
            y = h - 55 * mm

    c.showPage()

    # --- Page 3: user flow
    _pdf_draw_title(c, "2. 利用者の操作手順", "通常ユーザーの使い方")
    y = h - 55 * mm
    steps = (
        "1) 画面下の入力欄に質問を入力（または『おすすめ質問』ボタンをクリック）\n"
        "2) 回答が表示されます。必要に応じて『参照したFAQ（根拠）』を開いて確認します。\n"
        "3) 一致度が低い場合は『問い合わせテンプレ』が表示されるので、記載内容を添えて情シスへ連絡します。"
    )
    y = _pdf_draw_paragraph(c, margin, y, steps, "HeiseiKakuGo-W5", 11, maxw)
    y -= 8
    c.setFont("HeiseiKakuGo-W5", 11)
    c.drawString(margin, y, "運用フロー（概要）")
    y -= 10
    _pdf_draw_flow(c, margin, y - 70 * mm)
    c.showPage()

    # --- Page 4: admin ops
    _pdf_draw_title(c, "3. 管理者の操作手順", "ログ確認・FAQ育成・資料ダウンロード")
    y = h - 55 * mm
    admin_steps = [
        "管理者パスワードでログインします（左サイドバー『管理者』）。",
        "『問い合わせログ状況』で件数を確認し、必要に応じてログCSVをダウンロードします。",
        "ログ内の『該当なし』質問を確認し、よくある内容は faq.csv にQ/Aとして追加します（運用改善）。",
        "本操作説明書PDF・提案資料PDF・効果レポートPDFを、必要に応じてダウンロードします。",
    ]
    for s in admin_steps:
        y = _pdf_draw_paragraph(c, margin, y, f"・{s}", "HeiseiKakuGo-W5", 11, maxw)
        y -= 2

    y -= 6
    y = _pdf_draw_paragraph(
        c,
        margin,
        y,
        "※ faq.csv の更新後はアプリを再起動（Reboot app）すると反映されます。\n※ 個人情報/機密情報を入力しない運用ルールを社内で明確化してください。",
        "HeiseiKakuGo-W5",
        10,
        maxw,
    )

    c.save()
    buf.seek(0)
    return buf.getvalue()


def generate_sales_proposal_pdf() -> bytes:
    """営業（副業）向け：提案資料っぽい章立てPDF"""
    if not REPORTLAB_AVAILABLE:
        return b""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    pdfmetrics.registerFont(UnicodeCIDFont("HeiseiKakuGo-W5"))

    w, h = A4
    margin = 20 * mm
    maxw = w - margin * 2

    # Page 1: cover
    _pdf_draw_title(c, "情シス問い合わせAI 提案資料", "副業デモ用 / FAQ×AIで問い合わせ対応を削減")
    y = h - 60 * mm
    y = _pdf_draw_paragraph(
        c,
        margin,
        y,
        "目的：社内問い合わせ（情シス/総務/人事など）の一次対応を自動化し、担当者工数を削減しつつ回答品質を平準化します。\n\n構成：FAQ検索（根拠提示）＋AI補助（任意）＋『該当なし』の運用改善サイクル。",
        "HeiseiKakuGo-W5",
        11,
        maxw,
    )
    c.setFont("HeiseiKakuGo-W5", 10)
    c.drawString(margin, 20 * mm, f"生成日: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    c.showPage()

    # Page 2: pain & solution
    _pdf_draw_title(c, "1. 課題と解決アプローチ", "よくある現場の困りごと")
    y = h - 55 * mm
    pains = [
        "同じ質問が繰り返され、担当者が都度対応している",
        "回答品質が担当者の経験に依存し、新人が困る",
        "問い合わせ文がバラバラで、切り分けに時間がかかる",
        "FAQが更新されず、ナレッジが属人化する",
    ]
    y = _pdf_draw_paragraph(c, margin, y, "【現状の課題】", "HeiseiKakuGo-W5", 11, maxw)
    for p in pains:
        y = _pdf_draw_paragraph(c, margin, y, f"・{p}", "HeiseiKakuGo-W5", 11, maxw)
    y -= 8
    y = _pdf_draw_paragraph(c, margin, y, "【本提案の解決】", "HeiseiKakuGo-W5", 11, maxw)
    sols = [
        "FAQ根拠提示で『まずここを見れば解決』を実現",
        "低一致時はテンプレで必要情報を揃え、二次対応を短縮",
        "該当なしログを蓄積し、FAQを継続改善できる運用に",
    ]
    for s in sols:
        y = _pdf_draw_paragraph(c, margin, y, f"・{s}", "HeiseiKakuGo-W5", 11, maxw)

    c.showPage()

    # Page 3: flow diagram
    _pdf_draw_title(c, "2. 運用フロー", "FAQ育成で精度が上がる仕組み")
    y = h - 60 * mm
    c.setFont("HeiseiKakuGo-W5", 11)
    c.drawString(margin, y, "問い合わせ対応の流れ（図解）")
    y -= 10
    _pdf_draw_flow(c, margin, y - 70 * mm)
    y -= 92 * mm
    y = _pdf_draw_paragraph(
        c,
        margin,
        y,
        "ポイント：『該当なし』をログに残し、管理者が faq.csv に追記 → 次回から自動回答できる範囲が増えます。\nつまり運用するほど“育つ”ヘルプデスクになります。",
        "HeiseiKakuGo-W5",
        11,
        maxw,
    )

    c.showPage()

    # Page 4: ROI / pricing guide
    _pdf_draw_title(c, "3. 効果（削減時間）シミュレーション", "導入前に効果を数値化")
    y = h - 55 * mm
    y = _pdf_draw_paragraph(
        c,
        margin,
        y,
        "本アプリには『削減時間シミュレーター』を搭載しています。\n例：問い合わせ 300件/月、1件あたり対応5分、削減率30% → 75時間/月の削減。\n削減時間×人件費単価で、投資対効果（ROI）を説明できます。",
        "HeiseiKakuGo-W5",
        11,
        maxw,
    )
    y -= 8
    y = _pdf_draw_paragraph(
        c,
        margin,
        y,
        "（提案用の価格例）\n・スターター：月3〜5万円（FAQ整備 + 初期設定）\n・スタンダード：月8〜12万円（ログ運用 + FAQ育成支援 + レポート）\n・プロ：月15万円〜（部門横断/権限/監査/連携）",
        "HeiseiKakuGo-W5",
        11,
        maxw,
    )

    c.showPage()

    # Page 5: next steps
    _pdf_draw_title(c, "4. 導入ステップ", "最短で“動くデモ”まで")
    y = h - 55 * mm
    steps = [
        "1) 現状ヒアリング（問い合わせ種別 / 運用ルール / NG事項）",
        "2) FAQ（初期30〜100件）を用意（csv）",
        "3) Streamlitでデモ共有（社内トライアル）",
        "4) 該当なしログを週次で確認し、FAQを育成",
        "5) 定着後に部門拡張（総務/人事/経理など）",
    ]
    for s in steps:
        y = _pdf_draw_paragraph(c, margin, y, f"・{s}", "HeiseiKakuGo-W5", 11, maxw)
        y -= 2
    y -= 8
    y = _pdf_draw_paragraph(
        c,
        margin,
        y,
        "次のアクション：\n・御社の問い合わせ例（10件）をご提供ください → 即日でデモFAQを作成できます。\n・効果試算に必要な『月間件数/平均対応時間/単価』を確認します。",
        "HeiseiKakuGo-W5",
        11,
        maxw,
    )

    c.save()
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
    """該当なしログ件数を集計（今日 / 過去N日 / 累計）
    文字コードやCSV崩れに強い集計にする。
    """
    files = list_log_files()
    if not files:
        return 0, 0, 0

    today_str = datetime.now().strftime("%Y%m%d")
    today_count = 0
    total_count = 0
    recent_count = 0

    today = datetime.now().date()
    recent_days = {(today - timedelta(days=i)).strftime("%Y%m%d") for i in range(days)}

    for p in files:
        name = p.name
        m = re.match(r"nohit_(\d{8})\.csv$", name)
        day = m.group(1) if m else ""
        try:
            df_log = read_csv_flexible(Path(p))
            cnt = int(len(df_log)) if df_log is not None else 0
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
    if not REPORTLAB_AVAILABLE:
        return "Helvetica"

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
    if not REPORTLAB_AVAILABLE:
        raise ModuleNotFoundError("reportlab is not installed")
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

st.set_page_config(page_title="情シス問い合わせAI", layout="wide")


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

.kpi-grid {display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 12px; margin: 14px 0 18px 0;}
@media (max-width: 1100px){ .kpi-grid {grid-template-columns: repeat(2, minmax(0, 1fr));} }
.kpi {background:#ffffff; border:1px solid #e5e7eb; border-radius:16px; padding:14px 14px; box-shadow: 0 8px 26px rgba(0,0,0,0.06);}
.kpi .label {font-size:12px; color:#6b7280; margin-bottom:6px;}
.kpi .value {font-size:28px; font-weight:800; letter-spacing: -0.02em; margin:0;}
.kpi .sub {font-size:12px; color:#6b7280; margin-top:6px;}
.section-title {font-size:18px; font-weight:800; margin: 8px 0 10px 0;}
.cta-row {display:flex; gap:10px; flex-wrap:wrap; margin-top:12px;}
.cta {background: rgba(255,255,255,0.18); border: 1px solid rgba(255,255,255,0.25); padding: 10px 12px; border-radius: 12px; font-size: 13px;}

</style>
""",
    unsafe_allow_html=True,
)

# ===== 会社名 / ロゴ（左上）=====
contact_link = build_contact_link()
logo_path_obj = Path(LOGO_PATH)
col_logo, col_name, col_btn = st.columns([1, 6, 3])
with col_logo:
    if LOGO_PATH and logo_path_obj.exists():
        st.image(str(logo_path_obj), width=52)
    else:
        st.markdown("### 🏢")
with col_name:
    st.markdown(f"### {COMPANY_NAME}")
    st.caption("情シス問い合わせAI（営業デモ）")
with col_btn:
    if contact_link:
        st.link_button("📩 導入相談", contact_link, use_container_width=True)
    else:
        st.button("📩 導入相談（リンク未設定）", disabled=True, use_container_width=True)

# ===== ヒーローヘッダー =====
st.markdown(
    """
<div class="hero">
  <h1>情シス問い合わせAI</h1>
  <p>FAQ根拠付きで回答し、問い合わせ対応を削減する社内ヘルプデスクAI（RAG + LLM）</p>

  <div class="cta-row">
    <span class="cta">🎯 導入効果：問い合わせ削減 / 品質平準化 / ナレッジ蓄積</span>
    <span class="cta">🧩 既存FAQ（CSV）で即導入</span>
    <span class="cta">📄 効果レポートPDF出力</span>
  </div>

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

        # 営業用：削減時間（推定）KPI（サイドバー入力と連動）
        _avg_min_kpi = float(st.session_state.get("avg_min", 5))
        _deflect_kpi = float(st.session_state.get("deflect", 0.7))
        _hourly_cost_kpi = int(st.session_state.get("hourly_cost", 4000))
        _saved_min7 = _matched7 * _avg_min_kpi * _deflect_kpi
        _saved_h7 = _saved_min7 / 60.0
        _saved_yen7 = int(round(_saved_h7 * _hourly_cost_kpi)) if _hourly_cost_kpi else 0

        # 営業用：KPIカード（中央に大きく）
        st.markdown('<div class="section-title">📊 直近の利用状況</div>', unsafe_allow_html=True)
        st.markdown(
            f'''
<div class="kpi-grid">
  <div class="kpi">
    <div class="label">直近7日 問い合わせ</div>
    <div class="value">{_total7}</div>
    <div class="sub">ログベース</div>
  </div>
  <div class="kpi">
    <div class="label">直近7日 自動対応率</div>
    <div class="value">{_rate7:.1f}%</div>
    <div class="sub">FAQヒット率</div>
  </div>
  <div class="kpi">
    <div class="label">直近7日 自動対応件数</div>
    <div class="value">{_matched7}</div>
    <div class="sub">自己解決に寄与</div>
  </div>
  <div class="kpi">
    <div class="label">推定削減（直近7日）</div>
    <div class="value">{_saved_h7:.1f}h</div>
    <div class="sub">約{_saved_yen7:,}円（{_hourly_cost_kpi:,}円/時間）</div>
  </div>
  <div class="kpi">
    <div class="label">今日の問い合わせ</div>
    <div class="value">{_total_today}</div>
    <div class="sub">当日分</div>
  </div>
</div>
''',
            unsafe_allow_html=True,
        )
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
    avg_min = st.slider("1件あたりの平均対応時間（分）", 1, 20, int(st.session_state.get("avg_min", 5)), help="情シスが1件対応する平均時間の目安", key="avg_min")
    deflect_pct = st.slider("AIで解決できる割合（推定）", 30, 100, int(st.session_state.get("deflect_pct", 70)), help="AI回答で自己解決に至る割合の推定", key="deflect_pct")
    deflect = deflect_pct / 100.0
    st.session_state["deflect"] = deflect

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

    if not REPORTLAB_AVAILABLE:
        st.warning("PDF出力には 'reportlab' が必要です。Streamlit Cloud の requirements.txt に 'reportlab' を追加して再デプロイしてください。")
        st.code("reportlab", language="text")
    else:
        hourly_cost = st.number_input("想定人件費（円/時間）", min_value=0, max_value=20000, value=int(st.session_state.get("hourly_cost", 4000)), step=500, key="hourly_cost")
        # st.session_state["hourly_cost"] = int(hourly_cost)

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

            try:
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
            except Exception as e:
                st.error(f"PDF生成でエラー: {e}")
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



def _ensure_nohit_schema(path: Path):
    """既存nohit CSVが旧形式（timestamp,questionのみ）でも、新スキーマに移行する。"""
    cols = ["timestamp", "question", "device", "location", "network", "error_text", "impact", "channel"]
    if not path.exists():
        return cols

    try:
        # 先頭行だけ見る（軽量）
        with path.open("r", encoding="utf-8", errors="ignore") as f:
            header = f.readline().strip()
        header_cols = [h.strip() for h in header.split(",")] if header else []
    except Exception:
        header_cols = []

    # すでに新スキーマなら何もしない
    if set(cols).issubset(set(header_cols)):
        return header_cols

    # 移行：既存を読み取り→新ヘッダで書き直し
    try:
        old_df = read_csv_flexible(path)
        if old_df is None:
            old_df = pd.DataFrame()
    except Exception:
        old_df = pd.DataFrame()

    if len(old_df) == 0:
        # 空なら新ヘッダで作り直す
        with path.open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(cols)
        return cols

    qcol = pick_question_column(old_df.columns) or ("question" if "question" in old_df.columns else None)
    tcol = "timestamp" if "timestamp" in old_df.columns else None

    rows = []
    for _, r in old_df.iterrows():
        ts = str(r.get(tcol, "")).strip() if tcol else ""
        q = str(r.get(qcol, "")).strip() if qcol else ""
        if not q:
            continue
        rows.append([ts, q, "", "", "", "", "", ""])

    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        w.writerows(rows)

    return cols


def log_nohit(question: str, extra: dict | None = None) -> str:
    """該当なしログを追記して、記録したtimestamp（秒）を返す。"""
    if not question:
        return ""
    extra = extra or {}
    day = datetime.now().strftime("%Y%m%d")
    path = LOG_DIR / f"nohit_{day}.csv"
    cols = _ensure_nohit_schema(path)

    ts = datetime.now().isoformat(timespec="seconds")
    row = {
        "timestamp": ts,
        "question": question,
        "device": extra.get("device", ""),
        "location": extra.get("location", ""),
        "network": extra.get("network", ""),
        "error_text": extra.get("error_text", ""),
        "impact": extra.get("impact", ""),
        "channel": extra.get("channel", "web"),
    }

    try:
        is_new = not path.exists()
        with path.open("a", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            if is_new:
                w.writerow(cols)
            w.writerow([row.get(c, "") for c in cols])
    except Exception:
        pass
    return ts


def update_nohit_record(day: str, timestamp: str, question: str, extra: dict) -> bool:
    """同じday/timestamp/question の行があれば更新。無ければ追記。"""
    if not day or not timestamp or not question:
        return False
    path = LOG_DIR / f"nohit_{day}.csv"
    cols = _ensure_nohit_schema(path)

    try:
        df_log = read_csv_flexible(path)
        if df_log is None:
            df_log = pd.DataFrame(columns=cols)
    except Exception:
        df_log = pd.DataFrame(columns=cols)

    # 必須列を揃える
    for c in cols:
        if c not in df_log.columns:
            df_log[c] = ""

    # 既存行を更新（最初の一致）
    mask = (df_log["timestamp"].astype(str) == str(timestamp)) & (df_log["question"].astype(str) == str(question))
    idxs = df_log.index[mask].tolist()
    if idxs:
        i = idxs[0]
        for k, v in (extra or {}).items():
            if k in df_log.columns:
                df_log.at[i, k] = v
        df_log.at[i, "channel"] = extra.get("channel", df_log.at[i, "channel"] or "web")
    else:
        # 無ければ追記
        row = {c: "" for c in cols}
        row["timestamp"] = timestamp
        row["question"] = question
        for k, v in (extra or {}).items():
            if k in row:
                row[k] = v
        if not row.get("channel"):
            row["channel"] = "web"
        df_log = pd.concat([df_log, pd.DataFrame([row])], ignore_index=True)

    # UTF-8で書き戻す（Excel対応ならutf-8-sigでもOK）
    try:
        with path.open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(cols)
            for _, r in df_log[cols].iterrows():
                w.writerow([str(r.get(c, "")) for c in cols])
        return True
    except Exception:
        return False


def seed_nohit_questions(n: int = 20) -> int:
    """本番前のデモ用：情シス定番のnohit質問を今日のログに追加する。"""
    seeds = [
        "VPNにつながらない", "Outlookの送受信ができない", "Teamsにログインできない", "パスワードを忘れた",
        "アカウントがロックされた", "共有フォルダにアクセスできない", "プリンタが印刷できない", "Wi-Fiが頻繁に切れる",
        "PCが重い", "PCが固まる", "Excelが起動しない", "Excelがフリーズする", "OneDriveが同期しない",
        "メール添付ファイルが開けない", "二段階認証が通らない", "カメラが映らない", "マイクが認識されない",
        "ソフトのインストール申請方法が分からない", "Windows更新が終わらない", "画面が真っ黒になる",
    ]
    added = 0
    for q in seeds[:n]:
        ts = log_nohit(q, {"channel": "seed"})
        if ts:
            added += 1
    return added



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




import json

def normalize_question(q: str) -> str:
    q = (q or "").strip().lower()
    q = re.sub(r"\s+", " ", q)
    # 日本語も含めて記号類をざっくり除去
    q = re.sub(r"[\u3000\s\t\r\n]+", " ", q)
    q = re.sub(r"[!！?？。、,.，:：;；\-_=+~`'\"()（）\[\]{}<>＜＞/\\|@#%^&*]", "", q)
    return q.strip()



def load_nohit_questions_from_logs(files, max_questions: int = 100) -> list[str]:
    """nohit_*.csv から質問を収集（新しいログから優先）。文字コード/カラム揺れに強く読む。"""
    questions: list[str] = []
    seen: set[str] = set()
    for p in files:
        try:
            _df = read_csv_flexible(Path(p))
            if _df is None or len(_df) == 0:
                continue

            qcol = pick_question_column(_df.columns)
            if not qcol:
                continue

            for q in _df[qcol].fillna("").astype(str).tolist():
                nq = normalize_question(q)
                if not nq:
                    continue
                if nq in seen:
                    continue
                seen.add(nq)
                questions.append(q.strip())
                if len(questions) >= max_questions:
                    return questions
        except Exception:
            continue
    return questions



def generate_faq_candidates(nohit_questions: list[str], n_items: int = 8) -> pd.DataFrame:
    """該当なしログからFAQ案を生成してDataFrameで返す（category/question/answer）。"""
    if not nohit_questions:
        return pd.DataFrame(columns=["category", "question", "answer"])

    # 入力が長すぎると落ちるので上限
    max_in = min(len(nohit_questions), 80)
    sample = nohit_questions[:max_in]
    examples = "\n".join([f"- {q}" for q in sample])

    prompt = f"""あなたは社内情シスのベテラン担当です。
以下は『FAQに該当なし』として蓄積された、社員からの問い合わせ例です。

【目的】
この問い合わせ例から、社内で使えるFAQ（Q&A）を {n_items} 件作成してください。

【要件】
- 日本語のみ
- 1件ごとに category / question / answer を作る
- answer は手順を箇条書きで（3〜7行）
- 個人情報や会社固有の秘密情報は作らない
- できるだけ汎用的（どの会社でも通用）に
- 出力は必ずJSONのみ（前後に説明文を入れない）
- コードブロック ``` は使わない

【出力JSON形式】
[
  {{"category":"VPN", "question":"...", "answer":"- ...\n- ..."}},
  ...
]

【問い合わせ例】
{examples}
"""

    out = llm_chat(
        [
            {"role": "system", "content": "あなたは情シスのFAQ作成者です。出力はJSONのみ。"},
            {"role": "user", "content": prompt},
        ]
    )

    out_text = out if isinstance(out, str) else str(out)

    json_text = extract_json_array(out_text) or out_text.strip()

    try:
        data = json.loads(json_text)
        if not isinstance(data, list):
            raise ValueError("JSON is not a list")
    except Exception:
        return pd.DataFrame(columns=["category", "question", "answer"])

    rows = []
    for item in data:
        if not isinstance(item, dict):
            continue
        cat = str(item.get("category", "")).strip()
        q = str(item.get("question", "")).strip()
        a = str(item.get("answer", "")).strip()
        if not q or not a:
            continue
        rows.append({"category": cat, "question": q, "answer": a})

    return pd.DataFrame(rows, columns=["category", "question", "answer"])

def append_faq_csv(faq_path: Path, new_df: pd.DataFrame) -> int:
    """faq.csv に追記。重複（question）をざっくり除外して追記件数を返す。"""
    if new_df is None or len(new_df) == 0:
        return 0

    # 必須列を揃える
    for col in ["question", "answer", "category"]:
        if col not in new_df.columns:
            new_df[col] = ""

    new_df = new_df[["question", "answer", "category"]].copy()
    new_df["question"] = new_df["question"].fillna("").astype(str).str.strip()
    new_df["answer"] = new_df["answer"].fillna("").astype(str).str.strip()
    new_df["category"] = new_df["category"].fillna("").astype(str).str.strip()
    new_df = new_df[(new_df["question"] != "") & (new_df["answer"] != "")]
    if len(new_df) == 0:
        return 0

    # 既存読み込み
    if faq_path.exists():
        try:
            exist = pd.read_csv(faq_path, encoding="utf-8", engine="python", on_bad_lines="skip")
        except Exception:
            exist = pd.DataFrame(columns=["question", "answer", "category"])
    else:
        exist = pd.DataFrame(columns=["question", "answer", "category"])

    exist_q = set(normalize_question(x) for x in exist.get("question", pd.Series(dtype=str)).fillna("").astype(str).tolist())

    rows = []
    for _, r in new_df.iterrows():
        nq = normalize_question(str(r.get("question", "")))
        if not nq:
            continue
        if nq in exist_q:
            continue
        exist_q.add(nq)
        rows.append([r["question"], r["answer"], r.get("category", "")])

    if not rows:
        return 0

    is_new = not faq_path.exists()
    with faq_path.open("a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if is_new:
            w.writerow(["question", "answer", "category"])
        w.writerows(rows)

    return len(rows)


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

        # ===== FAQ自動生成（該当なしログ → FAQ案）=====
        
        # =========================
        # 管理者向け資料（PDF）ダウンロード
        # =========================
        with st.expander("📘 管理者向け資料（PDF）", expanded=False):
            if not REPORTLAB_AVAILABLE:
                st.warning("PDF出力には reportlab が必要です。requirements.txt に reportlab を追加してください。")
            else:
                col_a, col_b = st.columns(2)
                with col_a:
                    ops_pdf = generate_ops_manual_pdf()
                    st.download_button(
                        "📄 操作説明書PDFをダウンロード",
                        data=ops_pdf,
                        file_name="操作説明書_情シス問い合わせAI.pdf",
                        mime="application/pdf",
                        use_container_width=True,
                    )
                with col_b:
                    proposal_pdf = generate_sales_proposal_pdf()
                    st.download_button(
                        "📑 提案資料PDFをダウンロード",
                        data=proposal_pdf,
                        file_name="提案資料_情シス問い合わせAI.pdf",
                        mime="application/pdf",
                        use_container_width=True,
                    )
                st.caption("※ どちらもアプリの現状に合わせて自動生成されます（必要に応じて文面はカスタマイズ可能）。")

        st.markdown("---")
        with st.expander("🧠 FAQ自動生成（該当なしログ → FAQ案）", expanded=False):
            st.caption("『該当なし』ログからFAQを自動生成し、faq.csvへ追記できます。")

            log_files = list_log_files()
            if not log_files:
                st.info("まだ nohit_*.csv がありません。まず質問して『該当なし』を発生させてください。")
            else:
                labels = [f.name for f in log_files[:15]]
                pick = st.selectbox("参照するログファイル", labels, index=0)
                picked_path = next((p for p in log_files if p.name == pick), log_files[0])

                max_q = st.slider("生成に使う質問数（重複除外後）", 10, 200, 60, step=10)
                n_items = st.slider("生成するFAQ件数", 3, 20, 8)

                col_seed1, col_seed2 = st.columns([2, 3])
                with col_seed1:
                    if st.button("🧪 デモ用に定番質問を追加（20件）"):
                        added = seed_nohit_questions(20)
                        st.success(f"nohitログに {added} 件追加しました。")
                        st.rerun()
                with col_seed2:
                    st.caption("※ 本番前にFAQ生成を試すためのテストデータです（channel=seedで記録）。")

                if st.button("🤖 FAQ案を自動生成", type="primary"):
                    with st.spinner("FAQ案を生成中..."):
                        qs = load_nohit_questions_from_logs([picked_path], max_questions=max_q)

                        # 生成前に「有効質問数」を可視化（原因切り分け）
                        st.info(f"ログから抽出できた有効質問数（重複除外後）：{len(qs)} 件")
                        if len(qs) < 5:
                            st.session_state.generated_faq_df = pd.DataFrame(columns=["category", "question", "answer"])
                            st.warning("有効な質問が少なすぎてFAQを生成できません。ログのCSV形式（カラム名/文字コード/区切り）を確認してください。")
                        else:
                            try:
                                gen_df = generate_faq_candidates(qs, n_items=n_items)
                            except Exception:
                                gen_df = pd.DataFrame(columns=["category", "question", "answer"])
                            st.session_state.generated_faq_df = gen_df

                gen_df = st.session_state.get("generated_faq_df")
                if isinstance(gen_df, pd.DataFrame) and len(gen_df) > 0:
                    st.markdown("### ✅ 生成結果（編集して保存できます）")
                    edited = st.data_editor(
                        gen_df,
                        num_rows="dynamic",
                        use_container_width=True,
                        key="faq_editor",
                    )

                    col_a, col_b = st.columns(2)
                    with col_a:
                        if st.button("💾 faq.csv に追記"):
                            added = append_faq_csv(FAQ_PATH, edited.rename(columns={"category": "category"}))
                            if added > 0:
                                st.success(f"faq.csv に {added} 件追記しました。")
                                # 反映のため再読み込み
                                st.session_state.generated_faq_df = pd.DataFrame()
                                st.rerun()
                            else:
                                st.warning("追記できる新規FAQがありません（重複/空欄の可能性）。")

                    with col_b:
                        if st.button("🧹 生成結果をクリア"):
                            st.session_state.generated_faq_df = pd.DataFrame()
                            st.rerun()
                elif isinstance(gen_df, pd.DataFrame) and len(gen_df) == 0 and st.session_state.get("generated_faq_df") is not None:
                    st.warning("FAQ案が生成できませんでした。ログの内容が少ないか、出力形式が崩れています。")
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



def render_nohit_extra_form(info: dict | None = None, expanded: bool = True):
    """『該当なし』直後に表示する追加情報フォーム（端末/利用場所/ネットワーク等）。"""
    info = info or (st.session_state.get("pending_nohit", {}) or {})
    with st.expander("📝 追加情報を記録（任意）", expanded=expanded):
        st.caption("該当なしのときだけ、状況を少しだけ補足するとFAQが育ちやすくなります。")
        with st.form("nohit_extra_form", clear_on_submit=False):
            c1, c2, c3 = st.columns(3)
            with c1:
                device = st.selectbox(
                    "端末",
                    ["", "Windows", "Mac", "iPhone/iPad", "Android", "不明"],
                    index=0,
                    key="nohit_device",
                )
            with c2:
                location = st.selectbox(
                    "利用場所",
                    ["", "社内", "社外", "不明"],
                    index=0,
                    key="nohit_location",
                )
            with c3:
                network = st.selectbox(
                    "ネットワーク",
                    ["", "Wi-Fi", "有線", "VPN", "モバイル回線", "不明"],
                    index=0,
                    key="nohit_network",
                )

            impact = st.selectbox(
                "影響範囲",
                ["", "自分のみ", "他の人も", "不明"],
                index=0,
                key="nohit_impact",
            )
            error_text = st.text_area(
                "エラー内容（任意）",
                placeholder="例：0x80190001 / '資格情報が無効です' など",
                key="nohit_error_text",
            )

            submitted = st.form_submit_button("✅ この内容で記録")
            if submitted:
                ok = update_nohit_record(
                    day=str(info.get("day", "")),
                    timestamp=str(info.get("timestamp", "")),
                    question=str(info.get("question", "")),
                    extra={
                        "device": device,
                        "location": location,
                        "network": network,
                        "impact": impact,
                        "error_text": error_text,
                        "channel": "web",
                    },
                )
                if ok:
                    st.success("追加情報をログに保存しました。ありがとうございます！")
                    # 次回以降はフォームを閉じる（保持は消す）
                    st.session_state["pending_nohit_active"] = False
                else:
                    st.warning("保存に失敗しました（もう一度お試しください）。")


# ======================
# 入力 → 検索 → 回答
# ======================
# ===== 該当なし（nohit）の追加情報フォーム =====
if st.session_state.get("pending_nohit_active"):
    render_nohit_extra_form(expanded=True)

# 先に chat_input を描画（画面下に固定されます）
chat_typed = st.chat_input("質問を入力してください")

# 入力が無いときは pending_q（おすすめボタン等）を使う
user_q = (chat_typed or st.session_state.get("pending_q", ""))

# 「おすすめ質問」など pending_q から来たかどうか
used_pending = (not chat_typed) and bool(st.session_state.get("pending_q", ""))

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
        ts_nohit = log_nohit(user_q)
        st.session_state["last_nohit"] = {"day": datetime.now().strftime("%Y%m%d"), "timestamp": ts_nohit, "question": user_q}
        was_nohit = True
    else:
        used_hits = hits
        was_nohit = False
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

        if 'was_nohit' in locals() and was_nohit:
            # 「該当なし」のとき、追加情報フォームを"次のrerunでも"表示できるように保持
            st.session_state["pending_nohit_active"] = True
            st.session_state["pending_nohit"] = st.session_state.get("last_nohit", {})
            st.info("該当なしログに追加しました。必要なら下の『追加情報を記録』で状況を補足できます。")
            # 送信直後（この実行）でも必ずフォームを表示
            render_nohit_extra_form(info=st.session_state.get('pending_nohit', {}), expanded=True)

    st.session_state.messages.append({"role": "assistant", "content": str(answer)})

    # おすすめ質問ボタンから自動送信した場合は、もう一度 rerun して入力欄を確実に表示
    if used_pending:
        st.rerun()