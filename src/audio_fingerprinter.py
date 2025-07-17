"""
Shazam-style音声指紋

スペクトログラム生成、ピーク検出、ハッシュベースフィンガープリンティングを含む、
音声指紋に関するShazam風のアルゴリズムを実装します。
"""

import numpy as np
import librosa
import matplotlib.pyplot as plt
from scipy.signal import find_peaks
from skimage.feature import peak_local_max
from typing import List, Tuple, Dict, Optional
import hashlib
import sqlite3
from dataclasses import dataclass
import pickle

import logging
import time
from .adaptive_parameters import AdaptiveParameterTuner, PerformanceMonitor
from .database_base import Fingerprint


@dataclass
class Peak:
    """時間-周波数領域のスペクトルピークを表現"""
    time: float
    frequency: float
    amplitude: float


class SpectrogramAnalyzer:
    """スペクトログラム生成とピーク検出を処理"""
    
    def __init__(self, 
                 n_fft: int = 2048, 
                 hop_length: int = 512, 
                 sr: int = 22050):
        """
        スペクトログラム解析器を初期化
        
        Args:
            n_fft: FFTウィンドウサイズ
            hop_length: 連続するフレーム間のサンプル数
            sr: サンプルレート
        """
        self.n_fft = n_fft
        self.hop_length = hop_length
        self.sr = sr
    
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
            return mask, adaptive_threshold
        
        return mask, min_amplitude


    def _find_local_maxima(self, magnitude: np.ndarray, mask: np.ndarray, 
                          frequencies: np.ndarray, times: np.ndarray,
                          peak_neighborhood_size: int, debug: bool) -> List[Peak]:
        """スペクトログラム内の局所最大値を検出"""
        logger = logging.getLogger(__name__)
        
        peaks = []
        # 局所最大値の座標を取得
        coords = peak_local_max(
            magnitude,
            min_distance=peak_neighborhood_size,
            threshold_abs=None  # マスクで閾値制御
        )
        # マスクを適用
        coords = coords[mask[coords[:, 0], coords[:, 1]]]
        candidates_found = coords.shape[0]
        # 有効範囲外の座標を削除
        valid = []
        f_start, f_end = peak_neighborhood_size, magnitude.shape[0] - peak_neighborhood_size
        t_start, t_end = peak_neighborhood_size, magnitude.shape[1] - peak_neighborhood_size
        for f_idx, t_idx in coords:
            if f_start <= f_idx < f_end and t_start <= t_idx < t_end:
                valid.append((f_idx, t_idx))
        # Peakオブジェクトを作成
        peaks = [Peak(time=times[t], frequency=frequencies[f], amplitude=magnitude[f, t])
                 for f, t in valid]
        
        if debug:
            logger.info(f"Candidate points: {candidates_found}")
            logger.info(f"Detected peaks: {len(peaks)}")
            if len(peaks) > 0:
                amplitudes = [p.amplitude for p in peaks]
                logger.info(f"Peak amplitude range: {np.min(amplitudes):.2f} to {np.max(amplitudes):.2f} dB")
        
        return peaks
    
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
                  extent=[times[0], times[-1], frequencies[0], frequencies[-1]])
        
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
    
    def __init__(self, 
                 target_zone_size: int = 5,  # 8から5に削減
                 time_delta_range: Tuple[float, float] = (0.1, 2.0),  # 範囲を狭める
                 max_peaks_per_second: int = 15,  # 新規: 1秒あたりの最大ピーク数
                 min_peak_separation: float = 0.02):  # 新規: ピーク間の最小時間間隔
        """
        ハッシュジェネレータを初期化
        
        Args:
            target_zone_size: 各アンカーに対して考慮するターゲットピーク数
            time_delta_range: 考慮する時間差の範囲（秒）
            max_peaks_per_second: 1秒あたりの最大ピーク数（密度制御）
            min_peak_separation: ピーク間の最小時間間隔（秒）
        """
        self.target_zone_size = target_zone_size
        self.time_delta_range = time_delta_range
        self.max_peaks_per_second = max_peaks_per_second
        self.min_peak_separation = min_peak_separation
    
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
        sorted_peaks = sorted(filtered_peaks, key=lambda p: p.time)
        
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
        """ターゲットピークからフィンガープリントを作成"""
        fingerprints = []
        
        for target_peak in target_peaks:
            time_delta = target_peak.time - anchor_peak.time
            valid_time_deltas.append(time_delta)
            
            hash_value = self._create_hash(anchor_peak, target_peak)
            
            if hash_value not in seen_hashes:
                seen_hashes.add(hash_value)
                fingerprint = Fingerprint(
                    hash_value=hash_value,
                    time_offset=anchor_peak.time
                )
                fingerprints.append(fingerprint)
        
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
        """
        target_peaks = []
        
        for peak in candidate_peaks[:self.target_zone_size]:
            time_delta = peak.time - anchor.time
            
            # 時間差が許容範囲内かどうかをチェック
            if self.time_delta_range[0] <= time_delta <= self.time_delta_range[1]:
                target_peaks.append(peak)
        
        return target_peaks
    
    def _create_hash(self, anchor: Peak, target: Peak) -> str:
        """
        広い速度変化に対する改良されたロバスト性を持つアンカー-ターゲットピークペアからハッシュを作成
        
        Args:
            anchor: アンカーピーク
            target: ターゲットピーク
            
        Returns:
            ハッシュ文字列
        """
        # より堅牢な周波数量子化 - 広い速度変化対応のため大きなビン
        f1_quantized = int(anchor.frequency // 30) * 30  # 0.5x-2x速度変化対応のため大きなビン
        f2_quantized = int(target.frequency // 30) * 30
        
        # より広い速度範囲対応の適応的量子化を持つ時間差
        time_delta_raw = target.time - anchor.time
        
        # 0.5x-2x範囲のより良いカバレッジのため対数時間量子化を使用
        if time_delta_raw > 0:
            # より良い速度許容度のため50msビン（10msの代わり）に量子化
            time_delta = int(time_delta_raw * 20) * 5  # センチ秒単位での50msビン
        else:
            time_delta = 0
        
        # 速度変化に対する改良されたロバスト性を持つハッシュを作成
        primary_hash_input = f"{f1_quantized}|{f2_quantized}|{time_delta}"
        
        # ハッシュを生成
        hash_object = hashlib.sha256(primary_hash_input.encode())
        return hash_object.hexdigest()
    
    def _filter_peaks_by_density(self, peaks: List[Peak], debug: bool = False) -> List[Peak]:
        """
        ピーク密度に基づいてピークをフィルタリング
        
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
        
        # ピークを時間順にソート
        sorted_peaks = sorted(peaks, key=lambda p: p.time)
        
        # 最小間隔に基づくフィルタリング
        filtered_peaks = []
        last_time = -float('inf')
        
        for peak in sorted_peaks:
            if peak.time - last_time >= self.min_peak_separation:
                filtered_peaks.append(peak)
                last_time = peak.time
        
        if debug:
            logger.info(f"After minimum interval filtering: {len(filtered_peaks)} peaks")
        
        # 1秒あたりの最大ピーク数制限
        if len(filtered_peaks) == 0:
            return filtered_peaks
        
        duration = filtered_peaks[-1].time - filtered_peaks[0].time
        if duration > 0:
            current_density = len(filtered_peaks) / duration
            
            if current_density > self.max_peaks_per_second:
                # 振幅の高いピークを優先して選択
                target_count = int(duration * self.max_peaks_per_second)
                filtered_peaks.sort(key=lambda p: p.amplitude, reverse=True)
                filtered_peaks = filtered_peaks[:target_count]
                
                # 再度時間順にソート
                filtered_peaks.sort(key=lambda p: p.time)
                
                if debug:
                    logger.info(f"After density limit: {len(filtered_peaks)} peaks")
        
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
                 audible_only: bool = False):
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
        """
        self.spectrogram_analyzer = SpectrogramAnalyzer(n_fft, hop_length, sr)
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
        

    
    def load_audio(self, file_path: str) -> np.ndarray:
        """
        音声ファイルを読み込み
        
        Args:
            file_path: 音声ファイルのパス
            
        Returns:
            numpy配列としての音声信号
        """
        audio, _ = librosa.load(file_path, sr=self.sr)
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
            
            # HashGeneratorのパラメータも更新
            self.hash_generator.target_zone_size = adjusted_params['target_zone_size']
            self.hash_generator.max_peaks_per_second = adjusted_params['max_peaks_per_second']
            self.hash_generator.min_peak_separation = adjusted_params['min_peak_separation']
        else:
            min_amplitude = self.min_amplitude
            peak_neighborhood_size = self.peak_neighborhood_size
        

        fingerprints = self._process_audio_sequential(audio, min_amplitude, peak_neighborhood_size, debug)
        
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
                                peak_neighborhood_size: int, debug: bool) -> List[Fingerprint]:
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
        fingerprints = self.hash_generator.generate_hashes(peaks, debug)
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
            if debug:
                logger.error(f"Error processing audio file {file_path}: {e}")
            raise
    
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
