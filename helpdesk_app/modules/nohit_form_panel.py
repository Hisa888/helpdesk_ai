from __future__ import annotations

from helpdesk_app.modules.contact_cta_panel import render_answer_contact_cta


def render_nohit_extra_form(*, st, update_nohit_record, info: dict | None = None, expanded: bool = True):
    info = info or (st.session_state.get("pending_nohit", {}) or {})

    # 見出し崩れとフォーム警告を避けるため、通常コンテナ + ボタン構成にする
    st.write("")
    with st.expander("追加情報を記録（任意）", expanded=expanded):
        st.caption("解決しない場合は、状況を少し補足するとFAQ改善に役立ちます。")
        render_answer_contact_cta(st=st, was_nohit=True)

        c1, c2, c3 = st.columns(3)

        with c1:
            device = st.selectbox(
                "端末",
                ["", "Windows", "Mac", "iPhone/iPad", "Android", "不明"],
                index=0,
                key="nohit_device",
            )
        with c2:
            location = st.selectbox(
                "利用場所",
                ["", "社内", "社外", "不明"],
                index=0,
                key="nohit_location",
            )
        with c3:
            network = st.selectbox(
                "ネットワーク",
                ["", "Wi-Fi", "有線", "VPN", "モバイル回線", "不明"],
                index=0,
                key="nohit_network",
            )

        impact = st.selectbox(
            "影響範囲",
            ["", "自分のみ", "他の人も", "不明"],
            index=0,
            key="nohit_impact",
        )
        error_text = st.text_area(
            "エラー内容（任意）",
            placeholder="例：0x80190001 / '資格情報が無効です' など",
            key="nohit_error_text",
        )

        if st.button("この内容で記録", key="save_nohit_extra", width="stretch"):
            ok = update_nohit_record(
                day=str(info.get("day", "")),
                timestamp=str(info.get("timestamp", "")),
                question=str(info.get("question", "")),
                extra={
                    "device": device,
                    "location": location,
                    "network": network,
                    "impact": impact,
                    "error_text": error_text,
                    "channel": "web",
                },
            )

            if ok:
                st.success("追加情報をログに保存しました。ありがとうございます！")
                st.session_state["pending_nohit_active"] = False
            else:
                st.warning("保存に失敗しました（もう一度お試しください）。")
