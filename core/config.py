import streamlit as st
from pathlib import Path

def init_app():

    st.set_page_config(
        page_title="情シス問い合わせAI",
        layout="wide"
    )

    Path("runtime_data/logs").mkdir(parents=True, exist_ok=True)