import streamlit as st
from admin.feature_toggle_ui import render_feature_flags

def render_admin_panel():

    st.sidebar.title("管理者")

    render_feature_flags()