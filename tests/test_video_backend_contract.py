"""
非SQLite backend 対応・静かな不具合修正の回帰テスト

- search_frame_candidates が候補メタデータを get_videos で一括取得し、
  候補ごとの get_video 往復（N+1）を起こさないこと。
- Mimizam.search_movie が音声・映像の両モダリティとも例外で失敗した場合を
  「一致なし（空結果）」に潰さず MimizamError として通知すること。
- Mimizam._get_video_db が後続呼び出しの db_path を尊重し、別接続先を
  指定したら _video_db を作り直すこと（キャッシュ使い回しによる誤接続防止）。
- SQLite backend の get_videos が要求IDのみを返し未存在を None にすること。
"""

import logging
import os
import tempfile
import unittest

import numpy as np

from mimizam import Mimizam, Video
from mimizam.src.exceptions import MimizamError
from mimizam.src.video_database import VideoFingerprintDatabase as VDB

VLAD_DIM = 512


def _vlad_vec(seed):
    rng = np.random.default_rng(seed)
    v = rng.standard_normal(VLAD_DIM).astype(np.float32)
    return v / (np.linalg.norm(v) + 1e-8)


class _CountingBackend:
    """search_frame_candidates が呼ぶ最小限のバックエンド（呼び出し回数を計測）"""

    def __init__(self, agg, videos):
        self._agg = agg
        self._videos = videos
        self.get_video_calls = 0
        self.get_videos_calls = 0

    def search_frame_candidates(self, query_blobs, dims, k, thr):
        return self._agg

    def get_video(self, video_id):
        self.get_video_calls += 1
        return self._videos.get(video_id)

    def get_videos(self, video_ids):
        self.get_videos_calls += 1
        return {v: self._videos.get(v) for v in video_ids}


class TestSearchFrameCandidatesBulk(unittest.TestCase):
    """候補メタデータ取得が N+1 ではなく1回の一括取得で行われること"""

    def _make_db(self, backend):
        db = object.__new__(VDB)
        db.backend = backend
        db.logger = logging.getLogger("test.vdb.bulk")
        return db

    def test_uses_get_videos_bulk_not_per_candidate(self):
        agg = {
            "v1": {"votes": 3.0, "score_sum": 1.5},
            "v2": {"votes": 2.0, "score_sum": 0.8},
            "v3": {"votes": 0.0, "score_sum": 0.0},  # 得票0は候補外
        }
        videos = {
            "v1": Video(id="v1", title="V1", file_path="/a"),
            "v2": Video(id="v2", title="V2", file_path="/b"),
        }
        backend = _CountingBackend(agg, videos)
        db = self._make_db(backend)

        query = [(0, 0.0, _vlad_vec(1))]
        candidates = db.search_frame_candidates(query, top_k=5)

        # 候補ごとの get_video ではなく get_videos を1回だけ呼ぶ
        self.assertEqual(backend.get_video_calls, 0)
        self.assertEqual(backend.get_videos_calls, 1)

        by_id = {c["video_id"]: c for c in candidates}
        self.assertIn("v1", by_id)
        self.assertIn("v2", by_id)
        self.assertNotIn("v3", by_id)  # 得票0は除外
        self.assertIs(by_id["v1"]["video"], videos["v1"])
        self.assertAlmostEqual(by_id["v1"]["similarity"], 0.5, places=6)
        self.assertEqual(by_id["v1"]["votes"], 3)


class TestSearchMovieAllModalitiesFail(unittest.TestCase):
    """音声・映像の両方が例外で失敗した場合は空結果に潰さず例外化する"""

    def _make_mimizam(self):
        m = object.__new__(Mimizam)
        m.logger = logging.getLogger("test.mimizam.movie")
        return m

    def test_raises_when_both_modalities_fail(self):
        m = self._make_mimizam()

        def _boom_audio(path):
            raise RuntimeError("audio decode failed")

        def _boom_video(*a, **k):
            raise RuntimeError("video search failed")

        m._decode_audio_from_media = _boom_audio
        m.search_video = _boom_video

        with tempfile.NamedTemporaryFile(suffix=".mp4") as tf:
            with self.assertRaises(MimizamError):
                m.search_movie(tf.name)

    def test_no_raise_when_one_modality_returns_empty(self):
        """片方が例外でも、もう片方が正常に空を返せば「一致なし」を許容する"""
        m = self._make_mimizam()

        def _boom_audio(path):
            raise RuntimeError("audio decode failed")

        m._decode_audio_from_media = _boom_audio
        m.search_video = lambda *a, **k: []
        m._merge_movie_results = lambda audio, visual, tol: []

        with tempfile.NamedTemporaryFile(suffix=".mp4") as tf:
            result = m.search_movie(tf.name)
        self.assertEqual(result, [])


class TestGetVideoDbCache(unittest.TestCase):
    """_get_video_db が後続の db_path を尊重して作り直すこと"""

    class _NoConfigDB:
        config = None

        def disconnect(self):
            pass

    def _make_mimizam(self):
        m = object.__new__(Mimizam)
        m.logger = logging.getLogger("test.mimizam.db")
        m.database = self._NoConfigDB()
        return m

    def test_rebuilds_on_different_db_path(self):
        m = self._make_mimizam()
        with tempfile.TemporaryDirectory() as d:
            p1 = os.path.join(d, "video_a.db")
            p2 = os.path.join(d, "video_b.db")

            db1 = m._get_video_db(p1)
            db1_again = m._get_video_db(p1)
            self.assertIs(db1, db1_again)  # 同一パスはキャッシュ再利用

            db2 = m._get_video_db(p2)
            self.assertIsNot(db1, db2)  # 別パスは作り直す

            # db_path 未指定なら直近のキャッシュを使い回す
            db2_cached = m._get_video_db()
            self.assertIs(db2, db2_cached)
            m.close()


class TestSqliteGetVideosBulk(unittest.TestCase):
    """SQLite backend の get_videos が要求IDのみ返し未存在を None にする"""

    def test_get_videos_partial(self):
        from mimizam.src.backends.sqlite_backend import SQLiteBackend
        from mimizam import DatabaseConfig

        with tempfile.TemporaryDirectory() as d:
            cfg = DatabaseConfig(
                backend="sqlite",
                file_path=os.path.join(d, "v.db"),
            )
            backend = SQLiteBackend(cfg)
            self.assertTrue(backend.connect())
            backend.create_tables()

            backend.add_video(Video(id="a", title="A", file_path="/a"))
            backend.add_video(Video(id="b", title="B", file_path="/b"))

            got = backend.get_videos(["a", "b", "missing"])
            self.assertEqual(set(got.keys()), {"a", "b", "missing"})
            self.assertEqual(got["a"].title, "A")
            self.assertEqual(got["b"].title, "B")
            self.assertIsNone(got["missing"])
            self.assertEqual(backend.get_videos([]), {})
            backend.disconnect()


if __name__ == "__main__":
    unittest.main()
