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

    # ===== AKAZE記述子（指紋再生成用） =====

    def add_frame_descriptors(
        self,
        video_id: str,
        frame_descriptors: List[Tuple[int, float, np.ndarray]],
    ) -> bool:
        """
        フレーム単位のAKAZE記述子を保存（指紋再生成用）

        Args:
            video_id: 映像ID
            frame_descriptors: [(フレームインデックス, タイムスタンプ,
                                 記述子配列(N×61)), ...]

        Returns:
            成功時True
        """
        frames_blob = [
            (
                fidx,
                ts,
                desc.astype(np.float32).tobytes(),
                desc.shape[0],
            )
            for fidx, ts, desc in frame_descriptors
        ]
        return self.backend.add_frame_descriptors(video_id, frames_blob)

    def get_frame_descriptors(
        self, video_id: str,
    ) -> List[Tuple[int, float, np.ndarray]]:
        """
        保存済みフレーム記述子を取得

        Returns:
            [(フレームインデックス, タイムスタンプ, 記述子配列), ...]
        """
        raw = self.backend.get_frame_descriptors(video_id)
        result = []
        for fidx, ts, desc_blob, desc_count in raw:
            desc = np.frombuffer(desc_blob, dtype=np.float32).copy()
            desc = desc.reshape(desc_count, -1)
            result.append((fidx, ts, desc))
        return result

    def get_all_frame_descriptors(
        self,
    ) -> Dict[str, List[Tuple[int, float, np.ndarray]]]:
        """
        全映像のフレーム記述子を取得

        Returns:
            {video_id: [(fidx, ts, 記述子配列), ...], ...}
        """
        raw_all = self.backend.get_all_frame_descriptors()
        result: Dict[str, List[Tuple[int, float, np.ndarray]]] = {}
        for vid, frames in raw_all.items():
            converted = []
            for fidx, ts, desc_blob, desc_count in frames:
                desc = np.frombuffer(desc_blob, dtype=np.float32).copy()
                desc = desc.reshape(desc_count, -1)
                converted.append((fidx, ts, desc))
            result[vid] = converted
        return result

    # ===== 検索 =====

    def search_frame_candidates(
        self,
        query_frame_fps: List[Tuple[int, float, np.ndarray]],
        top_k: int = 10,
        k_per_query: int = 10,
        sim_threshold: float = 0.4,
    ) -> List[Dict]:
        """
        フレーム指紋のANN近傍投票で候補映像を絞り込む

        全体指紋ゲートを廃止し、クエリ各フレームのANN近傍から
        映像別の得票数・類似度合計を集計して候補化する。
        音声のhash投票と同じ思想で、部分クリップでも該当フレームを
        直接引ける。

        Args:
            query_frame_fps: クエリ映像のフレーム指紋リスト
            top_k: 返す候補数
            k_per_query: クエリ1フレームあたりのANN近傍数
            sim_threshold: ヒットとみなす最低類似度

        Returns:
            [{"video_id": ..., "similarity": ..., "votes": ...,
              "video": ...}, ...]
        """
        if not query_frame_fps:
            return []

        query_blobs = [
            fp_vec.astype(np.float32).tobytes()
            for _, _, fp_vec in query_frame_fps
        ]
        dims = query_frame_fps[0][2].shape[0]

        agg = self.backend.search_frame_candidates(
            query_blobs, dims, k_per_query, sim_threshold
        )

        candidates: List[Dict] = []
        for vid_id, stats in agg.items():
            votes = int(stats.get("votes", 0))
            if votes <= 0:
                continue
            avg_sim = stats.get("score_sum", 0.0) / max(votes, 1)
            video = self.backend.get_video(vid_id)
            candidates.append({
                "video_id": vid_id,
                "similarity": float(avg_sim),
                "votes": votes,
                "video": video,
            })

        # 得票数を主指標、平均類似度を副指標に候補を順位付け
        candidates.sort(
            key=lambda c: (c["votes"], c["similarity"]), reverse=True
        )
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
        また、一致区間の時間帯情報も返す。

        Args:
            query_frame_fps: クエリ映像のフレーム指紋リスト
            candidate_video_ids: 候補映像IDリスト
            threshold: 最低類似度閾値

        Returns:
            [{"video_id": ..., "frame_similarity": ...,
              "match_details": {...}, ...}, ...]
        """
        results = []

        if not query_frame_fps:
            return results

        # 候補映像のフレーム指紋を1クエリで一括取得（リモートDBのI/O往復を削減）
        frames_by_video = self.backend.get_frame_fingerprints_batch(
            candidate_video_ids
        )

        for vid_id in candidate_video_ids:
            raw_frames = frames_by_video.get(vid_id, [])
            if not raw_frames:
                continue

            db_frame_vecs = [
                (fidx, ts, np.frombuffer(fp_blob, dtype=np.float32).copy())
                for fidx, ts, fp_blob in raw_frames
            ]

            # クエリ×DBの全フレーム類似度を行列積で一括計算
            # （Python二重ループを回避し、BLASによる高速化を図る）
            q_mat = np.stack(
                [q_fp.astype(np.float32) for _, _, q_fp in query_frame_fps]
            )
            d_mat = np.stack([d_fp for _, _, d_fp in db_frame_vecs])
            # 非有限値（NaN/inf）混入時の行列積警告を抑止し0類似度化
            with np.errstate(all="ignore"):
                sims = q_mat @ d_mat.T  # (クエリフレーム数, DBフレーム数)
            np.nan_to_num(sims, copy=False, nan=0.0, posinf=0.0, neginf=0.0)

            best_idx = np.argmax(sims, axis=1)
            best_per_query = sims[np.arange(sims.shape[0]), best_idx]
            db_ts_arr = np.array(
                [d_ts for _, d_ts, _ in db_frame_vecs], dtype=np.float64
            )
            best_db_ts_arr = db_ts_arr[best_idx]

            frame_matches = [
                {
                    "query_ts": q_ts,
                    "db_ts": float(best_db_ts_arr[i]),
                    "similarity": float(best_per_query[i]),
                }
                for i, (_, q_ts, _) in enumerate(query_frame_fps)
            ]

            max_sim = float(np.max(best_per_query))
            if max_sim >= threshold:
                match_details = self._compute_match_regions(
                    frame_matches, threshold=0.4
                )
                db_timestamps = [d_ts for _, d_ts, _ in db_frame_vecs]
                match_details["db_duration"] = (
                    max(db_timestamps) if db_timestamps else 0.0
                )
                q_timestamps = [q_ts for _, q_ts, _ in query_frame_fps]
                match_details["query_duration"] = (
                    max(q_timestamps) if q_timestamps else 0.0
                )

                # 時間的一貫性のある区間がなければ偶然の類似として除外
                if not match_details.get("regions"):
                    continue

                results.append({
                    "video_id": vid_id,
                    "frame_similarity": max_sim,
                    "median_similarity": float(np.median(best_per_query)),
                    "match_details": match_details,
                })

        results.sort(key=lambda r: r["frame_similarity"], reverse=True)
        return results

    @staticmethod
    def _compute_match_regions(
        frame_matches: List[Dict],
        threshold: float = 0.4,
        offset_tolerance: float = 5.0,
        min_region_frames: int = 3,
    ) -> Dict:
        """
        フレームマッチ情報から一致区間を計算

        時間オフセット（db_ts - query_ts）の一貫性で一致区間を判定する。
        同じオフセットを持つフレーム群＝同じ部分を見ている。

        Args:
            frame_matches: フレーム単位のマッチ情報リスト
            threshold: 一致とみなす最低類似度
            offset_tolerance: 同一区間とみなすオフセット差の許容範囲（秒）
            min_region_frames: 区間として認定する最小フレーム数

        Returns:
            一致区間と統計情報
        """
        good = [
            m for m in frame_matches if m["similarity"] >= threshold
        ]
        if not good:
            return {
                "matched_frames": 0,
                "total_frames": len(frame_matches),
                "regions": [],
            }

        # 時間オフセットでクラスタリング
        for m in good:
            m["offset"] = m["db_ts"] - m["query_ts"]

        good.sort(key=lambda m: m["offset"])

        clusters: List[List[Dict]] = []
        cur_cluster = [good[0]]

        for m in good[1:]:
            if m["offset"] - cur_cluster[-1]["offset"] <= offset_tolerance:
                cur_cluster.append(m)
            else:
                clusters.append(cur_cluster)
                cur_cluster = [m]
        clusters.append(cur_cluster)

        # 各クラスタから区間情報を生成
        regions = []
        for cluster in clusters:
            if len(cluster) < min_region_frames:
                continue

            q_times = [m["query_ts"] for m in cluster]
            d_times = [m["db_ts"] for m in cluster]
            avg_sim = sum(m["similarity"] for m in cluster) / len(cluster)

            regions.append({
                "query_start": min(q_times),
                "query_end": max(q_times),
                "db_start": min(d_times),
                "db_end": max(d_times),
                "frame_count": len(cluster),
                "avg_similarity": round(avg_sim, 3),
            })

        regions.sort(key=lambda r: r["query_start"])

        return {
            "matched_frames": len(good),
            "total_frames": len(frame_matches),
            "match_ratio": len(good) / len(frame_matches),
            "regions": regions,
        }

    # ===== 統計 =====

    def get_stats(self) -> Dict[str, int]:
        """データベース統計を取得"""
        return self.backend.get_video_stats()
