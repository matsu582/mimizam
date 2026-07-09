"""
静かに劣化する不具合（①〜⑤）に対する回帰テスト

devブランチのレビューで検出された「例外を出さずに精度・速度を劣化させる不具合」を
再発防止するためのテスト群。各テストはバグ版で失敗し、修正版で通ることを意図している。

- ① クエリ側ハッシュ多重度の保持（dict化で潰さない）
- ② freq_scale（ピッチ変化）の実ハッシュ再計算
- ③ スケール探索でのDB問い合わせ回数の上限
- ⑤ alignment_ratio が符号を区別する
"""

import os
import tempfile
import unittest
from unittest.mock import Mock

import numpy as np

from mimizam import (
    FingerprintDatabase, FingerprintMatcher, Fingerprint, Song,
    HashGenerator, create_sqlite_config,
)
from mimizam.src.audio_fingerprinter import Peak
from mimizam.src.database_base import group_query_times


class TestQueryHashMultiplicity(unittest.TestCase):
    """① 同一ハッシュが複数のquery_timeに現れる多重度を保持する"""

    def test_group_query_times_preserves_duplicates(self):
        """group_query_times は同一ハッシュの全query_timeをリストで保持する"""
        fps = [
            Fingerprint(hash_value=100, time_offset=1.0, song_id=""),
            Fingerprint(hash_value=100, time_offset=2.0, song_id=""),
            Fingerprint(hash_value=200, time_offset=3.0, song_id=""),
        ]
        grouped = group_query_times(fps)
        self.assertEqual(sorted(grouped[100]), [1.0, 2.0])
        self.assertEqual(grouped[200], [3.0])

    def test_search_preserves_query_time_multiplicity(self):
        """同一ハッシュを複数query_timeで問い合わせても全ペアが返る（dict潰しの回帰）"""
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        tmp.close()
        try:
            db = FingerprintDatabase(create_sqlite_config(tmp.name))
            db.add_song(Song(id="s1", title="t", artist="a", file_path="/x.wav"))
            # DB側は hash=100 を1件だけ保持
            db.add_fingerprints("s1", [
                Fingerprint(hash_value=100, time_offset=5.0, song_id="s1"),
            ])
            # クエリ側は同一 hash=100 を2つの異なる query_time で持つ
            query = [
                Fingerprint(hash_value=100, time_offset=1.0, song_id=""),
                Fingerprint(hash_value=100, time_offset=2.0, song_id=""),
            ]
            matches = db.search_fingerprints(query)
            # 多重度が保持されれば2ペア。dict潰しだと最後の1件のみで1ペアになる。
            self.assertIn("s1", matches)
            self.assertEqual(len(matches["s1"]), 2)
            self.assertEqual(sorted(q for q, _ in matches["s1"]), [1.0, 2.0])
            self.assertTrue(all(db_t == 5.0 for _, db_t in matches["s1"]))
            db.disconnect()
        finally:
            if os.path.exists(tmp.name):
                os.unlink(tmp.name)


class TestBatchSongRetrieval(unittest.TestCase):
    """④ 楽曲メタ情報の真の一括取得（get_songs）"""

    def test_get_songs_single_query_via_backend(self):
        """FingerprintDatabase.get_songs はバックエンドの get_songs へ1回で委譲する"""
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        tmp.close()
        try:
            db = FingerprintDatabase(create_sqlite_config(tmp.name))
            for i in range(3):
                db.add_song(Song(id=f"s{i}", title=f"t{i}", artist="a",
                                 file_path=f"/x{i}.wav"))
            got = db.get_songs(["s0", "s1", "s2", "missing", "s1"])
            self.assertEqual(got["s0"].title, "t0")
            self.assertEqual(got["s2"].title, "t2")
            self.assertIsNone(got["missing"])
            # 重複IDは1エントリに集約
            self.assertEqual(len(got), 4)
            db.disconnect()
        finally:
            if os.path.exists(tmp.name):
                os.unlink(tmp.name)

    def test_get_songs_batch_delegates_not_per_id(self):
        """_get_songs_batch は get_songs を1回呼び、get_song を件数分呼ばない"""
        mock_db = Mock()
        mock_db.get_songs.return_value = {"s0": None, "s1": None}
        matcher = FingerprintMatcher(mock_db)
        matcher._get_songs_batch(["s0", "s1", "s0"])
        mock_db.get_songs.assert_called_once()
        mock_db.get_song.assert_not_called()


