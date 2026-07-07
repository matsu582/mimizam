"""
幾何検証済みマッチのDB時刻クラスタによる一致区間算出の回帰テスト

支配整列（単一の時間オフセット直線）とは別方式。RANSACで各フレームが同一画と
保証されている前提で、一致先のDB時刻が集中する塊を一致区間とする。OPは似たカットが
多くクエリ各フレームが同一OP内の別カットに一致するため時間オフセットは一定にならないが、
DB時刻はOP区間に集中するので塊として拾える、という観点を検証する。
"""

import unittest

from mimizam.src.video_database import VideoFingerprintDatabase as VDB


def _fm(query_ts, candidates):
    return {"query_ts": float(query_ts),
            "candidates": [(float(d), float(s)) for d, s in candidates]}


class TestGeometricRegions(unittest.TestCase):

    def test_op_block_with_varying_offsets_is_one_region(self):
        """時間オフセットがフレーム毎にバラつくOP塊を1区間に束ねる

        db時刻はOP区間(340〜427)に集中するが、query→dbのオフセットは
        167〜371までバラバラ（単一直線には乗らない）。DB時刻クラスタなら1区間。
        """
        # (query_ts, db_ts) いずれも幾何検証済み(score>=0.5)を想定
        pairs = [
            (173, 340), (174, 341), (178, 345), (179, 346),  # offset ~167
            (166, 382), (167, 383), (168, 384),              # offset ~216
            (74, 386), (143, 392), (145, 394),               # offset ~250-312
            (136, 401), (32, 403),                            # offset ~265-371
            (80, 419), (81, 420), (82, 421), (83, 422),       # offset ~339
            (121, 426), (123, 427),                           # offset ~304
        ]
        matches = [_fm(q, [(d, 0.8)]) for q, d in pairs]
        md = VDB._compute_geometric_regions(
            matches, min_region_frames=3, db_gap_merge=45.0,
            query_duration=190.0,
        )
        self.assertEqual(len(md["regions"]), 1)
        r = md["regions"][0]
        self.assertAlmostEqual(r["db_start"], 340.0, delta=1.0)
        self.assertAlmostEqual(r["db_end"], 427.0, delta=1.0)
        # 全18フレームが一致に採用される（相異なるquery）
        self.assertEqual(md["matched_frames"], len(pairs))

    def test_separate_db_clusters_are_distinct_regions(self):
        """DB時刻が離れた別クラスタ（OP と ED 等）は別区間になる"""
        op = [(173, 340), (174, 341), (178, 345), (179, 346),
              (80, 419), (81, 420), (166, 382), (167, 383)]
        ed = [(38, 1002), (39, 1006), (40, 1007)]
        matches = [_fm(q, [(d, 0.8)]) for q, d in op + ed]
        md = VDB._compute_geometric_regions(
            matches, min_region_frames=3, db_gap_merge=45.0,
            query_duration=190.0,
        )
        self.assertEqual(len(md["regions"]), 2)
        db_starts = sorted(r["db_start"] for r in md["regions"])
        self.assertAlmostEqual(db_starts[0], 340.0, delta=1.0)
        self.assertAlmostEqual(db_starts[1], 1002.0, delta=1.0)

    def test_small_cluster_below_min_is_dropped(self):
        """min_region_frames 未満の孤立クラスタは偶発一致として除外する"""
        op = [(173, 340), (174, 341), (178, 345), (179, 346)]
        lone = [(126, 246)]  # 1フレームだけの孤立クラスタ
        matches = [_fm(q, [(d, 0.8)]) for q, d in op + lone]
        md = VDB._compute_geometric_regions(
            matches, min_region_frames=3, db_gap_merge=45.0,
            query_duration=190.0,
        )
        self.assertEqual(len(md["regions"]), 1)
        self.assertAlmostEqual(md["regions"][0]["db_start"], 340.0, delta=1.0)
        # 246 の孤立フレームは採用されない
        for r in md["regions"]:
            self.assertGreater(r["db_start"], 300.0)

    def test_duplicate_query_counted_once_per_cluster(self):
        """同一クエリフレームが複数DB候補を持っても区間内で1回だけ数える"""
        # q173 は db340 と db345 の両方に幾何一致（同一OP内の別カット）
        matches = [
            _fm(173, [(340, 0.8), (345, 0.7)]),
            _fm(174, [(341, 0.8)]),
            _fm(178, [(346, 0.8)]),
            _fm(179, [(347, 0.8)]),
        ]
        md = VDB._compute_geometric_regions(
            matches, min_region_frames=3, db_gap_merge=45.0,
            query_duration=190.0,
        )
        self.assertEqual(len(md["regions"]), 1)
        # 相異なるqは4件（q173の2候補は1件に数える）
        self.assertEqual(md["regions"][0]["frame_count"], 4)
        self.assertEqual(md["matched_frames"], 4)

    def test_coverage_is_union_of_query_spans(self):
        """被覆率は各区間のクエリ時間スパンの和集合/クエリ長で算出する"""
        # 1塊: query 20〜60s → db 400〜410（連続）。query長100s。
        pairs = [(q, 400 + (q - 20) * 0.2) for q in range(20, 61, 5)]
        matches = [_fm(q, [(d, 0.8)]) for q, d in pairs]
        md = VDB._compute_geometric_regions(
            matches, min_region_frames=3, db_gap_merge=45.0,
            query_duration=100.0,
        )
        self.assertEqual(len(md["regions"]), 1)
        # スパン 40s / クエリ 100s = 0.4 付近
        self.assertAlmostEqual(md["coverage"], 0.4, delta=0.05)

    def test_no_candidates_returns_empty(self):
        """幾何一致候補が無ければ区間なし"""
        matches = [_fm(q, []) for q in range(0, 30, 5)]
        md = VDB._compute_geometric_regions(
            matches, min_region_frames=3, db_gap_merge=45.0,
            query_duration=100.0,
        )
        self.assertEqual(md["regions"], [])
        self.assertEqual(md["matched_frames"], 0)


class TestSubsampleIndices(unittest.TestCase):
    """幾何検証するクエリフレームの均等間引きの回帰テスト"""

    def test_returns_all_when_below_cap(self):
        """要素数がcap以下なら全件そのまま返す"""
        self.assertEqual(VDB._subsample_indices(5, 48), [0, 1, 2, 3, 4])

    def test_disabled_when_cap_non_positive(self):
        """cap<=0 は間引き無効（全件）"""
        self.assertEqual(VDB._subsample_indices(4, 0), [0, 1, 2, 3])

    def test_caps_count_and_keeps_endpoints(self):
        """capを超えたら件数を頭打ちにし、両端を必ず含み昇順・重複なし"""
        idx = VDB._subsample_indices(224, 48)
        self.assertLessEqual(len(idx), 48)
        self.assertEqual(idx[0], 0)
        self.assertEqual(idx[-1], 223)
        self.assertEqual(idx, sorted(set(idx)))

    def test_indices_in_range(self):
        """返るインデックスは全て 0..n-1 の範囲内"""
        idx = VDB._subsample_indices(87, 48)
        self.assertTrue(all(0 <= i < 87 for i in idx))


if __name__ == "__main__":
    unittest.main()
