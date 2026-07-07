"""
search_video_with_frame_matching の幾何検証経路（間引き・行列外出し）の回帰テスト

クエリの間引き高速化を入れた際、類似度行列を「VLADベクトル(512次元)」ではなく
「生記述子(フレーム毎に行数が異なるN×D)」から作ってしまい、np.stack が
"all input arrays must have the same shape" で落ちる不具合が入った。フレーム毎に
行数が異なる生記述子を与え、検索が例外なく最後まで通ることを固定する。
"""

import unittest

import numpy as np

from mimizam.src.video_database import VideoFingerprintDatabase as VDB
from mimizam.src.video_fingerprinter import KEYPOINT_COLS

DESC_DIM = 61  # AKAZE(MLDB)記述子の次元
VLAD_DIM = 512


class _FakeBackend:
    """search_video_with_frame_matching が呼ぶ最小限のバックエンド"""

    def __init__(self, frame_fps, frame_descs):
        # frame_fps: {vid: [(fidx, ts, fp_blob), ...]}
        # frame_descs: {vid: [(fidx, ts, desc_blob, desc_count), ...]}
        self._frame_fps = frame_fps
        self._frame_descs = frame_descs
        self.desc_calls = []

    def get_frame_fingerprints_batch(self, video_ids):
        return {v: self._frame_fps.get(v, []) for v in video_ids}

    def get_frame_descriptors(self, video_id, frame_indices=None):
        self.desc_calls.append((video_id, frame_indices))
        rows = self._frame_descs.get(video_id, [])
        if frame_indices is not None:
            wanted = set(frame_indices)
            rows = [r for r in rows if r[0] in wanted]
        return rows


def _vlad(seed):
    rng = np.random.default_rng(seed)
    v = rng.standard_normal(VLAD_DIM).astype(np.float32)
    return v / (np.linalg.norm(v) + 1e-8)


def _packed_desc(n_rows, seed):
    """結合記述子(N×(2+D)) float32 を作る（先頭2列が座標）"""
    rng = np.random.default_rng(seed)
    kpts = rng.uniform(0, 100, size=(n_rows, KEYPOINT_COLS)).astype(np.float32)
    desc = rng.integers(0, 256, size=(n_rows, DESC_DIM)).astype(np.float32)
    return np.hstack([kpts, desc])


