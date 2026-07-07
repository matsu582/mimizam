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
        db._geom_diag = False
        db._geom_scene_gap_factor = 1.8
        db._geom_uniform_subsample = False
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


class TestNonGeometricFallback(unittest.TestCase):
    """DB側に生記述子が無い候補（opt-out動画等）の非幾何フォールバック回帰テスト

    store_raw_descriptors=False で登録した動画は DB に生記述子が無く幾何検証
    できない。この候補を幾何検証パスで黙って落とすと use_frame_matching 既定
    検索でヒットしなくなる。VLADフレーム一致による非幾何スコアリングへ
    フォールバックして拾えることを固定する。
    """

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
        db._geom_diag = False
        db._geom_scene_gap_factor = 1.8
        db._geom_uniform_subsample = False
        db._frame_match_cand_threshold = 0.4
        db._frame_match_cap = 50
        import logging
        db.logger = logging.getLogger("test.vdb")
        return db

    def test_candidate_without_db_descriptors_is_recovered(self):
        """query_raw があっても DB記述子が空なら非幾何で拾う（幾何で落とさない）"""
        vid = "opt_out_vid"
        n = 8
        # クエリとDBのVLADを同一シードで揃え、対角(=時間整列)が強一致するようにする
        query_frame_fps = [(i, float(i), _vlad(i)) for i in range(n)]
        query_raw = [
            (i, float(i), _packed_desc(10 + i, 100 + i)) for i in range(n)
        ]
        db_frames = [(j, float(j), _vlad(j).tobytes()) for j in range(n)]

        db = self._make_db()
        # frame_descs は空＝opt-out動画（生記述子なし）
        backend = _FakeBackend({vid: db_frames}, {vid: []})
        db.backend = backend

        results = db.search_video_with_frame_matching(
            query_frame_fps, [vid], threshold=0.0, query_raw=query_raw,
        )
        # 幾何検証は不可能でも、非幾何フォールバックで候補が返ること
        self.assertTrue(results)
        self.assertEqual(results[0]["video_id"], vid)
        # DB記述子の取得は試みられている（＝幾何経路に入った上でのフォールバック）
        self.assertTrue(backend.desc_calls)


class TestSceneAwareSelection(unittest.TestCase):
    """シーン境界優先の間引き（_select_geom_indices / _scene_groups）の回帰テスト"""

    def _make_db(self):
        db = object.__new__(VDB)
        db._geom_scene_gap_factor = 1.8
        db._geom_uniform_subsample = False
        return db

    def test_scene_groups_splits_on_large_gap(self):
        """中央値ギャップを大きく超える所でシーンが分割される"""
        db = self._make_db()
        # 0,1,2,3 は等間隔(1s)、10で大ギャップ、11,12 が別シーン
        ts = [0.0, 1.0, 2.0, 3.0, 10.0, 11.0, 12.0]
        scenes = db._scene_groups(ts)
        self.assertEqual(scenes, [[0, 1, 2, 3], [4, 5, 6]])

    def test_scene_groups_single_scene_when_uniform(self):
        """等間隔なら分割されず1シーン"""
        db = self._make_db()
        ts = [float(i) for i in range(6)]
        self.assertEqual(db._scene_groups(ts), [[0, 1, 2, 3, 4, 5]])

    def test_select_keeps_every_scene_boundary(self):
        """各シーンの代表（先頭）フレームは必ず選ばれる（別カットの取りこぼし防止）"""
        db = self._make_db()
        # 5シーン×各3フレーム（シーン間は大ギャップ）
        ts = []
        t = 0.0
        for s in range(5):
            for _ in range(3):
                ts.append(t)
                t += 1.0
            t += 20.0  # シーン境界
        boundaries = [i for i in range(len(ts)) if i % 3 == 0]
        sel = db._select_geom_indices(ts, cap=6)
        for b in boundaries:
            self.assertIn(b, sel)

    def test_select_recovers_short_fragment_vs_uniform(self):
        """一様間引きでは落ちる短い断片フレームを、シーン優先だと拾える

        末尾に3フレームの短いシーン（別カット）を置き、一様間引きでは境界が
        取りこぼされる状況で、シーン優先だと代表が残ることを固定する。
        """
        # 前半は密な1シーン(30フレーム, 1s間隔)、末尾に大ギャップ後の短いシーン3枚
        ts = [float(i) for i in range(30)]
        base = ts[-1] + 20.0
        ts += [base, base + 1.0, base + 2.0]  # index 30,31,32（短い別シーン）
        db = self._make_db()
        cap = 16
        sel = db._select_geom_indices(ts, cap)
        # 短いシーンの先頭(index30)がシーン優先では必ず残る
        self.assertIn(30, sel)
        self.assertLessEqual(len(sel), cap)
        # 一様間引きだと同じ末尾シーンの中間フレームは落ちやすい（対照）
        uni = db._subsample_indices(len(ts), cap)
        # シーン優先は末尾シーンから一様間引きより多く残す
        tail_scene = {30, 31, 32}
        self.assertGreaterEqual(
            len(tail_scene & set(sel)), len(tail_scene & set(uni))
        )

    def test_select_respects_cap(self):
        """cap を超えて選ばない"""
        db = self._make_db()
        ts = [float(i) for i in range(200)]
        for cap in (1, 5, 50, 128):
            sel = db._select_geom_indices(ts, cap)
            self.assertLessEqual(len(sel), cap)
            self.assertEqual(sel, sorted(sel))

    def test_select_returns_all_when_under_cap(self):
        """n<=cap は全件（間引き無効）"""
        db = self._make_db()
        ts = [0.0, 1.0, 2.0]
        self.assertEqual(db._select_geom_indices(ts, 10), [0, 1, 2])

    def test_uniform_switch_falls_back(self):
        """_geom_uniform_subsample=True で従来の一様間引きへ戻る"""
        db = self._make_db()
        db._geom_uniform_subsample = True
        ts = [float(i) for i in range(20)]
        self.assertEqual(
            db._select_geom_indices(ts, 5), db._subsample_indices(20, 5)
        )


if __name__ == "__main__":
    unittest.main()
