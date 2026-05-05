from __future__ import annotations

from helpdesk_app.modules.contact_cta_panel import render_answer_contact_cta


def render_nohit_extra_form(*, st, update_nohit_record, info: dict | None = None, expanded: bool = False):
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
            "依頼内容（任意）",
            placeholder="例：ポケットWiFiが使えなくなった、申請書の作成を依頼したい など",
            key="nohit_error_text",
        )

        if st.button("この内容で記録", key="save_nohit_extra", width="stretch"):
            # 候補表示から開いた場合は timestamp が空になることがあるため、
            # 保存側で追記できるように最低限の値を補完します。
            from datetime import datetime
            day_value = str(info.get("day", "") or datetime.now().strftime("%Y%m%d"))
            timestamp_value = str(info.get("timestamp", "") or datetime.now().isoformat(timespec="seconds"))
            question_value = str(
                info.get("question", "")
                or st.session_state.get("last_user_q_for_learning", "")
                or st.session_state.get("pending_q", "")
                or "追加情報"
            )

            ok = update_nohit_record(
                day=day_value,
                timestamp=timestamp_value,
                question=question_value,
                extra={
                    "device": device,
                    "location": location,
                    "network": network,
                    "impact": impact,
                    "request_text": error_text,
                    "error_text": error_text,  # 既存ログ互換のため残す
                    "channel": "web",
                },
            )

            if ok:
                st.success("追加情報をログに保存しました。ありがとうございます！")
                st.session_state["pending_nohit_active"] = False
            else:
                st.warning("保存に失敗しました（もう一度お試しください）。")
