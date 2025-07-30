# MySQLバックエンド

> 関連するソースファイル

MySQLバックエンドは、本番環境での使用に適した実績豊富なリレーショナルデータベース管理システムです。高いパフォーマンス、信頼性、スケーラビリティを提供します。

他のデータベースバックエンドについては、[データベースバックエンド概要](./05_database_backends.md)を参照してください。

## 主要特徴

### 利点

- **高性能**: 大量データでの高速処理
- **スケーラビリティ**: レプリケーションとクラスタリング対応
- **信頼性**: 実績豊富で安定した動作
- **同時接続**: 多数のクライアント同時接続
- **豊富な機能**: ストアドプロシージャ、トリガー、ビュー

### 考慮事項

- **設定の複雑さ**: サーバー設定とメンテナンスが必要
- **リソース使用量**: メモリとCPUを多く消費
- **ライセンス**: 商用利用時のライセンス考慮
- **運用コスト**: 専門知識を持つ管理者が必要

## 基本的な使用方法

### ファクトリ関数

```python
from mimizam import create_mimizam_mysql

# 基本的な接続
mimizam = create_mimizam_mysql(
    host="localhost",
    user="mimizam_user",
    password="secure_password",
    database="music_db"
)

# 詳細設定
mimizam = create_mimizam_mysql(
    host="mysql.example.com",
    port=3306,
    user="mimizam_user",
    password="secure_password",
    database="music_production",
    charset="utf8mb4",
    autocommit=True,
    pool_size=10
)
```

### SSL接続

```python
# SSL接続の設定
mimizam = create_mimizam_mysql(
    host="secure-mysql.example.com",
    user="mimizam_user",
    password="secure_password",
    database="music_db",
    ssl_disabled=False,
    ssl_ca="/path/to/ca.pem",
    ssl_cert="/path/to/client-cert.pem",
    ssl_key="/path/to/client-key.pem"
)
```

## データベース設定

### 初期設定

```sql
-- データベース作成
CREATE DATABASE music_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- ユーザー作成と権限付与
CREATE USER 'mimizam_user'@'%' IDENTIFIED BY 'secure_password';
GRANT ALL PRIVILEGES ON music_db.* TO 'mimizam_user'@'%';
FLUSH PRIVILEGES;
```

### テーブル作成

```sql
-- 楽曲テーブル
CREATE TABLE songs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    artist VARCHAR(255),
    album VARCHAR(255),
    duration FLOAT,
    file_path VARCHAR(500),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_songs_name (name),
    INDEX idx_songs_artist (artist)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 指紋テーブル
CREATE TABLE fingerprints (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    song_id INT NOT NULL,
    hash BIGINT NOT NULL,
    time_offset FLOAT NOT NULL,
    anchor_freq INT,
    target_freq INT,
    time_delta INT,
    FOREIGN KEY (song_id) REFERENCES songs(id) ON DELETE CASCADE,
    INDEX idx_fingerprints_hash (hash),
    INDEX idx_fingerprints_song_id (song_id),
    INDEX idx_fingerprints_composite (hash, song_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

## パフォーマンス最適化

### MySQL設定（my.cnf）

```ini
[mysqld]
# 基本設定
innodb_buffer_pool_size = 2G
innodb_log_file_size = 256M
innodb_flush_log_at_trx_commit = 2
innodb_flush_method = O_DIRECT

# 接続設定
max_connections = 200
max_connect_errors = 1000000

# クエリキャッシュ
query_cache_type = 1
query_cache_size = 256M

# 一時テーブル
tmp_table_size = 256M
max_heap_table_size = 256M

# ログ設定
slow_query_log = 1
slow_query_log_file = /var/log/mysql/slow.log
long_query_time = 2
```

### インデックス最適化

```sql
-- 複合インデックスの作成
CREATE INDEX idx_fingerprints_hash_time ON fingerprints(hash, time_offset);
CREATE INDEX idx_songs_artist_album ON songs(artist, album);

-- インデックス使用状況の確認
SHOW INDEX FROM fingerprints;
EXPLAIN SELECT * FROM fingerprints WHERE hash = 12345;
```

### クエリ最適化

```python
def optimize_mysql_queries(connection):
    """MySQLクエリを最適化"""
    cursor = connection.cursor()
    
    # クエリキャッシュの状態確認
    cursor.execute("SHOW STATUS LIKE 'Qcache%'")
    cache_stats = cursor.fetchall()
    
    # スロークエリの確認
    cursor.execute("SHOW STATUS LIKE 'Slow_queries'")
    slow_queries = cursor.fetchone()
    
    # インデックス効率の確認
    cursor.execute("""
        SELECT table_name, index_name, cardinality 
        FROM information_schema.statistics 
        WHERE table_schema = DATABASE()
        ORDER BY cardinality DESC
    """)
    index_stats = cursor.fetchall()
    
    return {
        'cache_stats': cache_stats,
        'slow_queries': slow_queries,
        'index_stats': index_stats
    }
