# SQLiteバックエンド

SQLiteバックエンドは、mimizamシステムの最もシンプルで使いやすいストレージオプションです。ファイルベースのデータベースとして、ゼロ設定で即座に使用開始でき、開発、プロトタイピング、小規模デプロイメントに最適です。

他のデータベースバックエンドについては、[データベースバックエンド概要](./09_database_backends.md)を参照してください。

## 主要特徴

### 利点

- **ゼロ設定**: サーバーインストール不要
- **ファイルベース**: 単一ファイルでデータベース全体を管理
- **高速**: 小〜中規模データセットで優秀な性能
- **移植性**: データベースファイルの簡単な移動・共有
- **信頼性**: ACID準拠のトランザクション

### 制限事項

- **同時書き込み**: 単一の書き込み接続のみ
- **スケーラビリティ**: 大規模データセットでは性能低下
- **ネットワークアクセス**: 直接的なリモートアクセス不可

## 基本的な使用方法

### ファクトリ関数

```python
from mimizam import create_mimizam_sqlite

# 基本的な使用
mimizam = create_mimizam_sqlite("music.db")

# 設定付きの使用
mimizam = create_mimizam_sqlite(
    "music.db",
    n_fft=2048,
    hop_length=512,
    min_amplitude=-60,
    enable_adaptive_params=True
)
```

### コンテキストマネージャー

```python
# 推奨: コンテキストマネージャーを使用
with create_mimizam_sqlite("music.db") as mimizam:
    song_id = mimizam.add_song("song.wav", "Title", "Artist")
    result = mimizam.identify_audio("query.wav")
# 自動的にデータベース接続が閉じられる
```

## 設定オプション

### データベースファイルパス

```python
# 相対パス
mimizam = create_mimizam_sqlite("music.db")

# 絶対パス
mimizam = create_mimizam_sqlite("/path/to/music.db")

# メモリ内データベース（テスト用）
mimizam = create_mimizam_sqlite(":memory:")
```

### SQLite固有の最適化

```python
class SQLiteBackend:
    def _optimize_sqlite(self):
        """SQLite固有の最適化設定"""
        # WALモード（Write-Ahead Logging）
        self.execute_query("PRAGMA journal_mode=WAL")
        
        # 同期モード調整
        self.execute_query("PRAGMA synchronous=NORMAL")
        
        # キャッシュサイズ増加
        self.execute_query("PRAGMA cache_size=10000")
        
        # 一時ストレージをメモリに
        self.execute_query("PRAGMA temp_store=MEMORY")
        
        # 外部キー制約有効化
        self.execute_query("PRAGMA foreign_keys=ON")
```

## パフォーマンス最適化

### 書き込み最適化

```python
def batch_insert_songs(mimizam, song_list):
    """バッチ挿入による高速化"""
    with mimizam.database.backend.transaction():
        for file_path, title, artist in song_list:
            mimizam.add_song(file_path, title, artist)
```

### インデックス最適化

```python
def optimize_sqlite_indices(backend):
    """SQLiteインデックスの最適化"""
    # 統計情報更新
    backend.execute_query("ANALYZE")
    
    # インデックス再構築
    backend.execute_query("REINDEX")
    
    # 自動バキューム有効化
    backend.execute_query("PRAGMA auto_vacuum=INCREMENTAL")
    backend.execute_query("PRAGMA incremental_vacuum")
```

### メモリ設定

```python
def configure_sqlite_memory(backend):
    """SQLiteメモリ設定の最適化"""
    # ページキャッシュサイズ（MB単位）
    cache_size_mb = 64
    page_size = 4096
    cache_pages = (cache_size_mb * 1024 * 1024) // page_size
    
    backend.execute_query(f"PRAGMA cache_size={cache_pages}")
    
    # 一時ファイルをメモリに
    backend.execute_query("PRAGMA temp_store=MEMORY")
    
    # メモリマップサイズ
    backend.execute_query("PRAGMA mmap_size=268435456")  # 256MB
```

## データベーススキーマ

### テーブル定義

```sql
-- 楽曲テーブル
CREATE TABLE songs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    artist TEXT NOT NULL,
    duration REAL,
    file_path TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 指紋テーブル
CREATE TABLE fingerprints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    song_id INTEGER NOT NULL,
    hash TEXT NOT NULL,
    time_offset REAL NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (song_id) REFERENCES songs (id) ON DELETE CASCADE
);

-- インデックス
CREATE INDEX idx_fingerprints_hash ON fingerprints(hash);
CREATE INDEX idx_fingerprints_song_id ON fingerprints(song_id);
CREATE INDEX idx_fingerprints_time_offset ON fingerprints(time_offset);
CREATE INDEX idx_songs_title ON songs(title);
CREATE INDEX idx_songs_artist ON songs(artist);
```

## バックアップと復元

### ファイルベースバックアップ

```python
import shutil
from datetime import datetime

def backup_sqlite_database(db_path):
    """SQLiteデータベースのバックアップ"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{db_path}.backup_{timestamp}"
    
    shutil.copy2(db_path, backup_path)
    print(f"バックアップ作成: {backup_path}")
    
    return backup_path
```

### SQLダンプバックアップ

```python
import sqlite3

def dump_sqlite_database(db_path, dump_path):
    """SQLiteデータベースのSQLダンプ"""
    conn = sqlite3.connect(db_path)
    
    with open(dump_path, 'w') as f:
        for line in conn.iterdump():
            f.write(f"{line}\n")
    
    conn.close()
    print(f"SQLダンプ作成: {dump_path}")
```

### 復元

