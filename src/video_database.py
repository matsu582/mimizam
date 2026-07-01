"""
映像指紋のデータベース管理

SQLiteバックエンドを使用して映像指紋の保存・検索を行う。
映像全体指紋（高速候補絞り込み）とフレーム単位指紋（PiP対策精密照合）の
2段階検索をサポート。
"""

import json
import logging
import sqlite3
from typing import List, Optional, Dict, Tuple

import numpy as np

from .database_base import Video

logger = logging.getLogger(__name__)


class VideoFingerprintDatabase:
    """映像指紋のデータベース管理クラス"""

    def __init__(self, db_path: str = "video_fingerprints.db"):
        """
        映像指紋データベースを初期化

        Args:
            db_path: SQLiteデータベースファイルのパス
        """
        self.db_path = db_path
        self._conn = None
        self._connect()
        self._create_tables()

    def _connect(self) -> None:
        """データベースに接続"""
        self._conn = sqlite3.connect(
            self.db_path,
            check_same_thread=False,
            timeout=30.0,
        )
        cursor = self._conn.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.execute("PRAGMA journal_mode = WAL")
        cursor.execute("PRAGMA synchronous = NORMAL")
        cursor.execute("PRAGMA cache_size = -64000")
        logger.info(f"映像指紋DB接続: {self.db_path}")

    def _create_tables(self) -> None:
        """テーブルを作成"""
        cursor = self._conn.cursor()

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

        # 映像全体指紋（高速候補絞り込み用）
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS video_fingerprints (
                video_id TEXT PRIMARY KEY,
                fingerprint BLOB NOT NULL,
                dimensions INTEGER NOT NULL,
                descriptor_count INTEGER DEFAULT 0,
                FOREIGN KEY (video_id) REFERENCES videos (id)
                    ON DELETE CASCADE
            )
        """)

        # フレーム単位指紋（PiP対策精密照合用）
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

        self._conn.commit()

    def add_video(self, video: Video) -> bool:
        """
        映像メタデータを追加

        Args:
            video: 映像オブジェクト

        Returns:
            成功時True
        """
        try:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO videos
                    (id, title, file_path, duration, frame_count)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    video.id,
                    video.title,
                    video.file_path,
                    video.duration,
                    video.frame_count,
                ),
            )
            self._conn.commit()
            return True
        except Exception as exc:
            logger.error(f"映像追加エラー: {exc}")
            return False

    def add_video_fingerprint(
        self,
        video_id: str,
        fingerprint: np.ndarray,
        descriptor_count: int = 0,
    ) -> bool:
        """
        映像全体指紋を保存

        Args:
            video_id: 映像ID
            fingerprint: L2正規化済み指紋ベクトル
            descriptor_count: 抽出された記述子の総数

        Returns:
            成功時True
        """
        try:
            fp_blob = fingerprint.astype(np.float32).tobytes()
            dims = fingerprint.shape[0]
            cursor = self._conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO video_fingerprints
                    (video_id, fingerprint, dimensions, descriptor_count)
                VALUES (?, ?, ?, ?)
                """,
                (video_id, fp_blob, dims, descriptor_count),
            )
            self._conn.commit()
            return True
        except Exception as exc:
            logger.error(f"映像指紋保存エラー: {exc}")
            return False

    def add_frame_fingerprints(
        self,
        video_id: str,
        frame_fps: List[Tuple[int, float, np.ndarray]],
    ) -> bool:
        """
        フレーム単位指紋を一括保存

        Args:
            video_id: 映像ID
            frame_fps: [(フレームインデックス, タイムスタンプ, 指紋ベクトル), ...]

        Returns:
            成功時True
        """
        try:
            cursor = self._conn.cursor()
            # 既存データを削除
            cursor.execute(
                "DELETE FROM frame_fingerprints WHERE video_id = ?",
                (video_id,),
            )

            rows = []
            for fidx, ts, fp_vec in frame_fps:
                fp_blob = fp_vec.astype(np.float32).tobytes()
                rows.append((video_id, fidx, float(ts), fp_blob))

            cursor.executemany(
                """
                INSERT INTO frame_fingerprints
                    (video_id, frame_index, timestamp, fingerprint)
                VALUES (?, ?, ?, ?)
                """,
                rows,
            )
            self._conn.commit()
            return True
        except Exception as exc:
            logger.error(f"フレーム指紋保存エラー: {exc}")
            return False

    def search_video(
        self,
        query_fp: np.ndarray,
        top_k: int = 10,
        threshold: float = 0.3,
    ) -> List[Dict]:
        """
        映像全体指紋で候補を高速検索

        全登録映像の指紋とドット積を計算し、上位N件を返す。

        Args:
            query_fp: クエリ映像のL2正規化済み指紋
            top_k: 返す候補数
            threshold: 最低類似度閾値

        Returns:
            [{"video_id": ..., "similarity": ..., "video": ...}, ...]
        """
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT vf.video_id, vf.fingerprint, vf.dimensions,
                   v.title, v.file_path, v.duration, v.frame_count
            FROM video_fingerprints vf
            JOIN videos v ON vf.video_id = v.id
            """
        )

        candidates = []
        query_f32 = query_fp.astype(np.float32)

        for row in cursor.fetchall():
            vid_id, fp_blob, dims, title, fpath, dur, fcount = row
            db_fp = np.frombuffer(fp_blob, dtype=np.float32)
            if db_fp.shape[0] != query_f32.shape[0]:
                continue
            sim = float(np.dot(query_f32, db_fp))
            if sim >= threshold:
                candidates.append({
                    "video_id": vid_id,
                    "similarity": sim,
                    "video": Video(
                        id=vid_id,
                        title=title,
                        file_path=fpath,
                        duration=dur,
                        frame_count=fcount,
                    ),
                })

        candidates.sort(key=lambda c: c["similarity"], reverse=True)
        return candidates[:top_k]

    def search_video_with_frame_matching(
        self,
        query_frame_fps: List[Tuple[int, float, np.ndarray]],
        candidate_video_ids: List[str],
        threshold: float = 0.5,
    ) -> List[Dict]:
        """
        フレーム単位マッチングで精密照合（PiP対策）

        各クエリフレームについて、DB側の全フレームとの最高スコアを計算し、
        全クエリフレーム中の最高スコアを映像の最終スコアとする。

        Args:
            query_frame_fps: クエリ映像のフレーム指紋リスト
            candidate_video_ids: 候補映像IDリスト
            threshold: 最低類似度閾値

        Returns:
            [{"video_id": ..., "frame_similarity": ..., ...}, ...]
        """
        results = []
        cursor = self._conn.cursor()

        for vid_id in candidate_video_ids:
            cursor.execute(
                """
                SELECT frame_index, timestamp, fingerprint
                FROM frame_fingerprints
                WHERE video_id = ?
                """,
                (vid_id,),
            )

            db_frame_fps = []
            for fidx, ts, fp_blob in cursor.fetchall():
                fp_vec = np.frombuffer(fp_blob, dtype=np.float32).copy()
                db_frame_fps.append((fidx, ts, fp_vec))

            if not db_frame_fps:
                continue

            # 各クエリフレームの最高スコア
            best_per_query = []
            for _, _, q_fp in query_frame_fps:
                q_f32 = q_fp.astype(np.float32)
                frame_best = max(
                    float(np.dot(q_f32, d_fp))
                    for _, _, d_fp in db_frame_fps
                )
                best_per_query.append(frame_best)

            max_sim = float(np.max(best_per_query))
            if max_sim >= threshold:
                results.append({
                    "video_id": vid_id,
                    "frame_similarity": max_sim,
                    "median_similarity": float(np.median(best_per_query)),
                })

        results.sort(key=lambda r: r["frame_similarity"], reverse=True)
        return results

    def get_video(self, video_id: str) -> Optional[Video]:
        """映像情報を取得"""
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT id, title, file_path, duration, frame_count, created_at
            FROM videos WHERE id = ?
            """,
            (video_id,),
        )
        row = cursor.fetchone()
        if row:
            return Video(
                id=row[0],
                title=row[1],
                file_path=row[2],
                duration=row[3],
                frame_count=row[4],
                created_at=row[5],
            )
        return None

    def list_videos(self) -> List[Video]:
        """全映像をリスト取得"""
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT id, title, file_path, duration, frame_count, created_at
            FROM videos ORDER BY title
            """
        )
        return [
            Video(
                id=r[0], title=r[1], file_path=r[2],
                duration=r[3], frame_count=r[4], created_at=r[5],
            )
            for r in cursor.fetchall()
        ]

    def delete_video(self, video_id: str) -> bool:
        """映像と関連指紋を削除"""
        try:
            cursor = self._conn.cursor()
            cursor.execute(
                "DELETE FROM frame_fingerprints WHERE video_id = ?",
                (video_id,),
            )
            cursor.execute(
                "DELETE FROM video_fingerprints WHERE video_id = ?",
                (video_id,),
            )
            cursor.execute(
                "DELETE FROM videos WHERE id = ?", (video_id,)
            )
            self._conn.commit()
            return True
        except Exception as exc:
            logger.error(f"映像削除エラー: {exc}")
            return False

    def get_stats(self) -> Dict[str, int]:
        """データベース統計を取得"""
        stats = {"videos": 0, "video_fingerprints": 0, "frame_fingerprints": 0}
        try:
            cursor = self._conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM videos")
            stats["videos"] = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM video_fingerprints")
            stats["video_fingerprints"] = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM frame_fingerprints")
            stats["frame_fingerprints"] = cursor.fetchone()[0]
        except Exception as exc:
            logger.error(f"統計取得エラー: {exc}")
        return stats

    def close(self) -> None:
        """データベース接続を閉じる"""
        if self._conn:
            self._conn.close()
            self._conn = None

    def __del__(self):
        """デストラクタ"""
        self.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
