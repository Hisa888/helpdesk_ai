import csv
from datetime import datetime
from pathlib import Path

LOG_DIR = Path("runtime_data/logs")

def save_nohit_log(question):

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    day = datetime.now().strftime("%Y%m%d")

    path = LOG_DIR / f"nohit_{day}.csv"

    with open(path,"a",newline="",encoding="utf-8") as f:

        writer = csv.writer(f)

        writer.writerow([datetime.now(),question])