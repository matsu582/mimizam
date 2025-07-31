# SQLiteバックエンド

> 関連するソースファイル

SQLiteバックエンドは、開発環境やプロトタイピングに最適な軽量ファイルベースデータベースソリューションです。設定が不要で、単一ファイルでデータベース全体を管理できます。

他のデータベースバックエンドについては、[データベースバックエンド概要](./05_database_backends.md)を参照してください。

## 主要特徴

### 利点

- **設定不要**: インストールや設定が不要
- **軽量**: 単一ファイルでデータベース全体を管理
- **高速**: 小規模データセットでの高速アクセス
- **ポータブル**: ファイルコピーで簡単にバックアップ・移行
- **ACID準拠**: トランザクションの完全性を保証

### 制限事項

- **同時接続制限**: 複数の書き込み接続は不可
- **スケーラビリティ**: 大規模データには不向き
- **ネットワークアクセス**: リモートアクセス不可
- **パフォーマンス**: 大量データでの性能低下

## 基本的な使用方法

### ファクトリ関数

SQLiteバックエンドは、専用のファクトリ関数を通じて簡単に初期化できます。基本的な使用では単純にデータベースファイルパスを指定するだけで、カスタムパラメータによる詳細な調整も可能です。

### データベースファイル管理

SQLiteの特徴である単一ファイル管理により、データベースの存在確認、サイズ監視、バックアップが容易に実現できます。ファイルベースの特性を活かした効率的な管理が可能です。

## データベーススキーマ

### テーブル構造

SQLiteバックエンドは、楽曲メタデータと指紋データを効率的に管理する最適化されたスキーマを使用します。楽曲テーブルには基本的なメタデータが格納され、指紋テーブルには音響指紋の詳細情報が保存されます。適切なインデックス設計により、高速な検索性能を実現します。

## パフォーマンス最適化

### WALモード

Write-Ahead Logging（WAL）モードの有効化により、読み取り性能の向上と同時アクセスの改善を実現します。従来のロールバックジャーナルと比較して、より効率的な並行処理が可能になります。

### メモリ設定

SQLiteの性能最適化には、キャッシュサイズの調整、同期モードの設定、一時ファイルの管理が重要です。これらの設定により、メモリ使用量と処理速度のバランスを最適化できます。

## バックアップと復元

### ファイルベースバックアップ

```python
import shutil
from datetime import datetime

def backup_sqlite_database(db_path, backup_dir="backups"):
    """SQLiteデータベースをバックアップ"""
    import os
    
    if not os.path.exists(backup_dir):
        os.makedirs(backup_dir)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"music_backup_{timestamp}.db"
    backup_path = os.path.join(backup_dir, backup_filename)
    
    shutil.copy2(db_path, backup_path)
    print(f"バックアップ完了: {backup_path}")
    
    return backup_path

# 使用例
backup_path = backup_sqlite_database("music.db")
```

### SQLダンプバックアップ

```python
import sqlite3

def dump_sqlite_database(db_path, dump_path):
    """SQLiteデータベースをSQLダンプとしてバックアップ"""
    conn = sqlite3.connect(db_path)
    
    with open(dump_path, 'w', encoding='utf-8') as f:
        for line in conn.iterdump():
            f.write(f"{line}\n")
    
    conn.close()
    print(f"SQLダンプ完了: {dump_path}")

# 使用例
dump_sqlite_database("music.db", "music_dump.sql")
```

## トラブルシューティング

### データベースロック

```python
import sqlite3
import time

def handle_database_lock(db_path, max_retries=5):
    """データベースロックを処理"""
    for attempt in range(max_retries):
        try:
            conn = sqlite3.connect(db_path, timeout=30.0)
            # データベース操作を実行
            conn.execute("SELECT COUNT(*) FROM songs")
            conn.close()
            return True
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e):
                print(f"データベースがロックされています（試行 {attempt + 1}/{max_retries}）")
                time.sleep(1)
            else:
                raise
    
    return False
```

### データベース修復

```python
def repair_sqlite_database(db_path):
    """SQLiteデータベースの整合性をチェックし修復"""
    conn = sqlite3.connect(db_path)
    
    # 整合性チェック
    cursor = conn.cursor()
    cursor.execute("PRAGMA integrity_check")
    result = cursor.fetchone()
    
    if result[0] == "ok":
        print("データベースの整合性に問題ありません")
    else:
        print(f"整合性エラー: {result[0]}")
        
        # VACUUMで修復を試行
        try:
            conn.execute("VACUUM")
            print("VACUUM実行完了")
        except Exception as e:
            print(f"修復エラー: {e}")
    
    conn.close()
```

## 開発のベストプラクティス

### 接続管理