class TestDetailedMatchInfoNoResearch(unittest.TestCase):
    """③④ detailed_match_info は取得済み match_pairs からDB再検索なしで構築する"""

    def test_match_pairs_skips_search(self):
        mock_db = Mock()
        matcher = FingerprintMatcher(mock_db)
        pairs = [(1.0, 10.0), (2.0, 11.0), (3.0, 12.0)]
        info = matcher.detailed_match_info(pairs)
        # 再検索(search_fingerprints)は呼ばれない
        mock_db.search_fingerprints.assert_not_called()
        self.assertEqual(info['statistics']['total_matches'], 3)

    def test_detailed_info_handles_time_scale(self):
        """速度変化一致（time_scale≠1）で整列とオフセットを誤らない

        query_time - db_time が一定という前提のままだと、db≈s·query の速度変化一致で
        差分が一定にならず aligned_matches が崩れる。傾きで正規化した残差
        query - db/s で集計するため、time_scale未指定でも自動推定して正しく整列する。
        """
        mock_db = Mock()
        matcher = FingerprintMatcher(mock_db)
        # 傾き1.2・オフセット0.5の完全一致ペア10件
        pairs = [(float(q), 1.2 * q + 0.5) for q in range(1, 11)]
        # 自動推定（time_scale未指定）でも全件整列する
        auto = matcher.detailed_match_info(pairs)
        self.assertEqual(auto['statistics']['aligned_matches'], 10)
        # 明示指定でも同じ
        given = matcher.detailed_match_info(pairs, time_scale=1.2)
        self.assertEqual(given['statistics']['aligned_matches'], 10)
        # 後方互換: 恒等倍率(time_scale=1.0)では従来どおり query-db を用いる
        idp = [(1.0, 1.5), (2.0, 2.5), (3.0, 3.5)]
        self.assertAlmostEqual(
            matcher._calculate_time_offset(idp, 1.0), -0.5, places=6
        )


class TestErrorVsNoMatch(unittest.TestCase):
    """② 高レベルAPIは「一致なし」と「処理失敗」を区別する"""

    def _make_mimizam(self):
        from mimizam import create_mimizam_sqlite
        return create_mimizam_sqlite(':memory:')

    def test_add_song_missing_file_raises(self):
        m = self._make_mimizam()
        try:
            with self.assertRaises(FileNotFoundError):
                m.add_song(file_path="/no/such/file.wav", title="t", artist="a")
        finally:
            m.close()

    def test_add_song_wraps_processing_failure(self):
        """指紋生成が空を返すと処理失敗として例外を送出（Noneに潰さない）"""
        from mimizam import create_mimizam_sqlite
        from mimizam.src.exceptions import AudioProcessingError
        m = create_mimizam_sqlite(':memory:')
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.wav')
        tmp.write(b'not audio')
        tmp.close()
        try:
            m.fingerprinter.fingerprint_file = Mock(return_value=[])
            with self.assertRaises(AudioProcessingError):
                m.add_song(file_path=tmp.name, title="t", artist="a")
        finally:
            m.close()
            if os.path.exists(tmp.name):
                os.unlink(tmp.name)

    def test_search_song_empty_fingerprints_raises_not_empty_list(self):
        """クエリ指紋が空のとき、[]（一致なし）ではなく処理失敗例外を送出する"""
        from mimizam import create_mimizam_sqlite
        from mimizam.src.exceptions import AudioProcessingError
        m = create_mimizam_sqlite(':memory:')
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.wav')
        tmp.write(b'not audio')
        tmp.close()
        try:
            m.fingerprinter.fingerprint_file = Mock(return_value=[])
            with self.assertRaises(AudioProcessingError):
                m.search_song(query_file_path=tmp.name)
        finally:
            m.close()
            if os.path.exists(tmp.name):
                os.unlink(tmp.name)


