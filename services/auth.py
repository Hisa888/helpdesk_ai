import streamlit as st

def check_password(password: str) -> bool:
    admin_password = "admin123"
    return password == admin_password
