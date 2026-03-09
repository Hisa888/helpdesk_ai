import pandas as pd
from pathlib import Path

FAQ_PATH = Path("runtime_data/faq.csv")

def load_faq():

    if not FAQ_PATH.exists():

        return pd.DataFrame(columns=["question","answer","category"])

    return pd.read_csv(FAQ_PATH)