```python
import sqlite3
from contextlib import contextmanager

@contextmanager
def sqlite_connection(db_path):
    """SQLite接続のコンテキストマネージャー"""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row  # 辞書形式でアクセス可能
    try:
        yield conn
    finally:
        conn.close()

# 使用例
with sqlite_connection("music.db") as conn:
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM songs LIMIT 5")
    songs = cursor.fetchall()
    for song in songs:
        print(f"楽曲: {song['name']}")
```

### バッチ処理

```python
def batch_insert_songs(db_path, songs_data):
    """楽曲データをバッチで挿入"""
    with sqlite_connection(db_path) as conn:
        cursor = conn.cursor()
        
        # バッチ挿入
        cursor.executemany('''
            INSERT INTO songs (name, artist, album, duration, file_path)
            VALUES (?, ?, ?, ?, ?)
        ''', songs_data)
        
        conn.commit()
        print(f"{len(songs_data)}曲をバッチ挿入しました")

# 使用例
songs_data = [
    ("Song 1", "Artist 1", "Album 1", 180.5, "/path/to/song1.wav"),
    ("Song 2", "Artist 2", "Album 2", 210.3, "/path/to/song2.wav"),
]
batch_insert_songs("music.db", songs_data)
```

## 制限事項と対処法

### 同時書き込み制限

```python
import threading
import queue
import time

class SQLiteWriteQueue:
    """SQLite書き込み操作のキューイング"""
    
    def __init__(self, db_path):
        self.db_path = db_path
        self.write_queue = queue.Queue()
        self.worker_thread = threading.Thread(target=self._process_writes)
        self.worker_thread.daemon = True
        self.worker_thread.start()
    
    def _process_writes(self):
        """書き込み操作を順次処理"""
        while True:
            try:
                operation = self.write_queue.get(timeout=1)
                if operation is None:
                    break
                
                # 書き込み操作を実行
                with sqlite_connection(self.db_path) as conn:
                    operation(conn)
                
                self.write_queue.task_done()
            except queue.Empty:
                continue
    
    def add_write_operation(self, operation):
        """書き込み操作をキューに追加"""
        self.write_queue.put(operation)
    
    def shutdown(self):
        """ワーカースレッドを終了"""
        self.write_queue.put(None)
        self.worker_thread.join()

# 使用例
write_queue = SQLiteWriteQueue("music.db")

def insert_song(conn):
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO songs (name, artist) VALUES (?, ?)",
        ("Test Song", "Test Artist")
    )
    conn.commit()

write_queue.add_write_operation(insert_song)
```

## 監視とメンテナンス

### データベース統計

```python
def get_sqlite_statistics(db_path):
    """SQLiteデータベースの統計情報を取得"""
    with sqlite_connection(db_path) as conn:
        cursor = conn.cursor()
        
        # テーブル統計
        cursor.execute("SELECT COUNT(*) FROM songs")
        song_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM fingerprints")
        fingerprint_count = cursor.fetchone()[0]
        
        # ファイルサイズ
        file_size = os.path.getsize(db_path)
        
        # ページ統計
        cursor.execute("PRAGMA page_count")
        page_count = cursor.fetchone()[0]
        
        cursor.execute("PRAGMA page_size")
        page_size = cursor.fetchone()[0]
        
        return {
            'song_count': song_count,
            'fingerprint_count': fingerprint_count,
            'file_size_mb': file_size / 1024 / 1024,
            'page_count': page_count,
            'page_size': page_size,
            'database_size_mb': (page_count * page_size) / 1024 / 1024
        }

# 使用例
stats = get_sqlite_statistics("music.db")
print(f"楽曲数: {stats['song_count']}")
print(f"指紋数: {stats['fingerprint_count']}")
print(f"ファイルサイズ: {stats['file_size_mb']:.2f} MB")
```

### 定期メンテナンス

```python
def maintain_sqlite_database(db_path):
    """SQLiteデータベースの定期メンテナンス"""
    with sqlite_connection(db_path) as conn:
        cursor = conn.cursor()
        
        # 統計情報を更新
        cursor.execute("ANALYZE")
        
        # 未使用領域を回収
        cursor.execute("VACUUM")
        
        # インデックスを再構築
        cursor.execute("REINDEX")
        
        conn.commit()
        print("データベースメンテナンス完了")

# 定期実行の例
import schedule

schedule.every().week.do(maintain_sqlite_database, "music.db")
```

## 関連ドキュメント

- [データベースバックエンド概要](./05_database_backends.md) - 全バックエンドの比較
- [MySQLバックエンド](./05_2_mysql_backend.md) - 本番環境向けRDBMS
- [PostgreSQLバックエンド](./05_3_postgresql_backend.md) - 高機能RDBMS
- [Elasticsearchバックエンド](./05_4_elasticsearch_backend.md) - 分散検索エンジン
