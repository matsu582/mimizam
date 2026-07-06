"""
Shazam-style音声指紋の生成
スペクトログラム生成、ピーク検出、ハッシュベースフィンガープリンティングを含む、
音声指紋に関するShazam風のアルゴリズムを実装します。
"""

import numpy as np
import librosa
from pydub import AudioSegment
import matplotlib.pyplot as plt
from scipy.signal import find_peaks
from typing import List, Tuple, Dict, Optional
import sqlite3
from dataclasses import dataclass
import pickle

import logging
import math
import time
from .adaptive_parameters import AdaptiveParameterTuner, PerformanceMonitor
from .database_base import Fingerprint
from .exceptions import AudioProcessingError, FingerprintGenerationError

# Numba JIT最適化（オプション）
try:
    from numba import njit, prange
    NUMBA_AVAILABLE = True
except ImportError:
    # フォールバック実装
    def njit(**_kwargs):
        def decorator(func):
            return func
        return decorator
    prange = range
    NUMBA_AVAILABLE = False


@dataclass
class Peak:
    """時間-周波数領域のスペクトルピークを表現"""
    time: np.float64
    frequency: np.float64
    amplitude: np.float64


@njit(cache=True, parallel=False)  # parallel=Falseに変更（順序保証のため）
def _numba_optimized_peak_detection(magnitude_db: np.ndarray, mask: np.ndarray,
                                  min_distance: int) -> Tuple[np.ndarray, np.ndarray]:
    """
    Numba JIT最適化されたピーク検出
    元の_find_local_maximaと完全に同じロジックを実装
    Args:
        magnitude_db: dBスケールのマグニチュード
        mask: 閾値フィルタリング済みマスク
        min_distance: 最小距離
    Returns:
        ピークの行インデックス、列インデックス
    """
    rows, cols = magnitude_db.shape
    
    max_peaks = rows * cols // 4
    peaks_f = np.zeros(max_peaks, dtype=np.int32)  # frequency indices
    peaks_t = np.zeros(max_peaks, dtype=np.int32)  # time indices
    peak_count = 0
    
    # 元の実装と同じ順序: 時間優先、周波数次優先
    for t_idx in range(min_distance, cols - min_distance):
        for f_idx in range(min_distance, rows - min_distance):
            # マスクチェック（元の実装と同じ）
            if not mask[f_idx, t_idx]:
                continue
            
            # 局所最大値判定（元の実装と同じ近傍比較）
            center_val = magnitude_db[f_idx, t_idx]
            is_peak = True
            
            # 近傍内の全ての値と比較
            for df in range(-min_distance, min_distance + 1):
                if not is_peak:
                    break
                for dt in range(-min_distance, min_distance + 1):
                    if df == 0 and dt == 0:
                        continue
                    
                    neighbor_val = magnitude_db[f_idx + df, t_idx + dt]
                    # 元の実装では np.max を使用しているので、厳密には == ではなく >= での判定
                    if neighbor_val > center_val:
                        is_peak = False
                        break
            
            if is_peak and peak_count < max_peaks:
                peaks_f[peak_count] = f_idx
                peaks_t[peak_count] = t_idx
                peak_count += 1
    
    return peaks_f[:peak_count], peaks_t[:peak_count]


