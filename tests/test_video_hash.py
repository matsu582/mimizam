"""
時間 3 点ハッシュ（configure_video(method="hash")）の回帰テスト

- DB（0.5 秒ごと・2 枚先と組む）とクエリ（1 秒ごと・次と組む）のハッシュが一致すること
- 投票で、同じハッシュが複数のクエリ時刻に出ても潰さず数えること
- 時刻ずれの符号（DB 時刻 − クエリ時刻）を保つこと
- 静止点（前後のフレームの同じ位置・同じ視覚語）をハッシュに使わないこと
- SQLite での保存・検索・置き換え・削除、DB 障害を空結果に潰さないこと
- 全 backend が add_video_hashes / search_video_hashes を実装していること
"""

import os
import tempfile
import unittest
from unittest import mock

import numpy as np

from mimizam import Mimizam, Video
from mimizam.src.database_base import DatabaseBackend
from mimizam.src.exceptions import DatabaseError, MimizamError
from mimizam.src.video_database import VideoFingerprintDatabase as VDB
from mimizam.src.video_hash import VideoHashConfig, VideoHasher, vote


def _frames(n, step, seed=0, start=0.0, npts=80):
    """少しずつ動く点のフレーム列 (時刻, 座標, 大きさ, 向き, 視覚語)"""
    rng = np.random.default_rng(seed)
    p0 = rng.uniform(0, 400, (npts, 2))
    v = rng.normal(0, 3, (npts, 2))
    sz = rng.uniform(8, 14, npts)
    th = rng.uniform(0, 2 * np.pi, npts)
    w = rng.integers(0, 64, npts)
    return [
        (start + i * step, p0 + v * i, sz.copy(), th.copy(), w.copy())
        for i in range(n)
    ]


def _rows(hasher, frames, vid, ver=0):
    return [(h, vid, ver, ts, a, s, t)
            for h, ts, a, s, t in hasher.db_rows(frames)]


class TestHashAndVote(unittest.TestCase):

    def setUp(self):
        self.hasher = VideoHasher()

    def test_query_hashes_match_db_pairs(self):
        db = _frames(20, 0.5)
        q = db[::2]
        dbh = {r[0] for r in self.hasher.db_rows(db)}
        qh, _, _ = self.hasher.query_hashes(q)
        self.assertTrue(len(qh) > 0)
        self.assertGreater(len(set(qh.tolist()) & dbh), 0)

    def test_vote_finds_video_and_keeps_offset_sign(self):
        c = self.hasher.config
        db_a = _frames(40, 0.5, seed=1)
        db_b = _frames(40, 0.5, seed=2)
        rows = _rows(self.hasher, db_a, "a") + _rows(self.hasher, db_b, "b")
        # クエリは DB の 8 秒目から始まる区間（クエリ時刻は 0 から数える）
        q = [(t - 8.0, p, s, th, w) for t, p, s, th, w in db_a[16::2]]
        qh, qf, qa = self.hasher.query_hashes(q)
        best = vote(c, q, qh, qf, qa, rows)
        top = max(best, key=lambda k: best[k]["votes"])
        self.assertEqual(top, "a")
        self.assertEqual(best["a"]["offset"], 8.0)
        self.assertGreater(best["a"]["votes"], best.get("b", {"votes": 0})["votes"])

    def test_vote_keeps_query_time_multiplicity(self):
        c = VideoHashConfig()
        frames = [(0.0, np.zeros((2, 2)), np.ones(2), np.zeros(2), np.zeros(2, np.int64)),
                  (1.0, np.zeros((2, 2)), np.ones(2), np.zeros(2), np.zeros(2, np.int64))]
        # 同じハッシュ 7 が 2 つのクエリ時刻に出る。DB 側も 2 か所にある
        qh = np.array([7, 7], np.int64)
        qf = np.array([0, 1], np.int64)
        qa = np.array([0, 0], np.int64)
        rows = [(7, "v", 0, 0.0, 0, 1.0, 0.0), (7, "v", 0, 1.0, 300, 1.0, 0.0)]
        best = vote(c, frames, qh, qf, qa, rows)
        self.assertEqual(best["v"]["votes"], 2.0)
        self.assertEqual(best["v"]["offset"], 0.0)

    def test_vote_ignores_too_common_hashes(self):
        c = VideoHashConfig(max_hits=1)
        frames = [(0.0, np.zeros((1, 2)), np.ones(1), np.zeros(1), np.zeros(1, np.int64))]
        rows = [(5, "v", 0, 0.0, 0, 1.0, 0.0), (5, "w", 0, 0.0, 0, 1.0, 0.0)]
        self.assertEqual(vote(c, frames, np.array([5]), np.array([0]), np.array([0]), rows), {})

    def test_static_points_are_not_used(self):
        hasher = VideoHasher()
        hasher.centers = np.zeros((64, 488), np.float32)
        hasher.words = lambda d: np.zeros(len(d), np.int64)
        moving = np.array([[10.0, 10.0], [100.0, 100.0]])
        raw = []
        for i in range(3):
            p = moving.copy()
            p[1] += i * 20  # 2 点目だけ動く。1 点目は同じ位置に止まっている
            raw.append((i * 0.5, p, np.full(2, 10.0), np.zeros(2),
                        np.array([1.0, 0.5]), np.zeros((2, 61), np.uint8)))
        sel = hasher.select(raw, static_px=2.0)
        for _, p, _, _, _ in sel:
            self.assertEqual(len(p), 1)
            self.assertGreaterEqual(p[0][0], 100.0)

    def test_model_save_load_roundtrip(self):
        h = VideoHasher()
        rng = np.random.default_rng(0)
        h.train([[rng.integers(0, 256, (300, 61)).astype(np.uint8) for _ in range(3)]])
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "m.npz")
            h.save(path)
            h2 = VideoHasher()
            h2.load(path)
        np.testing.assert_array_equal(h.centers, h2.centers)


