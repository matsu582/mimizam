# PostgreSQLバックエンド

PostgreSQLバックエンドは、高性能アプリケーションや複雑なクエリ要件を持つシステムに最適な高機能リレーショナルデータベースソリューションです。高度なインデックス機能、JSON対応、優秀な拡張性を提供します。

他のデータベースバックエンドについては、[データベースバックエンド概要](./09_database_backends.md)を参照してください。

## 主要特徴

### 利点

- **高度なクエリ最適化**: 複雑なクエリで優秀な性能
- **豊富なデータ型**: JSON、配列、カスタム型をサポート
- **優秀な同時実行制御**: MVCC（Multi-Version Concurrency Control）
- **拡張性**: カスタム関数、演算子、データ型の追加可能
- **ACID準拠**: 完全なトランザクション保証

### 考慮事項

- **設定の複雑さ**: 最適化には詳細な設定が必要
- **リソース使用量**: メモリとCPUを多く消費
- **学習コスト**: 高度な機能の習得に時間が必要

## 基本的な使用方法

### ファクトリ関数

```python
from mimizam import create_mimizam_postgresql

# 基本的な接続
mimizam = create_mimizam_postgresql(
    host="localhost",
    database="music_db",
    username="mimizam_user",
    password="secure_password"
)

# ポート指定
mimizam = create_mimizam_postgresql(
    host="db.example.com",
    port=5432,
    database="music_db",
    username="mimizam_user",
    password="secure_password"
)
```

### 高度な接続設定

```python
# SSL接続
mimizam = create_mimizam_postgresql(
    host="secure-db.example.com",
    database="music_db",
    username="mimizam_user",
    password="secure_password",
    sslmode="require",
    sslcert="/path/to/client.crt",
    sslkey="/path/to/client.key",
    sslrootcert="/path/to/ca.crt"
)

# 接続プール設定
mimizam = create_mimizam_postgresql(
    host="localhost",
    database="music_db",
    username="mimizam_user",
    password="secure_password",
    pool_size=15,
    max_overflow=25,
    pool_timeout=60,
    pool_recycle=3600
)
```

## データベースセットアップ

### データベース作成

```sql
-- データベース作成
CREATE DATABASE music_db 
    WITH ENCODING 'UTF8' 
    LC_COLLATE='ja_JP.UTF-8' 
    LC_CTYPE='ja_JP.UTF-8';

-- ユーザー作成と権限付与
CREATE USER mimizam_user WITH PASSWORD 'secure_password';
GRANT ALL PRIVILEGES ON DATABASE music_db TO mimizam_user;

-- 接続
\c music_db

-- スキーマ権限
GRANT ALL ON SCHEMA public TO mimizam_user;
```

### テーブル作成

```sql
-- 楽曲テーブル
CREATE TABLE songs (
    id BIGSERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    artist VARCHAR(255) NOT NULL,
    duration DOUBLE PRECISION,
    file_path TEXT,
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 指紋テーブル
CREATE TABLE fingerprints (
    id BIGSERIAL PRIMARY KEY,
    song_id BIGINT NOT NULL REFERENCES songs(id) ON DELETE CASCADE,
    hash VARCHAR(64) NOT NULL,
    time_offset DOUBLE PRECISION NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- インデックス作成
CREATE INDEX idx_songs_title ON songs USING btree(title);
CREATE INDEX idx_songs_artist ON songs USING btree(artist);
CREATE INDEX idx_songs_metadata ON songs USING gin(metadata);
CREATE INDEX idx_songs_created_at ON songs USING btree(created_at);

CREATE INDEX idx_fingerprints_hash ON fingerprints USING hash(hash);
CREATE INDEX idx_fingerprints_song_id ON fingerprints USING btree(song_id);
CREATE INDEX idx_fingerprints_time_offset ON fingerprints USING btree(time_offset);
CREATE INDEX idx_fingerprints_hash_btree ON fingerprints USING btree(hash);
CREATE INDEX idx_fingerprints_composite ON fingerprints USING btree(hash, song_id);
```

## パフォーマンス最適化

### PostgreSQL設定最適化

```sql
-- メモリ設定
ALTER SYSTEM SET shared_buffers = '256MB';
ALTER SYSTEM SET effective_cache_size = '1GB';
ALTER SYSTEM SET work_mem = '64MB';
ALTER SYSTEM SET maintenance_work_mem = '256MB';

-- 接続設定
ALTER SYSTEM SET max_connections = 200;
ALTER SYSTEM SET max_worker_processes = 8;
ALTER SYSTEM SET max_parallel_workers = 8;
ALTER SYSTEM SET max_parallel_workers_per_gather = 4;

-- WAL設定
ALTER SYSTEM SET wal_buffers = '16MB';
ALTER SYSTEM SET checkpoint_completion_target = 0.9;
ALTER SYSTEM SET wal_writer_delay = '200ms';

-- 設定再読み込み
SELECT pg_reload_conf();
```

