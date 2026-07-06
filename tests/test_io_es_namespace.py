"""
PR-A（性能・方式改善）の回帰テスト

- 項目3: ffmpegパイプによる音声デコード（一時WAVを書かない）と、
  movie経由の音声登録/検索がパイプ経路で機能すること
- 項目4: Elasticsearchのrefresh方針（書き込み時refresh・検索時refreshは既定オフ）
- 項目5: mimizam.audio / mimizam.video の名前空間分離
"""

import os
import subprocess
import tempfile
import unittest

import numpy as np

from mimizam import create_mimizam_sqlite
from mimizam.src.database_base import DatabaseConfig


def _ffmpeg_available() -> bool:
    from shutil import which
    return which("ffmpeg") is not None


class TestPipeAudioDecode(unittest.TestCase):
    """項目3: ffmpegパイプで音声をnumpy配列として取り込む"""

    @unittest.skipUnless(_ffmpeg_available(), "ffmpeg not available")
    def test_decode_returns_normalized_float32_at_sr(self):
        m = create_mimizam_sqlite(':memory:')
        sr = int(m.fingerprinter.sr)
        try:
            import soundfile as sf
            t = np.linspace(0, 2, sr * 2, endpoint=False)
            wav = (0.3 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
            f = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
            f.close()
            sf.write(f.name, wav, sr)
            audio = m._decode_audio_from_media(f.name)
            self.assertEqual(audio.dtype, np.float32)
            # 2秒 × sr サンプル（±数サンプルの誤差を許容）
            self.assertAlmostEqual(len(audio), sr * 2, delta=sr // 10)
            self.assertLessEqual(float(np.max(np.abs(audio))), 1.0)
        finally:
            m.close()
            if os.path.exists(f.name):
                os.unlink(f.name)

    @unittest.skipUnless(_ffmpeg_available(), "ffmpeg not available")
    def test_add_and_search_movie_audio_via_pipe(self):
        """skip_visualでmovieの音声のみをパイプ経路で登録→検索できる"""
        m = create_mimizam_sqlite(':memory:')
        wav = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
        wav.close()
        vid = tempfile.NamedTemporaryFile(suffix='.mp4', delete=False)
        vid.close()
        try:
            import soundfile as sf
            # 複数トーン＋ノイズのリッチな音声（指紋が疎になりすぎないように）
            sr = int(m.fingerprinter.sr)
            t = np.linspace(0, 5, sr * 5, endpoint=False)
            rng = np.random.default_rng(0)
            sig = (
                0.3 * np.sin(2 * np.pi * 440 * t)
                + 0.2 * np.sin(2 * np.pi * 880 * t)
                + 0.2 * np.sin(2 * np.pi * 1500 * t)
                + 0.1 * rng.standard_normal(t.shape)
            ).astype(np.float32)
            sf.write(wav.name, sig, sr)
            # 音声トラック付きの短いテスト動画をffmpegで生成
            subprocess.run([
                "ffmpeg", "-nostdin", "-y",
                "-i", wav.name,
                "-f", "lavfi", "-i", "testsrc=size=64x64:rate=5:duration=5",
                "-ar", str(sr), "-ac", "1", "-shortest", vid.name,
            ], capture_output=True, check=True)

            info = m.add_movie(vid.name, title="tone", artist="a", skip_visual=True)
            self.assertTrue(info["audio_registered"])
            # 保存される file_path は一時WAVではなく元の動画パス
            song = m.database.get_song(info["id"])
            self.assertEqual(song.file_path, vid.name)

            results = m.search_movie(
                vid.name, skip_visual=True, min_combined_score=0.0,
            )
            ids = [r["id"] for r in results]
            self.assertIn(info["id"], ids)
        finally:
            m.close()
            for p in (wav.name, vid.name):
                if os.path.exists(p):
                    os.unlink(p)


class TestElasticsearchRefreshConfig(unittest.TestCase):
    """項目4: refresh方針のデフォルト"""

    def test_refresh_defaults(self):
        cfg = DatabaseConfig(backend='elasticsearch')
        # 書き込み時refreshで追加データを即可視化し、検索時refreshは既定オフ
        self.assertTrue(cfg.es_refresh_on_write)
        self.assertFalse(cfg.es_refresh_on_search)

    def test_maybe_refresh_for_search_respects_flag(self):
        """_maybe_refresh_for_search はフラグに従い音声/映像の全読み取り経路を統一制御する"""
        from mimizam.src.backends.elasticsearch_backend import ElasticsearchBackend

        class _FakeIndices:
            def __init__(self):
                self.calls = []

            def refresh(self, index):
                self.calls.append(index)

        class _FakeClient:
            def __init__(self):
                self.indices = _FakeIndices()

        class _Stub:
            pass

        stub = _Stub()
        stub.client = _FakeClient()

        # 既定（検索時refreshオフ）ではrefreshを呼ばない
        stub.config = DatabaseConfig(backend='elasticsearch')
        ElasticsearchBackend._maybe_refresh_for_search(stub, 'idx_a', 'idx_b')
        self.assertEqual(stub.client.indices.calls, [])

        # 明示的に有効化した場合のみ、指定インデックスをrefreshする
        stub.config = DatabaseConfig(backend='elasticsearch', es_refresh_on_search=True)
        ElasticsearchBackend._maybe_refresh_for_search(stub, 'idx_a', 'idx_b')
        self.assertEqual(stub.client.indices.calls, ['idx_a', 'idx_b'])


class TestNamespaceSeparation(unittest.TestCase):
    """項目5: mimizam.audio / mimizam.video の名前空間分離"""

    def test_audio_namespace_exports(self):
        import mimizam.audio as a
        self.assertTrue(hasattr(a, 'AudioFingerprinter'))
        self.assertTrue(hasattr(a, 'FingerprintDatabase'))
        # 映像シンボルは音声名前空間には無い
        self.assertFalse(hasattr(a, 'VideoFingerprinter'))

    def test_top_level_backcompat(self):
        import mimizam
        self.assertTrue(hasattr(mimizam, 'AudioFingerprinter'))


if __name__ == '__main__':
    unittest.main()
