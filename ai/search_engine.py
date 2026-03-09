from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

def search_faq(question, faq_df):

    vect = TfidfVectorizer()

    matrix = vect.fit_transform(faq_df["question"])

    q = vect.transform([question])

    sim = cosine_similarity(q, matrix)[0]

    idx = sim.argmax()

    return {
        "faq": faq_df.iloc[idx],
        "score": sim[idx]
    }