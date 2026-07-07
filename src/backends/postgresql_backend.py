"""PostgreSQLデータベースバックエンド実装"""

from typing import List, Optional, Dict, Tuple
from ..database_base import (
    DatabaseBackend, DatabaseConfig, Song, Video, Fingerprint,
    group_query_times as _group_query_times,
)
from ..exceptions import ConnectionError, QueryError, DatabaseError
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
        self._pgvector_available = False
    
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
            
            # pgvector拡張の有効化
            self._pgvector_available = False
            try:
                cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
                self._pgvector_available = True
                self.logger.info("Enabled pgvector extension")
            except PostgresError as e:
                self.logger.info(
                    f"pgvector not found (audio only; required for video fingerprints): {e}"
                )
            
            cursor.close()
            
            self.logger.info(f"Connected to PostgreSQL database: {self.config.host}:{self.config.port}")
            return True
        except PostgresError as e:
            self.logger.error(f"PostgreSQL connection error: {e} | Context: {{'host': self.config.host, 'port': self.config.port}}")
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
                    hash_value BIGINT NOT NULL,
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
            self.logger.error(f"PostgreSQL song addition error: {e} | Context: {{'song_id': song.id}}")
            raise DatabaseError(
                "Failed to add song", original_error=e,
                context={'song_id': song.id},
            ) from e
    
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
            self.logger.error(f"PostgreSQL fingerprint addition error: {e} | Context: {{'song_id': song_id, 'count': len(fingerprints)}}")
            raise DatabaseError(
                "Failed to add fingerprints", original_error=e,
                context={'song_id': song_id, 'count': len(fingerprints)},
            ) from e
    
    def search_fingerprints(self, query_fingerprints: List[Fingerprint]) -> Dict[str, List[Tuple[float, float]]]:
        """PostgreSQLでフィンガープリントを検索"""
        matches = {}
        
        if not query_fingerprints:
            return matches
        
        try:
            cursor = self.connection.cursor()
            
            # バッチクエリ方式：ANY句を使用して1回のクエリで全てのマッチを取得
            # 同一ハッシュの多重度を保持するため hash -> query_time群 で集約
            hash_to_query_times = _group_query_times(query_fingerprints)
            hash_values = list(hash_to_query_times.keys())
            
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
                
                # 結果を処理：DB返り行ごとに該当する全query_timeへ展開
                for song_id, db_time_offset, hash_value in cursor.fetchall():
                    db_time = float(db_time_offset)
                    bucket = matches.setdefault(song_id, [])
                    for query_time in hash_to_query_times[hash_value]:
                        bucket.append((float(query_time), db_time))
                    
        except PostgresError as e:
            self.logger.error(f"PostgreSQL fingerprint search error: {e}")
            raise DatabaseError(
                "Failed to search fingerprints", original_error=e,
            ) from e

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

    def get_songs(self, song_ids: List[str]) -> Dict[str, Optional[Song]]:
        """PostgreSQLから複数楽曲を ANY 句で一括取得する"""
        unique_ids = list(dict.fromkeys(song_ids))  # 重複排除・順序保持
        song_map: Dict[str, Optional[Song]] = {sid: None for sid in unique_ids}
        if not unique_ids:
            return song_map
        try:
            cursor = self.connection.cursor()
            cursor.execute("""
                SELECT id, title, artist, file_path, created_at, meta
                FROM songs
                WHERE id = ANY(%s)
            """, (unique_ids,))
            for row in cursor.fetchall():
                meta = None
                if row[5]:
                    try:
                        meta = json.loads(row[5])
                    except Exception:
                        meta = None
                song_map[row[0]] = Song(
                    id=row[0], title=row[1], artist=row[2],
                    file_path=row[3], created_at=row[4], meta=meta,
                )
        except PostgresError as e:
            self.logger.error(f"PostgreSQL batch song retrieval error: {e}")
        return song_map

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
            self.logger.error(f"PostgreSQL song deletion error: {e} | Context: {{'song_id': song_id}}")
            raise DatabaseError(
                "Failed to delete song", original_error=e,
                context={'song_id': song_id},
            ) from e

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

    # ===== 映像指紋メソッド =====

    def _ensure_pgvector_frame_column(self, dimensions: int) -> bool:
        """frame_fingerprintsテーブルにpgvector列とHNSW索引を追加

        L2正規化済みフレーム指紋をvector型で保持し、cosine距離のHNSW索引で
        近傍検索できるようにする（フレームANN投票の索引）。
        """
        if not self._pgvector_available:
            return False
        try:
            cursor = self.connection.cursor()
            cursor.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'frame_fingerprints' "
                "AND column_name = 'embedding'"
            )
            if cursor.fetchone() is None:
                cursor.execute(
                    f"ALTER TABLE frame_fingerprints "
                    f"ADD COLUMN embedding vector({dimensions})"
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS idx_frame_fp_embedding "
                    "ON frame_fingerprints "
                    "USING hnsw (embedding vector_cosine_ops)"
                )
            cursor.close()
            return True
        except Exception as e:
            self.logger.warning(f"pgvector frame column addition error: {e}")
            return False

    @staticmethod
    def _vec_literal(fp_blob: bytes) -> str:
        """float32バイト列をpgvectorのベクトルリテラルへ変換"""
        import numpy as np
        vec = np.frombuffer(fp_blob, dtype=np.float32)
        return '[' + ','.join(str(float(x)) for x in vec) + ']'

    def search_frame_candidates(
        self, query_fps: List[bytes], dimensions: int,
        k_per_query: int = 10, sim_threshold: float = 0.4,
    ) -> Dict[str, Dict[str, float]]:
        """クエリ各フレームのANN近傍を引き、映像別に得票/類似度を集計

        戻り値: {video_id: {"votes": 得票数, "score_sum": 類似度合計}}
        """
        agg: Dict[str, Dict[str, float]] = {}
        if not query_fps:
            return agg
        if not self._pgvector_available or not \
                self._ensure_pgvector_frame_column(dimensions):
            raise QueryError(
                "pgvector extension is required (pgvector is mandatory for video fingerprints)"
            )
        try:
            cursor = self.connection.cursor()
            # recall/速度のトレードオフ調整
            cursor.execute(
                "SET LOCAL hnsw.ef_search = %s",
                (max(k_per_query * 4, 40),),
            )
            for q_blob in query_fps:
                vec_str = self._vec_literal(q_blob)
                cursor.execute(
                    """SELECT video_id,
                              1.0 - (embedding <=> %s::vector) AS sim
                       FROM frame_fingerprints
                       WHERE embedding IS NOT NULL
                       ORDER BY embedding <=> %s::vector
                       LIMIT %s""",
                    (vec_str, vec_str, k_per_query),
                )
                for vid_id, sim in cursor.fetchall():
                    sim = float(sim)
                    if sim < sim_threshold:
                        continue
                    slot = agg.setdefault(
                        vid_id, {"votes": 0.0, "score_sum": 0.0}
                    )
                    slot["votes"] += 1.0
                    slot["score_sum"] += sim
            cursor.close()
            return agg
        except QueryError:
            raise
        except Exception as e:
            self.logger.error(f"pgvector frame search error: {e}")
            return agg

    def _create_video_tables(self) -> bool:
        """映像指紋テーブルを作成"""
        try:
            cursor = self.connection.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS videos (
                    id VARCHAR(255) PRIMARY KEY,
                    title TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    duration DOUBLE PRECISION,
                    frame_count INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS frame_fingerprints (
                    id BIGSERIAL PRIMARY KEY,
                    video_id VARCHAR(255) NOT NULL,
                    frame_index INTEGER NOT NULL,
                    timestamp DOUBLE PRECISION NOT NULL,
                    fingerprint BYTEA NOT NULL,
                    FOREIGN KEY (video_id) REFERENCES videos (id)
                        ON DELETE CASCADE
                )
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_frame_fp_video
                ON frame_fingerprints (video_id)
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS frame_descriptors (
                    id BIGSERIAL PRIMARY KEY,
                    video_id VARCHAR(255) NOT NULL,
                    frame_index INTEGER NOT NULL,
                    timestamp DOUBLE PRECISION NOT NULL,
                    descriptors BYTEA NOT NULL,
                    descriptor_count INTEGER NOT NULL,
                    FOREIGN KEY (video_id) REFERENCES videos (id)
                        ON DELETE CASCADE
                )
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_frame_desc_video
                ON frame_descriptors (video_id)
            """)

            return True
        except PostgresError as e:
            self.logger.error(f"PostgreSQL video table creation error: {e}")
            return False

    def add_video(self, video: Video) -> bool:
        """PostgreSQLに映像メタデータを追加"""
        try:
            self._create_video_tables()
            cursor = self.connection.cursor()
            cursor.execute(
                """INSERT INTO videos
                    (id, title, file_path, duration, frame_count)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    title = EXCLUDED.title,
                    file_path = EXCLUDED.file_path,
                    duration = EXCLUDED.duration,
                    frame_count = EXCLUDED.frame_count""",
                (video.id, video.title, video.file_path,
                 video.duration, video.frame_count),
            )
            return True
        except PostgresError as e:
            self.logger.error(f"PostgreSQL video addition error: {e}")
            raise DatabaseError(
                "Failed to add video", original_error=e,
                context={'video_id': video.id},
            ) from e

    def add_frame_fingerprints(
        self, video_id: str,
        frames: List[Tuple[int, float, bytes]],
    ) -> bool:
        """PostgreSQLにフレーム単位指紋を一括保存"""
        try:
            self._create_video_tables()
            cursor = self.connection.cursor()
            cursor.execute(
                "DELETE FROM frame_fingerprints WHERE video_id = %s",
                (video_id,),
            )
            if not frames:
                return True
            dims = len(frames[0][2]) // 4  # float32バイト列 → 次元数
            if not self._pgvector_available or not \
                    self._ensure_pgvector_frame_column(dims):
                raise QueryError(
                    "pgvector extension is required (pgvector is mandatory for video fingerprints)"
                )
            rows = [
                (video_id, fidx, float(ts), fp_blob,
                 self._vec_literal(fp_blob))
                for fidx, ts, fp_blob in frames
            ]
            cursor.executemany(
                """INSERT INTO frame_fingerprints
                    (video_id, frame_index, timestamp,
                     fingerprint, embedding)
                VALUES (%s, %s, %s, %s, %s::vector)""",
                rows,
            )
            return True
        except PostgresError as e:
            self.logger.error(f"PostgreSQL frame fingerprint save error: {e}")
            raise DatabaseError(
                "Failed to add frame fingerprints", original_error=e,
                context={'video_id': video_id, 'count': len(frames)},
            ) from e

    def get_frame_fingerprints(
        self, video_id: str,
    ) -> List[Tuple[int, float, bytes]]:
        """PostgreSQLから指定映像のフレーム指紋を取得"""
        try:
            self._create_video_tables()
            cursor = self.connection.cursor()
            cursor.execute(
                """SELECT frame_index, timestamp, fingerprint
                   FROM frame_fingerprints WHERE video_id = %s""",
                (video_id,),
            )
            return [
                (int(fidx), float(ts), bytes(fp_blob))
                for fidx, ts, fp_blob in cursor.fetchall()
            ]
        except PostgresError as e:
            self.logger.error(f"PostgreSQL frame fingerprint retrieval error: {e}")
            raise DatabaseError(
                "Failed to get frame fingerprints", original_error=e,
                context={'video_id': video_id},
            ) from e

    def get_frame_fingerprints_batch(
        self, video_ids: List[str],
    ) -> Dict[str, List[Tuple[int, float, bytes]]]:
        """PostgreSQLから複数映像のフレーム指紋を1クエリで一括取得"""
        result: Dict[str, List[Tuple[int, float, bytes]]] = {
            vid: [] for vid in video_ids
        }
        if not video_ids:
            return result
        try:
            self._create_video_tables()
            cursor = self.connection.cursor()
            cursor.execute(
                """SELECT video_id, frame_index, timestamp, fingerprint
                   FROM frame_fingerprints
                   WHERE video_id = ANY(%s)""",
                (list(video_ids),),
            )
            for vid, fidx, ts, fp_blob in cursor.fetchall():
                result[vid].append(
                    (int(fidx), float(ts), bytes(fp_blob))
                )
        except PostgresError as e:
            self.logger.error(
                f"PostgreSQL frame fingerprint batch retrieval error: {e}"
            )
            raise DatabaseError(
                "Failed to get frame fingerprints batch", original_error=e,
            ) from e
        return result

    def get_video(self, video_id: str) -> Optional[Video]:
        """PostgreSQLから映像情報を取得"""
        try:
            self._create_video_tables()
            cursor = self.connection.cursor()
            cursor.execute(
                """SELECT id, title, file_path, duration, frame_count,
                          created_at
                   FROM videos WHERE id = %s""",
                (video_id,),
            )
            row = cursor.fetchone()
            if row:
                return Video(
                    id=row[0], title=row[1], file_path=row[2],
                    duration=row[3], frame_count=row[4],
                    created_at=str(row[5]) if row[5] else None,
                )
        except PostgresError as e:
            self.logger.error(f"PostgreSQL video retrieval error: {e}")
        return None

    def get_videos(
        self, video_ids: List[str]
    ) -> Dict[str, Optional[Video]]:
        """PostgreSQLから複数映像のメタデータを1クエリで一括取得（N+1回避）"""
        result: Dict[str, Optional[Video]] = {vid: None for vid in video_ids}
        if not video_ids:
            return result
        try:
            self._create_video_tables()
            cursor = self.connection.cursor()
            cursor.execute(
                """SELECT id, title, file_path, duration, frame_count,
                          created_at
                   FROM videos WHERE id = ANY(%s)""",
                (list(video_ids),),
            )
            for r in cursor.fetchall():
                result[r[0]] = Video(
                    id=r[0], title=r[1], file_path=r[2],
                    duration=r[3], frame_count=r[4],
                    created_at=str(r[5]) if r[5] else None,
                )
        except PostgresError as e:
            self.logger.error(f"PostgreSQL video batch retrieval error: {e}")
        return result

    def list_videos(self) -> List[Video]:
        """PostgreSQLから全映像をリスト取得"""
        try:
            self._create_video_tables()
            cursor = self.connection.cursor()
            cursor.execute(
                """SELECT id, title, file_path, duration, frame_count,
                          created_at
                   FROM videos ORDER BY title"""
            )
            return [
                Video(
                    id=r[0], title=r[1], file_path=r[2],
                    duration=r[3], frame_count=r[4],
                    created_at=str(r[5]) if r[5] else None,
                )
                for r in cursor.fetchall()
            ]
        except PostgresError as e:
            self.logger.error(f"PostgreSQL video list retrieval error: {e}")
            return []

    def delete_video(self, video_id: str) -> bool:
        """PostgreSQLから映像と関連指紋を削除"""
        try:
            self._create_video_tables()
            cursor = self.connection.cursor()
            cursor.execute(
                "DELETE FROM videos WHERE id = %s", (video_id,)
            )
            return True
        except PostgresError as e:
            self.logger.error(f"PostgreSQL video deletion error: {e}")
            raise DatabaseError(
                "Failed to delete video", original_error=e,
                context={'video_id': video_id},
            ) from e

    def add_frame_descriptors(
        self, video_id: str,
        frames: List[Tuple[int, float, bytes, int]],
    ) -> bool:
        """PostgreSQLにフレーム単位AKAZE記述子を一括保存（幾何検証・再生成用）"""
        try:
            self._create_video_tables()
            cursor = self.connection.cursor()
            cursor.execute(
                "DELETE FROM frame_descriptors WHERE video_id = %s",
                (video_id,),
            )
            rows = [
                (video_id, int(fidx), float(ts),
                 psycopg2.Binary(desc_blob), int(desc_count))
                for fidx, ts, desc_blob, desc_count in frames
            ]
            if rows:
                cursor.executemany(
                    """INSERT INTO frame_descriptors
                        (video_id, frame_index, timestamp,
                         descriptors, descriptor_count)
                    VALUES (%s, %s, %s, %s, %s)""",
                    rows,
                )
            return True
        except PostgresError as e:
            self.logger.error(f"PostgreSQL frame descriptor save error: {e}")
            raise DatabaseError(
                "Failed to add frame descriptors", original_error=e,
                context={'video_id': video_id, 'count': len(frames)},
            ) from e

    def get_frame_descriptors(
        self, video_id: str,
        frame_indices: Optional[List[int]] = None,
    ) -> List[Tuple[int, float, bytes, int]]:
        """PostgreSQLから指定映像のフレーム記述子を取得

        frame_indices を渡すと、そのフレームインデックスの記述子だけを取得する。
        幾何検証はANN上位候補のDBフレームしか突き合わせないため、必要なフレームに
        限定して読み込むことで生記述子の無駄なI/Oを避ける。None なら全件取得。
        """
        try:
            self._create_video_tables()
            cursor = self.connection.cursor()
            if frame_indices is not None:
                if not frame_indices:
                    return []
                cursor.execute(
                    """SELECT frame_index, timestamp,
                              descriptors, descriptor_count
                       FROM frame_descriptors
                       WHERE video_id = %s AND frame_index = ANY(%s)
                       ORDER BY frame_index""",
                    (video_id, [int(f) for f in frame_indices]),
                )
            else:
                cursor.execute(
                    """SELECT frame_index, timestamp,
                              descriptors, descriptor_count
                       FROM frame_descriptors WHERE video_id = %s
                       ORDER BY frame_index""",
                    (video_id,),
                )
            return [
                (int(fidx), float(ts), bytes(desc), int(cnt))
                for fidx, ts, desc, cnt in cursor.fetchall()
            ]
        except PostgresError as e:
            self.logger.error(
                f"PostgreSQL frame descriptor retrieval error: {e}"
            )
            raise DatabaseError(
                "Failed to get frame descriptors", original_error=e,
                context={'video_id': video_id},
            ) from e

    def get_all_frame_descriptors(
        self,
    ) -> Dict[str, List[Tuple[int, float, bytes, int]]]:
        """PostgreSQLから全映像のフレーム記述子を取得"""
        result: Dict[str, List[Tuple[int, float, bytes, int]]] = {}
        try:
            self._create_video_tables()
            cursor = self.connection.cursor()
            cursor.execute(
                """SELECT video_id, frame_index, timestamp,
                          descriptors, descriptor_count
                   FROM frame_descriptors
                   ORDER BY video_id, frame_index"""
            )
            for vid, fidx, ts, desc, cnt in cursor.fetchall():
                result.setdefault(vid, []).append(
                    (int(fidx), float(ts), bytes(desc), int(cnt))
                )
        except PostgresError as e:
            self.logger.error(
                f"PostgreSQL all frame descriptor retrieval error: {e}"
            )
            raise DatabaseError(
                "Failed to get all frame descriptors", original_error=e,
            ) from e
        return result

    def get_video_stats(self) -> Dict[str, int]:
        """PostgreSQLの映像指紋統計を取得"""
        stats = {"videos": 0, "frame_fingerprints": 0}
        try:
            self._create_video_tables()
            cursor = self.connection.cursor()
            cursor.execute("SELECT COUNT(*) FROM videos")
            stats["videos"] = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM frame_fingerprints")
            stats["frame_fingerprints"] = cursor.fetchone()[0]
        except PostgresError as e:
            self.logger.error(f"PostgreSQL video statistics error: {e}")
        return stats
