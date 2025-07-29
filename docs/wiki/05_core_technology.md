# コア技術詳細

mimizamの音声指紋システムを支える核となる技術について詳しく解説します。本ドキュメントでは、音声処理、信号解析、機械学習の観点から、システムの技術的基盤を深く理解できます。

## 🎵 音声信号処理技術

### 短時間フーリエ変換（STFT）

mimizamの音声解析の基盤となる技術です。

#### 理論的背景
```python
# STFT の数学的定義
# X(m,k) = Σ[n] x[n] * w[n-mH] * e^(-j2πkn/N)
# 
# where:
# - m: 時間フレームインデックス
# - k: 周波数ビンインデックス  
# - H: ホップ長
# - N: FFTサイズ
# - w[n]: 窓関数

import librosa
import numpy as np

def compute_stft_detailed(audio, n_fft=2048, hop_length=512, window='hann'):
    """詳細なSTFT計算"""
    # 窓関数の適用
    window_func = np.hanning(n_fft)
    
    # STFT計算
    stft_matrix = librosa.stft(
        audio, 
        n_fft=n_fft,
        hop_length=hop_length,
        window=window_func,
        center=True,
        pad_mode='constant'
    )
    
    # 振幅スペクトログラム
    magnitude = np.abs(stft_matrix)
    
    # 位相スペクトログラム
    phase = np.angle(stft_matrix)
    
    return magnitude, phase, stft_matrix
```

#### パラメータ最適化
```python
def get_optimal_stft_params(audio: np.ndarray) -> dict:
    """音声内容に応じたSTFTパラメータ最適化"""
    
    optimization_profiles = {
        'high_frequency_resolution': {
            'n_fft': 4096,
            'hop_length': 1024,
            'window': 'blackman'
        },
        'high_time_resolution': {
            'n_fft': 1024,
            'hop_length': 256,
            'window': 'hann'
        },
        'balanced': {
            'n_fft': 2048,
            'hop_length': 512,
            'window': 'hann'
        }
    }
    
    # 音声特性分析
    spectral_centroid = librosa.feature.spectral_centroid(y=audio)[0]
    tempo, _ = librosa.beat.beat_track(y=audio)
    
    if np.mean(spectral_centroid) > 3000:  # 高周波成分が多い
        return optimization_profiles['high_frequency_resolution']
    elif tempo > 140:  # 高速な楽曲
        return optimization_profiles['high_time_resolution']
    else:
        return optimization_profiles['balanced']
```

### 窓関数の選択と影響

```python
import matplotlib.pyplot as plt

def compare_window_functions():
    """窓関数の比較"""
    n_fft = 2048
    
    windows = {
        'hann': np.hanning(n_fft),
        'hamming': np.hamming(n_fft),
        'blackman': np.blackman(n_fft),
        'kaiser': np.kaiser(n_fft, beta=8.6)
    }
    
    for name, window in windows.items():
        # 周波数応答
        freq_response = np.fft.fft(window, 8192)
        freq_response_db = 20 * np.log10(np.abs(freq_response))
        
        print(f"{name}窓:")
        print(f"  メインローブ幅: {calculate_main_lobe_width(freq_response_db):.2f} Hz")
        print(f"  サイドローブレベル: {np.max(freq_response_db[100:]):.2f} dB")
```

## 🔍 ピーク検出アルゴリズム

### 局所最大値検出

```python
from scipy import ndimage
from scipy.signal import find_peaks

class AdvancedPeakDetector:
    """高度なピーク検出器"""
    
    def __init__(self, min_amplitude=-60, neighborhood_size=20):
        self.min_amplitude = min_amplitude
        self.neighborhood_size = neighborhood_size
    
    def detect_peaks_adaptive(self, spectrogram: np.ndarray) -> List[Peak]:
        """適応的ピーク検出"""
        peaks = []
        
        # 動的閾値計算
        local_maxima = ndimage.maximum_filter(
            spectrogram, 
            size=self.neighborhood_size
        )
        
        # ピーク候補の特定
        peak_mask = (spectrogram == local_maxima) & (spectrogram > self.min_amplitude)
        
        # ピーク品質評価
        for time_idx, freq_idx in np.argwhere(peak_mask):
            amplitude = spectrogram[freq_idx, time_idx]
            
            # 周辺との対比評価
            local_contrast = self._calculate_local_contrast(
                spectrogram, freq_idx, time_idx
            )
            
            if local_contrast > 0.3:  # 十分なコントラスト
                peak = Peak(
                    time=time_idx * self.hop_length / self.sample_rate,
                    frequency=freq_idx * self.sample_rate / (2 * self.n_fft),
                    amplitude=amplitude
                )
                peaks.append(peak)
        
        return self._filter_peaks_by_density(peaks)
    
    def _calculate_local_contrast(self, spectrogram, freq_idx, time_idx):
        """局所コントラスト計算"""
        window_size = 5
        
        # 周辺領域の抽出
        freq_start = max(0, freq_idx - window_size)
        freq_end = min(spectrogram.shape[0], freq_idx + window_size + 1)
        time_start = max(0, time_idx - window_size)
        time_end = min(spectrogram.shape[1], time_idx + window_size + 1)
        
        local_region = spectrogram[freq_start:freq_end, time_start:time_end]
        center_value = spectrogram[freq_idx, time_idx]
        
        # コントラスト計算
        mean_surrounding = np.mean(local_region) - center_value / local_region.size
        return (center_value - mean_surrounding) / (center_value + mean_surrounding + 1e-10)
```