### インデックス最適化

```python
def optimize_postgresql_indices(backend):
    """PostgreSQLインデックスの最適化"""
    # 統計情報更新
    backend.execute_query("ANALYZE songs, fingerprints")
    
    # インデックス使用状況確認
    result = backend.execute_query("""
        SELECT schemaname, tablename, indexname, idx_tup_read, idx_tup_fetch
        FROM pg_stat_user_indexes
        ORDER BY idx_tup_read DESC
    """)
    
    for schema, table, index, reads, fetches in result:
        efficiency = fetches / max(reads, 1) * 100
        print(f"インデックス: {index}, 効率: {efficiency:.1f}%")
    
    # 未使用インデックス検出
    result = backend.execute_query("""
        SELECT schemaname, tablename, indexname
        FROM pg_stat_user_indexes
        WHERE idx_tup_read = 0 AND idx_tup_fetch = 0
    """)
    
    for schema, table, index in result:
        print(f"未使用インデックス: {index}")
```

### クエリ最適化

```python
def optimize_postgresql_queries(backend):
    """PostgreSQLクエリの最適化"""
    # 自動バキューム設定
    backend.execute_query("""
        ALTER TABLE songs SET (
            autovacuum_vacuum_scale_factor = 0.1,
            autovacuum_analyze_scale_factor = 0.05
        )
    """)
    
    backend.execute_query("""
        ALTER TABLE fingerprints SET (
            autovacuum_vacuum_scale_factor = 0.05,
            autovacuum_analyze_scale_factor = 0.02
        )
    """)
    
    # 並列クエリ有効化
    backend.execute_query("SET max_parallel_workers_per_gather = 4")
    backend.execute_query("SET parallel_tuple_cost = 0.1")
    backend.execute_query("SET parallel_setup_cost = 1000")
```

## 高度な機能

### JSON メタデータ活用

```python
def add_song_with_metadata(mimizam, file_path, title, artist, metadata):
    """メタデータ付き楽曲追加"""
    backend = mimizam.database.backend
    
    # メタデータをJSONBとして保存
    query = """
        INSERT INTO songs (title, artist, file_path, metadata)
        VALUES (%s, %s, %s, %s)
        RETURNING id
    """
    
    result = backend.execute_query(query, (title, artist, file_path, json.dumps(metadata)))
    song_id = result[0][0]
    
    # 指紋生成と保存
    fingerprints = mimizam.fingerprinter.generate_fingerprints(file_path)
    mimizam.database._store_fingerprints(song_id, fingerprints)
    
    return song_id

def search_songs_by_metadata(backend, metadata_query):
    """JSONBメタデータによる楽曲検索"""
    query = """
        SELECT id, title, artist, metadata
        FROM songs
        WHERE metadata @> %s
    """
    
    return backend.execute_query(query, (json.dumps(metadata_query),))
```

### 全文検索

```python
def setup_fulltext_search(backend):
    """全文検索の設定"""
    # 全文検索インデックス作成
    backend.execute_query("""
        ALTER TABLE songs ADD COLUMN search_vector tsvector
    """)
    
    backend.execute_query("""
        UPDATE songs SET search_vector = 
            to_tsvector('japanese', coalesce(title, '') || ' ' || coalesce(artist, ''))
    """)
    
    backend.execute_query("""
        CREATE INDEX idx_songs_search_vector ON songs USING gin(search_vector)
    """)
    
    # 自動更新トリガー
    backend.execute_query("""
        CREATE OR REPLACE FUNCTION update_search_vector() RETURNS trigger AS $$
        BEGIN
            NEW.search_vector := to_tsvector('japanese', 
                coalesce(NEW.title, '') || ' ' || coalesce(NEW.artist, ''));
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    
    backend.execute_query("""
        CREATE TRIGGER update_songs_search_vector
        BEFORE INSERT OR UPDATE ON songs
        FOR EACH ROW EXECUTE FUNCTION update_search_vector();
    """)

def fulltext_search_songs(backend, search_term):
    """全文検索による楽曲検索"""
    query = """
        SELECT id, title, artist, ts_rank(search_vector, query) as rank
        FROM songs, plainto_tsquery('japanese', %s) query
        WHERE search_vector @@ query
        ORDER BY rank DESC
    """
    
    return backend.execute_query(query, (search_term,))
```

