"""
映像クエリ経路の改善（キーフレーム 5 秒上限・格子順・止まっている点の除去・
新 PiP 検出・4:3 両方検索と枠 30）の回帰テスト
"""

import logging
import os
import tempfile
import types
import unittest
from unittest import mock

import cv2
import numpy as np
from mimizam.src import pip_detector
from mimizam.src.video_fingerprinter import (
    FrameSelector,
    VideoFingerprint,
    VideoFingerprintConfig,
    grid_keypoint_order,
    static_point_masks,
)

from mimizam import Mimizam


def _frames_with_static(n_frames, n_static, n_moving, seed=0):
    """各フレームに、同じ位置・同じ記述子の点 n_static 個と、毎回違う点 n_moving 個を置く"""
    rng = np.random.default_rng(seed)
    s_xy = rng.uniform(0, 1000, (n_static, 2)).astype(np.float32)
    s_desc = rng.integers(0, 256, (n_static, 61), dtype=np.uint8)
    frames = []
    for _ in range(n_frames):
        m_xy = rng.uniform(0, 1000, (n_moving, 2)).astype(np.float32)
        m_desc = rng.integers(0, 256, (n_moving, 61), dtype=np.uint8)
        frames.append((
            np.vstack([s_desc, m_desc]), np.vstack([s_xy, m_xy]),
        ))
    return frames


class TestStaticPointMasks(unittest.TestCase):

    def test_marks_only_points_static_across_frames(self):
        masks = static_point_masks(_frames_with_static(6, 30, 40))
        for m in masks:
            self.assertTrue(m[:30].all())
            self.assertFalse(m[30:].any())

    def test_keeps_frame_when_too_few_points_remain(self):
        # 動く点が 20 点未満しか残らないフレームでは何も除かない
        masks = static_point_masks(_frames_with_static(6, 30, 10))
        for m in masks:
            self.assertFalse(m.any())

    def test_no_removal_with_few_keyframes(self):
        masks = static_point_masks(_frames_with_static(3, 30, 40))
        for m in masks:
            self.assertFalse(m.any())


class TestGridKeypointOrder(unittest.TestCase):

    def test_takes_best_point_of_every_cell_first(self):
        # 左上のマスに response の高い点が多くても、先頭 4 点は 4 マスから 1 点ずつ
        coords = np.array([
            [1, 1], [2, 2], [3, 3], [4, 4],
            [99, 1], [1, 99], [99, 99],
        ], dtype=np.float32)
        resp = np.array([9, 8, 7, 6, 1, 2, 3], dtype=np.float32)
        order = grid_keypoint_order(coords, resp, 2)
        self.assertEqual(sorted(order.tolist()), list(range(7)))
        self.assertEqual(set(order[:4].tolist()), {0, 4, 5, 6})
        self.assertEqual(order[0], 0)
        self.assertEqual(order[4], 1)


class TestKeyframeMaxInterval(unittest.TestCase):

    def _static_video(self, path, seconds=20, fps=10):
        rng = np.random.default_rng(0)
        img = rng.integers(0, 256, (120, 160, 3), dtype=np.uint8)
        wr = cv2.VideoWriter(
            path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (160, 120)
        )
        for _ in range(seconds * fps):
            wr.write(img)
        wr.release()

    def test_static_scene_is_sampled_every_max_interval(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "static.mp4")
            self._static_video(path)
            ts = [t for _, t, _ in FrameSelector(
                VideoFingerprintConfig()).select_keyframes(path)]
            cfg = VideoFingerprintConfig()
            cfg.max_keyframe_interval = 0.0
            ts_off = [t for _, t, _ in FrameSelector(cfg).select_keyframes(path)]
        self.assertGreaterEqual(len(ts), 4)
        self.assertLessEqual(max(np.diff(ts)), 5.0 + 1e-6)
        self.assertLess(len(ts_off), len(ts))


class TestEdgeCorrPipDetection(unittest.TestCase):

    def test_detects_inner_moving_rectangle(self):
        rng = np.random.default_rng(1)
        bg = cv2.GaussianBlur(
            rng.integers(0, 256, (270, 480, 3), dtype=np.uint8), (5, 5), 0
        )
        x, y, w, h = 200, 80, 192, 108
        frames = []
        for _ in range(30):
            f = bg.copy()
            f[y:y + h, x:x + w] = cv2.GaussianBlur(
                rng.integers(0, 256, (h, w, 3), dtype=np.uint8), (5, 5), 0
            )
            frames.append(f)
        regs = pip_detector.detect_pip_regions(frames)
        self.assertTrue(regs)
        r = regs[0]
        self.assertGreaterEqual(r.pip_score, pip_detector.DEFAULT_PIP_SCORE_THRESHOLD)
        for got, exp in ((r.x, x), (r.y, y), (r.x + r.w, x + w), (r.y + r.h, y + h)):
            self.assertLessEqual(abs(got - exp), 4)

    def test_static_video_has_no_region(self):
        img = np.random.default_rng(2).integers(0, 256, (270, 480, 3), dtype=np.uint8)
        self.assertEqual(pip_detector.detect_pip_regions([img] * 30), [])


class TestNarrowQuerySearch(unittest.TestCase):

    def _run(self, narrow):
        m = Mimizam.__new__(Mimizam)
        m.logger = logging.getLogger("test_narrow")
        fp = VideoFingerprint(
            frame_fingerprints=[(0, 0.0, object())], raw_descriptors=[],
        )
        st = VideoFingerprint(
            frame_fingerprints=[(0, 0.0, object())], raw_descriptors=[],
        ) if narrow else None
        vfp = mock.MagicMock()
        vfp.is_trained = True
        vfp.config = types.SimpleNamespace(store_raw_descriptors=False)
        vfp.fingerprint_query_video.return_value = (fp, st, narrow)
        vdb = mock.MagicMock()
        vdb._geom_top_k_narrow = 30
        m._get_video_fingerprinter = lambda: vfp
        m._get_video_db = lambda _p=None: vdb
        m._match_and_rank = mock.MagicMock(side_effect=[
            [{"video_id": "a", "similarity": 0.3}],
            [{"video_id": "a", "similarity": 0.6},
             {"video_id": "b", "similarity": 0.2}],
        ])
        with mock.patch("os.path.exists", return_value=True):
            res = m.search_video("q.mp4", top_k=5, detect_pip=False)
        return m, res

    def test_narrow_query_searches_both_with_wider_geometric_window(self):
        m, res = self._run(True)
        self.assertEqual(m._match_and_rank.call_count, 2)
        for c in m._match_and_rank.call_args_list:
            self.assertEqual(c.kwargs["geom_top_k"], 30)
        self.assertEqual([r["video_id"] for r in res], ["a", "b"])
        self.assertAlmostEqual(res[0]["similarity"], 0.6)

    def test_wide_query_searches_once_with_default_window(self):
        m, res = self._run(False)
        m._match_and_rank.assert_called_once()
        self.assertIsNone(m._match_and_rank.call_args.kwargs["geom_top_k"])
        self.assertEqual([r["video_id"] for r in res], ["a"])


if __name__ == "__main__":
    unittest.main()
