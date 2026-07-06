"""
映像フレームマッチのRANSAC幾何検証の回帰テスト

VLAD/PCA大域記述子＋コサイン閾値は、局所特徴（AKAZE）レベルでは強く一致する
フレームでもスコアを潰してしまう。そこでANN上位候補に対しAKAZE記述子を
BF(Hamming)+Lowe比+RANSACで突き合わせ、幾何整合するインライア数で採否を
決める経路を検証する。

- 記述子とキーポイント座標の結合/分離（保存レイヤ後方互換）
- 同一フレームは高インライア、無関係フレームは低インライア
- ANN上位候補からの幾何検証でコサインが低くても真の一致を回復する
"""

import os
import tempfile
import unittest

import numpy as np

from mimizam.src.video_database import VideoFingerprintDatabase as VDB
from mimizam.src.video_fingerprinter import (
    KEYPOINT_COLS,
    geometric_match,
    pack_raw_descriptors,
    split_raw_descriptor,
)

DESC_DIM = 61


def _make_frame(n=60, seed=0):
    """一意なAKAZE記述子群とキーポイント座標を生成"""
    rng = np.random.default_rng(seed)
    # 各記述子が一意になるよう行ごとに異なるビットパターンを与える
    desc = rng.integers(0, 256, size=(n, DESC_DIM), dtype=np.uint8)
    kpts = rng.uniform(0, 1280, size=(n, 2)).astype(np.float32)
    return desc, kpts


class TestPackSplit(unittest.TestCase):

    def test_pack_split_roundtrip(self):
        """記述子とキーポイント座標を結合→分離して元に戻せる"""
        desc, kpts = _make_frame(n=40, seed=1)
        per_frame = [(0, 0.0, desc)]
        per_frame_kpts = [(0, 0.0, kpts)]
        packed = pack_raw_descriptors(per_frame, per_frame_kpts)
        _, _, arr = packed[0]
        self.assertEqual(arr.shape, (40, DESC_DIM + KEYPOINT_COLS))

        k, d = split_raw_descriptor(arr, DESC_DIM)
        self.assertIsNotNone(k)
        np.testing.assert_allclose(k, kpts, rtol=0, atol=1e-4)
        np.testing.assert_array_equal(d.astype(np.uint8), desc)

    def test_split_legacy_without_keypoints(self):
        """座標を持たない旧形式（N×D）は座標Noneで記述子を返す"""
        desc, _ = _make_frame(n=30, seed=2)
        arr = desc.astype(np.float32)
        k, d = split_raw_descriptor(arr, DESC_DIM)
        self.assertIsNone(k)
        np.testing.assert_array_equal(d.astype(np.uint8), desc)

    def test_pack_handles_missing_keypoints(self):
        """座標が取れないフレームは0座標で埋めて結合する"""
        desc, _ = _make_frame(n=20, seed=3)
        packed = pack_raw_descriptors([(0, 0.0, desc)], [(0, 0.0, None)])
        _, _, arr = packed[0]
        self.assertEqual(arr.shape, (20, DESC_DIM + KEYPOINT_COLS))
        np.testing.assert_array_equal(arr[:, :KEYPOINT_COLS], 0.0)


class TestGeometricMatch(unittest.TestCase):

    def test_identical_frame_high_inliers(self):
        """同一の記述子・座標なら多数のインライアが得られる"""
        desc, kpts = _make_frame(n=80, seed=10)
        good, inl = geometric_match(
            desc.astype(np.float32), kpts,
            desc.astype(np.float32), kpts,
        )
        self.assertGreaterEqual(inl, 50)
        self.assertGreaterEqual(good, inl)

    def test_unrelated_frames_low_inliers(self):
        """無関係な記述子同士はインライアがごく僅か"""
        desc_q, kpt_q = _make_frame(n=80, seed=20)
        desc_d, kpt_d = _make_frame(n=80, seed=21)
        _good, inl = geometric_match(
            desc_q.astype(np.float32), kpt_q,
            desc_d.astype(np.float32), kpt_d,
        )
        self.assertLess(inl, 20)

    def test_falls_back_to_good_count_without_keypoints(self):
        """座標が無い場合はインライアに良マッチ数を代用する"""
        desc, _ = _make_frame(n=80, seed=30)
        good, inl = geometric_match(
            desc.astype(np.float32), None,
            desc.astype(np.float32), None,
        )
        self.assertEqual(inl, good)
        self.assertGreater(inl, 0)