```

## レプリケーション設定

### マスター設定

```ini
# マスターサーバー設定（my.cnf）
[mysqld]
server-id = 1
log-bin = mysql-bin
binlog-format = ROW
binlog-do-db = music_db
```

### スレーブ設定

```ini
# スレーブサーバー設定（my.cnf）
[mysqld]
server-id = 2
relay-log = mysql-relay-bin
read-only = 1
```

### レプリケーション用ユーザー作成

```sql
-- マスターサーバーで実行
CREATE USER 'replication_user'@'%' IDENTIFIED BY 'replication_password';
GRANT REPLICATION SLAVE ON *.* TO 'replication_user'@'%';
FLUSH PRIVILEGES;

-- スレーブサーバーで実行
CHANGE MASTER TO
    MASTER_HOST='master-server.example.com',
    MASTER_USER='replication_user',
    MASTER_PASSWORD='replication_password',
    MASTER_LOG_FILE='mysql-bin.000001',
    MASTER_LOG_POS=0;

START SLAVE;
```

## バックアップと復元

### mysqldumpによるバックアップ

```bash
#!/bin/bash
# バックアップスクリプト

DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/backup/mysql"
DB_NAME="music_db"

# ディレクトリ作成
mkdir -p $BACKUP_DIR

# フルバックアップ
mysqldump -u mimizam_user -p$MYSQL_PASSWORD \
    --single-transaction \
    --routines \
    --triggers \
    --events \
    $DB_NAME > $BACKUP_DIR/music_backup_$DATE.sql

# 圧縮
gzip $BACKUP_DIR/music_backup_$DATE.sql

echo "バックアップ完了: music_backup_$DATE.sql.gz"
```

### バイナリログバックアップ

```bash
#!/bin/bash
# バイナリログバックアップ

BINLOG_DIR="/var/lib/mysql"
BACKUP_DIR="/backup/mysql/binlogs"

# バイナリログをフラッシュ
mysql -u root -p -e "FLUSH LOGS"

# 古いバイナリログをバックアップ
rsync -av $BINLOG_DIR/mysql-bin.* $BACKUP_DIR/

echo "バイナリログバックアップ完了"
```

### 復元

```bash
#!/bin/bash
# データベース復元

BACKUP_FILE="/backup/mysql/music_backup_20240101_120000.sql.gz"
DB_NAME="music_db"

# データベース削除・再作成
mysql -u root -p -e "DROP DATABASE IF EXISTS $DB_NAME"
mysql -u root -p -e "CREATE DATABASE $DB_NAME CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"

# バックアップから復元
gunzip -c $BACKUP_FILE | mysql -u mimizam_user -p $DB_NAME

echo "復元完了"
```

## 監視とメンテナンス

### パフォーマンス監視

```python
def monitor_mysql_performance(connection):
    """MySQLパフォーマンスを監視"""
    cursor = connection.cursor()
    
    # 接続状況
    cursor.execute("SHOW STATUS LIKE 'Connections'")
    connections = cursor.fetchone()
    
    cursor.execute("SHOW STATUS LIKE 'Threads_connected'")
    active_connections = cursor.fetchone()
    
    # クエリ統計
    cursor.execute("SHOW STATUS LIKE 'Questions'")
    questions = cursor.fetchone()
    
    cursor.execute("SHOW STATUS LIKE 'Slow_queries'")
    slow_queries = cursor.fetchone()
    
    # InnoDB統計
    cursor.execute("SHOW STATUS LIKE 'Innodb_buffer_pool_read_requests'")
    buffer_reads = cursor.fetchone()
    
    cursor.execute("SHOW STATUS LIKE 'Innodb_buffer_pool_reads'")
    disk_reads = cursor.fetchone()
    
    # バッファプール効率
    if buffer_reads[1] > 0:
        hit_ratio = (1 - int(disk_reads[1]) / int(buffer_reads[1])) * 100
    else:
        hit_ratio = 0
    
    return {
        'total_connections': connections[1],
        'active_connections': active_connections[1],
        'total_questions': questions[1],
        'slow_queries': slow_queries[1],
        'buffer_pool_hit_ratio': f"{hit_ratio:.2f}%"
    }
