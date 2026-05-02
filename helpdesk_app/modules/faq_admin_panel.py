from __future__ import annotations

import pandas as pd


FAQ_ADMIN_COLUMNS = [
    "faq_id", "question", "answer", "intent", "keywords", "category",
    "answer_format", "enabled", "updated_at", "updated_by", "note",
]
FAQ_UPLOAD_COLUMNS = ["operation"] + FAQ_ADMIN_COLUMNS


def _empty_faq_df() -> pd.DataFrame:
    return pd.DataFrame(columns=FAQ_ADMIN_COLUMNS)


def load_current_faq_df(ns: dict) -> pd.DataFrame:
    normalize_faq_columns = ns["normalize_faq_columns"]
    read_csv_flexible = ns["read_csv_flexible"]
    FAQ_PATH = ns["FAQ_PATH"]
    return normalize_faq_columns(read_csv_flexible(FAQ_PATH)) if FAQ_PATH.exists() else _empty_faq_df()


def clear_faq_admin_runtime(ns: dict, latest_df: pd.DataFrame | None = None) -> None:
    """FAQ更新後にFAQ検索系キャッシュだけを更新する。

    メモリ爆速版:
    - st.cache_resource.clear() / st.cache_data.clear() は使わない
    - 保存直後のDataFrameから検索インデックスを直接メモリへprimeする
    - 次の問い合わせでDB/CSVを読み直さない
    """
    load_faq_index = ns["load_faq_index"]
    get_faq_index_state = ns["get_faq_index_state"]
    reset_faq_index_runtime = ns["reset_faq_index_runtime"]
    prime_faq_index_from_df = ns.get("prime_faq_index_from_df")

    for fn in (load_faq_index, get_faq_index_state):
        try:
            fn.clear()
        except Exception:
            pass

    if latest_df is not None and callable(prime_faq_index_from_df):
        try:
            prime_faq_index_from_df(latest_df)
            return
        except Exception:
            pass

    try:
        reset_faq_index_runtime()
    except Exception:
        pass


def replace_faq_from_uploaded_df(ns: dict, incoming_df: pd.DataFrame) -> tuple[int, pd.DataFrame]:
    """FAQを保存して、反映後DataFrameを返す。

    保存直後にDBから全件SELECTし直すと、アップロード行数が多い場合に
    体感がかなり遅くなる。保存対象の incoming_df はすでに最終形なので、
    正規化済みDataFrameをそのまま返して再読込を省略する。
    """
    save_faq_csv_full = ns["save_faq_csv_full"]
    normalize_faq_columns = ns["normalize_faq_columns"]
    FAQ_PATH = ns["FAQ_PATH"]
    persist_faq_now = ns.get("persist_faq_now")

    final_df = normalize_faq_columns(incoming_df)
    saved = save_faq_csv_full(FAQ_PATH, final_df, persist_callback=persist_faq_now, already_normalized=True)
    clear_faq_admin_runtime(ns, latest_df=final_df)
    return int(saved), final_df


def apply_faq_operation_result(ns: dict, result_df: pd.DataFrame, summary: dict | None = None) -> tuple[int, pd.DataFrame]:
    saved, reloaded_df = replace_faq_from_uploaded_df(ns, result_df)
    append_history = ns.get("append_faq_import_history")
    if callable(append_history) and summary:
        try:
            append_history(ns["FAQ_PATH"], summary, persist_callback=ns.get("persist_faq_now"))
        except Exception:
            # 履歴出力に失敗してもFAQ本体の反映は止めない
            pass
    return saved, reloaded_df


def _to_preview_df(df: pd.DataFrame) -> pd.DataFrame:
    rename = {
        "operation": "操作",
        "faq_id": "FAQ_ID",
        "question": "質問",
        "answer": "回答",
        "intent": "意図",
        "keywords": "キーワード・言い換え",
        "category": "カテゴリ",
        "answer_format": "表示形式",
        "enabled": "有効",
        "updated_at": "更新日",
        "updated_by": "更新者",
        "note": "備考",
    }
    return df.rename(columns=rename)