class TestSQLiteVideoHashes(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.vdb = VDB(db_path=os.path.join(self.tmp.name, "v.db"))
        for vid in ("a", "b"):
            self.vdb.add_video(Video(id=vid, title=vid, file_path="/x"))

    def tearDown(self):
        self.vdb.close()
        self.tmp.cleanup()

    def test_add_search_replace_delete(self):
        self.vdb.add_video_hashes("a", [(1, 0, 0.5, 3, 10.0, 0.1), (2, 1, 1.0, 4, 11.0, 0.2)])
        self.vdb.add_video_hashes("b", [(1, 2, 2.0, 5, 12.0, 0.3)])
        got = sorted(self.vdb.search_video_hashes([1, 1, 2, 99]))
        self.assertEqual(got, [(1, "a", 0, 0.5, 3, 10.0, 0.1), (1, "b", 2, 2.0, 5, 12.0, 0.3),
                               (2, "a", 1, 1.0, 4, 11.0, 0.2)])
        self.vdb.add_video_hashes("a", [(3, 0, 0.0, 0, 1.0, 0.0)])
        self.assertEqual([r[1] for r in self.vdb.search_video_hashes([1, 2])], ["b"])
        self.vdb.delete_video("b")
        self.assertEqual(self.vdb.search_video_hashes([1, 3]), [(3, "a", 0, 0.0, 0, 1.0, 0.0)])

    def test_large_query_is_chunked(self):
        self.vdb.add_video_hashes("a", [(h, 0, 0.0, h, 1.0, 0.0) for h in range(3000)])
        self.assertEqual(len(self.vdb.search_video_hashes(list(range(3000)))), 3000)

    def test_backend_failure_is_not_empty_result(self):
        self.vdb.backend.connection.close()
        with self.assertRaises(DatabaseError):
            self.vdb.search_video_hashes([1])
        with self.assertRaises(DatabaseError):
            self.vdb.add_video_hashes("a", [(1, 0, 0.0, 0, 1.0, 0.0)])


class TestAllBackendsImplementVideoHashes(unittest.TestCase):

    def test_overrides(self):
        from mimizam.src.backends.elasticsearch_backend import ElasticsearchBackend
        from mimizam.src.backends.mariadb_backend import MariaDBBackend
        from mimizam.src.backends.mysql_backend import MySQLBackend
        from mimizam.src.backends.postgresql_backend import PostgreSQLBackend
        from mimizam.src.backends.sqlite_backend import SQLiteBackend
        for cls in (SQLiteBackend, PostgreSQLBackend, MySQLBackend, MariaDBBackend, ElasticsearchBackend):
            for name in ("add_video_hashes", "search_video_hashes"):
                self.assertIsNot(getattr(cls, name), getattr(DatabaseBackend, name), f"{cls.__name__}.{name}")


class TestMimizamHashMethod(unittest.TestCase):

    def test_unknown_method_rejected(self):
        m = Mimizam()
        with self.assertRaises(ValueError):
            m.configure_video(method="bad")

    def test_default_is_vlad(self):
        m = Mimizam()
        m._ensure_video_system()
        self.assertEqual(m._video_method, "vlad")

    def test_search_video_returns_only_match(self):
        m = Mimizam()
        m.configure_video(method="hash")
        m._get_video_hasher().centers = np.zeros((64, 488), np.float32)
        ranked = [{"video_id": "a", "is_match": True}, {"video_id": "b", "is_match": False}]
        with tempfile.NamedTemporaryFile(suffix=".mp4") as f, \
                mock.patch.object(m, "_rank_video_hash", return_value=ranked), \
                mock.patch.object(m, "_get_video_db"):
            self.assertEqual(m.search_video(f.name), [ranked[0]])

    def test_search_video_untrained_raises(self):
        m = Mimizam()
        m.configure_video(method="hash")
        with tempfile.NamedTemporaryFile(suffix=".mp4") as f, mock.patch.object(m, "_get_video_db"):
            with self.assertRaises(MimizamError):
                m.search_video(f.name)

    def test_rebuild_not_supported(self):
        m = Mimizam()
        m.configure_video(method="hash")
        with self.assertRaises(MimizamError):
            m.rebuild_video_fingerprints()


if __name__ == "__main__":
    unittest.main()
