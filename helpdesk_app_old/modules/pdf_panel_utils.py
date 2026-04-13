from __future__ import annotations


def resolve_monthly_effect_df(*, read_interactions, pd, datetime):
    df_month_all = read_interactions(days=60)
    if df_month_all is None or len(df_month_all) == 0:
        return None

    try:
        ts = pd.to_datetime(df_month_all["timestamp"], errors="coerce")
        month_start = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return df_month_all[ts >= month_start]
    except Exception:
        return df_month_all
