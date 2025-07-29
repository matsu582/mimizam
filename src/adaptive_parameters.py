"""適応的パラメータ調整モジュール - 音声の特性に基づいて動的にフィンガープリンティングパラメータを調整します。"""

import numpy as np
import librosa
import logging
try:
    from numba import njit
    NUMBA_AVAILABLE = True
except ImportError:
    def njit(**_kwargs):
        def decorator(func):
            return func
        return decorator
    NUMBA_AVAILABLE = False
@njit(cache=True)
def numba_spectral_entropy(power_spectrum_norm):
    entropy = 0.0
    for i in range(power_spectrum_norm.shape[0]):
        p = power_spectrum_norm[i]
        entropy -= p * np.log2(p + 1e-10)
    return entropy

@njit(cache=True)
def numba_zero_crossing_rate(audio):
    count = 0
    for i in range(1, audio.shape[0]):
        if (audio[i-1] < 0 and audio[i] > 0) or (audio[i-1] > 0 and audio[i] < 0):
            count += 1
    return count / audio.shape[0]
from typing import Dict, List, Tuple, Any


class AdaptiveParameterTuner:
    """音声特性に基づいて動的にパラメータを調整するクラス"""
    
    def __init__(self):
        """適応的パラメータチューナーを初期化（JITコンパイルを事前実行）"""
        self.logger = logging.getLogger(__name__)
        
        # ダミーデータでJITコンパイルを事前実行
        if NUMBA_AVAILABLE:
            dummy_power = np.ones(128, dtype=np.float32)
            dummy_audio = np.zeros(2048, dtype=np.float32)
            numba_spectral_entropy(dummy_power)
            numba_zero_crossing_rate(dummy_audio)
    
    def analyze_audio_characteristics(self, audio: np.ndarray, sr: int) -> Dict[str, float]:
        """
        音声の特性を分析
        
        Args:
            audio: 音声信号
            sr: サンプルレート
            
        Returns:
            音声特性の辞書
        """
        characteristics = {}
        
        # 音声の基本統計
        characteristics['duration'] = len(audio) / sr
        characteristics['rms'] = np.sqrt(np.mean(audio**2))
        characteristics['peak_amplitude'] = np.max(np.abs(audio))
        characteristics['silence_ratio'] = np.sum(np.abs(audio) < 0.001) / len(audio)
        
        # スペクトルエントロピー（Numba高速化）
        stft = librosa.stft(audio)
        magnitude = np.abs(stft)
        power_spectrum = np.mean(magnitude**2, axis=1)
        power_spectrum_norm = power_spectrum / np.sum(power_spectrum)
        spectral_entropy = numba_spectral_entropy(power_spectrum_norm)
        characteristics['spectral_entropy'] = spectral_entropy

        # ゼロクロッシング率（Numba高速化）
        zero_crossing_rate = numba_zero_crossing_rate(audio)
        characteristics['zero_crossing_rate'] = zero_crossing_rate
        
        # テンポ推定
        try:
            tempo, _ = librosa.beat.beat_track(y=audio, sr=sr)
            characteristics['tempo'] = tempo
        except Exception:
            characteristics['tempo'] = 120.0  # デフォルト値
        
        # 動的レンジ（音声の範囲）
        characteristics['dynamic_range'] = np.max(audio) - np.min(audio)
        
        # スペクトル重心（音色の特性）
        spectral_centroids = librosa.feature.spectral_centroid(y=audio, sr=sr)[0]
        characteristics['spectral_centroid_mean'] = np.mean(spectral_centroids)
        
        return characteristics
    
    def adjust_parameters(self, characteristics: Dict[str, float]) -> Dict[str, Any]:
        """
        音声特性に基づいてパラメータを調整
        
        Args:
            characteristics: 音声特性の辞書
            
        Returns:
            調整されたパラメータの辞書
        """
        params = self._get_default_parameters()
        params = self._adjust_for_silence(params, characteristics)
        params = self._adjust_for_complexity(params, characteristics)
        params = self._adjust_for_amplitude(params, characteristics)
        params = self._adjust_for_tempo(params, characteristics)
        params = self._adjust_for_duration(params, characteristics)
        params = self._adjust_for_spectral_characteristics(params, characteristics)
        
        return params
    
    def _get_default_parameters(self) -> Dict[str, Any]:
        """デフォルトパラメータを取得"""
        return {
            'min_amplitude': -60,
            'peak_neighborhood_size': 10,
            'target_zone_size': 5,
            'max_peaks_per_second': 15,
            'min_peak_separation': 0.02,
            'time_delta_range': (0.1, 2.0)
        }
    
    def _adjust_for_silence(self, params: Dict[str, Any], characteristics: Dict[str, float]) -> Dict[str, Any]:
        """静寂に基づいてパラメータを調整"""
        if characteristics['silence_ratio'] > 0.5:
            params['min_amplitude'] = -70
            params['max_peaks_per_second'] = 10
        return params
    
    def _adjust_for_complexity(self, params: Dict[str, Any], characteristics: Dict[str, float]) -> Dict[str, Any]:
        """複雑さに基づいてパラメータを調整"""
        if characteristics['spectral_entropy'] > 7:
            params['min_amplitude'] = -50
            params['peak_neighborhood_size'] = 15
            params['target_zone_size'] = 3
        elif characteristics['spectral_entropy'] < 4:
            params['target_zone_size'] = 8
            params['max_peaks_per_second'] = 20
        return params
    
    def _adjust_for_amplitude(self, params: Dict[str, Any], characteristics: Dict[str, float]) -> Dict[str, Any]:
        """振幅に基づいてパラメータを調整"""
        if characteristics['rms'] < 0.01:
            params['min_amplitude'] = -75
        elif characteristics['rms'] > 0.1:
            params['min_amplitude'] = -45
        return params
    
    def _adjust_for_tempo(self, params: Dict[str, Any], characteristics: Dict[str, float]) -> Dict[str, Any]:
        """テンポに基づいてパラメータを調整"""
        if characteristics['tempo'] > 140:
            params['max_peaks_per_second'] = 20
            params['min_peak_separation'] = 0.01
        elif characteristics['tempo'] < 80:
            params['max_peaks_per_second'] = 12
            params['min_peak_separation'] = 0.03
        return params
    
    def _adjust_for_duration(self, params: Dict[str, Any], characteristics: Dict[str, float]) -> Dict[str, Any]:
        """継続時間に基づいてパラメータを調整"""
        if characteristics['duration'] < 10:
            params['max_peaks_per_second'] = 25
        elif characteristics['duration'] > 120:
            params['max_peaks_per_second'] = 12
            params['target_zone_size'] = 3
        return params
    
    def _adjust_for_spectral_characteristics(self, params: Dict[str, Any], characteristics: Dict[str, float]) -> Dict[str, Any]:
        """スペクトル特性に基づいてパラメータを調整"""
        # 高い周波数成分が多い音声（音楽）
        if characteristics['spectral_centroid_mean'] > 3000:
            params['peak_neighborhood_size'] = 8
            params['max_peaks_per_second'] = 18
        # 低い周波数成分が多い音声（人の声、低音楽器）
        elif characteristics['spectral_centroid_mean'] < 1000:
            params['peak_neighborhood_size'] = 12
            params['target_zone_size'] = 6
        
        return params
    
    def get_parameter_summary(self, characteristics: Dict[str, float], adjusted_params: Dict[str, Any]) -> str:
        """
        パラメータ調整の概要を文字列で返す
        
        Args:
            characteristics: 音声特性
            adjusted_params: 調整されたパラメータ
            
        Returns:
            概要文字列
        """
        # テンポの値を適切にフォーマット
        tempo_value = characteristics['tempo']
        if isinstance(tempo_value, (list, np.ndarray)):
            tempo_str = f"{tempo_value[0]:.1f}"
        else:
            tempo_str = f"{tempo_value:.1f}"
        
        summary = f"""
Audio Analysis Results:
- Duration: {characteristics['duration']:.2f}s
- RMS: {characteristics['rms']:.4f}
- Silence ratio: {characteristics['silence_ratio']:.2f}
- Spectral entropy: {characteristics['spectral_entropy']:.2f}
- Tempo: {tempo_str} BPM
- Spectral centroid: {characteristics['spectral_centroid_mean']:.0f} Hz

Adjusted Parameters:
- Min amplitude: {adjusted_params['min_amplitude']} dB
- Peak neighborhood size: {adjusted_params['peak_neighborhood_size']}
- Target zone size: {adjusted_params['target_zone_size']}
- Max peaks/second: {adjusted_params['max_peaks_per_second']}
- Min peak separation: {adjusted_params['min_peak_separation']:.3f}s
"""
        return summary