### パーティショニング

```python
def setup_table_partitioning(backend):
    """テーブルパーティショニングの設定"""
    # 日付ベースパーティショニング
    backend.execute_query("""
        CREATE TABLE songs_partitioned (
            LIKE songs INCLUDING ALL
        ) PARTITION BY RANGE (created_at);
    """)
    
    # 月別パーティション作成
    from datetime import datetime, timedelta
    
    current_date = datetime.now().replace(day=1)
    for i in range(12):
        start_date = current_date + timedelta(days=32*i)
        end_date = current_date + timedelta(days=32*(i+1))
        
        partition_name = f"songs_{start_date.strftime('%Y_%m')}"
        
        backend.execute_query(f"""
            CREATE TABLE {partition_name} PARTITION OF songs_partitioned
            FOR VALUES FROM ('{start_date}') TO ('{end_date}')
        """)
```

## レプリケーション設定

### ストリーミングレプリケーション

```python
class PostgreSQLReplicationBackend:
    def __init__(self, master_config, replica_configs):
        self.master = PostgreSQLBackend(**master_config)
        self.replicas = [PostgreSQLBackend(**config) for config in replica_configs]
        self.current_replica = 0
    
    def execute_write_query(self, query, params=()):
        """書き込みクエリはマスターに送信"""
        return self.master.execute_query(query, params)
    
    def execute_read_query(self, query, params=()):
        """読み取りクエリはレプリカに分散"""
        replica = self.replicas[self.current_replica]
        self.current_replica = (self.current_replica + 1) % len(self.replicas)
        
        try:
            return replica.execute_query(query, params)
        except Exception as e:
            # レプリカ障害時はマスターにフォールバック
            print(f"レプリカエラー、マスターにフォールバック: {e}")
            return self.master.execute_query(query, params)
```

### 論理レプリケーション

```sql
-- パブリケーション作成（マスター側）
CREATE PUBLICATION mimizam_pub FOR TABLE songs, fingerprints;

-- サブスクリプション作成（レプリカ側）
CREATE SUBSCRIPTION mimizam_sub 
CONNECTION 'host=master_host dbname=music_db user=replication_user password=repl_password'
PUBLICATION mimizam_pub;
```

## バックアップと復元

### pg_dumpバックアップ

```python
import subprocess
from datetime import datetime

def backup_postgresql_database(config):
    """PostgreSQLデータベースのバックアップ"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = f"music_db_backup_{timestamp}.sql"
    
    env = os.environ.copy()
    env['PGPASSWORD'] = config['password']
    
    cmd = [
        "pg_dump",
        f"--host={config['host']}",
        f"--port={config.get('port', 5432)}",
        f"--username={config['username']}",
        "--format=custom",
        "--compress=9",
        "--verbose",
        config['database']
    ]
    
    with open(backup_file, 'wb') as f:
        subprocess.run(cmd, stdout=f, env=env, check=True)
    
    print(f"バックアップ作成: {backup_file}")
    return backup_file
```

### 継続的アーカイブ

```python
def setup_continuous_archiving(config):
    """継続的アーカイブの設定"""
    # postgresql.confに以下を追加:
    archive_config = """
    # WALアーカイブ設定
    wal_level = replica
    archive_mode = on
    archive_command = 'cp %p /backup/postgresql/wal/%f'
    max_wal_senders = 3
    wal_keep_segments = 32
    """
    
    # ベースバックアップスクリプト
    backup_script = f"""
    #!/bin/bash
    BACKUP_DIR="/backup/postgresql/base"
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    
    pg_basebackup -h {config['host']} -U {config['username']} \\
        -D $BACKUP_DIR/backup_$TIMESTAMP \\
        -Ft -z -P -v
    """
    
    return archive_config, backup_script
```

### 復元

```python
def restore_postgresql_database(config, backup_file):
    """PostgreSQLデータベースの復元"""
    env = os.environ.copy()
    env['PGPASSWORD'] = config['password']
    
    cmd = [
        "pg_restore",
        f"--host={config['host']}",
        f"--port={config.get('port', 5432)}",
        f"--username={config['username']}",
        f"--dbname={config['database']}",
        "--clean",
        "--if-exists",
        "--verbose",
        backup_file
    ]
    
    subprocess.run(cmd, env=env, check=True)
    print(f"データベース復元完了: {backup_file}")
```

## 監視とメンテナンス

### パフォーマンス監視