class TestScaleInvariantHash(unittest.TestCase):
    """② 尺度不変ハッシュ：ピッチ変化・速度変化でハッシュが不変になる

    旧方式（探索時に freq_scale でハッシュを再計算する brute-force）は完全置換され、
    ハッシュ自体が「三つ組の時間比・周波数比」で構成され尺度不変になった。よって
    「変換時に再計算する」のではなく「変換しても同じハッシュが出る」ことを検証する。
    """

    @staticmethod
    def _peak(t, f, a=1.0):
        return Peak(time=np.float64(t), frequency=np.float64(f), amplitude=np.float64(a))

    def test_pitch_shift_preserves_hash(self):
        """全周波数を定数倍（ピッチシフト）してもハッシュ集合が不変"""
        hg = HashGenerator()
        anchor = self._peak(1.0, 200.0)
        t1 = self._peak(1.5, 400.0)
        t2 = self._peak(2.5, 300.0)
        base = set(hg._create_triplet_hashes(anchor, t1, t2))
        p = 2 ** (3 / 12.0)  # 3半音上げ
        shifted = set(hg._create_triplet_hashes(
            self._peak(1.0, 200.0 * p),
            self._peak(1.5, 400.0 * p),
            self._peak(2.5, 300.0 * p),
        ))
        # 周波数比 log2(f/fa) は定数倍で不変 → 共通ハッシュが存在する
        self.assertTrue(base & shifted)

    def test_speed_change_preserves_hash(self):
        """全時刻を定数倍（速度変化）してもハッシュ集合が不変"""
        hg = HashGenerator()
        anchor = self._peak(1.0, 200.0)
        t1 = self._peak(1.5, 400.0)
        t2 = self._peak(2.5, 300.0)
        base = set(hg._create_triplet_hashes(anchor, t1, t2))
        s = 1.2  # 20%遅く（時間伸長）
        stretched = set(hg._create_triplet_hashes(
            self._peak(1.0 * s, 200.0),
            self._peak(1.5 * s, 400.0),
            self._peak(2.5 * s, 300.0),
        ))
        # 時間比 (t1-ta)/(t2-ta) は定数倍で不変 → 共通ハッシュが存在する
        self.assertTrue(base & stretched)

    def test_hash_fits_32bit(self):
        """生成ハッシュは32bitに収まる（DBスキーマ非互換化しない）"""
        hg = HashGenerator()
        hashes = hg._create_triplet_hashes(
            self._peak(1.0, 200.0), self._peak(1.5, 800.0), self._peak(2.5, 150.0)
        )
        self.assertTrue(hashes)
        for h in hashes:
            self.assertGreaterEqual(h, 0)
            self.assertLess(h, 1 << 32)


class TestSingleSearchQueryCount(unittest.TestCase):
    """③ 尺度不変化により、スケール探索ループが撤廃されDB検索は1回のみになる"""

    def setUp(self):
        self.mock_db = Mock()
        self.mock_db.search_fingerprints.return_value = {
            "s1": [(float(i), float(i)) for i in range(10)]
        }
        self.mock_db.get_songs.return_value = {
            "s1": Song(id="s1", title="t", artist="a", file_path="/x.wav")
        }
        self.mock_db.get_song.return_value = Song(
            id="s1", title="t", artist="a", file_path="/x.wav"
        )
        self.matcher = FingerprintMatcher(self.mock_db)
        self.query = [Fingerprint(hash_value=i, time_offset=0.0, song_id="") for i in range(5)]

    def test_no_scale_factor_loops(self):
        """旧 brute-force のスケール係数ループ属性は撤去されている"""
        self.assertFalse(hasattr(self.matcher, "freq_scale_factors"))
        self.assertFalse(hasattr(self.matcher, "time_scale_factors"))
        self.assertFalse(hasattr(self.matcher, "_scale_fingerprints"))

    def test_scale_invariant_searches_once(self):
        """尺度不変マッチングはDB検索を1回だけ発行する（多重発行の回帰）"""
        self.matcher.find_matches(self.query, min_matches=1, include_details=True)
        self.assertEqual(self.mock_db.search_fingerprints.call_count, 1)


