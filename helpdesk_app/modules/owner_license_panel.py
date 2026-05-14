from __future__ import annotations

from datetime import date, datetime

import pandas as pd

from helpdesk_app.modules.trial_license import (
    delete_tenant_license,
    list_tenant_licenses,
    upsert_tenant_license,
)


def _is_owner(st) -> bool:
    return str(st.session_state.get("tenant_role", "")).strip().lower() == "owner"


def render_owner_license_panel(st) -> None:
    """運営者専用: 会社ID・無料トライアル期限管理。

    顧客側の admin には表示せず、role=owner のIDだけに表示します。
    """
    if not _is_owner(st):
        return

    with st.expander("🏢 会社・ライセンス管理（運営者専用）", expanded=False):
        st.markdown(
            """
<div style="border:1px solid #bfdbfe;background:#eff6ff;border-radius:14px;padding:12px 14px;margin-bottom:12px;">
  <div style="font-weight:800;color:#1e3a8a;">この画面は運営者専用です</div>
  <div style="color:#334155;font-size:13px;line-height:1.7;margin-top:4px;">
    会社IDごとの無料トライアル期限・有効/停止を管理します。<br>
    ログインユーザーの追加は <code>TENANT_USERS</code> にも追加してください。
  </div>
</div>
            """,
            unsafe_allow_html=True,
        )

        rows = list_tenant_licenses()
        if rows:
            df = pd.DataFrame(rows)
            show_cols = [
                "tenant_id",
                "company_name",
                "license_type",
                "expire_date",
                "enabled",
                "max_users",
                "note",
                "updated_at",
            ]
            st.dataframe(df[[c for c in show_cols if c in df.columns]], use_container_width=True, hide_index=True)
        else:
            st.info("まだ会社ライセンスは登録されていません。下のフォームから登録してください。")

        st.markdown("#### 会社IDの登録・更新")
        with st.form("owner_tenant_license_form", clear_on_submit=False):
            col1, col2 = st.columns(2)
            with col1:
                tenant_id = st.text_input("会社ID", placeholder="例：abc", key="owner_license_tenant_id")
                company_name = st.text_input("会社名", placeholder="例：ABC商事", key="owner_license_company_name")
                license_type = st.selectbox(
                    "ライセンス種別",
                    options=["trial", "standard", "light", "enterprise", "demo", "owner"],
                    index=0,
                    key="owner_license_type",
                )
            with col2:
                expire_value = st.date_input("有効期限", value=date.today(), key="owner_license_expire_date")
                enabled = st.checkbox("有効", value=True, key="owner_license_enabled")
                max_users = st.number_input("最大ユーザー数（0=制限なし）", min_value=0, value=0, step=1, key="owner_license_max_users")
            note = st.text_area("メモ", placeholder="契約状況・要望など", key="owner_license_note")
            submitted = st.form_submit_button("会社ライセンスを保存", type="primary", use_container_width=True)

        if submitted:
            tenant_id_clean = str(tenant_id or "").strip().lower()
            if not tenant_id_clean:
                st.error("会社IDを入力してください。")
            else:
                expire_text = "" if license_type in ("standard", "enterprise", "owner") and not expire_value else expire_value.isoformat()
                upsert_tenant_license(
                    tenant_id=tenant_id_clean,
                    company_name=str(company_name or "").strip(),
                    license_type=str(license_type or "trial").strip(),
                    expire_date=expire_text,
                    enabled=bool(enabled),
                    max_users=int(max_users or 0),
                    note=str(note or "").strip(),
                )
                st.success(f"会社ID「{tenant_id_clean}」のライセンスを保存しました。")
                st.rerun()

        st.markdown("#### 停止・削除")
        delete_tenant_id = st.text_input("削除する会社ID", placeholder="例：abc", key="owner_delete_tenant_id")
        col_disable, col_delete = st.columns(2)
        with col_disable:
            if st.button("この会社IDを停止", use_container_width=True, key="owner_disable_tenant"):
                tid = str(delete_tenant_id or "").strip().lower()
                if tid:
                    upsert_tenant_license(tenant_id=tid, enabled=False, updated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                    st.warning(f"会社ID「{tid}」を停止しました。")
                    st.rerun()
                else:
                    st.error("会社IDを入力してください。")
        with col_delete:
            if st.button("この会社IDをライセンスDBから削除", use_container_width=True, key="owner_delete_tenant"):
                tid = str(delete_tenant_id or "").strip().lower()
                if tid:
                    delete_tenant_license(tid)
                    st.warning(f"会社ID「{tid}」をライセンスDBから削除しました。")
                    st.rerun()
                else:
                    st.error("会社IDを入力してください。")

        st.caption("※ ライセンスDBから削除しても、会社別のFAQ/RAG/ログデータフォルダは削除しません。")