def _build_operation_template_df(current_faq_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    if len(current_faq_df) > 0:
        first = current_faq_df.iloc[0].to_dict()
        first["operation"] = ""
        first["answer"] = str(first.get("answer", "")) + "\n\n※この行は操作が空白なので、FAQ_IDに一致する既存FAQを更新します。"
        rows.append(first)
    else:
        rows.append({
            "operation": "",
            "faq_id": "FAQ-000001",
            "question": "Windowsのパスワードを忘れました。",
            "answer": "Windowsのパスワードを忘れた場合は、パスワード再設定画面から再設定してください。",
            "intent": "Windowsログイン用パスワードを再設定したい",
            "keywords": "ログインできない, パスワード忘れた, アカウントロック",
            "category": "アカウント / パスワード",
            "answer_format": "markdown",
            "enabled": "TRUE",
            "updated_at": "",
            "updated_by": "",
            "note": "初回テンプレート",
        })
    rows.append({
        "operation": "+",
        "faq_id": "",
        "question": "Teamsをインストールしたいです。",
        "answer": "Teamsのインストールは、システム作業申請書を使用して申請してください。\n\n手順:\n1. 該当する書式を開きます。\n2. 必要事項を入力します。\n3. 社内ルールに従って承認・提出してください。",
        "intent": "Teamsアプリのインストール申請方法を知りたい",
        "keywords": "Teams, アプリ, ソフト, インストール, 導入, 申請",
        "category": "アプリ / 申請",
        "answer_format": "markdown",
        "enabled": "TRUE",
        "updated_at": "",
        "updated_by": "",
        "note": "新規追加例",
    })
    if len(current_faq_df) > 1:
        delete_row = current_faq_df.iloc[1].to_dict()
        delete_row["operation"] = "-"
        rows.append(delete_row)
    else:
        rows.append({
            "operation": "-",
            "faq_id": "FAQ-000002",
            "question": "削除したい既存FAQの質問を入れてください。",
            "answer": "",
            "intent": "",
            "keywords": "",
            "category": "",
            "answer_format": "markdown",
            "enabled": "TRUE",
            "updated_at": "",
            "updated_by": "",
            "note": "削除例",
        })
    return pd.DataFrame(rows, columns=FAQ_UPLOAD_COLUMNS)


def render_faq_admin_panel(ns: dict) -> None:
    st = ns["st"]
    faq_df_to_excel_bytes = ns["faq_df_to_excel_bytes"]
    read_faq_uploaded_file = ns["read_faq_uploaded_file"]
    read_faq_operation_uploaded_file = ns.get("read_faq_operation_uploaded_file")
    apply_faq_upload_operations = ns.get("apply_faq_upload_operations")
    get_current_admin_name = ns.get("get_current_admin_name") or (lambda: "管理者")

    with st.expander("📂 FAQ管理（Excelダウンロード / アップロード）", expanded=False):
        st.caption("管理者は FAQ を Excel(.xlsx) で一括入出力できます。差分反映では『操作』列を使います。+ は追加、- は削除、空白は更新です。更新日・更新者はFAQ反映時に自動設定されます。")
        st.info("推奨運用: 現在のFAQをExcelでダウンロード → 操作列に + / - / 空白を指定 → アップロード → プレビュー確認後に反映します。更新は ~ ではなく、操作列を空白にしてください。更新日と更新者はExcelの値ではなくアプリ側で自動設定します。")

        if st.session_state.get("faq_replace_result"):
            st.success(st.session_state["faq_replace_result"])
            st.session_state.pop("faq_replace_result", None)

        current_faq_df = load_current_faq_df(ns)
        excel_bytes = faq_df_to_excel_bytes(current_faq_df)
        st.download_button(
            "⬇ 現在のFAQをExcelでダウンロード（操作列付き）",
            data=excel_bytes,
            file_name="faq_operation_template.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            width="stretch",
        )

        sample_df = _build_operation_template_df(current_faq_df)
        st.download_button(
            "🧪 差分更新テスト用FAQテンプレートをExcelでダウンロード",
            data=faq_df_to_excel_bytes(sample_df),
            file_name="faq_operation_test_template.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            width="stretch",
        )

        st.markdown("""
**操作列のルール**

| 操作 | 処理 | 備考 |
|---|---|---|
| `+` | 追加 | FAQ_ID欄の値は使わず、新しいFAQ_IDを自動採番します |
| 空白 | 更新 | FAQ_IDに一致する既存FAQを上書きします |
| `-` | 削除 | FAQ_IDに一致する既存FAQを削除します |
""")
        st.caption(f"現在登録中のFAQ件数: {len(current_faq_df)} 件")

        uploaded_faq = st.file_uploader(
            "FAQファイルをアップロード",
            type=["xlsx", "xls", "csv"],
            key="faq_excel_uploader_admin",
            help="Excel(.xlsx) 推奨。操作 / FAQ_ID / 質問 / 回答 / 意図 / キーワード・言い換え / カテゴリ / 表示形式 / 有効 / 更新日 / 更新者 / 備考 に対応。操作は +追加、-削除、空白更新です。+追加ではFAQ_IDを新しく自動採番します。更新日・更新者は反映時に自動設定します。",
        )

        if uploaded_faq is not None:
            try:
                raw = uploaded_faq.getvalue()
                operation_handler_ready = callable(read_faq_operation_uploaded_file) and callable(apply_faq_upload_operations)
                if operation_handler_ready:
                    incoming_df = read_faq_operation_uploaded_file(uploaded_faq.name, raw)
                    has_operation_spec = bool(incoming_df.attrs.get("has_operation_spec"))
                else:
                    st.error("FAQ差分取込の内部関数が管理画面へ渡されていません。アプリを最新版ZIPに差し替えて再起動してください。")
                    incoming_df = read_faq_uploaded_file(uploaded_faq.name, raw)
                    has_operation_spec = False

                if has_operation_spec and operation_handler_ready:
                    result_df, summary = apply_faq_upload_operations(current_faq_df, incoming_df, updated_by=get_current_admin_name())
                    st.success(f"差分アップロード確認OK: {len(incoming_df)} 行を読み込みました。")
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("追加", int(summary.get("added", 0)))
                    c2.metric("更新", int(summary.get("updated", 0)))
                    c3.metric("削除", int(summary.get("deleted", 0)))
                    c4.metric("反映後件数", len(result_df))

                    preview_df = _to_preview_df(incoming_df)
                    st.dataframe(preview_df.head(30), width="stretch", height=420)
                    if len(incoming_df) > 30:
                        st.caption(f"先頭30行を表示中です。処理対象は全 {len(incoming_df)} 行です。")

                    if summary.get("details"):
                        with st.expander("処理予定の詳細を見る", expanded=False):
                            st.dataframe(pd.DataFrame(summary["details"]).head(200), width="stretch", height=320)

                    errors = summary.get("errors") or []
                    if errors:
                        st.error(f"{len(errors)} 件のエラーがあります。修正してから再アップロードしてください。")
                        for msg in errors[:20]:
                            st.warning(msg)
                        if len(errors) > 20:
                            st.caption(f"他 {len(errors) - 20} 件のエラーがあります。")
                    else:
                        if st.button("📥 差分内容でFAQを反映する", type="primary", key="apply_faq_operation_admin", width="stretch"):
                            with st.spinner("FAQを差分反映しています..."):
                                final_df, final_summary = apply_faq_upload_operations(current_faq_df, incoming_df, updated_by=get_current_admin_name())
                                saved, reloaded_df = apply_faq_operation_result(ns, final_df, final_summary)
                                msg = f"FAQを差分反映しました。追加 {final_summary.get('added', 0)} 件 / 更新 {final_summary.get('updated', 0)} 件 / 削除 {final_summary.get('deleted', 0)} 件 / 現在 {len(reloaded_df)} 件です。更新日: {final_summary.get('updated_at', '')} / 更新者: {final_summary.get('updated_by', '')}"
                                if int(saved) != int(len(reloaded_df)):
                                    st.error(f"保存件数と再読込件数が一致しません。保存: {saved} 件 / 再読込: {len(reloaded_df)} 件")
                                else:
                                    st.session_state["faq_replace_result"] = msg
                                    st.success(msg)
                                    st.info("FAQの反映が完了しました。再読み込みは不要です。GitHub永続化ONなら自動で外部保存されます。")
                else:
                    if not operation_handler_ready:
                        st.stop()
                    st.warning("操作列が無いFAQファイルです。既存FAQを消さないため、標準では『追加のみ』として扱います。")
                    incoming_df = read_faq_uploaded_file(uploaded_faq.name, raw)
                    incoming_add_df = incoming_df.copy()
                    incoming_add_df.insert(0, "operation", "+")
                    result_df, summary = apply_faq_upload_operations(current_faq_df, incoming_add_df, updated_by=get_current_admin_name())

                    st.success(f"アップロード確認OK: {len(incoming_df)} 件のFAQを検出しました。追加予定: {summary.get('added', 0)} 件")
                    c1, c2, c3 = st.columns(3)
                    c1.metric("現在件数", len(current_faq_df))
                    c2.metric("追加予定", int(summary.get("added", 0)))
                    c3.metric("反映後件数", len(result_df))

                    preview_df = _to_preview_df(incoming_add_df)
                    st.dataframe(preview_df.head(30), width="stretch", height=420)
                    if len(incoming_add_df) > 30:
                        st.caption(f"先頭30件を表示中です。追加対象は全 {len(incoming_add_df)} 件です。")

                    errors = summary.get("errors") or []
                    if errors:
                        st.error(f"{len(errors)} 件のエラーがあります。修正してから再アップロードしてください。")
                        for msg in errors[:50]:
                            st.warning(msg)
                        if len(errors) > 50:
                            st.caption(f"他 {len(errors) - 50} 件のエラーがあります。")
                    else:
                        if st.button("📥 既存FAQを残して追加する", type="primary", key="append_faq_excel_admin", width="stretch"):
                            with st.spinner("FAQを追加しています..."):
                                final_df, final_summary = apply_faq_upload_operations(current_faq_df, incoming_add_df, updated_by=get_current_admin_name())
                                saved, reloaded_df = apply_faq_operation_result(ns, final_df, final_summary)
                                if int(saved) != int(len(reloaded_df)):
                                    st.error(f"保存件数と再読込件数が一致しません。保存: {saved} 件 / 再読込: {len(reloaded_df)} 件")
                                else:
                                    msg = f"FAQを追加しました。追加 {final_summary.get('added', 0)} 件 / 現在 {len(reloaded_df)} 件です。更新日: {final_summary.get('updated_at', '')} / 更新者: {final_summary.get('updated_by', '')}"
                                    st.session_state["faq_replace_result"] = msg
                                    st.success(msg)
                                    st.info("FAQの反映が完了しました。再読み込みは不要です。GitHub永続化ONなら自動で外部保存されます。")
            except Exception as e:
                st.error(f"FAQファイルの取込でエラー: {e}")