class TestAlignmentSign(unittest.TestCase):
    """⑤ 時間整列が符号（ズレの向き）を区別する"""

    def setUp(self):
        self.matcher = FingerprintMatcher(Mock())

    def test_consistent_offset_is_single_group(self):
        """一定の符号付きオフセットで揃っていれば単一グループにまとまる"""
        pairs = [(4.0, 1.0), (5.0, 2.0), (6.0, 3.0)]  # 全て +3.0
        groups = self.matcher._find_time_aligned_matches(pairs, tolerance=0.2)
        largest = max(groups, key=len)
        self.assertEqual(len(largest), 3)

    def test_mirror_offset_not_aligned(self):
        """+3s と -3s の鏡像的ズレは同一グループに入れない（abs()回帰）"""
        pairs = [(4.0, 1.0), (1.0, 4.0)]  # +3.0 と -3.0
        groups = self.matcher._find_time_aligned_matches(pairs, tolerance=0.2)
        # abs()で符号を捨てると両方が同一視され1グループになってしまう。
        # 符号付きなら残差 +3 と -3 に分かれ別グループになる。
        largest = max(groups, key=len)
        self.assertEqual(len(largest), 1)


class TestMoviePositionDivergence(unittest.TestCase):
    """統合検索: 音声位置と映像位置の乖離判定の符号を誤らない

    time_offset は支配直線 db≈time_scale·query+offset の切片（query=0でのDB位置）。
    これを負号で扱うと、音声・映像が同一区間に整列していても乖離扱いになり、
    正しい二重一致が幾何平均で持ち上げられず不当に減点される。
    """

    def _visual(self, db_start, db_end, query_duration):
        return {
            "match_details": {
                "query_duration": query_duration,
                "regions": [{
                    "db_start": db_start, "db_end": db_end, "frame_count": 40,
                }],
            }
        }

    def test_aligned_positions_not_diverged(self):
        """音声DB 22:28〜 と映像DB 22:28〜 は同一区間→乖離なし"""
        from mimizam.src.mimizam import Mimizam
        # 22:28 = 1348秒から84.7秒の一致（速度変化なし）
        audio = {"time_offset": 1348.0, "time_scale": 1.0}
        visual = self._visual(db_start=1348.0, db_end=1433.0, query_duration=84.7)
        self.assertFalse(
            Mimizam._movie_position_diverges(audio, visual, tolerance=30.0)
        )

    def test_far_positions_diverged(self):
        """音声DBと映像DBが数百秒離れていれば乖離ありとして除外する"""
        from mimizam.src.mimizam import Mimizam
        audio = {"time_offset": 100.0, "time_scale": 1.0}
        visual = self._visual(db_start=1348.0, db_end=1433.0, query_duration=84.7)
        self.assertTrue(
            Mimizam._movie_position_diverges(audio, visual, tolerance=30.0)
        )

    def test_speed_changed_positions_use_time_scale(self):
        """速度変化ありでも倍率でDB終端を伸ばし、同一区間なら乖離なし"""
        from mimizam.src.mimizam import Mimizam
        # time_scale=1.2 → DB区間 [1000, 1000+1.2*100]=[1000,1120]
        audio = {"time_offset": 1000.0, "time_scale": 1.2}
        visual = self._visual(db_start=1000.0, db_end=1120.0, query_duration=100.0)
        self.assertFalse(
            Mimizam._movie_position_diverges(audio, visual, tolerance=30.0)
        )


if __name__ == "__main__":
    unittest.main()
