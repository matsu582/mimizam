# PostgreSQLバックエンド

PostgreSQLバックエンドは、高度な機能と優れたパフォーマンスを提供するオープンソースのリレーショナルデータベース管理システムです。複雑なクエリ、JSON データ、高度なインデックス機能をサポートします。

他のデータベースバックエンドについては、[データベースバックエンド概要](./05_database_backends.md)を参照してください。

## 主要特徴

### 利点

- **高機能**: 高度なSQL機能とデータ型
- **拡張性**: カスタム関数とプロシージャ
- **JSON対応**: ネイティブJSON/JSONBサポート
- **高度なインデックス**: GIN、GiST、BRIN等の特殊インデックス
- **ACID準拠**: 完全なトランザクション整合性
- **並列処理**: 並列クエリ実行

### 考慮事項

- **学習コスト**: 高度な機能の習得が必要
- **メモリ使用量**: 大量のメモリを消費
- **設定の複雑さ**: 最適化には専門知識が必要
- **バックアップ**: 大規模データでのバックアップ時間

## 基本的な使用方法

### ファクトリ関数

```python
from mimizam import create_mimizam_postgresql

# 基本的な接続
mimizam = create_mimizam_postgresql(
    host="localhost",
    user="mimizam_user",
    password="secure_password",
    database="music_db"
)

# 詳細設定
mimizam = create_mimizam_postgresql(
    host="postgres.example.com",
    port=5432,
    user="mimizam_user",
    password="secure_password",
    database="music_production",
    sslmode="require"
)
```

## データベース設定

### 初期設定

```sql
-- データベース作成
CREATE DATABASE music_db 
    WITH ENCODING 'UTF8' 
    LC_COLLATE='ja_JP.UTF-8' 
    LC_CTYPE='ja_JP.UTF-8';

-- ユーザー作成と権限付与
CREATE USER mimizam_user WITH PASSWORD 'secure_password';
GRANT ALL PRIVILEGES ON DATABASE music_db TO mimizam_user;
```

### テーブル作成

```sql
-- 楽曲テーブル
CREATE TABLE songs (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    artist VARCHAR(255),
    album VARCHAR(255),
    duration REAL,
    file_path VARCHAR(500),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 指紋テーブル
CREATE TABLE fingerprints (
    id BIGSERIAL PRIMARY KEY,
    song_id INTEGER NOT NULL REFERENCES songs(id) ON DELETE CASCADE,
    hash BIGINT NOT NULL,
    time_offset REAL NOT NULL,
    anchor_freq INTEGER,
    target_freq INTEGER,
    time_delta INTEGER
);

-- インデックス作成
CREATE INDEX idx_fingerprints_hash ON fingerprints USING HASH (hash);
CREATE INDEX idx_fingerprints_song_id ON fingerprints(song_id);
```

## 関連ドキュメント

- [データベースバックエンド概要](./05_database_backends.md) - 全バックエンドの比較
- [SQLiteバックエンド](./05_1_sqlite_backend.md) - 軽量ファイルベースDB
- [MySQLバックエンド](./05_2_mysql_backend.md) - 本番環境向けRDBMS
- [Elasticsearchバックエンド](./05_4_elasticsearch_backend.md) - 分散検索エンジン
