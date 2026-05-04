# サイドバー「>>」二重表示の追加修正

## 修正目的

Streamlit標準のサイドバー復帰ボタンと、独自に追加した復帰ボタンが同時に表示され、
画面左側に「>>」が2つ出る問題を修正しました。

## 修正ファイル

- `helpdesk_app/modules/app_bootstrap.py`

## 修正内容

- Streamlit標準の折りたたみ復帰ボタンをCSSだけでなくJavaScriptでも検出して非表示にしました。
- Streamlitのバージョン差に対応するため、以下のような複数パターンを検出します。
  - `collapsedControl`
  - `stSidebarCollapsedControl`
  - `stSidebarNavCollapseControl`
  - `Expand sidebar`
  - `Show sidebar`
  - `Open sidebar`
  - `サイドバーを表示`
  - `サイドバーを開く`
  - 画面左上付近に出る小さい `>>` / `≫` / `»`
- 独自の「>>」ボタンは残し、そこから管理メニューを再表示できる動作は維持しました。

## 確認ポイント

1. 左上の `<<` でサイドバーを閉じる
2. 画面左側の `>>` が1つだけ表示される
3. 表示されている `>>` を押すと管理メニューが戻る
4. 青い縦バーや左側の不要な余白が残らない

