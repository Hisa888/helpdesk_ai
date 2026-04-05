from __future__ import annotations

import io
from datetime import datetime

import pandas as pd

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


def _pdf_set_stroke_fill(c, stroke="#0F172A", fill="#FFFFFF"):
    c.setStrokeColor(HexColor(stroke))
    c.setFillColor(HexColor(fill))


def _pdf_draw_box(c, x, y, w, h, title, subtitle=None, fill="#FFFFFF", stroke="#CBD5E1", title_color="#0F172A"):
    _pdf_set_stroke_fill(c, stroke=stroke, fill=fill)
    c.roundRect(x, y, w, h, 8, stroke=1, fill=1)
    c.setFillColor(HexColor(title_color))
    c.setFont("HeiseiKakuGo-W5", 10)
    lines = _wrap_lines_for_pdf(title, "HeiseiKakuGo-W5", 10, w - 12)
    yy = y + h - 14
    for ln in lines[:3]:
        c.drawString(x + 6, yy, ln)
        yy -= 12
    if subtitle:
        c.setFillColor(HexColor("#475569"))
        c.setFont("HeiseiKakuGo-W5", 8)
        for ln in _wrap_lines_for_pdf(subtitle, "HeiseiKakuGo-W5", 8, w - 12)[:3]:
            c.drawString(x + 6, yy, ln)
            yy -= 10


def _pdf_draw_arrow(c, x1, y1, x2, y2, color="#64748B"):
    import math
    c.setStrokeColor(HexColor(color))
    c.setLineWidth(1.2)
    c.line(x1, y1, x2, y2)
    ang = math.atan2(y2 - y1, x2 - x1)
    ah = 6
    a1 = ang + math.pi * 0.86
    a2 = ang - math.pi * 0.86
    c.line(x2, y2, x2 + ah * math.cos(a1), y2 + ah * math.sin(a1))
    c.line(x2, y2, x2 + ah * math.cos(a2), y2 + ah * math.sin(a2))


def _pdf_draw_section_band(c, x, y, w, label, fill="#E0F2FE", text_color="#075985"):
    _pdf_set_stroke_fill(c, stroke=fill, fill=fill)
    c.roundRect(x, y - 4, w, 14, 6, stroke=0, fill=1)
    c.setFillColor(HexColor(text_color))
    c.setFont("HeiseiKakuGo-W5", 10)
    c.drawString(x + 6, y, label)


def _pdf_draw_bullet_list(c, x, y, items, max_width_pt, font_size=11, bullet_color="#0EA5E9", text_color="#0F172A", gap_after=2):
    for item in items:
        c.setFillColor(HexColor(bullet_color))
        c.setFont("HeiseiKakuGo-W5", font_size)
        c.drawString(x, y, "•")
        c.setFillColor(HexColor(text_color))
        y = _pdf_draw_paragraph(c, x + 10, y, str(item), "HeiseiKakuGo-W5", font_size, max_width_pt - 10)
        y -= gap_after
    return y


def _pdf_draw_two_column_steps(c, x, y, col_w, left_title, left_items, right_title, right_items):
    _pdf_draw_section_band(c, x, y, col_w, left_title)
    _pdf_draw_section_band(c, x + col_w + 10 * mm, y, col_w, right_title, fill="#DCFCE7", text_color="#166534")
    y_body = y - 16
    y_left = _pdf_draw_bullet_list(c, x, y_body, left_items, col_w)
    y_right = _pdf_draw_bullet_list(c, x + col_w + 10 * mm, y_body, right_items, col_w, bullet_color="#22C55E")
    return min(y_left, y_right)