class TestBuildGeometricMatches(unittest.TestCase):

    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.vdb = VDB(db_path=self.db_path)

    def tearDown(self):
        self.vdb = None
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def test_recovers_match_ignoring_low_cosine(self):
        """コサインが低くても幾何検証で真の一致フレームを回復する"""
        # クエリ3フレーム、DB4フレーム。q_i は db_i と同一記述子（真の一致）だが
        # コサイン類似度行列は敢えて低め＆別フレームを僅差で上位に置く。
        q_frames = {}
        db_frames = {}
        for i in range(4):
            desc, kpts = _make_frame(n=70, seed=100 + i)
            db_frames[i] = (kpts, desc.astype(np.float32))
        for i in range(3):
            # クエリ i は DB i と同一
            db_kpts, db_desc = db_frames[i]
            q_frames[i] = (db_kpts.copy(), db_desc.copy())

        query_frame_fps = [(i, float(i), np.zeros(4, np.float32))
                           for i in range(3)]
        db_frame_vecs = [(i, float(100 + i), np.zeros(4, np.float32))
                         for i in range(4)]
        db_ts_arr = np.array([100.0, 101.0, 102.0, 103.0])

        # コサインは全体的に低く（0.2〜0.35）、真の一致(対角)を最上位にはしない
        sims = np.array([
            [0.30, 0.28, 0.25, 0.22],
            [0.26, 0.31, 0.27, 0.24],
            [0.23, 0.25, 0.33, 0.29],
        ], dtype=np.float32)

        frame_matches, geom_scores = self.vdb._build_geometric_matches(
            query_frame_fps, db_frame_vecs, db_ts_arr, sims,
            q_frames, db_frames,
        )

        # 3フレームとも幾何検証で一致が回復する
        self.assertEqual(len(geom_scores), 3)
        for score in geom_scores:
            self.assertGreater(score, 0.0)
        # 各クエリの最良一致DB時刻が対角（真の一致）になっている
        self.assertAlmostEqual(frame_matches[0]["db_ts"], 100.0)
        self.assertAlmostEqual(frame_matches[1]["db_ts"], 101.0)
        self.assertAlmostEqual(frame_matches[2]["db_ts"], 102.0)

    def test_no_match_when_all_unrelated(self):
        """全て無関係なら幾何検証で一致は得られない"""
        q_frames = {}
        db_frames = {}
        for i in range(3):
            desc, kpts = _make_frame(n=70, seed=200 + i)
            db_frames[i] = (kpts, desc.astype(np.float32))
        for i in range(3):
            desc, kpts = _make_frame(n=70, seed=300 + i)
            q_frames[i] = (kpts, desc.astype(np.float32))

        query_frame_fps = [(i, float(i), np.zeros(4, np.float32))
                           for i in range(3)]
        db_frame_vecs = [(i, float(100 + i), np.zeros(4, np.float32))
                         for i in range(3)]
        db_ts_arr = np.array([100.0, 101.0, 102.0])
        sims = np.full((3, 3), 0.3, dtype=np.float32)

        _fm, geom_scores = self.vdb._build_geometric_matches(
            query_frame_fps, db_frame_vecs, db_ts_arr, sims,
            q_frames, db_frames,
        )
        self.assertEqual(geom_scores, [])


if __name__ == "__main__":
    unittest.main()
