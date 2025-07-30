# データベースバックエンド概要

このページでは、mimizamシステムがサポートする各データベースバックエンドの概要と比較を提供します。mimizamは統一インターフェースを通じて複数のデータベース技術をサポートし、アプリケーションのニーズに応じて最適なストレージソリューションを選択できます。

個別のバックエンド設定については、[SQLiteバックエンド](./10_sqlite_backend.md)、[MySQLバックエンド](./11_mysql_backend.md)、[PostgreSQLバックエンド](./12_postgresql_backend.md)、[Elasticsearchバックエンド](./13_elasticsearch_backend.md)を参照してください。

## 対応データベースバックエンド

| バックエンド | 用途 | 主要特徴 | 推奨シナリオ |
|-------------|------|----------|-------------|
| **SQLite** | 開発・小規模デプロイ | ファイルベース、ゼロ設定、高速クエリ | プロトタイピング、個人プロジェクト |
| **MySQL** | 本番Webアプリケーション | ACID準拠、レプリケーション、大規模対応 | Webアプリケーション、中規模システム |
| **PostgreSQL** | 高性能アプリケーション | 高度なインデックス、JSON対応、拡張性 | 複雑なクエリ、大規模システム |
| **Elasticsearch** | 分散検索システム | 全文検索、水平スケーリング、分析機能 | 大規模検索、分析ワークロード |

## パフォーマンス比較

### 書き込み性能

| バックエンド | 楽曲追加速度 | バッチ挿入 | 同時書き込み |
|-------------|-------------|-----------|-------------|
| SQLite | 高速 | 中程度 | 制限あり |
| MySQL | 中程度 | 高速 | 優秀 |
| PostgreSQL | 中程度 | 高速 | 優秀 |
| Elasticsearch | 中程度 | 非常に高速 | 優秀 |

### 検索性能

| バックエンド | 単一クエリ | 複雑クエリ | 全文検索 |
|-------------|-----------|-----------|----------|
| SQLite | 高速 | 中程度 | 制限あり |
| MySQL | 高速 | 高速 | 中程度 |
| PostgreSQL | 高速 | 非常に高速 | 高速 |
| Elasticsearch | 高速 | 高速 | 非常に高速 |

## スケーラビリティ

### データ容量

| バックエンド | 最大データベースサイズ | 楽曲数制限 | 指紋数制限 |
|-------------|---------------------|-----------|-----------|
| SQLite | ~281TB | ~100万曲 | ~10億指紋 |
| MySQL | 無制限 | 無制限 | 無制限 |
| PostgreSQL | 無制限 | 無制限 | 無制限 |
| Elasticsearch | 無制限 | 無制限 | 無制限 |

### 同時接続

| バックエンド | 最大同時接続数 | 読み取り専用接続 | 書き込み接続 |
|-------------|---------------|----------------|-------------|
| SQLite | 1（書き込み） | 無制限 | 1 |
| MySQL | 設定可能 | 高い | 高い |
| PostgreSQL | 設定可能 | 非常に高い | 高い |
| Elasticsearch | 設定可能 | 非常に高い | 高い |

## 設定の複雑さ

### セットアップ要件

| バックエンド | インストール | 設定 | 保守 |
|-------------|-------------|------|------|
| SQLite | 不要 | 最小限 | 最小限 |
| MySQL | 必要 | 中程度 | 中程度 |
| PostgreSQL | 必要 | 中程度 | 中程度 |
| Elasticsearch | 必要 | 複雑 | 複雑 |

## ファクトリ関数

各バックエンドは専用のファクトリ関数を提供します：

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
    database="music_db",
    username="user",
    password="password"
)
```

### PostgreSQL

```python
from mimizam import create_mimizam_postgresql

mimizam = create_mimizam_postgresql(
    host="localhost",
    database="music_db",
    username="user",
    password="password"
)
```

### Elasticsearch

```python
from mimizam import create_mimizam_elasticsearch