class PerformanceMonitor:
    """フィンガープリンティングのパフォーマンスを監視するクラス"""
    
    def __init__(self):
        """パフォーマンス監視器を初期化"""
        self.logger = logging.getLogger(__name__)
        self.metrics = {}
        self.processing_times = []
        self.fingerprint_counts = []
        self.peak_counts = []
    
    def record_processing_time(self, operation: str, time_seconds: float):
        """処理時間を記録"""
        if operation not in self.metrics:
            self.metrics[operation] = []
        self.metrics[operation].append(time_seconds)
        self.processing_times.append(time_seconds)
    
    def record_fingerprint_count(self, count: int):
        """生成されたフィンガープリント数を記録"""
        self.fingerprint_counts.append(count)
    
    def record_peak_count(self, count: int):
        """検出されたピーク数を記録"""
        self.peak_counts.append(count)
    
    def get_performance_summary(self) -> str:
        """パフォーマンスサマリーを取得"""
        summary = "Performance Monitoring Results:\n"
        
        if self.processing_times:
            summary += f"- Average processing time: {np.mean(self.processing_times):.3f}s\n"
            summary += f"- Max processing time: {np.max(self.processing_times):.3f}s\n"
        
        if self.fingerprint_counts:
            summary += f"- Average fingerprint count: {np.mean(self.fingerprint_counts):.0f}\n"
            summary += f"- Fingerprint range: {np.min(self.fingerprint_counts)} - {np.max(self.fingerprint_counts)}\n"
        
        if self.peak_counts:
            summary += f"- Average peak count: {np.mean(self.peak_counts):.0f}\n"
        
        for operation, times in self.metrics.items():
            summary += f"- {operation}: average {np.mean(times):.3f}s\n"
        
        return summary
    
    def reset_metrics(self):
        """すべてのメトリクスをリセット"""
        self.metrics.clear()
        self.processing_times.clear()
        self.fingerprint_counts.clear()
        self.peak_counts.clear()
