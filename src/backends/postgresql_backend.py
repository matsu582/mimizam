"""PostgreSQLデータベースバックエンド実装"""

from typing import List, Optional, Dict, Tuple
from ..database_base import DatabaseBackend, DatabaseConfig, Song, Fingerprint
from ..exceptions import ConnectionError, QueryError, log_and_raise
import json

try:
    import psycopg2
    from psycopg2 import Error as PostgresError
except ImportError:
    psycopg2 = None
    PostgresError = Exception


class PostgreSQLBackend(DatabaseBackend):
    """PostgreSQLデータベースバックエンド"""
    
    def __init__(self, config: DatabaseConfig):
        super().__init__(config)
        self.connection = None
    
    def connect(self) -> bool:
        """PostgreSQLデータベースに接続"""
        try:
            if psycopg2 is None:
                raise ImportError("psycopg2 module is not available")
            
            # PostgreSQL接続最適化設定
            self.connection = psycopg2.connect(
                host=self.config.host,
                port=self.config.port or 5432,
                database=self.config.database,
                user=self.config.username,
                password=self.config.password,
                # 接続タイムアウト設定
                connect_timeout=30
            )
            self.connection.autocommit = True
            
            # PostgreSQL最適化パラメータ設定（セッションレベル）
            cursor = self.connection.cursor()
            try:
                # セッションレベルでの作業メモリ最適化
                cursor.execute("SET work_mem = '64MB'")
                cursor.execute("SET maintenance_work_mem = '128MB'")
                
                # クエリ最適化設定
                cursor.execute("SET random_page_cost = 1.1")  # SSD最適化
                cursor.execute("SET seq_page_cost = 1.0")
                cursor.execute("SET cpu_tuple_cost = 0.01")
                cursor.execute("SET cpu_index_tuple_cost = 0.005")
                
                # 並列処理設定（セッションレベル）
                cursor.execute("SET max_parallel_workers_per_gather = 2")
                cursor.execute("SET parallel_tuple_cost = 0.1")
                cursor.execute("SET parallel_setup_cost = 1000.0")
                
                # バッチクエリ最適化
                cursor.execute("SET enable_hashjoin = on")
                cursor.execute("SET enable_mergejoin = on")
                cursor.execute("SET enable_nestloop = on")
                
            except PostgresError as optimize_error:
                # 最適化設定でエラーが発生した場合は警告のみ出力
                self.logger.warning(f"PostgreSQL optimization setting error: {optimize_error}")
            
            cursor.close()
            
            self.logger.info(f"Connected to PostgreSQL database: {self.config.host}:{self.config.port}")
            return True
        except PostgresError as e:
            self.logger.error(f"PostgreSQL connection error: {e}")
            return False
    
    def disconnect(self) -> None:
        """PostgreSQLデータベースから切断"""
        if self.connection:
            self.connection.close()
            self.connection = None
    
    def create_tables(self) -> bool:
        """PostgreSQLテーブルを作成"""
        try:
            cursor = self.connection.cursor()
            
            # 楽曲テーブル
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS songs (
                    id VARCHAR(255) PRIMARY KEY,
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
                    id BIGSERIAL PRIMARY KEY,
                    song_id VARCHAR(255) NOT NULL,
                    hash_value VARCHAR(64) NOT NULL,
                    time_offset DOUBLE PRECISION NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (song_id) REFERENCES songs (id) ON DELETE CASCADE
                )
            """)
            
            # 基本インデックス作成
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_fingerprints_hash 
                ON fingerprints (hash_value)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_fingerprints_song_id 
                ON fingerprints (song_id)
            """)
            
            # 高性能複合インデックス追加
            try:
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_fingerprints_hash_song_time 
                    ON fingerprints (hash_value, song_id, time_offset)
                """)
            except PostgresError as e:
                if "already exists" not in str(e):
                    self.logger.warning(f"Composite index creation error: {e}")
            
            # ハッシュ値専用高速インデックス（PostgreSQL HASH インデックス）
            try:
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_fingerprints_hash_optimized 
                    ON fingerprints USING HASH (hash_value)
                """)
            except PostgresError as e:
                if "already exists" not in str(e):
                    self.logger.warning(f"Hash index creation error: {e}")
            
            # 統計情報更新 (クエリプランナー最適化)
            cursor.execute("ANALYZE fingerprints")
            cursor.execute("ANALYZE songs")
            
            return True
        except PostgresError as e:
            self.logger.error(f"PostgreSQL table creation error: {e}")
            return False
    
    def add_song(self, song: Song) -> bool:
        """PostgreSQLに楽曲を追加"""
        try:
            cursor = self.connection.cursor()
            meta_json = json.dumps(song.meta, ensure_ascii=False) if song.meta else None
            cursor.execute("""
                INSERT INTO songs (id, title, artist, file_path, meta)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                title = EXCLUDED.title,
                artist = EXCLUDED.artist,
                file_path = EXCLUDED.file_path,
                meta = EXCLUDED.meta
            """, (song.id, song.title, song.artist, song.file_path, meta_json))
            return True
        except PostgresError as e:
            self.logger.error(f"PostgreSQL song addition error: {e}")
            return False
    
    def add_fingerprints(self, song_id: str, fingerprints: List[Fingerprint]) -> bool:
        """PostgreSQLにフィンガープリントを追加"""
        try:
            cursor = self.connection.cursor()
            
            # 既存フィンガープリントを削除
            cursor.execute("DELETE FROM fingerprints WHERE song_id = %s", (song_id,))
            
            # numpy型をPython型に変換
            fingerprint_data = [
                (song_id, fp.hash_value, float(fp.time_offset)) 
                for fp in fingerprints
            ]
            
            cursor.executemany("""
                INSERT INTO fingerprints (song_id, hash_value, time_offset)
                VALUES (%s, %s, %s)
            """, fingerprint_data)
            
            return True
        except PostgresError as e:
            self.logger.error(f"PostgreSQL fingerprint addition error: {e}")
            return False
    
    def search_fingerprints(self, query_fingerprints: List[Fingerprint]) -> Dict[str, List[Tuple[float, float]]]:
        """PostgreSQLでフィンガープリントを検索"""
        matches = {}
        
        if not query_fingerprints:
            return matches
        
        try:
            cursor = self.connection.cursor()
            
            # バッチクエリ方式：ANY句を使用して1回のクエリで全てのマッチを取得
            hash_to_query_time = {fp.hash_value: fp.time_offset for fp in query_fingerprints}
            hash_values = list(hash_to_query_time.keys())
            
            # PostgreSQLのパラメータ制限を考慮してバッチ分割
            batch_size = 10000  # PostgreSQLは大きなIN句に対応
            for i in range(0, len(hash_values), batch_size):
                batch_hashes = hash_values[i:i + batch_size]
                
                # PostgreSQLのANY構文を使用
                cursor.execute("""
                    SELECT song_id, time_offset, hash_value
                    FROM fingerprints
                    WHERE hash_value = ANY(%s)
                """, (batch_hashes,))
                
                # 結果を処理
                for song_id, db_time_offset, hash_value in cursor.fetchall():
                    query_time = hash_to_query_time[hash_value]
                    if song_id not in matches:
                        matches[song_id] = []
                    matches[song_id].append((float(query_time), float(db_time_offset)))
                    
        except PostgresError as e:
            self.logger.error(f"PostgreSQL fingerprint search error: {e}")
        
        return matches
    
    def get_song(self, song_id: str) -> Optional[Song]:
        """PostgreSQLから楽曲情報を取得"""
        try:
            cursor = self.connection.cursor()
            cursor.execute("""
                SELECT id, title, artist, file_path, created_at, meta
                FROM songs
                WHERE id = %s
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
        except PostgresError as e:
            self.logger.error(f"PostgreSQL song retrieval error: {e}")
        
        return None
    
    def list_songs(self) -> List[Song]:
        """PostgreSQLから全楽曲をリスト表示"""
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
        except PostgresError as e:
            self.logger.error(f"PostgreSQL song list retrieval error: {e}")
        
        return songs
    
    def get_database_stats(self) -> Dict[str, int]:
        """PostgreSQLデータベース統計を取得"""
        stats = {"songs": 0, "fingerprints": 0}
        
        try:
            cursor = self.connection.cursor()
            
            cursor.execute("SELECT COUNT(*) FROM songs")
            stats["songs"] = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM fingerprints")
            stats["fingerprints"] = cursor.fetchone()[0]
            
        except PostgresError as e:
            self.logger.error(f"PostgreSQL statistics retrieval error: {e}")
        
        return stats
    
    def delete_song(self, song_id: str) -> bool:
        """PostgreSQLから楽曲を削除"""
        try:
            cursor = self.connection.cursor()
            
            # 外部キー制約により、楽曲を削除すれば自動的にフィンガープリントも削除される
            cursor.execute("DELETE FROM songs WHERE id = %s", (song_id,))
            
            return True
        except PostgresError as e:
            self.logger.error(f"PostgreSQL song deletion error: {e}")
            return False

    def get_fingerprints_by_song(self, song_id: str) -> List[Fingerprint]:
        """指定した楽曲のフィンガープリントを取得"""
        fingerprints = []
        
        try:
            cursor = self.connection.cursor()
            cursor.execute("""
                SELECT hash_value, time_offset FROM fingerprints 
                WHERE song_id = %s
            """, (song_id,))
            
            for hash_value, time_offset in cursor.fetchall():
                fp = Fingerprint(
                    hash_value=hash_value,
                    time_offset=float(time_offset),
                    song_id=song_id
                )
                fingerprints.append(fp)
        except PostgresError as e:
            self.logger.error(f"PostgreSQL fingerprint retrieval error: {e}")
        
        return fingerprints