### ピーク密度制御

```python
class PeakDensityController:
    """ピーク密度制御"""
    
    def __init__(self, target_density=10, time_window=1.0):
        self.target_density = target_density  # peaks per second
        self.time_window = time_window
    
    def control_density(self, peaks: List[Peak]) -> List[Peak]:
        """ピーク密度の制御"""
        if not peaks:
            return peaks
        
        # 時間でソート
        peaks.sort(key=lambda p: p.time)
        
        controlled_peaks = []
        current_window_start = peaks[0].time
        current_window_peaks = []
        
        for peak in peaks:
            if peak.time - current_window_start <= self.time_window:
                current_window_peaks.append(peak)
            else:
                # 現在のウィンドウを処理
                selected = self._select_best_peaks(
                    current_window_peaks, 
                    self.target_density
                )
                controlled_peaks.extend(selected)
                
                # 新しいウィンドウ開始
                current_window_start = peak.time
                current_window_peaks = [peak]
        
        # 最後のウィンドウを処理
        if current_window_peaks:
            selected = self._select_best_peaks(
                current_window_peaks, 
                self.target_density
            )
            controlled_peaks.extend(selected)
        
        return controlled_peaks
    
    def _select_best_peaks(self, peaks: List[Peak], max_count: int) -> List[Peak]:
        """最良のピークを選択"""
        if len(peaks) <= max_count:
            return peaks
        
        # 振幅でソートして上位を選択
        peaks.sort(key=lambda p: p.amplitude, reverse=True)
        return peaks[:max_count]
```

## 🔐 ハッシュ生成技術

### アンカー・ターゲット方式

```python
def generate_robust_hashes(peaks: List[Peak]) -> List[Fingerprint]:
    """ロバストなハッシュ生成"""
    from mimizam import HashGenerator
    
    # 実際のHashGeneratorを使用
    generator = HashGenerator()
    fingerprints = generator.generate_hashes(peaks)
    
    return fingerprints

def analyze_hash_quality(peaks: List[Peak]) -> dict:
    """ハッシュ品質分析"""
    from mimizam import HashGenerator
    import hashlib
    
    generator = HashGenerator()
    fingerprints = generator.generate_hashes(peaks)
    
    # 基本統計
    analysis = {
        'total_fingerprints': len(fingerprints),
        'unique_hashes': len(set(fp.hash_value for fp in fingerprints)),
        'time_span': max(fp.time_offset for fp in fingerprints) - min(fp.time_offset for fp in fingerprints) if fingerprints else 0
    }
    
    # 衝突率計算
    if analysis['total_fingerprints'] > 0:
        analysis['collision_rate'] = 1 - (analysis['unique_hashes'] / analysis['total_fingerprints'])
    else:
        analysis['collision_rate'] = 0
    
    return analysis
```

### ハッシュ衝突対策

```python
def analyze_hash_distribution(fingerprints):
    """ハッシュ分布分析"""
    hash_counts = {}
    
    for fp in fingerprints:
        hash_prefix = fp.hash_value[:8]  # 最初の8文字
        hash_counts[hash_prefix] = hash_counts.get(hash_prefix, 0) + 1
    
    # 衝突率計算
    total_hashes = len(fingerprints)
    unique_prefixes = len(hash_counts)
    collision_rate = 1 - (unique_prefixes / total_hashes)
    
    print(f"ハッシュ衝突率: {collision_rate:.3%}")
    print(f"最大衝突数: {max(hash_counts.values())}")
    
    return hash_counts

def optimize_hash_parameters(peaks):
    """ハッシュパラメータ最適化"""
    from mimizam import HashGenerator
    
    best_params = None
    min_collision_rate = float('inf')
    
    # パラメータ候補
    freq_tolerances = [25, 50, 100]
    time_windows = [(1, 5), (1, 10), (2, 15)]
    
    for freq_tol in freq_tolerances:
        for time_window in time_windows:
            generator = HashGenerator()
            
            # 簡単な衝突率計算（実際の実装に合わせて調整）
            fingerprints = generator.generate_hashes(peaks)
            collision_rate = calculate_collision_rate(fingerprints)
            
            if collision_rate < min_collision_rate:
                min_collision_rate = collision_rate
                best_params = {
                    'freq_tolerance': freq_tol,
                    'target_zone_size': time_window
                }
    
    return best_params

def calculate_collision_rate(fingerprints):
    """衝突率計算"""
    hash_set = set(fp.hash_value for fp in fingerprints)
    return 1 - (len(hash_set) / len(fingerprints))
```

## 🧠 適応的パラメータ調整

### 音声特性分析

