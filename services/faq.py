import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

def load_faq_index(faq_path str)
    df = pd.read_csv(faq_path, encoding=utf-8-sig)
    df[qa_text] = (df[question].fillna() +    + df[answer].fillna()).astype(str)

    vectorizer = TfidfVectorizer(analyzer=word, ngram_range=(1, 2), min_df=1)
    X = vectorizer.fit_transform(df[qa_text].tolist())
    return df, vectorizer, X

def retrieve_faq(df, vectorizer, X, query str, top_k int)
    qv = vectorizer.transform([query])
    sims = cosine_similarity(qv, X).flatten()
    idxs = sims.argsort()[-1][top_k]
    hits = [(df.iloc[i], float(sims[i])) for i in idxs]
    return hits

def build_prompt(user_q str, hits)
    context_lines = []
    for j, (row, score) in enumerate(hits, 1)
        context_lines.append(
            f[FAQ{j}] score={score.3f} category={row.get('category','')} owner={row.get('owner','')}n
            fQ {row['question']}n
            fA {row['answer']}n
        )
    context = n.join(context_lines)

    return f
あなたは社内の情シスヘルプデスク担当です。回答は日本語で丁寧に、手順は箇条書きで。

# ルール
- 次の「参照FAQ」だけを根拠に回答し、推測や創作はしない。
- FAQに該当が無い根拠が弱い場合は、必ず「情シスへ問い合わせ（チケット発行）してください」と案内する。
- 問い合わせ誘導の際は、確認すべき情報を箇条書き（OS、端末名、エラー文、発生時刻、ネットワーク種別、再現手順など）で出す。
- 最後に「参照：FAQ番号」を必ず書く（該当なしの場合は「参照：該当なし」）。

# 参照FAQ
{context}

# 質問
{user_q}

# 出力形式
- 結論（1〜2行）
- 手順（箇条書き）
- 注意点（必要なら）
- 参照：FAQ番号
.strip()