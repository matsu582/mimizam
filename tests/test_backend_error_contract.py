"""
項目6: backend層のエラー契約統一に対する回帰テスト

データ変更メソッド（add_song / add_fingerprints / delete_song /
add_video / add_frame_fingerprints / delete_video）は、失敗を bool(False) に
潰さず DatabaseError を送出する契約であることを検証する。

- 起動時のライフサイクル述語（connect / create_tables）は従来通り bool を返す。
- 高レベルAPI（Mimizam.delete_song 等）は backend の例外を捕捉して従来の
  bool 契約を維持する（呼び出し側の後方互換）。
"""

import os
import tempfile
import unittest
from unittest.mock import Mock

from mimizam import (
    FingerprintDatabase, Fingerprint, Song, Video, create_sqlite_config,
)
from mimizam.src.backends.sqlite_backend import SQLiteBackend
from mimizam.src.database_base import DatabaseConfig
from mimizam.src.exceptions import DatabaseError


class TestSQLiteBackendRaisesOnFailure(unittest.TestCase):
    """SQLiteBackend のデータ変更メソッドは失敗時に DatabaseError を送出する"""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.tmp.close()
        self.backend = SQLiteBackend(create_sqlite_config(self.tmp.name))
        self.assertTrue(self.backend.connect())
        self.assertTrue(self.backend.create_tables())

    def tearDown(self):
        try:
            self.backend.disconnect()
        finally:
            if os.path.exists(self.tmp.name):
                os.unlink(self.tmp.name)

    def _break_connection(self):
        """接続を壊してデータ操作を必ず失敗させる"""
        self.backend.connection.close()

    def test_add_song_raises_on_failure(self):
        self._break_connection()
        with self.assertRaises(DatabaseError):
            self.backend.add_song(
                Song(id="s1", title="t", artist="a", file_path="/x.wav")
            )

    def test_add_fingerprints_raises_on_failure(self):
        self._break_connection()
        with self.assertRaises(DatabaseError):
            self.backend.add_fingerprints(
                "s1", [Fingerprint(hash_value=1, time_offset=0.0, song_id="s1")]
            )

    def test_delete_song_raises_on_failure(self):
        self._break_connection()
        with self.assertRaises(DatabaseError):
            self.backend.delete_song("s1")

    def test_add_video_raises_on_failure(self):
        self._break_connection()
        with self.assertRaises(DatabaseError):
            self.backend.add_video(
                Video(id="v1", title="t", file_path="/x.mp4",
                      duration=1.0, frame_count=1)
            )

    def test_add_frame_fingerprints_raises_on_failure(self):
        self._break_connection()
        with self.assertRaises(DatabaseError):
            self.backend.add_frame_fingerprints(
                "v1", [(0, 0.0, b"\x00\x00\x80\x3f")]
            )

    def test_delete_video_raises_on_failure(self):
        self._break_connection()
        with self.assertRaises(DatabaseError):
            self.backend.delete_video("v1")

    def test_success_returns_true(self):
        """成功時は従来通り True を返す（例外は送出しない）"""
        self.assertTrue(
            self.backend.add_song(
                Song(id="s1", title="t", artist="a", file_path="/x.wav")
            )
        )
        self.assertTrue(
            self.backend.add_fingerprints(
                "s1", [Fingerprint(hash_value=1, time_offset=0.0, song_id="s1")]
            )
        )
        self.assertTrue(self.backend.delete_song("s1"))


class TestMariaDBBackendRaisesOnFailure(unittest.TestCase):
    """MariaDBBackend も他バックエンドと同契約: 失敗時 DatabaseError を送出する

    同型実装の取りこぼし（add_frame_fingerprints だけ False 返却）を回帰として固定。
    ドライバ非導入環境でも動くよう、接続はモックで置き換えて失敗を注入する。
    """

    def _make_backend(self):
        from mimizam.src.backends.mariadb_backend import MariaDBBackend, MySQLError
        backend = MariaDBBackend(create_sqlite_config(':memory:'))
        backend._mariadb_vector_available = True
        # ベクトル表準備は成功させ、書き込みだけを失敗させる
        backend._ensure_frame_vector_table = lambda dims: True
        cursor = Mock()
        cursor.executemany.side_effect = MySQLError("boom")
        backend.connection = Mock()
        backend.connection.cursor.return_value = cursor
        return backend

    def test_add_frame_fingerprints_raises_on_failure(self):
        backend = self._make_backend()
        # 4バイト=float32 1次元のダミー埋め込み
        with self.assertRaises(DatabaseError):
            backend.add_frame_fingerprints("v1", [(0, 0.0, b"\x00\x00\x80\x3f")])


class TestLifecyclePredicatesReturnBool(unittest.TestCase):
    """connect / create_tables は起動述語として bool を返し例外化しない"""

    def test_connect_failure_returns_false(self):
        # 存在しないディレクトリ配下のパスで接続失敗させる
        backend = SQLiteBackend(
            DatabaseConfig(backend='sqlite',
                           file_path='/nonexistent_dir/x/y/z.db')
        )
        self.assertFalse(backend.connect())


class TestHighLevelCompatibility(unittest.TestCase):
    """呼び出し側の後方互換: backend例外は高レベルAPIで従来契約に変換される"""

    def test_register_rolls_back_song_on_fingerprint_error(self):
        """add_fingerprints が失敗したら add_song 分をロールバックして再送出する"""
        db = FingerprintDatabase(create_sqlite_config(':memory:'))
        # add_song は成功、add_fingerprints は失敗、delete_song は成功を模倣
        db.add_song = Mock(return_value=True)
        db.add_fingerprints = Mock(side_effect=DatabaseError("boom"))
        db.delete_song = Mock(return_value=True)

        from mimizam import create_mimizam_sqlite
        m = create_mimizam_sqlite(':memory:')
        m.database = db
        with self.assertRaises(DatabaseError):
            m._register_fingerprints(
                [Fingerprint(hash_value=1, time_offset=0.0, song_id="")],
                title="t", artist="a", stored_path="/x.wav", song_id="s1",
            )
        db.delete_song.assert_called_once_with("s1")
        m.close()

    def test_delete_song_converts_error_to_false(self):
        """Mimizam.delete_song は backend の DatabaseError を False に変換する"""
        from mimizam import create_mimizam_sqlite
        m = create_mimizam_sqlite(':memory:')
        m.database.delete_song = Mock(side_effect=DatabaseError("boom"))
        self.assertFalse(m.delete_song("s1"))
        m.close()


if __name__ == "__main__":
    unittest.main()
