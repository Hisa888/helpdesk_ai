import streamlit as st
from core.feature_flags import FLAGS, save_flags

def render_feature_flags():

    st.subheader("機能ON/OFF")

    flags = FLAGS.copy()

    for k in flags:

        flags[k] = st.checkbox(k, flags[k])

    if st.button("保存"):

        save_flags(flags)

        st.success("保存しました")