def _pdf_draw_flow(c, x0, y0):
    """PDFで崩れにくい、左基準の縦フロー図。本文はこの関数では描画しない。"""
    box_w = 95 * mm
    box_h = 18 * mm
    gap = 8 * mm

    steps = [
        ("① ユーザーが質問", "チャット / おすすめ質問から入力", "#F8FAFC", "#CBD5E1", "#0F172A"),
        ("② AIがFAQを検索", "登録済みのFAQから近い回答を探す", "#EFF6FF", "#60A5FA", "#1E3A8A"),
        ("③ 回答を表示", "参考FAQもあわせて表示", "#ECFDF5", "#4ADE80", "#166534"),
        ("④ 見つからない場合", "問い合わせテンプレートを表示", "#FEF3C7", "#F59E0B", "#92400E"),
        ("⑤ 管理者がログ確認", "不足FAQを追加して次回に備える", "#DCFCE7", "#22C55E", "#166534"),
    ]

    x = x0
    y = y0

    for idx, (title, subtitle, fill, stroke, title_color) in enumerate(steps):
        _pdf_draw_box(
            c, x, y, box_w, box_h, title, subtitle,
            fill=fill, stroke=stroke, title_color=title_color
        )

        if idx < len(steps) - 1:
            arrow_x = x + box_w / 2
            _pdf_draw_arrow(c, arrow_x, y, arrow_x, y - gap)

            if idx == 2:
                c.setFillColor(HexColor("#92400E"))
                c.setFont("HeiseiKakuGo-W5", 9)
                c.drawString(x, y - gap + 1.5 * mm, "解決しない場合は、問い合わせテンプレートへ進みます")

        y -= (box_h + gap)

    return y - 2 * mm

def _pdf_draw_growth_cycle(c, x0, y0):
    """FAQ育成サイクル図"""
    box_w = 38 * mm
    box_h = 15 * mm
    gap = 9 * mm
    coords = [
        (x0, y0, "① 該当なしを記録"),
        (x0 + box_w + gap, y0, "② ログを確認"),
        (x0 + box_w + gap, y0 - box_h - gap, "③ FAQを追加"),
        (x0, y0 - box_h - gap, "④ 次回から自動回答"),
    ]
    for x, y, label in coords:
        _pdf_draw_box(c, x, y, box_w, box_h, label, fill="#F8FAFC")
    _pdf_draw_arrow(c, x0 + box_w, y0 + box_h / 2, x0 + box_w + gap, y0 + box_h / 2)
    _pdf_draw_arrow(c, x0 + box_w + gap + box_w / 2, y0, x0 + box_w + gap + box_w / 2, y0 - gap)
    _pdf_draw_arrow(c, x0 + box_w + gap, y0 - box_h - gap + box_h / 2, x0 + box_w, y0 - box_h - gap + box_h / 2)
    _pdf_draw_arrow(c, x0 + box_w / 2, y0 - box_h - gap + box_h, x0 + box_w / 2, y0 - 2)
    return y0 - box_h - gap - 14 * mm


def _pdf_draw_value_cards(c, x, y, cards, total_width):
    """カード群を重なりなく描画する。上部ラベルは外に出し、カード内は見出し+説明だけにする。"""
    gap = 5 * mm
    label_gap = 3 * mm
    card_w = (total_width - gap * (len(cards) - 1)) / len(cards)
    card_h = 26 * mm
    label_h = 6 * mm
    side_pad = 6

    for idx, (title, value, note, fill, stroke) in enumerate(cards):
        cx = x + idx * (card_w + gap)
        label_y = y - label_h
        cy = label_y - label_gap - card_h

        _pdf_set_stroke_fill(c, stroke=stroke, fill=fill)
        c.roundRect(cx, label_y, card_w, label_h, 6, stroke=1, fill=1)
        c.setFillColor(HexColor("#334155"))
        c.setFont("HeiseiKakuGo-W5", 8)
        for i, ln in enumerate(_wrap_lines_for_pdf(title, "HeiseiKakuGo-W5", 8, card_w - side_pad * 2)[:1]):
            c.drawString(cx + side_pad, label_y + label_h - 10 - i * 8, ln)

        _pdf_set_stroke_fill(c, stroke=stroke, fill="#FFFFFF")
        c.roundRect(cx, cy, card_w, card_h, 8, stroke=1, fill=1)

        c.setFillColor(HexColor("#0F172A"))
        c.setFont("HeiseiKakuGo-W5", 14)
        value_y = cy + card_h - 16
        for ln in _wrap_lines_for_pdf(value, "HeiseiKakuGo-W5", 14, card_w - side_pad * 2)[:2]:
            c.drawString(cx + side_pad, value_y, ln)
            value_y -= 15

        c.setFillColor(HexColor("#475569"))
        c.setFont("HeiseiKakuGo-W5", 8)
        note_y = cy + 12
        for ln in _wrap_lines_for_pdf(note, "HeiseiKakuGo-W5", 8, card_w - side_pad * 2)[:2]:
            c.drawString(cx + side_pad, note_y, ln)
            note_y -= 9

    return cy - 6 * mm