class TestGeometricSearchPath(unittest.TestCase):

    def _make_db(self):
        db = object.__new__(VDB)
        db._geom_top_k = 6
        db._geom_min_inliers = 15
        db._geom_ransac_thresh = 5.0
        db._geom_inlier_saturation = 100.0
        db._geom_max_hits = 3
        db._geom_max_query_frames = 48
        db._geom_max_desc = 400
        db._geom_region_db_gap = 45.0
        db._geom_max_workers = 1
        db._geom_max_candidates = 0
        import logging
        db.logger = logging.getLogger("test.vdb")
        return db

    def test_search_runs_with_ragged_raw_descriptors(self):
        """フレーム毎に生記述子の行数が異なっても例外なく検索できる"""
        vid = "vid1"
        n_query = 8
        query_frame_fps = [
            (i, float(i), _vlad(i)) for i in range(n_query)
        ]
        # 生記述子の行数はフレーム毎にバラバラ（旧実装だと np.stack が落ちる）
        row_counts = [10, 13, 7, 21, 9, 15, 6, 18]
        query_raw = [
            (i, float(i), _packed_desc(row_counts[i], 100 + i))
            for i in range(n_query)
        ]

        # DB側フレーム指紋(VLADブロブ)と生記述子
        db_frames = []
        db_descs = []
        for j in range(4):
            db_frames.append((j, float(300 + j), _vlad(500 + j).tobytes()))
            arr = _packed_desc(12 + j, 700 + j)
            db_descs.append(
                (j, float(300 + j), arr.astype(np.float32).tobytes(),
                 arr.shape[0])
            )

        db = self._make_db()
        db.backend = _FakeBackend({vid: db_frames}, {vid: db_descs})

        # 例外が出ないこと（＝行列形状不一致の回帰）。結果はリストで返る。
        results = db.search_video_with_frame_matching(
            query_frame_fps, [vid], threshold=0.0, query_raw=query_raw,
        )
        self.assertIsInstance(results, list)

    def test_search_runs_with_parallel_workers(self):
        """候補間並列（workers>1）でも例外なく検索できる"""
        n_query = 6
        query_frame_fps = [(i, float(i), _vlad(i)) for i in range(n_query)]
        row_counts = [10, 13, 7, 21, 9, 15]
        query_raw = [
            (i, float(i), _packed_desc(row_counts[i], 100 + i))
            for i in range(n_query)
        ]
        frame_fps = {}
        frame_descs = {}
        vids = ["v1", "v2", "v3"]
        for k, vid in enumerate(vids):
            db_frames = []
            db_descs = []
            for j in range(4):
                db_frames.append(
                    (j, float(300 + j), _vlad(500 + 10 * k + j).tobytes())
                )
                arr = _packed_desc(12 + j, 700 + 10 * k + j)
                db_descs.append(
                    (j, float(300 + j), arr.astype(np.float32).tobytes(),
                     arr.shape[0])
                )
            frame_fps[vid] = db_frames
            frame_descs[vid] = db_descs

        db = self._make_db()
        db._geom_max_workers = 3
        db.backend = _FakeBackend(frame_fps, frame_descs)
        results = db.search_video_with_frame_matching(
            query_frame_fps, vids, threshold=0.0, query_raw=query_raw,
        )
        self.assertIsInstance(results, list)

    def test_only_needed_frames_are_read(self):
        """DB生記述子は必要フレームに限定して取得する（無駄なI/O回避）"""
        vid = "vid1"
        n_query = 4
        query_frame_fps = [(i, float(i), _vlad(i)) for i in range(n_query)]
        query_raw = [
            (i, float(i), _packed_desc(10 + i, 100 + i))
            for i in range(n_query)
        ]
        # DBフレームを多めに用意し、top_k で一部だけが必要になるようにする
        db_frames = []
        db_descs = []
        for j in range(20):
            db_frames.append((j, float(300 + j), _vlad(500 + j).tobytes()))
            arr = _packed_desc(12, 700 + j)
            db_descs.append(
                (j, float(300 + j), arr.astype(np.float32).tobytes(),
                 arr.shape[0])
            )

        db = self._make_db()
        db._geom_top_k = 3
        backend = _FakeBackend({vid: db_frames}, {vid: db_descs})
        db.backend = backend
        db.search_video_with_frame_matching(
            query_frame_fps, [vid], threshold=0.0, query_raw=query_raw,
        )
        # frame_indices=None（全件読み）ではなく、必要フレームに限定されていること
        self.assertTrue(backend.desc_calls)
        for _vid, fidxs in backend.desc_calls:
            self.assertIsNotNone(fidxs)
            # 4クエリ×top_k3 の和集合 ≤ 12 < 20（全件）
            self.assertLessEqual(len(fidxs), n_query * db._geom_top_k)

    def test_geom_max_candidates_limits_verified_videos(self):
        """_geom_max_candidates で幾何検証する候補数（＝DB読み込み対象）を絞る"""
        n_query = 4
        query_frame_fps = [(i, float(i), _vlad(i)) for i in range(n_query)]
        query_raw = [
            (i, float(i), _packed_desc(10 + i, 100 + i))
            for i in range(n_query)
        ]
        frame_fps = {}
        frame_descs = {}
        vids = ["v1", "v2", "v3", "v4", "v5"]
        for k, vid in enumerate(vids):
            db_frames = []
            db_descs = []
            for j in range(4):
                db_frames.append(
                    (j, float(300 + j), _vlad(500 + 10 * k + j).tobytes())
                )
                arr = _packed_desc(12, 700 + 10 * k + j)
                db_descs.append(
                    (j, float(300 + j), arr.astype(np.float32).tobytes(),
                     arr.shape[0])
                )
            frame_fps[vid] = db_frames
            frame_descs[vid] = db_descs

        db = self._make_db()
        db._geom_max_candidates = 2
        backend = _FakeBackend(frame_fps, frame_descs)
        db.backend = backend
        db.search_video_with_frame_matching(
            query_frame_fps, vids, threshold=0.0, query_raw=query_raw,
        )
        # 生記述子の読み込みは上位2候補だけに限定される
        read_vids = {v for v, _ in backend.desc_calls}
        self.assertEqual(read_vids, {"v1", "v2"})

    def test_subsample_limits_geometric_query_frames(self):
        """_geom_max_query_frames で幾何検証するクエリ数を頭打ちにする"""
        db = self._make_db()
        db._geom_max_query_frames = 4
        sel = db._subsample_indices(20, db._geom_max_query_frames)
        self.assertLessEqual(len(sel), 4)
        self.assertEqual(sel[0], 0)
        self.assertEqual(sel[-1], 19)


if __name__ == "__main__":
    unittest.main()
