"""MySQLデータベースバックエンド実装"""

from typing import List, Optional, Dict, Tuple
from ..database_base import (
    DatabaseBackend, DatabaseConfig, Song, Video, Fingerprint,
    group_query_times as _group_query_times,
)
from ..exceptions import ConnectionError, QueryError, DatabaseError
import json

try:
    import mysql.connector
    from mysql.connector import Error as MySQLError
except ImportError:
    mysql = None
    MySQLError = Exception


class MySQLBackend(DatabaseBackend):
    """MySQLデータベースバックエンド"""
    
    def __init__(self, config: DatabaseConfig):
        super().__init__(config)
        self.connection = None
    
    def connect(self) -> bool:
        """MySQLデータベースに接続"""
        try:
            if mysql is None:
                raise ImportError("mysql-connector-python module is not available")
            
            self.connection = mysql.connector.connect(
                host=self.config.host,
                port=self.config.port or 3306,
                database=self.config.database,
                user=self.config.username,
                password=self.config.password,
                pool_size=self.config.pool_size or 10,
                autocommit=True,
                # MySQL最適化設定
                use_unicode=True,
                charset='utf8mb4',
                collation='utf8mb4_unicode_ci',
                connection_timeout=30,
                buffered=True,  # バッファード検索で高速化
                raise_on_warnings=False
            )
            
            # MySQL最適化パラメータ設定（MySQL 8.0対応）
            cursor = self.connection.cursor()
            try:
                # 基本的なセッション最適化設定
                cursor.execute("SET SESSION tmp_table_size = 67108864")  # 64MB
                cursor.execute("SET SESSION max_heap_table_size = 67108864")  # 64MB
                cursor.execute("SET SESSION join_buffer_size = 2097152")  # 2MB
                cursor.execute("SET SESSION read_buffer_size = 1048576")  # 1MB
                cursor.execute("SET SESSION sort_buffer_size = 2097152")  # 2MB
                
                # MySQL 8.0対応オプティマイザー設定
                cursor.execute("SET SESSION optimizer_switch = 'index_merge=on,index_merge_union=on,index_merge_sort_union=on,index_merge_intersection=on'")
                
                # 並列処理設定（MySQL 8.0以降）
                cursor.execute("SET SESSION innodb_parallel_read_threads = 4")
                
            except MySQLError as optimize_error:
                # 最適化設定でエラーが発生した場合は警告のみ出力
                self.logger.warning(f"MySQL optimization setting error: {optimize_error}")
            
            cursor.close()
            
            self.logger.info(f"Connected to MySQL database: {self.config.host}:{self.config.port}")
            return True
        except MySQLError as e:
            self.logger.error(f"MySQL connection error: {e} | Context: {{'host': self.config.host, 'port': self.config.port}}")
            return False
    
    def disconnect(self) -> None:
        """MySQLデータベースから切断"""
        if self.connection and self.connection.is_connected():
            self.connection.close()
            self.connection = None
    
    def create_tables(self) -> bool:
        """MySQLテーブルを作成"""
        try:
            cursor = self.connection.cursor()
            
            # 楽曲テーブル
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS songs (
                    id VARCHAR(255) PRIMARY KEY,
                    title VARCHAR(500) NOT NULL,
                    artist VARCHAR(500) NOT NULL,
                    file_path TEXT NOT NULL,
                    meta TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                ) ENGINE=InnoDB CHARACTER SET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
            
            # フィンガープリントテーブル
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS fingerprints (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    song_id VARCHAR(255) NOT NULL,
                    hash_value BIGINT NOT NULL,
                    time_offset DOUBLE NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_fingerprints_hash (hash_value),
                    INDEX idx_fingerprints_song_id (song_id),
                    FOREIGN KEY (song_id) REFERENCES songs (id) ON DELETE CASCADE
                ) ENGINE=InnoDB CHARACTER SET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
            
            # 高性能複合インデックス追加
            try:
                cursor.execute("""
                    CREATE INDEX idx_fingerprints_hash_song_time 
                    ON fingerprints (hash_value, song_id, time_offset)
                """)
            except MySQLError as e:
                if "Duplicate key name" not in str(e):
                    self.logger.warning(f"Composite index creation error: {e}")
            
            # ハッシュ値専用高速インデックス
            try:
                cursor.execute("""
                    CREATE INDEX idx_fingerprints_hash_optimized 
                    ON fingerprints (hash_value) 
                    USING HASH
                """)
            except MySQLError as e:
                if "Duplicate key name" not in str(e):
                    self.logger.warning(f"Hash index creation error: {e}")
            
            # 統計情報更新（クエリオプティマイザー最適化）
            cursor.execute("ANALYZE TABLE fingerprints")
            cursor.execute("ANALYZE TABLE songs")
            
            return True
        except MySQLError as e:
            self.logger.error(f"MySQL table creation error: {e}")
            return False
    
    def add_song(self, song: Song) -> bool:
        """MySQLに楽曲を追加"""
        try:
            cursor = self.connection.cursor()
            meta_json = json.dumps(song.meta, ensure_ascii=False) if song.meta else None
            cursor.execute("""
                INSERT INTO songs (id, title, artist, file_path, meta)
                VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                title = VALUES(title),
                artist = VALUES(artist),
                file_path = VALUES(file_path),
                meta = VALUES(meta)
            """, (song.id, song.title, song.artist, song.file_path, meta_json))
            return True
        except MySQLError as e:
            self.logger.error(f"MySQL song addition error: {e} | Context: {{'song_id': song.id}}")
            raise DatabaseError(
                "Failed to add song", original_error=e,
                context={'song_id': song.id},
            ) from e
    
    def add_fingerprints(self, song_id: str, fingerprints: List[Fingerprint]) -> bool:
        """MySQLにフィンガープリントを追加"""
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
        except MySQLError as e:
            self.logger.error(f"MySQL fingerprint addition error: {e} | Context: {{'song_id': song_id, 'count': len(fingerprints)}}")
            raise DatabaseError(
                "Failed to add fingerprints", original_error=e,
                context={'song_id': song_id, 'count': len(fingerprints)},
            ) from e
    
    def search_fingerprints(self, query_fingerprints: List[Fingerprint]) -> Dict[str, List[Tuple[float, float]]]:
        """MySQLでフィンガープリントを検索"""
        matches = {}
        
        if not query_fingerprints:
            return matches
        
        try:
            cursor = self.connection.cursor(buffered=True)
            
            # バッチクエリ方式：IN句を使用して1回のクエリで全てのマッチを取得
            # 同一ハッシュの多重度を保持するため hash -> query_time群 で集約
            hash_to_query_times = _group_query_times(query_fingerprints)
            hash_values = list(hash_to_query_times.keys())
            
            # MySQLのプレースホルダー制限（65,535個）を考慮してバッチ分割
            batch_size = 10000  # 安全マージン
            for i in range(0, len(hash_values), batch_size):
                batch_hashes = hash_values[i:i + batch_size]
                placeholders = ','.join(['%s'] * len(batch_hashes))
                
                cursor.execute(f"""
                    SELECT song_id, time_offset, hash_value
                    FROM fingerprints
                    WHERE hash_value IN ({placeholders})
                """, batch_hashes)
                
                # 結果を処理：DB返り行ごとに該当する全query_timeへ展開
                for song_id, db_time_offset, hash_value in cursor.fetchall():
                    db_time = float(db_time_offset)
                    bucket = matches.setdefault(song_id, [])
                    for query_time in hash_to_query_times[hash_value]:
                        bucket.append((float(query_time), db_time))
                    
        except MySQLError as e:
            self.logger.error(f"MySQL fingerprint search error: {e}")
            raise DatabaseError(
                "Failed to search fingerprints", original_error=e,
            ) from e

        return matches

    def get_song(self, song_id: str) -> Optional[Song]:
        """MySQLから楽曲情報を取得"""
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
        except MySQLError as e:
            self.logger.error(f"MySQL song retrieval error: {e}")
        
        return None

    def get_songs(self, song_ids: List[str]) -> Dict[str, Optional[Song]]:
        """MySQLから複数楽曲を IN 句で一括取得する"""
        unique_ids = list(dict.fromkeys(song_ids))  # 重複排除・順序保持
        song_map: Dict[str, Optional[Song]] = {sid: None for sid in unique_ids}
        if not unique_ids:
            return song_map
        try:
            cursor = self.connection.cursor()
            batch_size = 10000  # 安全マージン
            for i in range(0, len(unique_ids), batch_size):
                batch = unique_ids[i:i + batch_size]
                placeholders = ','.join(['%s'] * len(batch))
                cursor.execute(f"""
                    SELECT id, title, artist, file_path, created_at, meta
                    FROM songs
                    WHERE id IN ({placeholders})
                """, batch)
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
        except MySQLError as e:
            self.logger.error(f"MySQL batch song retrieval error: {e}")
        return song_map

    def list_songs(self) -> List[Song]:
        """MySQLから全楽曲をリスト表示"""
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
        except MySQLError as e:
            self.logger.error(f"MySQL song list retrieval error: {e}")
        
        return songs
    
    def get_database_stats(self) -> Dict[str, int]:
        """MySQLデータベース統計を取得"""
        stats = {"songs": 0, "fingerprints": 0}
        
        try:
            cursor = self.connection.cursor()
            
            cursor.execute("SELECT COUNT(*) FROM songs")
            stats["songs"] = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM fingerprints")
            stats["fingerprints"] = cursor.fetchone()[0]
            
        except MySQLError as e:
            self.logger.error(f"MySQL statistics retrieval error: {e}")
        
        return stats
    
    def delete_song(self, song_id: str) -> bool:
        """MySQLから楽曲を削除"""
        try:
            cursor = self.connection.cursor()
            
            # 外部キー制約により、楽曲を削除すれば自動的にフィンガープリントも削除される
            cursor.execute("DELETE FROM songs WHERE id = %s", (song_id,))
            
            return True
        except MySQLError as e:
            self.logger.error(f"MySQL song deletion error: {e} | Context: {{'song_id': song_id}}")
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
        except MySQLError as e:
            self.logger.error(f"MySQL fingerprint retrieval error: {e}")
        
        return fingerprints

    # ===== 映像指紋メソッド =====

    def _create_video_tables(self) -> bool:
        """映像指紋テーブルを作成"""
        try:
            cursor = self.connection.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS videos (
                    id VARCHAR(255) PRIMARY KEY,
                    title VARCHAR(500) NOT NULL,
                    file_path TEXT NOT NULL,
                    duration DOUBLE,
                    frame_count INT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                ) ENGINE=InnoDB CHARACTER SET=utf8mb4
                  COLLATE=utf8mb4_unicode_ci
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS frame_fingerprints (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    video_id VARCHAR(255) NOT NULL,
                    frame_index INT NOT NULL,
                    timestamp DOUBLE NOT NULL,
                    fingerprint MEDIUMBLOB NOT NULL,
                    INDEX idx_frame_fp_video (video_id),
                    FOREIGN KEY (video_id) REFERENCES videos (id)
                        ON DELETE CASCADE
                ) ENGINE=InnoDB CHARACTER SET=utf8mb4
                  COLLATE=utf8mb4_unicode_ci
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS frame_descriptors (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    video_id VARCHAR(255) NOT NULL,
                    frame_index INT NOT NULL,
                    timestamp DOUBLE NOT NULL,
                    descriptors MEDIUMBLOB NOT NULL,
                    descriptor_count INT NOT NULL,
                    INDEX idx_frame_desc_video (video_id),
                    FOREIGN KEY (video_id) REFERENCES videos (id)
                        ON DELETE CASCADE
                ) ENGINE=InnoDB CHARACTER SET=utf8mb4
                  COLLATE=utf8mb4_unicode_ci
            """)

            return True
        except MySQLError as e:
            self.logger.error(f"MySQL video table creation error: {e}")
            return False

    def add_video(self, video: Video) -> bool:
        """MySQLに映像メタデータを追加"""
        try:
            self._create_video_tables()
            cursor = self.connection.cursor()
            cursor.execute(
                """INSERT INTO videos
                    (id, title, file_path, duration, frame_count)
                VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    title = VALUES(title),
                    file_path = VALUES(file_path),
                    duration = VALUES(duration),
                    frame_count = VALUES(frame_count)""",
                (video.id, video.title, video.file_path,
                 video.duration, video.frame_count),
            )
            return True
        except MySQLError as e:
            self.logger.error(f"MySQL video addition error: {e}")
            raise DatabaseError(
                "Failed to add video", original_error=e,
                context={'video_id': video.id},
            ) from e

    def add_frame_fingerprints(
        self, video_id: str,
        frames: List[Tuple[int, float, bytes]],
    ) -> bool:
        """MySQLにフレーム単位指紋を一括保存"""
        try:
            self._create_video_tables()
            cursor = self.connection.cursor()
            cursor.execute(
                "DELETE FROM frame_fingerprints WHERE video_id = %s",
                (video_id,),
            )
            rows = [
                (video_id, fidx, float(ts), fp_blob)
                for fidx, ts, fp_blob in frames
            ]
            cursor.executemany(
                """INSERT INTO frame_fingerprints
                    (video_id, frame_index, timestamp, fingerprint)
                VALUES (%s, %s, %s, %s)""",
                rows,
            )
            return True
        except MySQLError as e:
            self.logger.error(f"MySQL frame fingerprint save error: {e}")
            raise DatabaseError(
                "Failed to add frame fingerprints", original_error=e,
                context={'video_id': video_id, 'count': len(frames)},
            ) from e

    def search_frame_candidates(
        self, query_fps: List[bytes], dimensions: int,
        k_per_query: int = 10, sim_threshold: float = 0.4,
    ) -> Dict[str, Dict[str, float]]:
        """クエリ各フレームの近傍を引き、映像別に得票/類似度を集計

        MySQLコミュニティ版にはcosineのANN近似索引が無いため、全フレームを
        読み出して総当り（brute-force）で近傍を求める。結果の形式はANN実装
        （pgvector/ES/sqlite-vec）と同一で、大規模では低速になる点に留意。

        戻り値: {video_id: {"votes": 得票数, "score_sum": 類似度合計}}
        """
        import numpy as np
        agg: Dict[str, Dict[str, float]] = {}
        if not query_fps:
            return agg
        try:
            self._create_video_tables()
            cursor = self.connection.cursor()
            cursor.execute(
                "SELECT video_id, fingerprint FROM frame_fingerprints"
            )
            rows = cursor.fetchall()
            if not rows:
                return agg
            db_vids = [r[0] for r in rows]
            d_mat = np.stack([
                np.frombuffer(bytes(r[1]), dtype=np.float32) for r in rows
            ])
            q_mat = np.stack([
                np.frombuffer(q, dtype=np.float32) for q in query_fps
            ])
            with np.errstate(all="ignore"):
                sims = q_mat @ d_mat.T
            np.nan_to_num(sims, copy=False, nan=0.0, posinf=0.0, neginf=0.0)
            k = min(k_per_query, sims.shape[1])
            for i in range(sims.shape[0]):
                top_idx = np.argpartition(sims[i], -k)[-k:]
                for j in top_idx:
                    sim = float(sims[i, j])
                    if sim < sim_threshold:
                        continue
                    slot = agg.setdefault(
                        db_vids[j], {"votes": 0.0, "score_sum": 0.0}
                    )
                    slot["votes"] += 1.0
                    slot["score_sum"] += sim
        except MySQLError as e:
            self.logger.error(f"MySQL frame candidate brute-force error: {e}")
        return agg

    def get_frame_fingerprints(
        self, video_id: str,
    ) -> List[Tuple[int, float, bytes]]:
        """MySQLから指定映像のフレーム指紋を取得"""
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
        except MySQLError as e:
            self.logger.error(f"MySQL frame fingerprint retrieval error: {e}")
            raise DatabaseError(
                "Failed to get frame fingerprints", original_error=e,
                context={'video_id': video_id},
            ) from e

    def get_frame_fingerprints_batch(
        self, video_ids: List[str],
    ) -> Dict[str, List[Tuple[int, float, bytes]]]:
        """MySQLから複数映像のフレーム指紋を1クエリで一括取得"""
        result: Dict[str, List[Tuple[int, float, bytes]]] = {
            vid: [] for vid in video_ids
        }
        if not video_ids:
            return result
        try:
            self._create_video_tables()
            cursor = self.connection.cursor()
            placeholders = ",".join("%s" for _ in video_ids)
            cursor.execute(
                f"""SELECT video_id, frame_index, timestamp, fingerprint
                    FROM frame_fingerprints
                    WHERE video_id IN ({placeholders})""",
                tuple(video_ids),
            )
            for vid, fidx, ts, fp_blob in cursor.fetchall():
                result[vid].append(
                    (int(fidx), float(ts), bytes(fp_blob))
                )
        except MySQLError as e:
            self.logger.error(
                f"MySQL frame fingerprint batch retrieval error: {e}"
            )
            raise DatabaseError(
                "Failed to get frame fingerprints batch", original_error=e,
            ) from e
        return result

    def get_video(self, video_id: str) -> Optional[Video]:
        """MySQLから映像情報を取得"""
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
        except MySQLError as e:
            self.logger.error(f"MySQL video retrieval error: {e}")
        return None

    def get_videos(
        self, video_ids: List[str]
    ) -> Dict[str, Optional[Video]]:
        """MySQLから複数映像のメタデータを1クエリで一括取得（N+1回避）"""
        result: Dict[str, Optional[Video]] = {vid: None for vid in video_ids}
        if not video_ids:
            return result
        try:
            self._create_video_tables()
            cursor = self.connection.cursor()
            placeholders = ",".join("%s" for _ in video_ids)
            cursor.execute(
                f"""SELECT id, title, file_path, duration, frame_count,
                          created_at
                   FROM videos WHERE id IN ({placeholders})""",
                tuple(video_ids),
            )
            for r in cursor.fetchall():
                result[r[0]] = Video(
                    id=r[0], title=r[1], file_path=r[2],
                    duration=r[3], frame_count=r[4],
                    created_at=str(r[5]) if r[5] else None,
                )
        except MySQLError as e:
            self.logger.error(f"MySQL video batch retrieval error: {e}")
        return result

    def list_videos(self) -> List[Video]:
        """MySQLから全映像をリスト取得"""
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
        except MySQLError as e:
            self.logger.error(f"MySQL video list retrieval error: {e}")
            return []

    def delete_video(self, video_id: str) -> bool:
        """MySQLから映像と関連指紋を削除"""
        try:
            self._create_video_tables()
            cursor = self.connection.cursor()
            cursor.execute(
                "DELETE FROM videos WHERE id = %s", (video_id,)
            )
            return True
        except MySQLError as e:
            self.logger.error(f"MySQL video deletion error: {e}")
            raise DatabaseError(
                "Failed to delete video", original_error=e,
                context={'video_id': video_id},
            ) from e

    def add_frame_descriptors(
        self, video_id: str,
        frames: List[Tuple[int, float, bytes, int]],
    ) -> bool:
        """MySQLにフレーム単位AKAZE記述子を一括保存（幾何検証・再生成用）"""
        try:
            self._create_video_tables()
            cursor = self.connection.cursor()
            cursor.execute(
                "DELETE FROM frame_descriptors WHERE video_id = %s",
                (video_id,),
            )
            rows = [
                (video_id, int(fidx), float(ts), desc_blob, int(desc_count))
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
        except MySQLError as e:
            self.logger.error(f"MySQL frame descriptor save error: {e}")
            raise DatabaseError(
                "Failed to add frame descriptors", original_error=e,
                context={'video_id': video_id, 'count': len(frames)},
            ) from e

    def get_frame_descriptors(
        self, video_id: str,
        frame_indices: Optional[List[int]] = None,
    ) -> List[Tuple[int, float, bytes, int]]:
        """MySQLから指定映像のフレーム記述子を取得

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
                placeholders = ",".join("%s" for _ in frame_indices)
                cursor.execute(
                    f"""SELECT frame_index, timestamp,
                              descriptors, descriptor_count
                       FROM frame_descriptors
                       WHERE video_id = %s
                         AND frame_index IN ({placeholders})
                       ORDER BY frame_index""",
                    (video_id, *[int(f) for f in frame_indices]),
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
        except MySQLError as e:
            self.logger.error(f"MySQL frame descriptor retrieval error: {e}")
            raise DatabaseError(
                "Failed to get frame descriptors", original_error=e,
                context={'video_id': video_id},
            ) from e

    def get_all_frame_descriptors(
        self,
    ) -> Dict[str, List[Tuple[int, float, bytes, int]]]:
        """MySQLから全映像のフレーム記述子を取得"""
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
        except MySQLError as e:
            self.logger.error(
                f"MySQL all frame descriptor retrieval error: {e}"
            )
            raise DatabaseError(
                "Failed to get all frame descriptors", original_error=e,
            ) from e
        return result

    def get_video_stats(self) -> Dict[str, int]:
        """MySQLの映像指紋統計を取得"""
        stats = {"videos": 0, "frame_fingerprints": 0}
        try:
            self._create_video_tables()
            cursor = self.connection.cursor()
            cursor.execute("SELECT COUNT(*) FROM videos")
            stats["videos"] = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM frame_fingerprints")
            stats["frame_fingerprints"] = cursor.fetchone()[0]
        except MySQLError as e:
            self.logger.error(f"MySQL video statistics retrieval error: {e}")
        return stats