def generate_ops_manual_pdf() -> bytes:
    """完全版の操作説明書PDF（誰でも理解できる説明 + 図解付き）"""
    if not REPORTLAB_AVAILABLE:
        return b""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    pdfmetrics.registerFont(UnicodeCIDFont("HeiseiKakuGo-W5"))

    w, h = A4
    margin = 18 * mm
    maxw = w - margin * 2

    # Page 1: cover
    _pdf_draw_title(c, "操作説明書_情シス問い合わせAI", "社員向け / 管理者向け / 誰でもわかる完全版")
    y = h - 52 * mm
    _pdf_draw_section_band(c, margin, y, 74 * mm, "この資料でわかること")
    y -= 18
    y = _pdf_draw_bullet_list(
        c,
        margin,
        y,
        [
            "このAIで何ができるのか",
            "社員がどの順番で使えばよいのか",
            "回答が見つからない時にどう動けばよいのか",
            "管理者がFAQを育てて精度を上げる方法",
        ],
        maxw,
    )
    y -= 3
    _pdf_draw_section_band(c, margin, y, 90 * mm, "最初に知っておきたいこと", fill="#DCFCE7", text_color="#166534")
    y -= 18
    y = _pdf_draw_paragraph(
        c,
        margin,
        y,
        "このシステムは、社内のITに関するよくある質問へすぐに答えるための問い合わせAIです。\n"
        "まずAIに質問し、解決できない場合だけ情シス担当者へ問い合わせる運用にすると、対応時間を減らしながら回答品質をそろえられます。",
        "HeiseiKakuGo-W5",
        11,
        maxw,
    )
    c.setFont("HeiseiKakuGo-W5", 10)
    c.setFillColor(HexColor("#64748B"))
    c.drawString(margin, 18 * mm, f"生成日: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    c.showPage()

    # Page 2: what it does
    _pdf_draw_title(c, "1. このAIでできること", "まずは全体像をつかむ")
    y = h - 52 * mm
    cards = [
        ("すぐに答える", "FAQ検索", "登録済みの質問と回答を探します", "#EFF6FF", "#93C5FD"),
        ("根拠を見せる", "参考FAQ表示", "どのFAQを元にしたか確認できます", "#ECFEFF", "#67E8F9"),
        ("迷った時を助ける", "テンプレ表示", "必要情報をそろえて問い合わせできます", "#FEFCE8", "#FDE68A"),
    ]
    y = _pdf_draw_value_cards(c, margin, y, cards, maxw)
    y = _pdf_draw_bullet_list(
        c,
        margin,
        y,
        [
            "よくある問い合わせにすぐ回答します。",
            "AIの答えとあわせて、参考にしたFAQ候補も表示します。",
            "回答が見つからない場合は、問い合わせ時に必要な項目をテンプレートで案内します。",
            "管理者はFAQファイルの入れ替え、問い合わせログの確認、PDF資料のダウンロードができます。",
            "使われ方のログを見ながら、FAQを追加して精度を上げていけます。",
        ],
        maxw,
    )
    y -= 5
    _pdf_draw_section_band(c, margin, y, 84 * mm, "利用イメージ", fill="#F8FAFC", text_color="#334155")
    y -= 18
    y = _pdf_draw_paragraph(
        c,
        margin,
        y,
        "例: 社員が『Wi-Fiがつながらない』と入力すると、AIはFAQを探して最も近い回答を表示します。\n"
        "答えが見つからない時は、端末名・利用場所・発生時刻など、情シスが確認したい情報をそろえた問い合わせテンプレートを表示します。",
        "HeiseiKakuGo-W5",
        11,
        maxw,
    )
    c.showPage()

    # Page 3: employee flow
    _pdf_draw_title(c, "2. 社員の使い方", "まずはこの順番で使います")
    y = h - 52 * mm
    y = _pdf_draw_bullet_list(
        c,
        margin,
        y,
        [
            "画面の入力欄に困っている内容をそのまま入力します。",
            "表示された回答を読み、必要に応じて参考FAQも確認します。",
            "その場で解決できたら完了です。",
            "解決しない時は、問い合わせテンプレートに沿って情シスへ連絡します。",
        ],
        maxw,
    )
    y -= 8

    c.setFillColor(HexColor("#0F172A"))
    c.setFont("HeiseiKakuGo-W5", 11)
    c.drawString(margin, y, "問い合わせ対応の流れ")
    y -= 80
    y = _pdf_draw_flow(c, margin, y)
    y = _pdf_draw_paragraph(
        c,
        margin,
        y,
        "見つかった回答だけで解決できる質問は、情シスへ連絡せずにその場で自己解決できます。\n"
        "回答が見つからない質問はログに残るため、後からFAQへ追加して再発防止につなげられます。",
        "HeiseiKakuGo-W5",
        10,
        maxw,
    )
    c.showPage()

    # Page 4: admin steps
    _pdf_draw_title(c, "3. 管理者の使い方", "左メニューの管理者画面で行うこと")
    y = h - 52 * mm
    col_w = (maxw - 10 * mm) / 2
    y = _pdf_draw_two_column_steps(
        c,
        margin,
        y,
        col_w,
        "毎日または週次で確認すること",
        [
            "問い合わせログ状況を見て、該当なしの増減を確認する。",
            "必要に応じてログCSVをダウンロードする。",
            "利用状況や削減時間シミュレーションを確認する。",
        ],
        "FAQを改善する時に行うこと",
        [
            "FAQをExcelでダウンロードして現在内容を確認する。",
            "不足しているQ&Aを追加したExcelまたはCSVをアップロードする。",
            "反映後、必要に応じてキャッシュクリアや再確認を行う。",
        ],
    )
    y -= 4
    _pdf_draw_section_band(c, margin, y, 92 * mm, "管理者向けPDFでできること", fill="#FEF3C7", text_color="#92400E")
    y -= 18
    y = _pdf_draw_bullet_list(
        c,
        margin,
        y,
        [
            "操作説明書PDF: 社員や管理者へ使い方を説明する時に利用します。",
            "提案資料PDF: 導入効果や導入ステップを説明する営業資料として利用します。",
            "導入効果レポートPDF: 実際のログを元に削減時間や削減額の試算を共有できます。",
        ],
        maxw,
        bullet_color="#F59E0B",
    )
    c.showPage()

    # Page 5: FAQ growth cycle and rules
    _pdf_draw_title(c, "4. AIを育てる運用", "使うほど精度が上がる仕組み")
    y = h - 52 * mm
    c.setFillColor(HexColor("#0F172A"))
    c.setFont("HeiseiKakuGo-W5", 11)
    c.drawString(margin, y, "FAQ改善サイクル")
    y -= 10
    bottom = _pdf_draw_growth_cycle(c, margin, y - 28 * mm)
    y = bottom + 10 * mm
    y = _pdf_draw_bullet_list(
        c,
        margin,
        y,
        [
            "該当なしの質問をためるだけで終わらせず、週1回など決めて確認します。",
            "同じ内容が複数回出ているものは優先してFAQへ追加します。",
            "回答文は短く、社内で実際に使う手順や連絡先まで書くと使いやすくなります。",
            "個人情報・機密情報は入力しない運用ルールを明確にしてください。",
            "FAQ更新後は、必要に応じて反映確認を行ってから社内へ案内します。",
        ],
        maxw,
    )
    y -= 6
    _pdf_draw_section_band(c, margin, y, 70 * mm, "おすすめの社内周知文", fill="#E0F2FE", text_color="#075985")
    y -= 18
    y = _pdf_draw_paragraph(
        c,
        margin,
        y,
        "『まずは情シス問い合わせAIで確認してください。回答が見つからない場合だけ、表示されたテンプレートを添えて問い合わせしてください。』\n"
        "この一文を社内ポータルやTeams/Slackの案内に載せると、自己解決の定着に役立ちます。",
        "HeiseiKakuGo-W5",
        10,
        maxw,
    )

    c.save()
    buf.seek(0)
    return buf.getvalue()


def generate_sales_proposal_pdf() -> bytes:
    """コンサルレベルの営業提案資料PDF（図解・導入効果・提案ストーリー付き）"""
    if not REPORTLAB_AVAILABLE:
        return b""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    pdfmetrics.registerFont(UnicodeCIDFont("HeiseiKakuGo-W5"))

    w, h = A4
    margin = 18 * mm
    maxw = w - margin * 2

    # Page 1: cover
    _pdf_draw_title(c, "提案資料_情シス問い合わせAI", "社内問い合わせを減らし、対応品質をそろえるための提案書")
    y = h - 54 * mm
    _pdf_draw_section_band(c, margin, y, 78 * mm, "提案の結論")
    y -= 18
    y = _pdf_draw_paragraph(
        c,
        margin,
        y,
        "情シス問い合わせAIを導入することで、よくある問い合わせを自己解決へ誘導し、\n"
        "情シス担当者は本当に人手が必要な問い合わせへ集中できるようになります。",
        "HeiseiKakuGo-W5",
        12,
        maxw,
    )
    y -= 6
    cards = [
        ("問い合わせ削減", "一次対応を自動化", "同じ質問への繰り返し対応を減らす", "#EFF6FF", "#93C5FD"),
        ("品質平準化", "回答をそろえる", "担当者ごとの差を減らす", "#F0FDF4", "#86EFAC"),
        ("ナレッジ蓄積", "FAQが育つ", "ログから不足FAQを追加できる", "#FEFCE8", "#FDE68A"),
    ]
    y = _pdf_draw_value_cards(c, margin, y, cards, maxw)
    c.setFont("HeiseiKakuGo-W5", 10)
    c.setFillColor(HexColor("#64748B"))
    c.drawString(margin, 18 * mm, f"生成日: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    c.showPage()

    # Page 2: issues and solution
    _pdf_draw_title(c, "1. 現状課題と解決方針", "よくある課題をどう解決するか")
    y = h - 52 * mm
    y = _pdf_draw_two_column_steps(
        c,
        margin,
        y,
        (maxw - 10 * mm) / 2,
        "現場で起きがちな課題",
        [
            "同じ問い合わせが繰り返し発生している。",
            "担当者によって回答内容やスピードがばらつく。",
            "問い合わせ文に必要情報が不足し、切り分けに時間がかかる。",
            "FAQが更新されず、知識が属人化する。",
        ],
        "本提案の解決方針",
        [
            "まずAIに聞く導線をつくり、よくある質問を自己解決へ導く。",
            "FAQを元にした回答で、誰でも同じ案内ができる状態をつくる。",
            "見つからない場合はテンプレートで必要情報をそろえる。",
            "該当なしログからFAQを追加し、継続的に改善する。",
        ],
    )
    y -= 4
    _pdf_draw_section_band(c, margin, y, 85 * mm, "導入後の期待効果", fill="#DCFCE7", text_color="#166534")
    y -= 18
    y = _pdf_draw_bullet_list(
        c,
        margin,
        y,
        [
            "一次対応の自動化により、情シス担当者の負荷を下げる。",
            "回答品質を標準化し、新人や兼任担当でも案内しやすくする。",
            "問い合わせログを改善材料に変え、FAQ資産を増やす。",
        ],
        maxw,
        bullet_color="#22C55E",
    )
    c.showPage()

    # Page 3: process diagram
    _pdf_draw_title(c, "2. システムの仕組み", "問い合わせから改善までを1つの流れにする")
    y = h - 52 * mm
    c.setFillColor(HexColor("#0F172A"))
    c.setFont("HeiseiKakuGo-W5", 11)
    c.drawString(margin, y, "運用フロー図")
    y -= 10
    y = _pdf_draw_flow(c, margin, y)
    y = _pdf_draw_paragraph(
        c,
        margin,
        y,
        "ポイントは、回答できた質問だけでなく、回答できなかった質問も価値あるデータとして残ることです。\n"
        "この仕組みによって、導入直後はFAQが少なくても、使うほど回答範囲を広げられます。",
        "HeiseiKakuGo-W5",
        11,
        maxw,
    )
    y -= 4
    c.setFillColor(HexColor("#0F172A"))
    c.setFont("HeiseiKakuGo-W5", 11)
    c.drawString(margin, y, "FAQ育成サイクル")
    _pdf_draw_growth_cycle(c, margin, y - 26 * mm)
    c.showPage()

    # Page 4: ROI and model case
    _pdf_draw_title(c, "3. 導入効果の考え方", "削減時間を数字で説明する")
    y = h - 52 * mm
    cards = [
        ("モデルケース", "100件/月", "月100件の問い合わせを想定", "#F8FAFC", "#CBD5E1"),
        ("平均対応時間", "5分/件", "情シスが1件対応する平均", "#F8FAFC", "#CBD5E1"),
        ("削減時間", "約8時間/月", "100件 x 5分 = 500分", "#ECFEFF", "#67E8F9"),
    ]
    y = _pdf_draw_value_cards(c, margin, y, cards, maxw)
    y = _pdf_draw_paragraph(
        c,
        margin,
        y,
        "例として、月100件・1件5分の問い合わせがある場合、単純計算で月500分の対応時間が発生しています。\n"
        "このうち多くをAIで自己解決へ回せれば、月約8時間、年間では約96時間の削減余地があります。",
        "HeiseiKakuGo-W5",
        11,
        maxw,
    )
    y -= 6
    _pdf_draw_section_band(c, margin, y, 78 * mm, "経営層への説明ポイント", fill="#FEF3C7", text_color="#92400E")
    y -= 18
    y = _pdf_draw_bullet_list(
        c,
        margin,
        y,
        [
            "削減時間 = 問い合わせ件数 x 1件あたり対応時間 x AIで自己解決できる割合",
            "人件費換算を入れると、投資対効果を説明しやすくなる",
            "数値効果に加えて、回答品質の標準化や問い合わせ品質向上も副次効果として大きい",
        ],
        maxw,
        bullet_color="#F59E0B",
    )
    c.showPage()

    # Page 5: implementation plan
    _pdf_draw_title(c, "4. 導入ステップ", "最短でデモから本運用まで進める")
    y = h - 52 * mm
    y = _pdf_draw_bullet_list(
        c,
        margin,
        y,
        [
            "Step 1 現状確認: よくある問い合わせ、対応ルール、入力してはいけない情報を確認する。",
            "Step 2 FAQ準備: まずは30〜100件程度のFAQをCSVまたはExcelで用意する。",
            "Step 3 デモ公開: Streamlit上で社内向けに試験公開し、使い方を周知する。",
            "Step 4 ログ改善: 該当なしログを確認し、足りないFAQを追加する。",
            "Step 5 横展開: 総務、人事、経理など他部門の問い合わせへ拡張する。",
        ],
        maxw,
    )
    y -= 8
    _pdf_draw_section_band(c, margin, y, 84 * mm, "初回提案時に確認したい項目", fill="#E0F2FE", text_color="#075985")
    y -= 18
    y = _pdf_draw_bullet_list(
        c,
        margin,
        y,
        [
            "月間の問い合わせ件数",
            "1件あたり平均対応時間",
            "よくある問い合わせ上位10件",
            "社内で利用する連絡手段（メール / Teams / Slack など）",
            "個人情報や機密情報の取り扱いルール",
        ],
        maxw,
        bullet_color="#0EA5E9",
    )
    c.showPage()

    # Page 6: proposal closing
    _pdf_draw_title(c, "5. ご提案のまとめ", "小さく始めて、着実に育てる")
    y = h - 52 * mm
    y = _pdf_draw_paragraph(
        c,
        margin,
        y,
        "情シス問い合わせAIは、大規模なシステム刷新ではなく、既存のFAQ資産を活用しながら小さく始められる改善策です。\n"
        "まずはよくある問い合わせから対象にし、回答できなかった質問をログから追加する運用にすることで、短期間でも効果を体感しやすい構成です。",
        "HeiseiKakuGo-W5",
        11,
        maxw,
    )
    y -= 8
    _pdf_draw_section_band(c, margin, y, 64 * mm, "次のアクション", fill="#DCFCE7", text_color="#166534")
    y -= 18
    y = _pdf_draw_bullet_list(
        c,
        margin,
        y,
        [
            "問い合わせ例を10件いただければ、デモFAQを作成できます。",
            "月間件数・平均対応時間・単価がわかれば、削減効果の試算ができます。",
            "社内向け説明用として、本資料と操作説明書PDFをそのまま活用できます。",
        ],
        maxw,
        bullet_color="#22C55E",
    )

    c.save()
    buf.seek(0)
    return buf.getvalue()



# ===== PDF互換ラッパー（旧v25参照が残っていても落ちないようにする） =====
def _pdf_draw_bullet_list_safe(c, x, y, items, max_width_pt, font_size=11, bullet_color="#0EA5E9", text_color="#0F172A", gap_after=2):
    """旧PDFコード互換。既存の _pdf_draw_bullet_list が使えるならそれを優先し、
    使えない場合のみ簡易描画でフォールバックする。"""
    fn = globals().get("_pdf_draw_bullet_list")
    if callable(fn):
        return fn(c, x, y, items, max_width_pt, font_size=font_size, bullet_color=bullet_color, text_color=text_color, gap_after=gap_after)

    for item in items:
        try:
            c.setFillColor(HexColor(bullet_color))
        except Exception:
            pass
        try:
            c.setFont("HeiseiKakuGo-W5", font_size)
        except Exception:
            pass
        try:
            c.drawString(x, y, "•")
        except Exception:
            pass
        try:
            c.setFillColor(HexColor(text_color))
        except Exception:
            pass

        para = globals().get("_pdf_draw_paragraph")
        if callable(para):
            y = para(c, x + 10, y, str(item), "HeiseiKakuGo-W5", font_size, max_width_pt - 10)
        else:
            try:
                c.drawString(x + 10, y, str(item))
            except Exception:
                pass
            y -= font_size * 1.35
        y -= gap_after
    return y


def generate_sales_proposal_pdf_v25() -> bytes:
    """旧UI互換。v25名で呼ばれても現行の提案資料PDF生成へ委譲する。"""
    return generate_sales_proposal_pdf()

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
