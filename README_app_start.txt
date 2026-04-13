起動入口の整理版です。

通常起動:
- streamlit run app.py

内部エントリポイント:
- helpdesk_app.entrypoint.run_app()
- helpdesk_app.entrypoint.main()

補足:
- helpdesk_app/__main__.py を追加しているため、将来的に python -m helpdesk_app の入口としても整理しやすい構成です。
