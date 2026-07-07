"""
映像フレームマッチの支配オフセット整列（頑健直線フィット）の回帰テスト

従来のオフセット貪欲クラスタリングは、真に連続する一致でも僅かな速度差や
タイムスタンプ量子化でオフセットがドリフトすると別区間に割れ、別箇所の偶発
一致も被覆率へ混ざっていた。ここでは支配直線 db≈slope·query+offset を頑健推定
し、その直線に整合するインライアだけを一致とみなすことを検証する。
"""

import unittest

from mimizam.src.video_database import VideoFingerprintDatabase as VDB


def _fm(query_ts, db_ts, similarity=0.5):
    return {"query_ts": float(query_ts), "db_ts": float(db_ts),
            "similarity": float(similarity)}


class TestDominantAlignment(unittest.TestCase):

    def test_drifting_offset_merges_into_one_region(self):
        """僅かにオフセットがドリフトする連続一致は1本の支配整列に統合する"""
        # slope≈1 で offset が 394〜398 に揺れる連続一致（従来は複数区間に割れた）
        offsets = [396, 394, 398, 395, 397, 396, 394, 398, 395, 396]
        matches = [
            _fm(q, q + off, 0.5)
            for q, off in zip(range(26, 26 + 8 * 10, 8), offsets)
        ]
        md = VDB._compute_match_regions(matches, threshold=0.4,
                                        query_duration=200.0)
        self.assertEqual(md["aligned_frames"], 10)
        # ドリフトが残差許容内なので1区間に統合される
        self.assertEqual(len(md["regions"]), 1)
        self.assertAlmostEqual(md["time_scale"], 1.0, delta=0.05)

    def test_scattered_coincidental_matches_excluded(self):
        """別箇所の偶発一致（支配直線外れ値）はインライアから除外する"""
        matches = [_fm(q, q + 396, 0.5) for q in range(26, 26 + 8 * 8, 8)]
        # 全く別のDB時刻に偶発一致する2フレーム（18:59, 23:57相当）
        matches.append(_fm(38, 1139, 0.46))
        matches.append(_fm(54, 1437, 0.42))
        md = VDB._compute_match_regions(matches, threshold=0.4,
                                        query_duration=200.0)
        # 8件の連続一致のみインライア、偶発2件は除外
        self.assertEqual(md["aligned_frames"], 8)
        for r in md["regions"]:
            self.assertLess(r["db_start"], 1000.0)

    def test_speed_change_slope_estimated(self):
        """速度変化（slope≠1）でも傾きを推定して全件を整列とみなす"""
        matches = [_fm(q, 1.2 * q + 100.0, 0.5)
                   for q in range(10, 10 + 6 * 10, 6)]
        md = VDB._compute_match_regions(matches, threshold=0.4,
                                        query_duration=120.0)
        self.assertEqual(md["aligned_frames"], len(matches))
        self.assertAlmostEqual(md["time_scale"], 1.2, delta=0.06)

    def test_no_consistent_alignment_returns_empty(self):
        """時間的に一貫しない散乱一致は支配整列を持たず区間なし"""
        matches = [
            _fm(10, 500, 0.5), _fm(20, 50, 0.5), _fm(30, 900, 0.5),
            _fm(40, 200, 0.5), _fm(50, 1300, 0.5),
        ]
        md = VDB._compute_match_regions(matches, threshold=0.4,
                                        query_duration=120.0)
        self.assertEqual(md["regions"], [])
        self.assertEqual(md["aligned_frames"], 0)

    def test_secondary_candidate_on_line_is_recovered(self):
        """最類似候補が直線外でも、整列側の次点候補があれば取りこぼさない"""
        # 支配整列 offset=300。半数のフレームは「別箇所の偶発一致(sim0.55)」が
        # 最類似だが、整列側(sim0.50)を次点候補として持つ。
        matches = []
        for i, q in enumerate(range(0, 60, 6)):
            aligned = (q + 300.0, 0.50)
            if i % 2 == 0:
                # 最類似は別箇所の偶発一致、整列側は次点
                spurious = (900.0 + i, 0.55)
                cands = [spurious, aligned]
            else:
                cands = [aligned]
            matches.append({"query_ts": float(q), "candidates": cands})
        md = VDB._compute_match_regions(matches, threshold=0.4,
                                        query_duration=100.0)
        # 全10フレームが整列側候補で支配直線に乗る
        self.assertEqual(md["aligned_frames"], 10)
        self.assertAlmostEqual(md["time_offset"], 300.0, delta=3.0)
        # 偶発一致(900s台)はインライアに採用されない
        for r in md["regions"]:
            self.assertLess(r["db_end"], 400.0)

    def test_multiple_offset_segments_all_recovered(self):
        """同一傾きで別オフセットの複数共通区間（OP/ED等）を全て整列に採る"""
        # OP: query 0〜54s が db 300+（offset300）、ED: query 120〜174s が
        # db 900+（offset780）。傾きは共通(≈1)だがオフセットが異なる2列。
        matches = []
        for q in range(0, 55, 6):          # 10フレーム（OP）
            matches.append(_fm(q, q + 300, 0.6))
        for q in range(120, 175, 6):        # 10フレーム（ED）
            matches.append(_fm(q, q + 780, 0.6))
        md = VDB._compute_match_regions(matches, threshold=0.4,
                                        query_duration=200.0)
        # 両区間の全20フレームが整列に採用される
        self.assertEqual(md["aligned_frames"], 20)
        # 別オフセットなので2区間に分かれる
        self.assertEqual(len(md["regions"]), 2)
        self.assertAlmostEqual(md["time_scale"], 1.0, delta=0.05)
        # 被覆はクエリ時間軸の和集合（54+54=108s / 200s ≈ 0.54）
        self.assertAlmostEqual(md["coverage"], 108.0 / 200.0, delta=0.05)

    def test_coverage_reflects_continuous_span(self):
        """被覆率は連続一致のクエリ時間スパン/クエリ長で算出する"""
        # クエリ 0〜100s のうち 0〜60s を連続一致（slope1, offset300）
        matches = [_fm(q, q + 300, 0.6) for q in range(0, 61, 6)]
        md = VDB._compute_match_regions(matches, threshold=0.4,
                                        query_duration=100.0)
        # 連続スパン60s / クエリ100s = 0.6 付近
        self.assertAlmostEqual(md["coverage"], 0.6, delta=0.05)
        self.assertGreater(md["median_similarity"], 0.5)


if __name__ == "__main__":
    unittest.main()