mimizam = create_mimizam_elasticsearch(
    host="localhost",
    port=9200,
    index_name="music_fingerprints"
)
```

## データベース選択ガイド

### 開発・プロトタイピング

**推奨**: SQLite
- ゼロ設定で即座に開始可能
- ファイルベースで移植性が高い
- 小規模データセットに最適

### 小〜中規模本番環境

**推奨**: MySQL
- 成熟したエコシステム
- 豊富なホスティングオプション
- 優れたパフォーマンス

### 大規模・高性能システム

**推奨**: PostgreSQL
- 高度なクエリ最適化
- 豊富なデータ型サポート
- 優秀な同時実行制御

### 分散・分析システム

**推奨**: Elasticsearch
- 水平スケーリング
- 高度な検索機能
- リアルタイム分析

## 移行戦略

### SQLiteからMySQLへ

```python
# データエクスポート
sqlite_mimizam = create_mimizam_sqlite("source.db")
songs = sqlite_mimizam.get_all_songs()

# データインポート
mysql_mimizam = create_mimizam_mysql(host="localhost", ...)
for song in songs:
    mysql_mimizam.add_song(song.file_path, song.title, song.artist)
```

### バックエンド間データ移行

```python
def migrate_database(source_mimizam, target_mimizam):
    """データベース間でデータを移行"""
    songs = source_mimizam.get_all_songs()
    
    for song in songs:
        try:
            target_mimizam.add_song(song.file_path, song.title, song.artist)
            print(f"移行完了: {song.title}")
        except Exception as e:
            print(f"移行エラー: {song.title} - {e}")
```

## バックアップ戦略

### SQLite

```bash
# ファイルコピー
cp music.db music_backup.db

# SQLiteダンプ
sqlite3 music.db .dump > backup.sql
```

### MySQL

```bash
# mysqldump
mysqldump -u user -p music_db > backup.sql

# バイナリログ
mysqlbinlog mysql-bin.000001 > binlog_backup.sql
```

### PostgreSQL

```bash
# pg_dump
pg_dump -U user music_db > backup.sql

# 継続的アーカイブ
pg_basebackup -D backup_dir
```

### Elasticsearch

```bash
# スナップショット
curl -X PUT "localhost:9200/_snapshot/backup_repo/snapshot_1"

# インデックステンプレート
curl -X GET "localhost:9200/_template/mimizam_template"
```

## 監視とメンテナンス

### パフォーマンス監視

```python
def monitor_database_performance(mimizam):
    """データベースパフォーマンスを監視"""
    stats = mimizam.get_database_stats()
    
    print(f"楽曲数: {stats['song_count']}")
    print(f"指紋数: {stats['fingerprint_count']:,}")
    print(f"データベースサイズ: {stats['database_size_mb']:.1f}MB")
    print(f"平均クエリ時間: {stats['avg_query_time']:.3f}秒")
```

### インデックス最適化

```python
def optimize_database_indices(mimizam):
    """データベースインデックスを最適化"""
    if hasattr(mimizam.database.backend, 'optimize_indices'):
        mimizam.database.backend.optimize_indices()
        print("インデックス最適化完了")
```

## トラブルシューティング

### 一般的な問題

| 問題 | 症状 | 解決方法 |
|------|------|----------|
| 接続エラー | データベースに接続できない | 接続設定、サーバー状態を確認 |
| 性能低下 | クエリが遅い | インデックス最適化、統計更新 |
| 容量不足 | 書き込みエラー | ディスク容量、設定制限を確認 |
| 同時実行エラー | ロック待機タイムアウト | 接続プール、トランザクション設定を調整 |

### デバッグ設定

```python
# デバッグモードでの作成
mimizam = create_mimizam_sqlite("debug.db", debug=True, verbose=True)

# ログレベル設定
import logging
logging.basicConfig(level=logging.DEBUG)
```

## 関連ドキュメント

- [データベース層](./05_database_layer.md) - データベース抽象化の詳細
- [SQLiteバックエンド](./10_sqlite_backend.md) - SQLite固有の設定
- [MySQLバックエンド](./11_mysql_backend.md) - MySQL固有の設定
- [PostgreSQLバックエンド](./12_postgresql_backend.md) - PostgreSQL固有の設定
- [Elasticsearchバックエンド](./13_elasticsearch_backend.md) - Elasticsearch固有の設定
- [パフォーマンス最適化](./16_performance_optimization.md) - 高速化技術
