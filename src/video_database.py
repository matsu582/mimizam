"""
映像指紋のデータベース管理

既存のバックエンド基盤（SQLite/MySQL/PostgreSQL/Elasticsearch）を利用して
映像指紋の保存・検索を行う。
映像全体指紋（高速候補絞り込み）とフレーム単位指紋（PiP対策精密照合）の
2段階検索をサポート。
"""

import logging
from typing import List, Optional, Dict, Tuple

import numpy as np

from .database_base import Video, DatabaseConfig
from .database_backends import DatabaseBackend, create_database_backend


logger = logging.getLogger(__name__)


class VideoFingerprintDatabase:
    """映像指紋のデータベース管理クラス（複数バックエンド対応）"""

    def __init__(
        self,
        config: Optional[DatabaseConfig] = None,
        db_path: Optional[str] = None,
    ):
        """
        映像指紋データベースを初期化

        Args:
            config: データベース設定。Noneの場合はSQLiteを使用
            db_path: SQLite用ファイルパス（configがNoneの場合に使用）
        """
        self.logger = logging.getLogger(__name__)

        if config is None:
            path = db_path or "video_fingerprints.db"
            config = DatabaseConfig(backend="sqlite", file_path=path)

        self.config = config
        self.backend: DatabaseBackend = create_database_backend(config)

        if not self.backend.connect():
            raise RuntimeError(
                f"映像指紋DB接続に失敗: {config.backend}"
            )

        if not self.backend.create_tables():
            raise RuntimeError("映像指紋DBテーブル作成に失敗")

    def __del__(self):
        """デストラクタ"""
        try:
            if hasattr(self, "backend") and self.backend:
                self.backend.disconnect()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self) -> None:
        """データベース接続を閉じる"""
        if self.backend:
            self.backend.disconnect()

    # ===== 映像メタデータ =====

    def add_video(self, video: Video) -> bool:
        """
        映像メタデータを追加

        Args:
            video: 映像オブジェクト

        Returns:
            成功時True
        """
        success = self.backend.add_video(video)
        if success:
            self.logger.info(f"映像追加: {video.title} (ID: {video.id})")
        return success

    def get_video(self, video_id: str) -> Optional[Video]:
        """映像情報を取得"""
        return self.backend.get_video(video_id)

    def list_videos(self) -> List[Video]:
        """全映像をリスト取得"""
        return self.backend.list_videos()

    def delete_video(self, video_id: str) -> bool:
        """映像と関連指紋を削除"""
        success = self.backend.delete_video(video_id)
        if success:
            self.logger.info(f"映像削除: {video_id}")
        return success

    # ===== 映像指紋 =====

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
            fingerprint: L2正規化済み指紋ベクトル（numpy配列）
            descriptor_count: 抽出された記述子の総数

        Returns:
            成功時True
        """
        fp_blob = fingerprint.astype(np.float32).tobytes()
        dims = fingerprint.shape[0]
        return self.backend.add_video_fingerprint(
            video_id, fp_blob, dims, descriptor_count
        )

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
        frames_blob = [
            (fidx, ts, fp_vec.astype(np.float32).tobytes())
            for fidx, ts, fp_vec in frame_fps
        ]
        return self.backend.add_frame_fingerprints(video_id, frames_blob)

    # ===== 検索 =====

    def search_video(
        self,
        query_fp: np.ndarray,
        top_k: int = 10,
        threshold: float = 0.3,
    ) -> List[Dict]:
        """
        映像全体指紋で候補を高速検索

        Args:
            query_fp: クエリ映像のL2正規化済み指紋
            top_k: 返す候補数
            threshold: 最低類似度閾値

        Returns:
            [{"video_id": ..., "similarity": ..., "video": ...}, ...]
        """
        fp_blob = query_fp.astype(np.float32).tobytes()
        dims = query_fp.shape[0]
        return self.backend.search_video_fingerprints(
            fp_blob, dims, top_k, threshold
        )

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

        for vid_id in candidate_video_ids:
            raw_frames = self.backend.get_frame_fingerprints(vid_id)
            if not raw_frames:
                continue

            db_frame_vecs = [
                (fidx, ts, np.frombuffer(fp_blob, dtype=np.float32).copy())
                for fidx, ts, fp_blob in raw_frames
            ]

            best_per_query = []
            for _, _, q_fp in query_frame_fps:
                q_f32 = q_fp.astype(np.float32)
                frame_best = max(
                    float(np.dot(q_f32, d_fp))
                    for _, _, d_fp in db_frame_vecs
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

    # ===== 統計 =====

    def get_stats(self) -> Dict[str, int]:
        """データベース統計を取得"""
        return self.backend.get_video_stats()
