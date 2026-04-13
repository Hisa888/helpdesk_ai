from __future__ import annotations

"""検索エンジンの入口をまとめるファイル。

第三段階として、FAQ検索・インデックス生成・高速検索の呼び出し口を
このファイルに集約する。

実装本体は既存の modules 配下をそのまま使うため、既存機能を落とさずに
「検索の修正はここを見る」という導線を先に作る構成。
"""

from helpdesk_app.modules.faq_index_runtime import create_faq_index_runtime
from helpdesk_app.modules.search_runtime import create_search_runtime

__all__ = [
    'create_faq_index_runtime',
    'create_search_runtime',
]
