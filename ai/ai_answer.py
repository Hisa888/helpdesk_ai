from services.llm_router import chat

def generate_ai_answer(question, faq):

    prompt = f"""
以下のFAQを参考にユーザーの質問に回答してください。

FAQ
質問:{faq['question']}
回答:{faq['answer']}

ユーザー質問
{question}
"""

    return chat(prompt)