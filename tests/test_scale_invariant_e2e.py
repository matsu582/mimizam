"""
尺度不変ハッシュ＋頑健直線回帰マッチャの E2E 回帰テスト

項目1・2（既存 brute-force 探索の完全置換）で導入した「三つ組比率による尺度不変
ハッシュ」と「単一検索＋ハフ投票回帰」が、速度変化・ピッチ変化した音源を正しく
識別し、無関係曲を棄却できることを合成音源で検証する。旧設計ではピッチ探索が
実質無効・速度探索が brute-force だったため、この不変性を回帰として固定する。
"""

import unittest

import numpy as np

try:
    import librosa
    _HAS_LIBROSA = True
except Exception:  # pragma: no cover - 環境依存
    _HAS_LIBROSA = False

from mimizam import create_mimizam_sqlite
from mimizam.src.audio_fingerprinter import AudioFingerprinter
from mimizam.src.database_base import Song


def _make_reference(sr: int = 22050, dur: float = 12.0) -> np.ndarray:
    """倍音を含む音階状の合成信号（決定的）を生成する"""
    t = np.linspace(0, dur, int(dur * sr), endpoint=False)
    sig = np.zeros_like(t)
    notes = [220, 277, 330, 440, 554, 659]
    for k in range(6):
        seg = (t >= k * 2.0) & (t < (k + 1) * 2.0)
        f0 = notes[k % len(notes)]
        for h in range(1, 6):
            sig[seg] += (1.0 / h) * np.sin(2 * np.pi * f0 * h * t[seg])
    sig += 0.005 * np.random.default_rng(7).standard_normal(len(t))
    return (sig / np.max(np.abs(sig))).astype(np.float32)


def _norm(x: np.ndarray) -> np.ndarray:
    x = x.astype(np.float32)
    mx = np.max(np.abs(x))
    return x / mx if mx > 0 else x


@unittest.skipUnless(_HAS_LIBROSA, "librosa が必要")
class TestScaleInvariantMatchingE2E(unittest.TestCase):
    """尺度不変マッチングのエンドツーエンド検証"""

    SR = 22050

    @classmethod
    def setUpClass(cls):
        cls.sig = _make_reference(cls.SR)
        # 再現性のため適応パラメータは無効化し、ピーク保持数を十分確保する
        cls.fp = AudioFingerprinter(enable_adaptive_params=False)
        cls.fp.hash_generator.max_peaks_per_second = 60
        cls.ref_fps = cls.fp.fingerprint_audio(cls.sig)

    def setUp(self):
        self.m = create_mimizam_sqlite(':memory:')
        self.m.database.add_song(
            Song(id="s1", title="Ref", artist="A", file_path="/r.wav")
        )
        self.m.database.add_fingerprints("s1", self.ref_fps)

    def tearDown(self):
        self.m.close()

    def _top(self, sig2):
        qf = self.fp.fingerprint_audio(_norm(sig2))
        res = self.m.matcher.find_matches(qf, min_matches=3, include_details=False)
        return res[0] if res else None

    def test_identity_matches_high_confidence(self):
        top = self._top(self.sig)
        self.assertIsNotNone(top)
        self.assertEqual(top['song_id'], "s1")
        self.assertGreater(top['confidence'], 0.5)
        self.assertAlmostEqual(top['time_scale'], 1.0, delta=0.05)

    def test_speed_change_matches_and_recovers_scale(self):
        """再生速度1.15倍（時間・周波数とも変化）を識別し倍率を復元する"""
        sped = librosa.resample(self.sig, orig_sr=self.SR,
                                target_sr=int(self.SR / 1.15))
        top = self._top(sped)
        self.assertIsNotNone(top)
        self.assertEqual(top['song_id'], "s1")
        self.assertAlmostEqual(top['time_scale'], 1.15, delta=0.1)

    def test_tempo_change_matches(self):
        """テンポ変化（速度のみ、ピッチ不変）を識別する（両方向）"""
        for rate, expected in [(1.2, 1.2), (0.8, 0.8)]:
            with self.subTest(rate=rate):
                stretched = librosa.effects.time_stretch(self.sig, rate=rate)
                top = self._top(stretched)
                self.assertIsNotNone(top)
                self.assertEqual(top['song_id'], "s1")
                self.assertAlmostEqual(top['time_scale'], expected, delta=0.12)

    def test_pitch_shift_matches(self):
        """ピッチ変化（±2半音、速度不変）を識別する（旧方式では失敗していた）"""
        for steps in (2, -2):
            with self.subTest(steps=steps):
                pitched = librosa.effects.pitch_shift(
                    self.sig, sr=self.SR, n_steps=steps
                )
                top = self._top(pitched)
                self.assertIsNotNone(top)
                self.assertEqual(top['song_id'], "s1")
                # ピッチ変化は速度を変えないので time_scale は約1.0
                self.assertAlmostEqual(top['time_scale'], 1.0, delta=0.1)

    def test_unrelated_is_rejected(self):
        """無関係な音源は一致として返さない（偽陽性の棄却）"""
        t = np.linspace(0, 12.0, int(12.0 * self.SR), endpoint=False)
        u = np.zeros_like(t)
        for f in [311, 392, 494, 587]:
            u += np.sin(2 * np.pi * f * t)
        u += 0.005 * np.random.default_rng(11).standard_normal(len(t))
        top = self._top(u)
        self.assertIsNone(top)


if __name__ == '__main__':
    unittest.main()