class SpectrogramAnalyzer:
    """スペクトログラム生成とピーク検出を処理"""
    
    def __init__(self, 
                 n_fft: int = 2048, 
                 hop_length: int = 512, 
                 sr: int = 22050,
                 enable_numba_optimization: bool = False):
        """
        スペクトログラム解析器を初期化
        
        Args:
            n_fft: FFTウィンドウサイズ
            hop_length: 連続するフレーム間のサンプル数
            sr: サンプルレート
            enable_numba_optimization: Numba最適化を有効にするか
        """
        self.n_fft = n_fft
        self.hop_length = hop_length
        self.sr = sr
        self.enable_numba_optimization = enable_numba_optimization and NUMBA_AVAILABLE
        self._numba_compiled = False
        
        if self.enable_numba_optimization:
            logging.info("Numba enabled")
            # 初期化時に事前コンパイルを実行
            self._ensure_numba_compiled()
        else:
            if not NUMBA_AVAILABLE:
                logging.info("Numba not supported")
            else:
                logging.info("Numba disabled")

    def generate_spectrogram(self, audio: np.ndarray, audible_only: bool = False) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        音声信号からスペクトログラムを生成
        
        Args:
            audio: numpy配列としての音声信号
            audible_only: 可聴域(20Hz-20kHz)のみを使う場合True
            
        Returns:
            (マグニチュードスペクトログラム, 周波数, 時間)のタプル
        """
        # 短時間フーリエ変換を計算
        stft = librosa.stft(audio, n_fft=self.n_fft, hop_length=self.hop_length)
        magnitude = np.abs(stft)
        
        # dBスケールに変換
        magnitude_db = librosa.amplitude_to_db(magnitude, ref=np.max)
        
        # 周波数と時間軸を生成
        frequencies = librosa.fft_frequencies(sr=self.sr, n_fft=self.n_fft)
        times = librosa.frames_to_time(np.arange(magnitude.shape[1]), 
                                     sr=self.sr, hop_length=self.hop_length)
        
        # 可聴域のみを抽出
        if audible_only:
            freq_mask = (frequencies >= 20) & (frequencies <= 20000)
            magnitude_db = magnitude_db[freq_mask, :]
            frequencies = frequencies[freq_mask]
        return magnitude_db, frequencies, times
    
    def _ensure_numba_compiled(self):
        """
        Numba JIT事前コンパイル
        
        初回実行時のコンパイル時間を事前に処理することで、
        実際の音源処理時の遅延を回避
        """
        if self._numba_compiled or not self.enable_numba_optimization:
            return
        
        # 小さなダミーデータでコンパイル
        rng = np.random.default_rng(42)
        dummy_data = rng.random((100, 100)).astype(np.float32)
        dummy_mask = dummy_data > -30.0  # 閾値でbool型マスクを作成
        dummy_distance = 2
        
        # コンパイル実行
        _ = _numba_optimized_peak_detection(dummy_data, dummy_mask, dummy_distance)
        
        self._numba_compiled = True
        logging.info("Numba JIT compilation complete")
    
    def _check_threshold_and_adapt(self, magnitude: np.ndarray, min_amplitude: float, debug: bool) -> Tuple[np.ndarray, float]:
        """閾値をチェックし、必要に応じて適応的に調整"""
        logger = logging.getLogger(__name__)
        
        # 閾値を適用
        mask = magnitude > min_amplitude
        threshold_passed = np.sum(mask)
        
        if debug:
            logger.info(f"Points above threshold: {threshold_passed} / {magnitude.size}")
            logger.info(f"Percentage above threshold: {100 * threshold_passed / magnitude.size:.2f}%")
        
        # 閾値を超えるポイントが非常に少ない場合、閾値を下げる
        if threshold_passed < magnitude.size * 0.01:  # 1%未満
            adaptive_threshold = np.percentile(magnitude, 95)  # 95パーセンタイルを使用
            if debug:
                logger.warning(f"Too few points above threshold, using adaptive threshold: {adaptive_threshold:.2f} dB")
            mask = magnitude > adaptive_threshold
            return mask, float(adaptive_threshold)
        
        return mask, min_amplitude

    def _find_local_maxima(self, magnitude: np.ndarray, mask: np.ndarray,
                          frequencies: np.ndarray, times: np.ndarray,
                          peak_neighborhood_size: int, debug: bool) -> List[Peak]:
        """
        スペクトログラム内の局所最大値を検出

        Numbaの有無に関わらず同一の検出関数（_numba_optimized_peak_detection）
        を用いる。Numba未導入時はnjitがno-opとなり同じ関数が純Pythonで実行
        されるため、生成される指紋は環境に依存せず一致する（DB整合性を保証）。
        """
        logger = logging.getLogger(__name__)

        peak_f_indices, peak_t_indices = _numba_optimized_peak_detection(
            magnitude, mask, peak_neighborhood_size
        )

        n_freq = magnitude.shape[0]
        peaks = [
            Peak(
                time=np.float64(times[t_idx]),
                frequency=self._interpolate_peak_frequency(
                    magnitude, frequencies, f_idx, t_idx, n_freq
                ),
                amplitude=np.float64(magnitude[f_idx, t_idx])
            )
            for f_idx, t_idx in zip(peak_f_indices, peak_t_indices)
        ]

        if debug:
            logger.info(f"Detected peaks: {len(peaks)}")
            if len(peaks) > 0:
                amplitudes = [p.amplitude for p in peaks]
                logger.info(f"Peak amplitude range: {np.min(amplitudes):.2f} to {np.max(amplitudes):.2f} dB")
        return peaks
    
    @staticmethod
    def _interpolate_peak_frequency(magnitude: np.ndarray, frequencies: np.ndarray,
                                    f_idx: int, t_idx: int, n_freq: int) -> np.float64:
        """放物線補間でピーク周波数をサブビン精度に補正する

        線形周波数グリッド(約10.8Hz刻み)ではピークの真の周波数がビン中央から
        ずれ、尺度不変ハッシュの周波数比が量子化境界で跨りやすい。隣接3点の
        dB値で放物線を当て、サブビンのずれ delta∈[-0.5,0.5] を推定して補正する。
        端(0/n-1)は補間不能なのでビン中央を返す。
        """
        if f_idx <= 0 or f_idx >= n_freq - 1:
            return np.float64(frequencies[f_idx])
        a = float(magnitude[f_idx - 1, t_idx])
        b = float(magnitude[f_idx, t_idx])
        c = float(magnitude[f_idx + 1, t_idx])
        denom = a - 2.0 * b + c
        if abs(denom) < 1e-12:
            return np.float64(frequencies[f_idx])
        delta = 0.5 * (a - c) / denom
        # 数値誤差でサブビン範囲を超える場合はクランプ
        if delta > 0.5:
            delta = 0.5
        elif delta < -0.5:
            delta = -0.5
        bin_width = float(frequencies[f_idx + 1] - frequencies[f_idx])
        return np.float64(frequencies[f_idx] + delta * bin_width)

    def detect_peaks(self, 
                    magnitude: np.ndarray, 
                    frequencies: np.ndarray, 
                    times: np.ndarray,
                    min_amplitude: float = -60,
                    peak_neighborhood_size: int = 10,
                    debug: bool = False) -> List[Peak]:
        """
        スペクトログラム内のスペクトルピークを検出
        
        Args:
            magnitude: dBでのマグニチュードスペクトログラム
            frequencies: 周波数ビン
            times: 時間ビン
            min_amplitude: ピーク検出の最小振幅閾値
            peak_neighborhood_size: 局所最大値検出の近傍サイズ
            debug: デバッグログを有効にする
            
        Returns:
            検出されたピークのリスト
        """
        logger = logging.getLogger(__name__)
        
        if debug:
            logger.info(f"Spectrogram shape: {magnitude.shape}")
            logger.info(f"Magnitude range: {np.min(magnitude):.2f} to {np.max(magnitude):.2f} dB")
            logger.info(f"Minimum amplitude threshold: {min_amplitude} dB")
            logger.info(f"Peak neighborhood size: {peak_neighborhood_size}")
        
        # 閾値をチェックし、必要に応じて適応的に調整
        mask, _ = self._check_threshold_and_adapt(magnitude, min_amplitude, debug)
        
        # 局所最大値を検出
        peaks = self._find_local_maxima(magnitude, mask, frequencies, times, peak_neighborhood_size, debug)
        
        return peaks
    
    def visualize_spectrogram(self, 
                            magnitude: np.ndarray, 
                            frequencies: np.ndarray, 
                            times: np.ndarray,
                            peaks: Optional[List[Peak]] = None,
                            title: str = "Spectrogram") -> None:
        """
        スペクトログラムを可視化し、オプションでピークをオーバーレイ
        
        Args:
            magnitude: マグニチュードスペクトログラム
            frequencies: 周波数ビン
            times: 時間ビン
            peaks: オーバーレイするピークのオプションリスト
            title: プロットのタイトル
        """
        plt.figure(figsize=(12, 8))
        
        # スペクトログラムをプロット
        plt.imshow(magnitude, 
                  aspect='auto', 
                  origin='lower',
                  extent=(float(times[0]), float(times[-1]), float(frequencies[0]), float(frequencies[-1])))
        
        plt.colorbar(label='magnitude(dB)')
        plt.xlabel('time(s)')
        plt.ylabel('frequencie(Hz)')
        plt.title(title)
        
        # ピークが提供されている場合はオーバーレイ
        if peaks:
            peak_times = [p.time for p in peaks]
            peak_freqs = [p.frequency for p in peaks]
            plt.scatter(peak_times, peak_freqs, c='red', s=10, alpha=0.7, label='peak')
            plt.legend()
        
        plt.show()
    


class HashGenerator:
    """スペクトルピークからハッシュベースのフィンガープリントを作成"""

    # 尺度不変ハッシュ（Panako系）のビットパックレイアウト:
    #   [時間比ビン:8bit][周波数比1ビン:12bit][周波数比2ビン:12bit]
    # アンカーA・2ターゲットT1,T2（時間昇順 tA<t1<t2）の三つ組から、
    #   時間比 r_t = (t1-tA)/(t2-tA)          … 時間伸縮(速度変化)に不変
    #   周波数比 log2(f1/fA), log2(f2/fA)     … 乗法的ピッチ変化に不変
    # を量子化して詰める。ハッシュ自体が速度・ピッチに不変なため、
    # 照合側で time_scale/freq_scale をブルートフォース列挙する必要がない。
    _RT_BITS = 8
    _RT_SHIFT = 24
    _RT_MASK = 0xFF           # 8bit
    _FR_BITS = 12
    _FR_MASK = 0xFFF          # 12bit
    _FR1_SHIFT = 12
    _FR2_SHIFT = 0
    # 量子化粒度は STFT 分解能（n_fft=2048, sr=22050 → 約10.8Hz, hop=512 → 約23ms）
    # に合わせて粗くする。細かすぎるとピーク周波数/時刻の微小変動でビンが跨り、
    # 速度・ピッチ変化版がヒットしなくなるため。
    _RT_LEVELS = 48          # 時間比 r∈(0,1) を 48 段階に量子化（≒0.02刻み）
    _FR_STEP_OCT = 0.1       # 周波数比 log2 の量子化刻み（オクターブ, ≒1.2半音）
    _FR_MAX_OCT = 4.0        # 周波数比のクランプ範囲（±4オクターブ）
    _FR_CENTER = 0x800       # 12bit中央（符号付き比の0点）

    def __init__(self, 
                 target_zone_size: int = 5,
                 time_delta_range: Tuple[float, float] = (0.1, 2.0),
                 max_peaks_per_second: int = 30,  # 1秒あたりの最大ピーク数（密度制御）
                 min_peak_separation: float = 0.02,  # 後方互換のため受理（現方式では未使用）
                 density_time_window: float = 0.1):  # 定数マップの時間窓（秒）
        """
        ハッシュジェネレータを初期化
        
        Args:
            target_zone_size: 各アンカーに対して考慮するターゲットピーク数
            time_delta_range: 考慮する時間差の範囲（秒、現方式では選択は件数ベース）
            max_peaks_per_second: 1秒あたりの最大ピーク数（密度制御）
            min_peak_separation: 後方互換用（旧・時間方向潰し込みは廃止）
            density_time_window: 定数マップ密度制御の時間窓幅（秒）
        """
        self.target_zone_size = target_zone_size
        self.time_delta_range = time_delta_range
        self.max_peaks_per_second = max_peaks_per_second
        self.min_peak_separation = min_peak_separation
        self.density_time_window = density_time_window
    
    def generate_hashes(self, peaks: List[Peak], debug: bool = False) -> List[Fingerprint]:
        """
        スペクトルピークからハッシュフィンガープリントを生成
        
        Args:
            peaks: 検出されたスペクトルピークのリスト
            debug: デバッグログを有効にする
            
        Returns:
            フィンガープリントハッシュのリスト
        """
        logger = logging.getLogger(__name__)
        
        if debug:
            logger.info(f"Generating hashes from {len(peaks)} peaks")
        
        # ピーク密度フィルタリングを適用
        filtered_peaks = self._filter_peaks_by_density(peaks, debug)
        sorted_peaks = sorted(filtered_peaks, key=lambda p: float(p.time))
        
        if debug:
            self._log_peak_info(sorted_peaks, logger)
        
        # ハッシュ生成のメイン処理
        fingerprints = self._generate_hashes_from_peaks(sorted_peaks, debug, logger)
        
        if debug:
            logger.info(f"Generated {len(fingerprints)} unique fingerprint hashes")
        
        return fingerprints
    
    def _log_peak_info(self, sorted_peaks: List[Peak], logger) -> None:
        """ピーク情報をログ出力"""
        if len(sorted_peaks) > 0:
            time_range = sorted_peaks[-1].time - sorted_peaks[0].time
            logger.info(f"Peak time range after filtering: {sorted_peaks[0].time:.2f}s to {sorted_peaks[-1].time:.2f}s ({time_range:.2f}s)")
    
    def _generate_hashes_from_peaks(self, sorted_peaks: List[Peak], debug: bool, logger) -> List[Fingerprint]:
        """ソート済みピークからハッシュを生成"""
        fingerprints = []
        seen_hashes = set()
        anchor_count = 0
        pairs_checked = 0
        valid_time_deltas = []
        
        for i, anchor_peak in enumerate(sorted_peaks):
            target_peaks = self._find_target_peaks(anchor_peak, sorted_peaks[i+1:])
            
            if len(target_peaks) > 0:
                anchor_count += 1
            
            if debug and i < 5:
                self._debug_anchor_info(i, anchor_peak, sorted_peaks, logger)
            
            # ハッシュ生成
            new_fingerprints = self._create_fingerprints_from_targets(
                anchor_peak, target_peaks, seen_hashes, valid_time_deltas
            )
            fingerprints.extend(new_fingerprints)
            pairs_checked += len(target_peaks)
        
        if debug:
            self._log_generation_summary(pairs_checked, anchor_count, len(sorted_peaks), 
                                       valid_time_deltas, len(fingerprints), logger)
        
        return fingerprints

    def _debug_anchor_info(self, i: int, anchor_peak: Peak, sorted_peaks: List[Peak], logger) -> None:
        """アンカー情報をデバッグ出力"""
        candidates = sorted_peaks[i+1:i+1+self.target_zone_size]
        if candidates:
            sample_deltas = [p.time - anchor_peak.time for p in candidates]
            logger.debug(f"Anchor {i} at {anchor_peak.time:.2f}s, sample time deltas: {[f'{d:.3f}' for d in sample_deltas]}")
            logger.debug(f"Valid range: {self.time_delta_range[0]:.3f} - {self.time_delta_range[1]:.3f}s")
    
    def _create_fingerprints_from_targets(self, anchor_peak: Peak, target_peaks: List[Peak],
                                        seen_hashes: set, valid_time_deltas: List[float]) -> List[Fingerprint]:
        """ターゲットピークから尺度不変フィンガープリントを作成する

        アンカーと2つのターゲット（時間昇順の三つ組）から、時間比・周波数比を
        量子化した尺度不変ハッシュを生成する。time_offset にはアンカー時刻を
        保持し、照合時の頑健直線回帰（db_time≈s·query_time+c）で速度変化(s)と
        オフセット(c)を推定できるようにする。
        """
        fingerprints = []

        for j in range(len(target_peaks)):
            t1 = target_peaks[j]
            dt1 = t1.time - anchor_peak.time
            if dt1 <= 0:
                continue
            valid_time_deltas.append(dt1)
            for k in range(j + 1, len(target_peaks)):
                t2 = target_peaks[k]
                dt2 = t2.time - anchor_peak.time
                # 三つ組は tA < t1 < t2 を要求（時間比を (0,1) に収める）
                if dt2 <= dt1:
                    continue

                for hash_value in self._create_triplet_hashes(anchor_peak, t1, t2):
                    if hash_value not in seen_hashes:
                        seen_hashes.add(hash_value)
                        fingerprints.append(Fingerprint(
                            hash_value=hash_value,
                            time_offset=anchor_peak.time
                        ))

        return fingerprints
    
    def _log_generation_summary(self, pairs_checked: int, anchor_count: int, total_peaks: int,
                              valid_time_deltas: List[float], fingerprint_count: int, logger) -> None:
        """ハッシュ生成の概要をログ出力"""
        logger.info(f"Checked pairs: {pairs_checked}")
        logger.info(f"Anchors with targets: {anchor_count}/{total_peaks}")
        if valid_time_deltas:
            logger.info(f"Valid time delta range: {min(valid_time_deltas):.3f} - {max(valid_time_deltas):.3f}s")
        logger.info(f"Removed {pairs_checked - fingerprint_count} duplicate hashes")
    
    def _find_target_peaks(self, anchor: Peak, candidate_peaks: List[Peak]) -> List[Peak]:
        """
        指定されたアンカーピークのターゲットゾーン内でターゲットピークを検索
        
        Args:
            anchor: アンカーピーク
            candidate_peaks: 候補ターゲットピークのリスト
            
        Returns:
            有効なターゲットピークのリスト

        candidate_peaks は時間昇順であることを前提とする。

        尺度不変ハッシュでは「絶対時間窓(time_delta_range)」でターゲットを選ぶと、
        速度変化で同じ窓内に入るピーク集合が変わり、三つ組が別物になって不変性が
        崩れる。そこで選択は件数（ランク）ベースにする: アンカー直後の
        target_zone_size 件を採る。一様な時間伸縮では「直後のN件」は同じピーク集合
        （時刻が伸縮されただけ）になるため、時間比が保存される。
        """
        target_peaks = []

        for peak in candidate_peaks:
            time_delta = peak.time - anchor.time
            # 同一/直前フレームの重なりだけ除外（微小ε）。上限窓は設けない。
            if time_delta <= 1e-6:
                continue
            target_peaks.append(peak)
            if len(target_peaks) >= self.target_zone_size:
                break

        return target_peaks
    
    @classmethod
    def _quantize_time_ratio(cls, r_t: float) -> int:
        """時間比 r_t=(t1-tA)/(t2-tA) ∈ (0,1) を粗く量子化する

        STFT時間分解能に対して過剰に細かいと速度変化版が跨ってしまうため、
        _RT_LEVELS 段階の粗いビンに丸める。
        """
        idx = int(round(r_t * cls._RT_LEVELS))
        return min(max(idx, 0), cls._RT_MASK)

    @classmethod
    def _freq_ratio_bins(cls, f_target: float, f_anchor: float) -> List[int]:
        """周波数比 log2(f_target/f_anchor) を近傍2ビンへソフト量子化する

        乗法的ピッチ変化 f→p·f では log2 比が不変になる。ピーク周波数の微小な
        ブレや量子化境界跨ぎに強くするため、連続位置を挟む下側/上側の2ビンを
        両方返す（両者の真値が1ビン以内なら少なくとも一方のビンが一致する）。
        _FR_STEP_OCT オクターブ刻み、中央値 _FR_CENTER を0点として詰める。
        """
        ratio = math.log2(f_target / f_anchor)
        ratio = min(max(ratio, -cls._FR_MAX_OCT), cls._FR_MAX_OCT)
        pos = ratio / cls._FR_STEP_OCT + cls._FR_CENTER
        lo = int(math.floor(pos))
        bins = []
        for b in (lo, lo + 1):
            b = min(max(b, 0), cls._FR_MASK)
            if b not in bins:
                bins.append(b)
        return bins

    def _create_triplet_hashes(self, anchor: Peak, t1: Peak, t2: Peak) -> List[int]:
        """アンカー＋2ターゲットの三つ組から尺度不変ハッシュ群を作成する

        時間比（速度変化に不変）と2つの周波数比（ピッチ変化に不変）を量子化して
        32bitにビットパックする。ハッシュ自体が速度・ピッチに不変なため、照合側で
        time_scale/freq_scale を列挙する必要がない。周波数比は近傍2ビンへソフト
        量子化するため、1三つ組あたり最大4個のハッシュを返す（境界跨ぎに頑健）。

        Args:
            anchor: アンカーピーク（三つ組の基準、時間最小）
            t1: 中間ターゲット（tA < t1）
            t2: 後方ターゲット（t1 < t2）

        Returns:
            32bit符号なし整数のハッシュ値リスト

        レイアウト: [時間比:8bit][周波数比1:12bit][周波数比2:12bit]
        """
        dt1 = float(t1.time - anchor.time)
        dt2 = float(t2.time - anchor.time)
        # 呼び出し側で dt2>dt1>0 を保証済み。ゼロ割回避のため下限を敷く。
        r_t = dt1 / dt2 if dt2 > 0 else 0.0

        fa = float(anchor.frequency)
        f1 = float(t1.frequency)
        f2 = float(t2.frequency)
        # 周波数が非正の場合は比が定義できないため 0 ビンへ丸める（決定的）
        fr1_bins = self._freq_ratio_bins(f1, fa) if (fa > 0 and f1 > 0) else [0]
        fr2_bins = self._freq_ratio_bins(f2, fa) if (fa > 0 and f2 > 0) else [0]

        rt_bin = self._quantize_time_ratio(r_t)

        hashes = []
        for b1 in fr1_bins:
            for b2 in fr2_bins:
                hashes.append(
                    (rt_bin << self._RT_SHIFT)
                    | (b1 << self._FR1_SHIFT)
                    | (b2 << self._FR2_SHIFT)
                )
        return hashes
    
    def _filter_peaks_by_density(self, peaks: List[Peak], debug: bool = False) -> List[Peak]:
        """周波数を考慮した定数マップ方式でピーク密度を制御する

        尺度不変ハッシュでは「時間方向のみで1ピークに潰す」旧方式が致命的だった。
        速度・ピッチ変化で"生き残るピーク"が変わり三つ組が対応しなくなるためである
        （同時刻の複数周波数ピークを潰すと、変化後に別の周波数が選ばれてしまう）。

        そこで時間窓ごとに振幅上位K件を"周波数をまたいで"保持する定数マップ方式に
        する。窓内の強いピークは尺度変化しても概ね強いまま残るため、選択が安定し、
        変換版でも同じ三つ組が再現されやすい。1秒あたりのピーク数は
        max_peaks_per_second で概ね一定に保つ（K = 窓幅 × max_peaks_per_second）。

        Args:
            peaks: 検出されたスペクトルピークのリスト
            debug: デバッグログを有効にする

        Returns:
            フィルタリングされたピークのリスト
        """
        logger = logging.getLogger(__name__)

        if len(peaks) == 0:
            return peaks

        if debug:
            logger.info(f"Peak count before density filtering: {len(peaks)}")

        window = self.density_time_window
        peaks_per_window = max(1, int(round(self.max_peaks_per_second * window)))

        # 時間窓ごとに振幅上位K件を保持（周波数をまたいで選択）
        buckets: dict = {}
        for peak in peaks:
            b = int(float(peak.time) / window)
            buckets.setdefault(b, []).append(peak)

        filtered_peaks: List[Peak] = []
        for bucket_peaks in buckets.values():
            if len(bucket_peaks) > peaks_per_window:
                bucket_peaks.sort(key=lambda p: p.amplitude, reverse=True)
                bucket_peaks = bucket_peaks[:peaks_per_window]
            filtered_peaks.extend(bucket_peaks)

        filtered_peaks.sort(key=lambda p: float(p.time))

        if debug:
            logger.info(f"Final filtered peak count: {len(filtered_peaks)}")

        return filtered_peaks


class AudioFingerprinter:
    """Shazam-styleアルゴリズムを使用した音声フィンガープリンティングのメインクラス"""
    
    def __init__(self, 
                 n_fft: int = 2048,
                 hop_length: int = 512,
                 sr: int = 22050,
                 min_amplitude: float = -60,
                 peak_neighborhood_size: int = 10,
                 enable_adaptive_params: bool = True,
                 audible_only: bool = False,
                 enable_numba_optimization: bool = True):
        """
        音声フィンガープリンターを初期化
        
        Args:
            n_fft: FFTウィンドウサイズ
            hop_length: 連続するフレーム間のサンプル数
            sr: サンプルレート
            min_amplitude: ピーク検出の最小振幅閾値
            peak_neighborhood_size: 局所最大値検出の近傍サイズ
            enable_adaptive_params: 適応的パラメータ調整を有効にする
            audible_only: 可聴域(20Hz-20kHz)のみを使う場合True
            enable_numba_optimization: Numba JIT最適化を有効にする
        """
        self.spectrogram_analyzer = SpectrogramAnalyzer(
            n_fft, hop_length, sr, enable_numba_optimization=enable_numba_optimization
        )
        self.hash_generator = HashGenerator()
        self.sr = sr
        self.min_amplitude = min_amplitude
        self.peak_neighborhood_size = peak_neighborhood_size
        self.enable_adaptive_params = enable_adaptive_params
        self.audible_only = audible_only
        
        # 適応的パラメータ調整器
        if enable_adaptive_params:
            self.parameter_tuner = AdaptiveParameterTuner()
            self.performance_monitor = PerformanceMonitor()
        else:
            self.parameter_tuner = None
            self.performance_monitor = None
        
    def load_audio_with_pydub(self, file_path: str ) -> np.ndarray:
        audio = AudioSegment.from_file(file_path)
        # モノラル化
        audio = audio.set_channels(1)
        # サンプリングレート変換
        if self.sr and audio.frame_rate != self.sr:
            audio = audio.set_frame_rate(self.sr)
        # NumPy配列へ変換
        samples = np.array(audio.get_array_of_samples()).astype(np.float32)
        # 正規化（16bitの場合）
        if audio.sample_width == 2:
            samples /= 32768.0
        return samples
    
    def load_audio(self, file_path: str) -> np.ndarray:
        """
        音声ファイルを読み込み
        
        Args:
            file_path: 音声ファイルのパス
            
        Returns:
            numpy配列としての音声信号
        """
        audio, _ = librosa.load(file_path, sr=self.sr)
        #audio = self.load_audio_with_pydub(file_path)
        return audio
    
    def fingerprint_audio(self, audio: np.ndarray, debug: bool = False) -> List[Fingerprint]:
        """
        音声信号のフィンガープリントを生成
        
        Args:
            audio: numpy配列としての音声信号
            debug: デバッグログを有効にする
            
        Returns:
            フィンガープリントのリスト
        """
        logger = logging.getLogger(__name__)
        
        start_time = time.time()
        
        if debug:
            logger.info(f"Audio length: {len(audio)} samples ({len(audio)/self.sr:.2f}s)")
            logger.info(f"Audio amplitude range: {np.min(audio):.4f} to {np.max(audio):.4f}")
            logger.info(f"Audio RMS: {np.sqrt(np.mean(audio**2)):.4f}")
        
        # 適応的パラメータ調整
        if self.enable_adaptive_params and self.parameter_tuner:
            characteristics = self.parameter_tuner.analyze_audio_characteristics(audio, self.sr)
            adjusted_params = self.parameter_tuner.adjust_parameters(characteristics)
            
            if debug:
                summary = self.parameter_tuner.get_parameter_summary(characteristics, adjusted_params)
                logger.info(f"Adaptive parameter adjustment:\n{summary}")
            
            # パラメータを適用
            min_amplitude = adjusted_params['min_amplitude']
            peak_neighborhood_size = adjusted_params['peak_neighborhood_size']
            
            # 共有インスタンスを書き換えず、この呼び出し専用のHashGeneratorを作成
            # （同一インスタンスを複数スレッドで使っても競合しないようにするため）
            hash_generator = HashGenerator(
                target_zone_size=adjusted_params['target_zone_size'],
                time_delta_range=self.hash_generator.time_delta_range,
                max_peaks_per_second=adjusted_params['max_peaks_per_second'],
                min_peak_separation=adjusted_params['min_peak_separation'],
            )
        else:
            min_amplitude = self.min_amplitude
            peak_neighborhood_size = self.peak_neighborhood_size
            hash_generator = self.hash_generator
        

        fingerprints = self._process_audio_sequential(
            audio, min_amplitude, peak_neighborhood_size, hash_generator, debug
        )
        
        # パフォーマンス監視
        processing_time = time.time() - start_time
        if self.performance_monitor:
            self.performance_monitor.record_processing_time("fingerprint_audio", processing_time)
            self.performance_monitor.record_fingerprint_count(len(fingerprints))
        
        if debug:
            logger.info(f"Processing time: {processing_time:.2f} seconds")
            logger.info(f"Generated fingerprint count: {len(fingerprints)}")
        
        return fingerprints
    
    def _process_audio_sequential(self, audio: np.ndarray, min_amplitude: float,
                                peak_neighborhood_size: int,
                                hash_generator: 'HashGenerator',
                                debug: bool) -> List[Fingerprint]:
        """音声を順次処理"""
        logger = logging.getLogger(__name__)
        
        # スペクトログラムを生成
        magnitude, frequencies, times = self.spectrogram_analyzer.generate_spectrogram(audio, audible_only=self.audible_only)
        
        if debug:
            logger.info(f"Spectrogram generated successfully. Shape: {magnitude.shape}")
        
        # ピークを検出
        peaks = self.spectrogram_analyzer.detect_peaks(
            magnitude, frequencies, times,
            min_amplitude, peak_neighborhood_size, debug
        )
        
        if len(peaks) == 0:
            peaks = self._retry_with_relaxed_parameters(magnitude, frequencies, times, debug, logger)
        
        # パフォーマンス監視
        if self.performance_monitor:
            self.performance_monitor.record_peak_count(len(peaks))
        
        # ハッシュを生成
        fingerprints = hash_generator.generate_hashes(peaks, debug)
        return fingerprints
    

    
    def _retry_with_relaxed_parameters(self, magnitude: np.ndarray, frequencies: np.ndarray,
                                     times: np.ndarray, debug: bool, logger) -> List[Peak]:
        """緩和されたパラメータでピーク検出を再試行"""
        if debug:
            logger.warning("No peaks detected! Retrying with relaxed parameters...")
        
        relaxed_peaks = self.spectrogram_analyzer.detect_peaks(
            magnitude, frequencies, times,
            min_amplitude=-80,  # より緩和された閾値
            peak_neighborhood_size=5,  # より小さな近傍
            debug=debug
        )
        
        if len(relaxed_peaks) > 0 and debug:
            logger.info(f"Found {len(relaxed_peaks)} peaks with relaxed parameters")
        
        return relaxed_peaks
    
    def fingerprint_file(self, file_path: str, debug: bool = False) -> List[Fingerprint]:
        """
        音声ファイルのフィンガープリントを生成
        
        Args:
            file_path: 音声ファイルのパス
            debug: デバッグログを有効にする
            
        Returns:
            フィンガープリントのリスト
        """
        logger = logging.getLogger(__name__)
        
        if debug:
            logger.info(f"Loading audio file: {file_path}")
        
        try:
            audio = self.load_audio(file_path)
            return self.fingerprint_audio(audio, debug)
        except Exception as e:
            error_msg = f"Error processing audio file {file_path}"
            logger.error(f"{error_msg}: {e}")
            raise AudioProcessingError(error_msg, e)
    
    def visualize_analysis(self, audio: np.ndarray, title: str = "voice analysis") -> None:
        """
        完全な解析プロセスを可視化
        
        Args:
            audio: 音声信号
            title: プロットのタイトル
        """
        # スペクトログラムを生成
        magnitude, frequencies, times = self.spectrogram_analyzer.generate_spectrogram(audio)
        
        # ピークを検出
        peaks = self.spectrogram_analyzer.detect_peaks(
            magnitude, frequencies, times,
            self.min_amplitude, self.peak_neighborhood_size
        )
        
        # 可視化
        self.spectrogram_analyzer.visualize_spectrogram(
            magnitude, frequencies, times, peaks, title
        )

# エクスポートするシンボルを定義
__all__ = [
    'Peak',
    'SpectrogramAnalyzer',
    'HashGenerator',
    'AudioFingerprinter'
]