```python
def analyze_audio_characteristics(audio: np.ndarray, sr: int) -> dict:
    """音声特性分析"""
    import librosa
    import numpy as np
    
    characteristics = {}
    
    # 基本統計
    characteristics['duration'] = len(audio) / sr
    characteristics['rms_energy'] = np.sqrt(np.mean(audio**2))
    characteristics['zero_crossing_rate'] = calculate_zcr(audio)
    
    # スペクトル特性
    characteristics.update(analyze_spectral_features(audio, sr))
    
    # 複雑度指標
    characteristics['spectral_complexity'] = calculate_spectral_complexity(audio, sr)
    
    return characteristics

def analyze_spectral_features(audio: np.ndarray, sr: int) -> dict:
    """スペクトル特性分析"""
    import librosa
    import numpy as np
    
    # MFCC特徴量
    mfccs = librosa.feature.mfcc(y=audio, sr=sr, n_mfcc=13)
    
    # スペクトル特性
    spectral_centroids = librosa.feature.spectral_centroid(y=audio, sr=sr)[0]
    spectral_rolloff = librosa.feature.spectral_rolloff(y=audio, sr=sr)[0]
    spectral_bandwidth = librosa.feature.spectral_bandwidth(y=audio, sr=sr)[0]
    
    return {
        'mfcc_mean': np.mean(mfccs, axis=1),
        'mfcc_std': np.std(mfccs, axis=1),
        'spectral_centroid_mean': np.mean(spectral_centroids),
        'spectral_rolloff_mean': np.mean(spectral_rolloff),
        'spectral_bandwidth_mean': np.mean(spectral_bandwidth)
    }

def calculate_spectral_complexity(audio: np.ndarray, sr: int) -> float:
    """スペクトル複雑度計算"""
    import librosa
    import numpy as np
    
    # スペクトログラム計算
    stft = librosa.stft(audio)
    magnitude = np.abs(stft)
    
    # エントロピーベースの複雑度
    normalized_mag = magnitude / (np.sum(magnitude, axis=0, keepdims=True) + 1e-10)
    entropy = -np.sum(normalized_mag * np.log(normalized_mag + 1e-10), axis=0)
    
    return np.mean(entropy)

def calculate_zcr(audio: np.ndarray) -> float:
    """ゼロ交差率計算"""
    import numpy as np
    return np.mean(np.abs(np.diff(np.sign(audio)))) / 2
```

### 動的パラメータ調整

```python
def adjust_parameters_dynamically(characteristics: dict) -> dict:
    """動的パラメータ調整"""
    from mimizam import AdaptiveParameterTuner
    
    tuner = AdaptiveParameterTuner()
    
    # 音声特性に基づく最適化
    # AdaptiveParameterTunerの実際のメソッドを使用
    adjustment_rules = {
        'high_complexity': {
            'min_amplitude': -70,
            'peak_neighborhood_size': 30,
            'target_zone_size': (2, 15)
        },
        'low_complexity': {
            'min_amplitude': -50,
            'peak_neighborhood_size': 15,
            'target_zone_size': (1, 8)
        },
        'noisy_environment': {
            'min_amplitude': -40,
            'peak_neighborhood_size': 25,
            'target_zone_size': (1, 5)
        }
    }
    
    adjusted_params = {}
    
    # 複雑度に基づく調整
    if characteristics.get('spectral_complexity', 0) > 0.8:
        adjusted_params.update(adjustment_rules['high_complexity'])
    elif characteristics.get('spectral_complexity', 0) < 0.3:
        adjusted_params.update(adjustment_rules['low_complexity'])
    
    # ノイズレベルに基づく調整
    if characteristics.get('zero_crossing_rate', 0) > 0.1:
        adjusted_params.update(adjustment_rules['noisy_environment'])
    
    # エネルギーレベルに基づく調整
    if characteristics.get('rms_energy', 0) < 0.01:
        adjusted_params['min_amplitude'] = adjusted_params.get('min_amplitude', -60) - 10
    
    return adjusted_params
```

## 🔗 関連ドキュメント

- [音声指紋生成アルゴリズム](./13_fingerprint_generation.md) - 実装詳細
- [適応パラメータ調整](./15_adaptive_parameters.md) - パラメータ最適化
- [パフォーマンス最適化](./12_performance_optimization.md) - 性能向上技術
- [システムアーキテクチャ](./04_architecture.md) - 全体構成
- [デバッグとトラブルシューティング](./21_debugging.md) - 問題解決

## 💡 技術的考察

### 1. 精度と速度のトレードオフ
- **高精度設定**: より多くのピーク、細かい時間分解能
- **高速設定**: 少ないピーク、粗い時間分解能
- **適応設定**: 音声特性に応じた動的調整

### 2. ロバスト性の向上
- **複数ハッシュ方式**: 異なるアプローチの組み合わせ
- **適応的閾値**: 音声特性に応じた動的調整
- **ピーク品質評価**: コントラストベースの選択

### 3. スケーラビリティ
- **ハッシュ分散**: 衝突率の最小化
- **メモリ効率**: 大規模データベース対応
- **並列処理**: マルチコア活用

これらの技術により、mimizamは高精度で効率的な音声指紋システムを実現しています。
