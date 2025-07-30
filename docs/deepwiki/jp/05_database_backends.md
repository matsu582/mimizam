# データベースバックエンド

このドキュメントでは、mimizamがサポートする各データベースバックエンドの比較と選択ガイドを提供します。SQLite、MySQL、PostgreSQL、Elasticsearchの特徴、用途、設定方法について説明します。

個別のバックエンドについては、以下を参照してください：
- [SQLiteバックエンド](./05_1_sqlite_backend.md) - 軽量ファイルベースDB
- [MySQLバックエンド](./05_2_mysql_backend.md) - 本番環境向けRDBMS
- [PostgreSQLバックエンド](./05_3_postgresql_backend.md) - 高機能RDBMS
- [Elasticsearchバックエンド](./05_4_elasticsearch_backend.md) - 分散検索エンジン

## 概要

mimizamは、異なる規模と要件に対応するため、複数のデータベースバックエンドをサポートしています。統一されたAPIにより、アプリケーションコードを変更することなく、データベースバックエンド間での切り替えが可能です。

## データベースバックエンド比較

### 機能比較表

| 機能 | SQLite | MySQL | PostgreSQL | Elasticsearch |
|------|--------|-------|------------|---------------|
| **設定の簡単さ** | ★★★★★ | ★★★☆☆ | ★★★☆☆ | ★★☆☆☆ |
| **パフォーマンス** | ★★☆☆☆ | ★★★★☆ | ★★★★☆ | ★★★★★ |
| **スケーラビリティ** | ★☆☆☆☆ | ★★★★☆ | ★★★★☆ | ★★★★★ |
| **同時接続数** | ★☆☆☆☆ | ★★★★☆ | ★★★★☆ | ★★★★★ |
| **検索機能** | ★★☆☆☆ | ★★★☆☆ | ★★★★☆ | ★★★★★ |
| **運用コスト** | ★★★★★ | ★★★☆☆ | ★★★☆☆ | ★★☆☆☆ |
| **データ整合性** | ★★★★☆ | ★★★★☆ | ★★★★★ | ★★★☆☆ |

### 用途別推奨

#### 開発・プロトタイピング
- **SQLite**: 設定不要で即座に開始可能
- 小規模データセット（< 10,000楽曲）
- 単一ユーザー環境

#### 小〜中規模本番環境
- **MySQL**: 実績豊富で安定した性能
- 中規模データセット（10,000 - 100,000楽曲）
- 複数ユーザー同時アクセス

#### 高機能・大規模環境
- **PostgreSQL**: 高度なインデックスと分析機能
- 大規模データセット（100,000楽曲以上）
- 複雑なクエリと分析要件

#### 分散・超大規模環境
- **Elasticsearch**: 水平スケーリングと高速検索
- 超大規模データセット（1,000,000楽曲以上）
- リアルタイム分析と全文検索

## 使用例

### SQLite
```python
from mimizam import create_mimizam_sqlite

mimizam = create_mimizam_sqlite("music.db")
```

### MySQL
```python
from mimizam import create_mimizam_mysql

mimizam = create_mimizam_mysql(
    host="localhost",
    user="mimizam_user",
    password="secure_password",
    database="music_db"
)
```

### PostgreSQL
```python
from mimizam import create_mimizam_postgresql

mimizam = create_mimizam_postgresql(
    host="localhost",
    user="mimizam_user",
    password="secure_password",
    database="music_db"
)
```

### Elasticsearch
```python
from mimizam import create_mimizam_elasticsearch

mimizam = create_mimizam_elasticsearch(
    hosts="localhost:9200",
    index_name="music_fingerprints"
)
```

## 選択ガイド

### 決定フローチャート

```
開始
  │
  ▼
プロトタイプ・開発環境？
  │
  ├─ Yes → SQLite
  │
  ▼ No
楽曲数 < 10万曲？
  │
  ├─ Yes → MySQL または PostgreSQL
  │
  ▼ No
分散環境が必要？
  │
  ├─ Yes → Elasticsearch
  │
  ▼ No
高度な分析機能が必要？
  │
  ├─ Yes → PostgreSQL
  │
  ▼ No
MySQL
```

## 関連ドキュメント

- [コアアーキテクチャ](./03_core_architecture.md) - システム全体の構成
- [データベース層](./03_2_database_layer.md) - データベース抽象化
- [基本的な使用例](./06_1_basic_usage_examples.md) - 実践的な使用方法
