from pathlib import Path
from datetime import datetime, timedelta
import base64
import csv
import io
import json
import os
import re
import threading
import zipfile

import pandas as pd
import requests
import streamlit as st
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

def render_match_bar(score: float, label: str = "一致度"):
    """一致度（0-1）をバーで表示

    label を指定すると、FAQ一致度 / ドキュメント一致度のように
    ユーザーが意味を判別できる表示にできます。
    """
    try:
        v = float(score)
    except Exception:
        v = 0.0
    v = max(0.0, min(1.0, v))
    label = str(label or "一致度").strip()
    st.progress(v, text=f"{label}：{int(v*100)}%")