```python
def monitor_postgresql_performance(backend):
    """PostgreSQLパフォーマンス監視"""
    # 接続統計
    result = backend.execute_query("""
        SELECT count(*) as active_connections
        FROM pg_stat_activity
        WHERE state = 'active'
    """)
    active_connections = result[0][0] if result else 0
    
    # データベース統計
    result = backend.execute_query("""
        SELECT numbackends, xact_commit, xact_rollback, 
               blks_read, blks_hit, tup_returned, tup_fetched
        FROM pg_stat_database
        WHERE datname = current_database()
    """)
    
    if result:
        stats = result[0]
        cache_hit_ratio = stats[5] / max(stats[4] + stats[5], 1) * 100
        
        return {
            'active_connections': active_connections,
            'backends': stats[0],
            'commits': stats[1],
            'rollbacks': stats[2],
            'cache_hit_ratio': cache_hit_ratio,
            'tuples_returned': stats[6],
            'tuples_fetched': stats[7]
        }
    
    return {}
```

### 自動バキューム監視

```python
def monitor_autovacuum(backend):
    """自動バキューム監視"""
    result = backend.execute_query("""
        SELECT schemaname, tablename, last_vacuum, last_autovacuum,
               last_analyze, last_autoanalyze, vacuum_count, autovacuum_count
        FROM pg_stat_user_tables
        ORDER BY last_autovacuum DESC NULLS LAST
    """)
    
    print("自動バキューム統計:")
    for row in result:
        schema, table, last_vacuum, last_autovacuum, last_analyze, last_autoanalyze, vacuum_count, autovacuum_count = row
        print(f"テーブル: {table}")
        print(f"  最終バキューム: {last_autovacuum or last_vacuum}")
        print(f"  最終分析: {last_autoanalyze or last_analyze}")
        print(f"  バキューム回数: {autovacuum_count + vacuum_count}")
```

## トラブルシューティング

### 接続問題

```python
def diagnose_postgresql_connection(config):
    """PostgreSQL接続問題の診断"""
    import psycopg2
    
    try:
        connection = psycopg2.connect(**config)
        print("接続成功")
        connection.close()
        
    except psycopg2.OperationalError as e:
        error_msg = str(e)
        
        if "authentication failed" in error_msg:
            print("認証エラー: ユーザー名またはパスワードが間違っています")
        elif "could not connect to server" in error_msg:
            print("接続エラー: サーバーに接続できません")
        elif "database" in error_msg and "does not exist" in error_msg:
            print("データベースエラー: 指定されたデータベースが存在しません")
        else:
            print(f"その他のエラー: {e}")
```

### 性能問題の診断

```python
def analyze_postgresql_slow_queries(backend):
    """スロークエリの分析"""
    # pg_stat_statements拡張が必要
    backend.execute_query("CREATE EXTENSION IF NOT EXISTS pg_stat_statements")
    
    # スロークエリ取得
    result = backend.execute_query("""
        SELECT query, calls, total_time, mean_time, rows
        FROM pg_stat_statements
        WHERE mean_time > 1000  -- 1秒以上
        ORDER BY mean_time DESC
        LIMIT 10
    """)
    
    print("スロークエリ:")
    for query, calls, total_time, mean_time, rows in result:
        print(f"平均時間: {mean_time:.2f}ms, 呼び出し回数: {calls}")
        print(f"クエリ: {query[:100]}...")
```

## 実用例

### 本番環境設定

```python
def setup_production_postgresql():
    """本番環境用PostgreSQL設定"""
    config = {
        'host': 'prod-postgres.example.com',
        'port': 5432,
        'database': 'music_production',
        'username': 'mimizam_prod',
        'password': os.environ['POSTGRES_PASSWORD'],
        'sslmode': 'require',
        'pool_size': 20,
        'max_overflow': 30,
        'pool_timeout': 60,
        'pool_recycle': 3600
    }
    
    return create_mimizam_postgresql(**config)
```

### 開発環境設定

```python
def setup_development_postgresql():
    """開発環境用PostgreSQL設定"""
    config = {
        'host': 'localhost',
        'port': 5432,
        'database': 'music_dev',
        'username': 'dev_user',
        'password': 'dev_password',
        'pool_size': 5,
        'max_overflow': 10
    }
    
    return create_mimizam_postgresql(**config)
```

## 関連ドキュメント

- [データベースバックエンド概要](./09_database_backends.md) - 全バックエンドの比較
- [データベース層](./05_database_layer.md) - データベース抽象化
- [MySQLバックエンド](./11_mysql_backend.md) - MySQL固有の設定
- [Elasticsearchバックエンド](./13_elasticsearch_backend.md) - Elasticsearch固有の設定
- [パフォーマンス最適化](./16_performance_optimization.md) - 高速化技術