```python
def restore_sqlite_database(backup_path, target_path):
    """SQLiteデータベースの復元"""
    shutil.copy2(backup_path, target_path)
    print(f"データベース復元: {target_path}")

def restore_from_sql_dump(dump_path, db_path):
    """SQLダンプからの復元"""
    conn = sqlite3.connect(db_path)
    
    with open(dump_path, 'r') as f:
        sql_script = f.read()
    
    conn.executescript(sql_script)
    conn.close()
    print(f"SQLダンプから復元: {db_path}")
```

## 監視とメンテナンス

### データベース統計

```python
def get_sqlite_statistics(backend):
    """SQLiteデータベース統計を取得"""
    stats = {}
    
    # ファイルサイズ
    result = backend.execute_query("PRAGMA page_count")
    page_count = result[0][0] if result else 0
    
    result = backend.execute_query("PRAGMA page_size")
    page_size = result[0][0] if result else 0
    
    stats['file_size_bytes'] = page_count * page_size
    stats['file_size_mb'] = stats['file_size_bytes'] / (1024 * 1024)
    
    # テーブル統計
    result = backend.execute_query("SELECT COUNT(*) FROM songs")
    stats['song_count'] = result[0][0] if result else 0
    
    result = backend.execute_query("SELECT COUNT(*) FROM fingerprints")
    stats['fingerprint_count'] = result[0][0] if result else 0
    
    # インデックス情報
    result = backend.execute_query("PRAGMA index_list('fingerprints')")
    stats['index_count'] = len(result) if result else 0
    
    return stats
```

### 整合性チェック

```python
def check_sqlite_integrity(backend):
    """SQLiteデータベースの整合性チェック"""
    # 整合性チェック
    result = backend.execute_query("PRAGMA integrity_check")
    integrity_ok = result[0][0] == "ok" if result else False
    
    # 外部キー制約チェック
    result = backend.execute_query("PRAGMA foreign_key_check")
    foreign_key_ok = len(result) == 0 if result else False
    
    return {
        'integrity_ok': integrity_ok,
        'foreign_key_ok': foreign_key_ok,
        'overall_ok': integrity_ok and foreign_key_ok
    }
```

## トラブルシューティング

### 一般的な問題

#### データベースロック

```python
def handle_database_lock():
    """データベースロックの対処"""
    try:
        with create_mimizam_sqlite("music.db") as mimizam:
            # 操作実行
            pass
    except sqlite3.OperationalError as e:
        if "database is locked" in str(e):
            print("データベースがロックされています。しばらく待ってから再試行してください。")
            time.sleep(1)
            # 再試行ロジック
```

#### 破損データベース

```python
def repair_corrupted_database(db_path):
    """破損データベースの修復"""
    backup_path = f"{db_path}.corrupted_backup"
    shutil.copy2(db_path, backup_path)
    
    try:
        # ダンプして再作成
        dump_path = f"{db_path}.dump"
        dump_sqlite_database(db_path, dump_path)
        
        # 新しいデータベース作成
        os.remove(db_path)
        restore_from_sql_dump(dump_path, db_path)
        
        print("データベース修復完了")
        
    except Exception as e:
        # バックアップから復元
        shutil.copy2(backup_path, db_path)
        print(f"修復失敗、バックアップから復元: {e}")
```

### パフォーマンス問題

#### 遅いクエリの診断

```python
def analyze_slow_queries(backend):
    """遅いクエリの分析"""
    # クエリプランの確認
    explain_queries = [
        "EXPLAIN QUERY PLAN SELECT * FROM fingerprints WHERE hash = ?",
        "EXPLAIN QUERY PLAN SELECT * FROM songs WHERE title LIKE ?",
    ]
    
    for query in explain_queries:
        result = backend.execute_query(query, ("sample_hash",))
        print(f"Query Plan: {query}")
        for row in result:
            print(f"  {row}")
```

## 実用例

### 開発環境セットアップ

```python
def setup_development_database():
    """開発環境用データベースセットアップ"""
    with create_mimizam_sqlite("dev_music.db", debug=True) as mimizam:
        # テストデータ追加
        test_songs = [
            ("test1.wav", "Test Song 1", "Test Artist 1"),
            ("test2.wav", "Test Song 2", "Test Artist 2"),
        ]
        
        for file_path, title, artist in test_songs:
            try:
                song_id = mimizam.add_song(file_path, title, artist)
                print(f"テストデータ追加: {title} (ID: {song_id})")
            except Exception as e:
                print(f"エラー: {e}")
```

### 本番環境移行準備

```python
def prepare_production_migration(sqlite_path):
    """本番環境移行のためのデータ準備"""
    with create_mimizam_sqlite(sqlite_path) as mimizam:
        # データ統計取得
        stats = mimizam.get_database_stats()
        
        print("移行準備統計:")
        print(f"楽曲数: {stats['song_count']}")
        print(f"指紋数: {stats['fingerprint_count']:,}")
        print(f"データベースサイズ: {stats.get('file_size_mb', 0):.1f}MB")
        
        # データ整合性チェック
        integrity = check_sqlite_integrity(mimizam.database.backend)
        print(f"データ整合性: {'OK' if integrity['overall_ok'] else 'NG'}")
        
        return stats, integrity
```

## 関連ドキュメント

- [データベースバックエンド概要](./09_database_backends.md) - 全バックエンドの比較
- [データベース層](./05_database_layer.md) - データベース抽象化
- [基本的な使用方法](./02_installation.md) - インストールとセットアップ
- [高レベルAPI](./07_high_level_api.md) - 簡単な使用方法
- [パフォーマンス最適化](./16_performance_optimization.md) - 高速化技術
