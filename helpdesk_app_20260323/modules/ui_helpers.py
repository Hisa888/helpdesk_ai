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

def render_match_bar(score: float):
    """一致度（0-1）をバーで表示"""
    try:
        v = float(score)
    except Exception:
        v = 0.0
    v = max(0.0, min(1.0, v))
    st.progress(v, text=f"一致度：{int(v*100)}%")
