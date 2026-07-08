"""PiP経路の幾何検証・実効スコア統合・矩形数上限の回帰テスト

PiP矩形経路が通常経路と同じ照合（ANN絞り込み→フレーム単位の幾何検証→実効
スコア化）を通ること、統合が実効スコア基準であること、矩形が pip_score 上位
に絞られることを検証する。過去に PiP 経路が ANN 生類似度のみで照合し、真の
フレーム一致より上位に来て順位を歪めていた不具合の再発を防ぐ。
"""

import logging
import types
import unittest
from unittest import mock

from mimizam import Mimizam, VideoFingerprinter, VideoFingerprint, PipRegion


def _make_mimizam():
    """DB初期化を伴わない軽量な Mimizam インスタンスを作る"""
    m = Mimizam.__new__(Mimizam)
    m.logger = logging.getLogger("test_pip")
    return m


class TestMatchAndRank(unittest.TestCase):
    """共通ヘルパー _match_and_rank がフレーム単位の幾何検証を通すこと"""

    def test_invokes_frame_matching_with_raw_descriptors(self):
        m = _make_mimizam()
        vdb = mock.MagicMock()
        vdb.search_frame_candidates.return_value = [
            {"video_id": "v1", "votes": 8, "similarity": 0.6, "video": None},
        ]
        vdb.search_video_with_frame_matching.return_value = [
            {
                "video_id": "v1",
                "frame_similarity": 0.9,
                "match_details": {
                    "total_frames": 10, "coverage": 0.8,
                    "regions": [{"frame_count": 8}],
                },
            },
        ]
        raw = [(0, 0.0, object())]

        results = m._match_and_rank(vdb, [(0, 0.0, object())], raw, top_k=5)

        # ANNのみでなくフレーム単位マッチング（幾何検証）を必ず呼ぶ
        vdb.search_video_with_frame_matching.assert_called_once()
        _args, kwargs = vdb.search_video_with_frame_matching.call_args
        self.assertIs(kwargs["query_raw"], raw)

        self.assertEqual(len(results), 1)
        entry = results[0]
        self.assertEqual(entry["video_id"], "v1")
        self.assertIn("match_details", entry)
        # 実効スコアは frame_similarity を被覆率・得票率で減衰させた値
        self.assertLess(entry["similarity"], entry["frame_similarity"])
        self.assertGreater(entry["similarity"], 0.0)

    def test_no_candidates_returns_empty(self):
        m = _make_mimizam()
        vdb = mock.MagicMock()
        vdb.search_frame_candidates.return_value = []
        results = m._match_and_rank(vdb, [(0, 0.0, object())], None, top_k=5)
        self.assertEqual(results, [])
        vdb.search_video_with_frame_matching.assert_not_called()


class TestSearchPipRegions(unittest.TestCase):
    """_search_pip_regions が共通ヘルパー経由で照合し矩形情報を付すこと"""

    def test_uses_match_and_rank_and_tags_region(self):
        m = _make_mimizam()
        m._match_and_rank = mock.MagicMock(
            return_value=[{"video_id": "v1", "similarity": 0.7}]
        )

        region = PipRegion(
            x=10, y=20, w=100, h=50, area_ratio=0.1, pip_score=3.5,
        )
        fp = VideoFingerprint(
            frame_fingerprints=[(0, 0.0, object())],
            raw_descriptors=[(0, 0.0, object())],
        )

        vfp = mock.MagicMock()
        vfp.config = types.SimpleNamespace(store_raw_descriptors=False)
        seen = {}

        def _fp_regions(_path):
            # 指紋生成時は幾何検証用に生記述子保持が有効化されていること
            seen["store_raw"] = vfp.config.store_raw_descriptors
            return [(region, fp)]

        vfp.fingerprint_pip_regions.side_effect = _fp_regions
        vdb = mock.MagicMock()

        results = m._search_pip_regions("q.mp4", vfp, vdb, top_k=5)

        self.assertTrue(seen["store_raw"])
        # 呼び出し後は元の設定に戻す
        self.assertFalse(vfp.config.store_raw_descriptors)

        m._match_and_rank.assert_called_once_with(
            vdb, fp.frame_fingerprints, fp.raw_descriptors, 5,
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["pip_region"]["pip_score"], 3.5)
        self.assertEqual(results[0]["pip_region"]["x"], 10)


class TestMergePipResults(unittest.TestCase):
    """統合が実効スコア基準で行われ、PiP勝者は矩形情報を保持すること"""

    def test_pip_wins_by_effective_score_keeps_region(self):
        base = [{"video_id": "v1", "similarity": 0.3, "match_details": {}}]
        pip = [{
            "video_id": "v1", "similarity": 0.8, "match_details": {},
            "pip_region": {"x": 1, "y": 2, "w": 3, "h": 4, "pip_score": 2.0},
        }]
        merged = Mimizam._merge_pip_results(base, pip, top_k=5)
        self.assertEqual(len(merged), 1)
        self.assertAlmostEqual(merged[0]["similarity"], 0.8)
        self.assertIn("pip_region", merged[0])

    def test_base_wins_no_region(self):
        base = [{"video_id": "v1", "similarity": 0.9, "match_details": {}}]
        pip = [{
            "video_id": "v1", "similarity": 0.4,
            "pip_region": {"x": 1, "y": 2, "w": 3, "h": 4, "pip_score": 2.0},
        }]
        merged = Mimizam._merge_pip_results(base, pip, top_k=5)
        self.assertEqual(len(merged), 1)
        self.assertAlmostEqual(merged[0]["similarity"], 0.9)
        self.assertNotIn("pip_region", merged[0])

    def test_new_pip_only_video_appended(self):
        base = [{"video_id": "v1", "similarity": 0.5}]
        pip = [{
            "video_id": "v2", "similarity": 0.6,
            "pip_region": {"x": 0, "y": 0, "w": 1, "h": 1, "pip_score": 1.0},
        }]
        merged = Mimizam._merge_pip_results(base, pip, top_k=5)
        ids = {r["video_id"] for r in merged}
        self.assertEqual(ids, {"v1", "v2"})
        self.assertEqual(merged[0]["video_id"], "v2")


class TestLimitPipRegions(unittest.TestCase):
    """矩形が pip_score 上位に絞られること"""

    def _region(self, score):
        return PipRegion(
            x=0, y=0, w=10, h=10, area_ratio=0.1, pip_score=score,
        )

    def test_caps_to_top_three_by_score(self):
        regions = [self._region(s) for s in (0.5, 3.0, 1.0, 2.5, 0.9)]
        limited = VideoFingerprinter._limit_pip_regions(regions, 3)
        self.assertEqual(len(limited), 3)
        self.assertEqual(
            [r.pip_score for r in limited], [3.0, 2.5, 1.0],
        )

    def test_zero_means_unlimited(self):
        regions = [self._region(s) for s in (0.5, 3.0, 1.0)]
        limited = VideoFingerprinter._limit_pip_regions(regions, 0)
        self.assertEqual(len(limited), 3)


if __name__ == "__main__":
    unittest.main()