```

### 定期メンテナンス

```python
def maintain_mysql_database(connection):
    """MySQLデータベースの定期メンテナンス"""
    cursor = connection.cursor()
    
    # テーブル最適化
    cursor.execute("OPTIMIZE TABLE songs")
    cursor.execute("OPTIMIZE TABLE fingerprints")
    
    # 統計情報更新
    cursor.execute("ANALYZE TABLE songs")
    cursor.execute("ANALYZE TABLE fingerprints")
    
    # 不要なバイナリログ削除（7日以上古い）
    cursor.execute("PURGE BINARY LOGS BEFORE DATE_SUB(NOW(), INTERVAL 7 DAY)")
    
    print("MySQLメンテナンス完了")
```

## トラブルシューティング

### 接続問題

```python
import mysql.connector
from mysql.connector import Error
import time

def test_mysql_connection(config, max_retries=3):
    """MySQL接続をテスト"""
    for attempt in range(max_retries):
        try:
            connection = mysql.connector.connect(**config)
            if connection.is_connected():
                cursor = connection.cursor()
                cursor.execute("SELECT VERSION()")
                version = cursor.fetchone()
                print(f"MySQL接続成功: {version[0]}")
                connection.close()
                return True
        except Error as e:
            print(f"接続エラー（試行 {attempt + 1}/{max_retries}）: {e}")
            if attempt < max_retries - 1:
                time.sleep(2)
    
    return False
```

### デッドロック対処

```python
def handle_mysql_deadlock(operation, max_retries=3):
    """MySQLデッドロックを処理"""
    for attempt in range(max_retries):
        try:
            return operation()
        except mysql.connector.Error as e:
            if e.errno == 1213:  # Deadlock found
                print(f"デッドロック検出（試行 {attempt + 1}/{max_retries}）")
                if attempt < max_retries - 1:
                    time.sleep(0.1 * (2 ** attempt))  # 指数バックオフ
                else:
                    raise
            else:
                raise
```

### ログ分析

```python
def analyze_mysql_slow_log(log_file_path):
    """MySQLスローログを分析"""
    slow_queries = []
    
    with open(log_file_path, 'r') as f:
        current_query = {}
        for line in f:
            if line.startswith('# Time:'):
                if current_query:
                    slow_queries.append(current_query)
                current_query = {'timestamp': line.strip()}
            elif line.startswith('# Query_time:'):
                parts = line.split()
                current_query['query_time'] = float(parts[2])
                current_query['lock_time'] = float(parts[4])
            elif not line.startswith('#') and line.strip():
                current_query['query'] = line.strip()
    
    # 最後のクエリを追加
    if current_query:
        slow_queries.append(current_query)
    
    # クエリ時間でソート
    slow_queries.sort(key=lambda x: x.get('query_time', 0), reverse=True)
    
    return slow_queries[:10]  # 上位10件
```

## セキュリティ設定

### ユーザー権限管理

```sql
-- 読み取り専用ユーザー
CREATE USER 'mimizam_readonly'@'%' IDENTIFIED BY 'readonly_password';
GRANT SELECT ON music_db.* TO 'mimizam_readonly'@'%';

-- アプリケーション用ユーザー（制限付き）
CREATE USER 'mimizam_app'@'app-server.example.com' IDENTIFIED BY 'app_password';
GRANT SELECT, INSERT, UPDATE, DELETE ON music_db.songs TO 'mimizam_app'@'app-server.example.com';
GRANT SELECT, INSERT, DELETE ON music_db.fingerprints TO 'mimizam_app'@'app-server.example.com';

FLUSH PRIVILEGES;
```

### SSL設定

```sql
-- SSL必須設定
ALTER USER 'mimizam_user'@'%' REQUIRE SSL;

-- SSL証明書による認証
ALTER USER 'mimizam_secure'@'%' REQUIRE X509;
```

## 関連ドキュメント

- [データベースバックエンド概要](./05_database_backends.md) - 全バックエンドの比較
- [SQLiteバックエンド](./05_1_sqlite_backend.md) - 軽量ファイルベースDB
- [PostgreSQLバックエンド](./05_3_postgresql_backend.md) - 高機能RDBMS
- [Elasticsearchバックエンド](./05_4_elasticsearch_backend.md) - 分散検索エンジン
