from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path
from typing import Callable

import pandas as pd
import streamlit as st


def _safe_len(df: pd.DataFrame | None) -> int:
    try:
        return int(len(df)) if df is not None else 0
    except Exception:
        return 0


def _recent_questions_table(files: list[Path], max_questions: int = 50) -> pd.DataFrame:
    rows: list[dict] = []
    for p in files[:10]:
        try:
            df = pd.read_csv(p, encoding='utf-8')
        except Exception:
            try:
                df = pd.read_csv(p, encoding='utf-8', engine='python', on_bad_lines='skip')
            except Exception:
                continue
        q_col = next((c for c in ['question', 'user_question', 'query', '質問', '問い合わせ', '問合せ'] if c in df.columns), None)
        if not q_col:
            continue
        for _, row in df.head(max_questions).iterrows():
            q = str(row.get(q_col, '')).strip()
            if not q:
                continue
            rows.append({
                'log_file': p.name,
                'question': q,
                'timestamp': row.get('timestamp', ''),
                'device': row.get('device', ''),
                'location': row.get('location', ''),
                'network': row.get('network', ''),
            })
    if not rows:
        return pd.DataFrame(columns=['log_file', 'question', 'timestamp', 'device', 'location', 'network'])
    return pd.DataFrame(rows)


def render_admin_complete_tools(
    *,
    read_interactions: Callable[..., pd.DataFrame],
    count_nohit_logs: Callable[..., tuple[int, int, int]],
    list_log_files: Callable[[], list[Path]],
    make_logs_zip: Callable[[list[Path]], bytes],
    load_nohit_questions_from_logs: Callable[..., list[str]],
    generate_faq_candidates: Callable[..., pd.DataFrame],
    append_faq_csv: Callable[..., int],
    seed_nohit_questions: Callable[..., int],
    faq_path: str | Path,
) -> None:
    """既存の管理者機能を削らずに、足りない管理メニューを追加する。"""

    st.markdown('---')

    with st.expander('📊 管理ダッシュボード（拡張版）', expanded=False):
        df7 = read_interactions(days=7)
        df30 = read_interactions(days=30)
        today_nohit, nohit_7d, nohit_total = count_nohit_logs(days=7)

        matched_7d = int(pd.to_numeric(df7.get('matched', 0), errors='coerce').fillna(0).sum()) if _safe_len(df7) else 0
        total_7d = matched_7d + int(nohit_7d)
        auto_rate = (matched_7d / total_7d * 100.0) if total_7d > 0 else 0.0
        avg_min = st.number_input('1件あたり削減時間（分）', min_value=1, max_value=60, value=3, step=1, key='admin_ext_avg_min')
        hourly_cost = st.number_input('想定人件費（円/時間）', min_value=0, max_value=20000, value=4000, step=500, key='admin_ext_hourly_cost')
        saved_hours = round((matched_7d * float(avg_min)) / 60.0, 1)
        saved_yen = int(saved_hours * int(hourly_cost))

        c1, c2, c3, c4 = st.columns(4)
        c1.metric('7日間の総問い合わせ', total_7d)
        c2.metric('AI自動対応', matched_7d)
        c3.metric('該当なし', int(nohit_7d))
        c4.metric('AI対応率', f'{auto_rate:.1f}%')

        c5, c6 = st.columns(2)
        c5.metric('削減時間（推定）', f'{saved_hours} 時間')
        c6.metric('削減金額（推定）', f'{saved_yen:,} 円')

        if _safe_len(df30):
            df_plot = df30.copy()
            if 'timestamp' in df_plot.columns:
                df_plot['timestamp'] = pd.to_datetime(df_plot['timestamp'], errors='coerce')
                df_plot = df_plot.dropna(subset=['timestamp'])
                if len(df_plot):
                    df_plot['date'] = df_plot['timestamp'].dt.strftime('%m-%d')
                    daily = df_plot.groupby('date').size().reset_index(name='count')
                    st.caption('直近30日の問い合わせ件数推移')
                    st.line_chart(daily.set_index('date'))

        if _safe_len(df7):
            show_cols = [c for c in ['timestamp', 'question', 'category', 'best_score', 'matched'] if c in df7.columns]
            if show_cols:
                st.caption('直近7日ログ（先頭20件）')
                st.dataframe(df7[show_cols].head(20), use_container_width=True, hide_index=True)

    with st.expander('📝 ログ閲覧 / 一括ダウンロード', expanded=False):
        log_files = list_log_files()
        st.caption(f'nohitログファイル数: {len(log_files)} 件')
        if log_files:
            zip_bytes = make_logs_zip(log_files)
            st.download_button(
                '⬇ nohitログ一式をZIPでダウンロード',
                data=zip_bytes,
                file_name='nohit_logs.zip',
                mime='application/zip',
                width='stretch',
            )
            recent_df = _recent_questions_table(log_files, max_questions=200)
            if _safe_len(recent_df):
                st.caption('最近の該当なし質問')
                st.dataframe(recent_df.head(50), use_container_width=True, hide_index=True)
        else:
            st.info('まだ nohit ログはありません。')

    with st.expander('🧠 FAQ自動生成（該当なしログ → FAQ案）', expanded=False):
        st.caption('該当なしログからFAQ案を作り、確認後に faq.csv へ追記できます。')
        log_files = list_log_files()
        if not log_files:
            st.info('まだ nohit_*.csv がありません。まず質問して「該当なし」を発生させてください。')
        else:
            labels = [p.name for p in log_files[:15]]
            pick = st.selectbox('参照するログファイル', labels, index=0, key='admin_ext_nohit_pick')
            picked_path = next((p for p in log_files if p.name == pick), log_files[0])
            max_q = st.slider('生成に使う質問数（重複除外後）', 10, 200, 60, step=10, key='admin_ext_max_q')
            n_items = st.slider('生成するFAQ件数', 3, 20, 8, key='admin_ext_n_items')

            col1, col2 = st.columns([2, 3])
            with col1:
                if st.button('🧪 デモ用に定番質問を追加（20件）', key='admin_ext_seed'):
                    added = seed_nohit_questions(20)
                    st.success(f'nohitログに {added} 件追加しました。')
                    st.rerun()
            with col2:
                st.caption('営業デモ前にFAQ自動生成を試したい場合のテストデータです。')

            if st.button('🤖 FAQ案を自動生成', type='primary', key='admin_ext_generate_faq'):
                with st.spinner('FAQ案を生成中...'):
                    qs = load_nohit_questions_from_logs([picked_path], max_questions=max_q)
                    st.session_state['admin_generated_nohit_questions'] = qs
                    if len(qs) < 5:
                        st.session_state['generated_faq_df_ext'] = pd.DataFrame(columns=['category', 'question', 'answer'])
                        st.warning('有効な質問が少なすぎてFAQを生成できません。')
                    else:
                        try:
                            gen_df = generate_faq_candidates(qs, n_items=n_items)
                        except Exception as e:
                            st.error(f'FAQ案生成でエラー: {e}')
                            gen_df = pd.DataFrame(columns=['category', 'question', 'answer'])
                        st.session_state['generated_faq_df_ext'] = gen_df

            gen_df = st.session_state.get('generated_faq_df_ext')
            if isinstance(gen_df, pd.DataFrame) and len(gen_df) > 0:
                st.markdown('### ✅ 生成結果（編集して保存できます）')
                edited = st.data_editor(gen_df, num_rows='dynamic', use_container_width=True, key='admin_ext_faq_editor')
                c1, c2 = st.columns(2)
                with c1:
                    if st.button('💾 faq.csv に追記', key='admin_ext_append_faq'):
                        added = append_faq_csv(Path(faq_path), edited.rename(columns={'category': 'category'}))
                        if added > 0:
                            st.success(f'faq.csv に {added} 件追記しました。')
                            st.session_state['generated_faq_df_ext'] = pd.DataFrame()
                            st.rerun()
                        else:
                            st.warning('追記できる新規FAQがありません。')
                with c2:
                    if st.button('🧹 生成結果をクリア', key='admin_ext_clear_faq'):
                        st.session_state['generated_faq_df_ext'] = pd.DataFrame()
                        st.rerun()
            elif isinstance(gen_df, pd.DataFrame) and len(gen_df) == 0 and st.session_state.get('generated_faq_df_ext') is not None:
                st.warning('FAQ案が生成できませんでした。ログの内容が少ないか、出力形式が崩れています。')
