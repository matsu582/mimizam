"""
映像指紋のデータベース管理

既存のバックエンド基盤（SQLite/MySQL/PostgreSQL/Elasticsearch）を利用して
映像指紋の保存・検索を行う。
フレーム単位指紋の近傍検索（ANN）と映像別の得票集計で候補を絞り込み、
フレーム単位の時間整合照合とPiP矩形照合で確定する。
"""

import logging
import math
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
        # 支配整列判定に渡すDB候補の閾値と上限。似た画が反復する映像で整列側
        # フレームが僅差の偶発一致に負けて捨てられないよう、閾値以上の全DBフレーム
        # を候補にする（メモリ保護のため1フレームあたり cap 件で頭打ち）。
        self._frame_match_cand_threshold = 0.4
        self._frame_match_cap = 50
        self.backend: DatabaseBackend = create_database_backend(config)

        if not self.backend.connect():
            raise RuntimeError(
                f"Failed to connect to video fingerprint DB: {config.backend}"
            )

        if not self.backend.create_tables():
            raise RuntimeError("Failed to create video fingerprint DB tables")

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
            self.logger.info(f"Video added: {video.title} (ID: {video.id})")
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
            self.logger.info(f"Video deleted: {video_id}")
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

        クエリ各フレームのANN近傍から映像別の得票数・類似度合計を
        集計して候補化する。
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

            db_ts_arr = np.array(
                [d_ts for _, d_ts, _ in db_frame_vecs], dtype=np.float64
            )
            best_idx = np.argmax(sims, axis=1)
            best_per_query = sims[np.arange(sims.shape[0]), best_idx]

            # 各クエリフレームで「最類似の1件」だけを残すと、似た画が反復する
            # 映像（OP等）で真に時間整列するDBフレームが僅差の偶発一致に負けて
            # 捨てられ、整列が散る。候補は「上位1件」ではなく閾値(cand_threshold)
            # 以上の全DBフレームを保持し、支配直線フィットが直線に乗るものを選べる
            # ようにする。メモリ保護のため1フレームあたり _frame_match_cap 件で頭打ち。
            cand_threshold = self._frame_match_cand_threshold
            cap = self._frame_match_cap

            frame_matches = []
            for i, (_, q_ts, _) in enumerate(query_frame_fps):
                row = sims[i]
                cand_j = np.nonzero(row >= cand_threshold)[0]
                if cand_j.size > cap:
                    # 類似度上位capのみ残す（真の整列側を落とさないため十分大きく取る）
                    cand_j = cand_j[np.argsort(-row[cand_j])[:cap]]
                cands = [
                    (float(db_ts_arr[j]), float(row[j])) for j in cand_j
                ]
                frame_matches.append({
                    "query_ts": q_ts,
                    # 表示・後方互換用の最良1件
                    "db_ts": float(db_ts_arr[best_idx[i]]),
                    "similarity": float(best_per_query[i]),
                    # 支配整列用の候補（閾値以上の全DBフレーム、cap件まで）
                    "candidates": cands,
                })

            max_sim = float(np.max(best_per_query))
            if max_sim >= threshold:
                q_timestamps = [q_ts for _, q_ts, _ in query_frame_fps]
                query_duration = max(q_timestamps) if q_timestamps else 0.0
                match_details = self._compute_match_regions(
                    frame_matches, threshold=0.4,
                    query_duration=query_duration,
                )
                db_timestamps = [d_ts for _, d_ts, _ in db_frame_vecs]
                match_details["db_duration"] = (
                    max(db_timestamps) if db_timestamps else 0.0
                )
                match_details["query_duration"] = query_duration

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
    def _fit_dominant_alignment(
        per_query: List[Tuple[float, List[Tuple[float, float]]]],
        residual_tolerance: float,
        slope_range: Tuple[float, float],
        min_query_gap: float,
    ) -> Tuple[float, float, List[Tuple[float, float, float]]]:
        """支配直線 db≈slope·query+offset を頑健推定しインライアを返す

        音声側の頑健直線フィットと同型の考え方を映像フレームに適用する（Java実装
        等の外部コードは参照せず独自実装）。各クエリフレームは複数のDB候補
        (db_ts, similarity) を持ちうる。ペア間の傾きをlog2空間で投票して傾き候補を
        得て、各候補についてオフセット最頻ビン近傍のインライアを数え、整列する
        「クエリフレーム数」が最大の傾きを採用する。1クエリフレームにつき直線に乗る
        候補のうち最も類似度が高い1件を代表として採用するため、最類似候補が別箇所の
        偶発一致でも、整列側の次点候補があれば取りこぼさない。

        Args:
            per_query: [(query_ts, [(db_ts, similarity), ...]), ...]
            residual_tolerance: 直線からの残差をインライアとみなす許容（秒）
            slope_range: 妥当な傾き（=time_scale）の範囲
            min_query_gap: 傾き算出に使うペアの最小 query 時間差（秒）

        Returns:
            (slope, offset, inliers) inliers=[(query_ts, db_ts, similarity), ...]
        """
        n = len(per_query)
        if n == 0:
            return 1.0, 0.0, []

        lo, hi = slope_range

        # 傾き候補の投票には各クエリの最類似候補を代表点として使う
        reps = [
            (q, max(cands, key=lambda c: c[1])[0])
            for q, cands in per_query
        ]
        slopes: List[float] = []
        for i in range(n):
            qi, di = reps[i]
            for j in range(i + 1, n):
                qj, dj = reps[j]
                dq = qj - qi
                if abs(dq) < min_query_gap:
                    continue
                s = (dj - di) / dq
                if lo <= s <= hi:
                    slopes.append(s)

        candidates: List[float] = [1.0]  # 恒等倍率は常に評価対象
        if slopes:
            bin_w = 0.05  # log2空間のビン幅
            log_lo = math.log2(lo)
            votes: Dict[int, List[float]] = {}
            for s in slopes:
                b = int((math.log2(s) - log_lo) / bin_w)
                votes.setdefault(b, []).append(s)
            ranked = sorted(votes.values(), key=len, reverse=True)
            for v in ranked[:3]:
                candidates.append(float(np.median(v)))

        tol = residual_tolerance

        def evaluate(slope: float
                     ) -> Tuple[float, List[Tuple[float, float, float]]]:
            # 全候補のオフセットを (クエリ添字ごとに) 集計し、
            # 整列するクエリフレーム数が最大のオフセットビンを選ぶ
            bin_qs: Dict[int, set] = {}
            bin_offs: Dict[int, List[float]] = {}
            for qi, (q, cands) in enumerate(per_query):
                for d, _s in cands:
                    off = d - slope * q
                    b = int(round(off / tol))
                    bin_qs.setdefault(b, set()).add(qi)
                    bin_offs.setdefault(b, []).append(off)
            if not bin_qs:
                return 0.0, []
            best_b = max(bin_qs, key=lambda b: len(bin_qs[b]))
            offset = float(np.median(bin_offs[best_b]))
            # 各クエリフレームで直線±tolに乗る候補のうち最類似の1件を採用
            inliers: List[Tuple[float, float, float]] = []
            for q, cands in per_query:
                on_line = [
                    (d, s) for d, s in cands
                    if abs((d - slope * q) - offset) <= tol
                ]
                if on_line:
                    d, s = max(on_line, key=lambda c: c[1])
                    inliers.append((q, d, s))
            return offset, inliers

        best: Tuple[float, float, List[Tuple[float, float, float]]] = (
            1.0, 0.0, []
        )
        for cand in candidates:
            slope = min(max(cand, lo), hi)
            offset, inliers = evaluate(slope)
            if len(inliers) > len(best[2]):
                best = (slope, offset, inliers)
        return best

    @staticmethod
    def _compute_match_regions(
        frame_matches: List[Dict],
        threshold: float = 0.4,
        residual_tolerance: float = 3.0,
        min_region_frames: int = 3,
        slope_range: Tuple[float, float] = (0.5, 2.0),
        min_query_gap: float = 2.0,
        query_gap_merge: float = 8.0,
        query_duration: float = 0.0,
    ) -> Dict:
        """フレームマッチ情報から支配整列に乗る一致区間を計算する

        従来はオフセット差の貪欲クラスタリングで区間を切っていたため、真に連続する
        一致でも僅かな速度差・タイムスタンプ量子化でオフセットがドリフトすると別区間
        に割れ、別箇所の偶発一致も被覆率へ混ざっていた。ここでは支配直線
        db≈slope·query+offset を頑健推定し、その直線に整合するインライアだけを一致
        とみなす。連続するインライアは1区間に統合され、直線から外れる偶発一致は除外
        される。被覆率はクエリ時間軸で連続的にどれだけ覆うか（span/クエリ長）で測る。

        各フレームマッチは `candidates`=[(db_ts, similarity), ...] を持ちうる（無い
        場合は単一の (db_ts, similarity) を候補とみなす）。最類似1件だけに潰さず
        候補を渡すことで、整列側フレームが僅差の偶発一致に負けても取りこぼさない。

        Args:
            frame_matches: フレーム単位のマッチ情報リスト
            threshold: 一致とみなす最低類似度
            residual_tolerance: 支配直線からの残差の許容（秒）
            min_region_frames: 支配整列として認定する最小インライア数
            slope_range: 妥当な傾き（=time_scale）の範囲
            min_query_gap: 傾き算出に使うペアの最小 query 時間差（秒）
            query_gap_merge: 連続区間とみなすクエリ時間の最大空き（秒）
            query_duration: クエリ全体の長さ（被覆率算出に使用、0なら整列範囲で代替）

        Returns:
            一致区間と統計情報
        """
        # 各クエリフレームを (query_ts, [(db_ts, sim)>=threshold ...]) に正規化
        per_query: List[Tuple[float, List[Tuple[float, float]]]] = []
        for m in frame_matches:
            cands = m.get("candidates")
            if cands is None:
                cands = [(m["db_ts"], m["similarity"])]
            good_c = [
                (float(d), float(s)) for d, s in cands if s >= threshold
            ]
            if good_c:
                per_query.append((float(m["query_ts"]), good_c))

        total = len(frame_matches)
        empty = {
            "matched_frames": 0,
            "aligned_frames": 0,
            "total_frames": total,
            "match_ratio": 0.0,
            "coverage": 0.0,
            "time_scale": 1.0,
            "time_offset": 0.0,
            "median_similarity": 0.0,
            "regions": [],
        }
        if len(per_query) < min_region_frames:
            return empty

        slope, offset, inlier_pts = VideoFingerprintDatabase._fit_dominant_alignment(
            per_query, residual_tolerance, slope_range, min_query_gap
        )
        if len(inlier_pts) < min_region_frames:
            # 支配直線に整合するフレームが足りない＝時間的に一貫しない偶発一致
            return empty

        inliers = [
            {"query_ts": q, "db_ts": d, "similarity": s}
            for q, d, s in sorted(inlier_pts, key=lambda t: t[0])
        ]

        # 支配直線上のインライアをクエリ時間の空きで連続区間に分割する
        regions = []
        cur = [inliers[0]]
        for m in inliers[1:]:
            if m["query_ts"] - cur[-1]["query_ts"] <= query_gap_merge:
                cur.append(m)
            else:
                regions.append(cur)
                cur = [m]
        regions.append(cur)

        region_infos = []
        covered = 0.0
        for cluster in regions:
            q_times = [m["query_ts"] for m in cluster]
            d_times = [m["db_ts"] for m in cluster]
            avg_sim = sum(m["similarity"] for m in cluster) / len(cluster)
            q_start, q_end = min(q_times), max(q_times)
            covered += q_end - q_start
            region_infos.append({
                "query_start": q_start,
                "query_end": q_end,
                "db_start": min(d_times),
                "db_end": max(d_times),
                "frame_count": len(cluster),
                "avg_similarity": round(avg_sim, 3),
            })
        region_infos.sort(key=lambda r: r["query_start"])

        # 被覆率: 整列がクエリ時間軸を連続的にどれだけ覆うか
        span = query_duration if query_duration > 0 else (
            max(m["query_ts"] for m in inliers)
            - min(m["query_ts"] for m in inliers)
        )
        coverage = min(1.0, covered / span) if span > 0 else 0.0
        median_sim = float(np.median([m["similarity"] for m in inliers]))

        return {
            # 支配整列に乗ったインライア数（従来のmatched_framesを置換）
            "matched_frames": len(inliers),
            "aligned_frames": len(inliers),
            "total_frames": total,
            # 従来互換: 全フレームに対するインライアの割合
            "match_ratio": len(inliers) / total if total else 0.0,
            # 連続被覆率（スコアの主指標）
            "coverage": coverage,
            "time_scale": slope,
            "time_offset": offset,
            "median_similarity": median_sim,
            "regions": region_infos,
        }

    # ===== 統計 =====

    def get_stats(self) -> Dict[str, int]:
        """データベース統計を取得"""
        return self.backend.get_video_stats()
