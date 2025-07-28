"""SQLiteデータベースバックエンド実装"""

from typing import List, Optional, Dict, Tuple
from ..database_base import DatabaseBackend, DatabaseConfig, Song, Fingerprint
from ..exceptions import ConnectionError, QueryError, log_and_raise
import json

try:
    import sqlite3
except ImportError:
    sqlite3 = None


class SQLiteBackend(DatabaseBackend):
    """SQLiteデータベースバックエンド"""
    
    def __init__(self, config: DatabaseConfig):
        super().__init__(config)
        self.connection = None
        self.db_path = config.file_path or "fingerprints.db"
    
    def connect(self) -> bool:
        """SQLiteデータベースに接続（最適化設定付き）"""
        try:
            if sqlite3 is None:
                raise ImportError("sqlite3 module is not available")
            
            self.connection = sqlite3.connect(
                self.db_path, 
                check_same_thread=False,
                timeout=30.0  # タイムアウト設定
            )
            
            # パフォーマンス最適化設定
            cursor = self.connection.cursor()
            cursor.execute("PRAGMA foreign_keys = ON")
            cursor.execute("PRAGMA journal_mode = WAL")        # 読み取り時のブロック回避
            cursor.execute("PRAGMA synchronous = NORMAL")      # I/O最適化
            cursor.execute("PRAGMA cache_size = -64000")       # 64MBキャッシュ
            cursor.execute("PRAGMA temp_store = MEMORY")       # 一時テーブルをメモリに
            cursor.execute("PRAGMA mmap_size = 268435456")     # 256MBメモリマップ
            cursor.execute("PRAGMA optimize")                  # 統計情報最適化
            
            self.logger.info(f"Connected to SQLite database with optimization settings: {self.db_path}")
            return True
        except Exception as e:
            self.logger.error(f"SQLite connection error: {e}")
            return False
    
    def disconnect(self) -> None:
        """SQLiteデータベースから切断"""
        if self.connection:
            self.connection.close()
            self.connection = None
    
    def create_tables(self) -> bool:
        """SQLiteテーブルを作成"""
        try:
            cursor = self.connection.cursor()
            
            # 楽曲テーブル
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS songs (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    artist TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    meta TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # フィンガープリントテーブル
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS fingerprints (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    song_id TEXT NOT NULL,
                    hash_value TEXT NOT NULL,
                    time_offset REAL NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (song_id) REFERENCES songs (id)
                )
            """)
            
            # インデックス作成（最適化版）
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_fingerprints_hash 
                ON fingerprints (hash_value)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_fingerprints_song_id 
                ON fingerprints (song_id)
            """)
            
            # 複合インデックス追加
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_fingerprints_hash_song_time 
                ON fingerprints (hash_value, song_id, time_offset)
            """)
            
            # 統計情報更新
            cursor.execute("ANALYZE fingerprints")
            cursor.execute("ANALYZE songs")
            
            self.connection.commit()
            return True
        except Exception as e:
            self.logger.error(f"SQLite table creation error: {e}")
            return False
    
    def add_song(self, song: Song) -> bool:
        """SQLiteに楽曲を追加"""
        try:
            cursor = self.connection.cursor()
            meta_json = json.dumps(song.meta, ensure_ascii=False) if song.meta else None
            cursor.execute("""
                INSERT OR REPLACE INTO songs (id, title, artist, file_path, meta)
                VALUES (?, ?, ?, ?, ?)
            """, (song.id, song.title, song.artist, song.file_path, meta_json))
            self.connection.commit()
            return True
        except Exception as e:
            self.logger.error(f"SQLite song addition error: {e}")
            return False
    
    def add_fingerprints(self, song_id: str, fingerprints: List[Fingerprint]) -> bool:
        """SQLiteにフィンガープリントを追加"""
        try:
            cursor = self.connection.cursor()
            
            # 既存フィンガープリントを削除
            cursor.execute("DELETE FROM fingerprints WHERE song_id = ?", (song_id,))
            
            # numpy型をPython型に変換
            fingerprint_data = [
                (song_id, fp.hash_value, float(fp.time_offset)) 
                for fp in fingerprints
            ]
            
            cursor.executemany("""
                INSERT INTO fingerprints (song_id, hash_value, time_offset)
                VALUES (?, ?, ?)
            """, fingerprint_data)
            
            self.connection.commit()
            return True
        except Exception as e:
            self.logger.error(f"SQLite fingerprint addition error: {e}")
            return False
    
    def search_fingerprints(self, query_fingerprints: List[Fingerprint]) -> Dict[str, List[Tuple[float, float]]]:
        """SQLiteでフィンガープリントを検索"""
        matches = {}
        
        if not query_fingerprints:
            return matches
        
        try:
            cursor = self.connection.cursor()
            
            # バッチクエリ方式：IN句を使用して1回のクエリで全てのマッチを取得
            hash_to_query_time = {fp.hash_value: fp.time_offset for fp in query_fingerprints}
            hash_values = list(hash_to_query_time.keys())
            
            # SQLiteの変数制限（999個）を考慮してバッチ分割
            batch_size = 999
            for i in range(0, len(hash_values), batch_size):
                batch_hashes = hash_values[i:i + batch_size]
                placeholders = ','.join('?' * len(batch_hashes))
                
                cursor.execute(f"""
                    SELECT song_id, time_offset, hash_value
                    FROM fingerprints
                    WHERE hash_value IN ({placeholders})
                """, batch_hashes)
                
                # 結果を処理
                for song_id, db_time_offset, hash_value in cursor.fetchall():
                    query_time = hash_to_query_time[hash_value]
                    if song_id not in matches:
                        matches[song_id] = []
                    matches[song_id].append((float(query_time), float(db_time_offset)))
                    
        except Exception as e:
            self.logger.error(f"SQLite fingerprint search error: {e}")
        
        return matches
    
    def get_song(self, song_id: str) -> Optional[Song]:
        """SQLiteから楽曲情報を取得"""
        try:
            cursor = self.connection.cursor()
            cursor.execute("""
                SELECT id, title, artist, file_path, created_at, meta
                FROM songs
                WHERE id = ?
            """, (song_id,))
            
            row = cursor.fetchone()
            if row:
                meta = None
                if row[5]:
                    try:
                        meta = json.loads(row[5])
                    except Exception:
                        meta = None
                return Song(id=row[0], title=row[1], artist=row[2], file_path=row[3], created_at=row[4], meta=meta)
        except Exception as e:
            self.logger.error(f"SQLite song retrieval error: {e}")
        
        return None
    
    def list_songs(self) -> List[Song]:
        """SQLiteから全楽曲をリスト表示"""
        songs = []
        try:
            cursor = self.connection.cursor()
            cursor.execute("""
                SELECT id, title, artist, file_path, created_at, meta
                FROM songs
                ORDER BY title, artist
            """)
            
            for row in cursor.fetchall():
                meta = None
                if row[5]:
                    try:
                        meta = json.loads(row[5])
                    except Exception:
                        meta = None
                songs.append(Song(id=row[0], title=row[1], artist=row[2], file_path=row[3], created_at=row[4], meta=meta))
        except Exception as e:
            self.logger.error(f"SQLite song list retrieval error: {e}")
        
        return songs
    
    def get_database_stats(self) -> Dict[str, int]:
        """SQLiteデータベース統計を取得"""
        stats = {"songs": 0, "fingerprints": 0}
        
        try:
            cursor = self.connection.cursor()
            
            cursor.execute("SELECT COUNT(*) FROM songs")
            stats["songs"] = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM fingerprints")
            stats["fingerprints"] = cursor.fetchone()[0]
            
        except Exception as e:
            self.logger.error(f"SQLite statistics retrieval error: {e}")
        
        return stats
    
    def delete_song(self, song_id: str) -> bool:
        """SQLiteから楽曲を削除"""
        try:
            cursor = self.connection.cursor()
            
            # フィンガープリントを削除
            cursor.execute("DELETE FROM fingerprints WHERE song_id = ?", (song_id,))
            
            # 楽曲を削除
            cursor.execute("DELETE FROM songs WHERE id = ?", (song_id,))
            
            self.connection.commit()
            return True
        except Exception as e:
            self.logger.error(f"SQLite song deletion error: {e}")
            return False

    def get_fingerprints_by_song(self, song_id: str) -> List[Fingerprint]:
        """指定した楽曲のフィンガープリントを取得"""
        fingerprints = []
        
        try:
            cursor = self.connection.cursor()
            cursor.execute("""
                SELECT hash_value, time_offset FROM fingerprints 
                WHERE song_id = ?
            """, (song_id,))
            
            for hash_value, time_offset in cursor.fetchall():
                fp = Fingerprint(
                    hash_value=hash_value,
                    time_offset=float(time_offset),
                    song_id=song_id
                )
                fingerprints.append(fp)
        except Exception as e:
            self.logger.error(f"SQLite fingerprint retrieval error: {e}")
        
        return fingerprints
