"""SQLiteデータベースバックエンド実装"""

from typing import List, Optional, Dict, Any, Tuple
from ..database_base import DatabaseBackend, DatabaseConfig, Song, Video, Fingerprint
from ..exceptions import ConnectionError, QueryError
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
        self._vec_dim = None
        self._vec_frame_dim = None
    
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
            
            # sqlite-vec拡張の読み込み（ANNに必須）
            self._vec_dim = None
            self._vec_frame_dim = None
            import sqlite_vec
            self.connection.enable_load_extension(True)
            sqlite_vec.load(self.connection)
            self.connection.enable_load_extension(False)
            self.logger.info("sqlite-vec拡張を読み込みました")
            
            self.logger.info(f"Connected to SQLite database with optimization settings: {self.db_path}")
            return True
        except Exception as e:
            self.logger.error(f"SQLite connection error: {e} | Context: {{'db_path': self.db_path}}")
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
            self.logger.error(f"SQLite song addition error: {e} | Context: {{'song_id': '{song.id}'}}")
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
            self.logger.error(f"SQLite fingerprint addition error: {e} | Context: {{'song_id': '{song_id}', 'count': {len(fingerprints)}}}")
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
            self.logger.error(f"SQLite song deletion error: {e} | Context: {{'song_id': '{song_id}'}}")
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

    # ===== 映像指紋メソッド =====

    def _ensure_vec_frame_table(self, dimensions: int) -> bool:
        """フレーム指紋用vec0テーブルを確認・作成（sqlite-vec）

        video_id / timestamp をメタデータ列として保持し、
        KNN結果から所属映像と時刻を直接引けるようにする。
        """
        if self._vec_frame_dim == dimensions:
            return True
        try:
            cursor = self.connection.cursor()
            cursor.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name='vec_frame_fingerprints'"
            )
            if cursor.fetchone() is None:
                cursor.execute(
                    f"CREATE VIRTUAL TABLE vec_frame_fingerprints USING vec0("
                    f"fingerprint float[{dimensions}] distance_metric=cosine, "
                    f"video_id TEXT, "
                    f"timestamp FLOAT"
                    f")"
                )
                self.connection.commit()
            self._vec_frame_dim = dimensions
            return True
        except Exception as e:
            self.logger.warning(f"vec0フレームテーブル作成エラー: {e}")
            return False

    def _index_frames_vec(
        self, video_id: str,
        frames: List[Tuple[int, float, bytes]],
    ) -> None:
        """フレーム指紋をvec0索引へ投入（既存分は置換）"""
        if not frames:
            return
        dims = len(frames[0][2]) // 4  # float32バイト列 → 次元数
        if not self._ensure_vec_frame_table(dims):
            return
        try:
            cursor = self.connection.cursor()
            cursor.execute(
                "DELETE FROM vec_frame_fingerprints WHERE video_id = ?",
                (video_id,),
            )
            cursor.executemany(
                """INSERT INTO vec_frame_fingerprints
                    (fingerprint, video_id, timestamp)
                VALUES (?, ?, ?)""",
                [
                    (fp_blob, video_id, float(ts))
                    for _, ts, fp_blob in frames
                ],
            )
            self.connection.commit()
        except Exception as e:
            self.logger.warning(f"vec0フレーム索引投入エラー: {e}")

    def search_frame_candidates(
        self, query_fps: List[bytes], dimensions: int,
        k_per_query: int = 10, sim_threshold: float = 0.4,
    ) -> Dict[str, Dict[str, float]]:
        """クエリ各フレームでフレーム指紋のANN近傍を引き、映像別に集計

        音声のhash投票と同じ思想で、
        クエリフレームがどの映像に何票ヒットしたか（votes）と
        類似度合計（score_sum）を返す。

        Returns:
            {video_id: {"votes": 得票数, "score_sum": 類似度合計}}
        """
        agg: Dict[str, Dict[str, float]] = {}
        if not query_fps:
            return agg
        if not self._ensure_vec_frame_table(dimensions):
            return agg
        try:
            cursor = self.connection.cursor()
            for q_blob in query_fps:
                cursor.execute(
                    """SELECT video_id, distance
                       FROM vec_frame_fingerprints
                       WHERE fingerprint MATCH ? AND k = ?
                       ORDER BY distance""",
                    (q_blob, k_per_query),
                )
                for vid_id, dist in cursor.fetchall():
                    sim = 1.0 - float(dist)
                    if sim < sim_threshold:
                        continue
                    slot = agg.setdefault(
                        vid_id, {"votes": 0.0, "score_sum": 0.0}
                    )
                    slot["votes"] += 1.0
                    slot["score_sum"] += sim
            return agg
        except Exception as e:
            self.logger.error(f"vec0フレーム検索エラー: {e}")
            return agg

    def _create_video_tables(self) -> bool:
        """映像指紋テーブルを作成"""
        try:
            cursor = self.connection.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS videos (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    duration REAL,
                    frame_count INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS frame_fingerprints (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    video_id TEXT NOT NULL,
                    frame_index INTEGER NOT NULL,
                    timestamp REAL NOT NULL,
                    fingerprint BLOB NOT NULL,
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
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    video_id TEXT NOT NULL,
                    frame_index INTEGER NOT NULL,
                    timestamp REAL NOT NULL,
                    descriptors BLOB NOT NULL,
                    descriptor_count INTEGER NOT NULL,
                    FOREIGN KEY (video_id) REFERENCES videos (id)
                        ON DELETE CASCADE
                )
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_frame_desc_video
                ON frame_descriptors (video_id)
            """)

            self.connection.commit()
            return True
        except Exception as e:
            self.logger.error(f"SQLite video table creation error: {e}")
            return False

    def add_video(self, video: Video) -> bool:
        """SQLiteに映像メタデータを追加"""
        try:
            self._create_video_tables()
            cursor = self.connection.cursor()
            cursor.execute(
                """INSERT OR REPLACE INTO videos
                    (id, title, file_path, duration, frame_count)
                VALUES (?, ?, ?, ?, ?)""",
                (video.id, video.title, video.file_path,
                 video.duration, video.frame_count),
            )
            self.connection.commit()
            return True
        except Exception as e:
            self.logger.error(
                f"SQLite video addition error: {e} | "
                f"Context: {{'video_id': '{video.id}'}}"
            )
            return False

    def add_frame_fingerprints(
        self, video_id: str,
        frames: List[Tuple[int, float, bytes]],
    ) -> bool:
        """SQLiteにフレーム単位指紋を一括保存"""
        try:
            self._create_video_tables()
            cursor = self.connection.cursor()
            cursor.execute(
                "DELETE FROM frame_fingerprints WHERE video_id = ?",
                (video_id,),
            )
            rows = [
                (video_id, fidx, float(ts), fp_blob)
                for fidx, ts, fp_blob in frames
            ]
            cursor.executemany(
                """INSERT INTO frame_fingerprints
                    (video_id, frame_index, timestamp, fingerprint)
                VALUES (?, ?, ?, ?)""",
                rows,
            )
            self.connection.commit()
            # ANN検索用のvec0索引にも投入
            self._index_frames_vec(video_id, frames)
            return True
        except Exception as e:
            self.logger.error(
                f"SQLite frame fingerprint save error: {e} | "
                f"Context: {{'video_id': '{video_id}', 'count': {len(frames)}}}"
            )
            return False

    def get_video_by_id(self, video_id: str) -> Optional[Video]:
        """video_idから映像メタデータを取得（フレームANN候補の詳細補完用）"""
        return self.get_video(video_id)

    def get_frame_fingerprints(
        self, video_id: str,
    ) -> List[Tuple[int, float, bytes]]:
        """SQLiteから指定映像のフレーム指紋を取得"""
        try:
            self._create_video_tables()
            cursor = self.connection.cursor()
            cursor.execute(
                """SELECT frame_index, timestamp, fingerprint
                   FROM frame_fingerprints WHERE video_id = ?""",
                (video_id,),
            )
            return [
                (int(fidx), float(ts), bytes(fp_blob))
                for fidx, ts, fp_blob in cursor.fetchall()
            ]
        except Exception as e:
            self.logger.error(f"SQLite frame fingerprint retrieval error: {e}")
            return []

    def get_frame_fingerprints_batch(
        self, video_ids: List[str],
    ) -> Dict[str, List[Tuple[int, float, bytes]]]:
        """SQLiteから複数映像のフレーム指紋を1クエリで一括取得"""
        result: Dict[str, List[Tuple[int, float, bytes]]] = {
            vid: [] for vid in video_ids
        }
        if not video_ids:
            return result
        try:
            self._create_video_tables()
            cursor = self.connection.cursor()
            placeholders = ",".join("?" for _ in video_ids)
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
        except Exception as e:
            self.logger.error(
                f"SQLite frame fingerprint batch retrieval error: {e}"
            )
        return result

    def get_video(self, video_id: str) -> Optional[Video]:
        """SQLiteから映像情報を取得"""
        try:
            self._create_video_tables()
            cursor = self.connection.cursor()
            cursor.execute(
                """SELECT id, title, file_path, duration, frame_count,
                          created_at
                   FROM videos WHERE id = ?""",
                (video_id,),
            )
            row = cursor.fetchone()
            if row:
                return Video(
                    id=row[0], title=row[1], file_path=row[2],
                    duration=row[3], frame_count=row[4], created_at=row[5],
                )
        except Exception as e:
            self.logger.error(f"SQLite video retrieval error: {e}")
        return None

    def list_videos(self) -> List[Video]:
        """SQLiteから全映像をリスト取得"""
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
                    duration=r[3], frame_count=r[4], created_at=r[5],
                )
                for r in cursor.fetchall()
            ]
        except Exception as e:
            self.logger.error(f"SQLite video list retrieval error: {e}")
            return []

    def add_frame_descriptors(
        self, video_id: str,
        frames: List[Tuple[int, float, bytes, int]],
    ) -> bool:
        """SQLiteにフレーム単位AKAZE記述子を一括保存"""
        try:
            self._create_video_tables()
            cursor = self.connection.cursor()
            cursor.execute(
                "DELETE FROM frame_descriptors WHERE video_id = ?",
                (video_id,),
            )
            rows = [
                (video_id, fidx, float(ts), desc_blob, desc_count)
                for fidx, ts, desc_blob, desc_count in frames
            ]
            cursor.executemany(
                """INSERT INTO frame_descriptors
                    (video_id, frame_index, timestamp,
                     descriptors, descriptor_count)
                VALUES (?, ?, ?, ?, ?)""",
                rows,
            )
            self.connection.commit()
            return True
        except Exception as exc:
            self.logger.error(
                f"SQLite frame descriptor save error: {exc} | "
                f"Context: {{'video_id': '{video_id}'}}"
            )
            return False

    def get_frame_descriptors(
        self, video_id: str,
    ) -> List[Tuple[int, float, bytes, int]]:
        """SQLiteから指定映像のフレーム記述子を取得"""
        try:
            self._create_video_tables()
            cursor = self.connection.cursor()
            cursor.execute(
                """SELECT frame_index, timestamp,
                          descriptors, descriptor_count
                   FROM frame_descriptors WHERE video_id = ?
                   ORDER BY frame_index""",
                (video_id,),
            )
            return [
                (int(fidx), float(ts), bytes(desc), int(cnt))
                for fidx, ts, desc, cnt in cursor.fetchall()
            ]
        except Exception as exc:
            self.logger.error(
                f"SQLite frame descriptor retrieval error: {exc}"
            )
            return []

    def get_all_frame_descriptors(
        self,
    ) -> Dict[str, List[Tuple[int, float, bytes, int]]]:
        """全映像のフレーム記述子を取得"""
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
                if vid not in result:
                    result[vid] = []
                result[vid].append(
                    (int(fidx), float(ts), bytes(desc), int(cnt))
                )
        except Exception as exc:
            self.logger.error(
                f"SQLite all frame descriptor retrieval error: {exc}"
            )
        return result

    def delete_video(self, video_id: str) -> bool:
        """SQLiteから映像と関連指紋を削除"""
        try:
            self._create_video_tables()
            cursor = self.connection.cursor()
            # vec0フレーム索引からも削除
            try:
                cursor.execute(
                    "DELETE FROM vec_frame_fingerprints "
                    "WHERE video_id = ?",
                    (video_id,),
                )
            except Exception:
                pass
            cursor.execute(
                "DELETE FROM frame_descriptors WHERE video_id = ?",
                (video_id,),
            )
            cursor.execute(
                "DELETE FROM frame_fingerprints WHERE video_id = ?",
                (video_id,),
            )
            cursor.execute("DELETE FROM videos WHERE id = ?", (video_id,))
            self.connection.commit()
            return True
        except Exception as e:
            self.logger.error(
                f"SQLite video deletion error: {e} | "
                f"Context: {{'video_id': '{video_id}'}}"
            )
            return False

    def get_video_stats(self) -> Dict[str, int]:
        """SQLiteの映像指紋統計を取得"""
        stats = {"videos": 0, "frame_fingerprints": 0}
        try:
            self._create_video_tables()
            cursor = self.connection.cursor()
            cursor.execute("SELECT COUNT(*) FROM videos")
            stats["videos"] = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM frame_fingerprints")
            stats["frame_fingerprints"] = cursor.fetchone()[0]
        except Exception as e:
            self.logger.error(f"SQLite video statistics retrieval error: {e}")
        return stats
