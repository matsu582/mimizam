# 音声指紋エンジン

> 関連するソースファイル

このドキュメントでは、生の音声信号をShazam風アルゴリズムを使用してコンパクトな指紋ハッシュに変換するコア音声指紋エンジンについて説明します。エンジンは、スペクトログラム生成、ピーク検出、ハッシュ作成、適応的パラメータ最適化を含みます。

他のコンポーネントについては、[データベース層](./03_2_database_layer.md)および[マッチング・識別システム](./03_3_matching_identification.md)を参照してください。

## 概要

音声指紋エンジンは、Avery Li-Chun Wangの2003年Shazamアルゴリズムに基づくコンステレーションマップアプローチを実装しています。システムは以下の4つの主要段階で音声を処理します：

| 処理段階 | 説明 | 主要技術 |
|---------|------|---------|
| **スペクトログラム生成** | 短時間フーリエ変換（STFT）による時間-周波数解析 | librosa STFT、ハニング窓 |
| **ピーク検出** | 局所最大値アルゴリズムによるスペクトルピークの特定 | 適応的閾値、近傍抑制 |
| **ハッシュ生成** | アンカー・ターゲットピークペアリング | SHA-1ハッシュ、時間量子化 |
| **適応的パラメータ調整** | 音声特性に基づく自動最適化 | 動的範囲分析、品質評価 |

## 音声指紋パイプライン

```
生音声ファイル
    │
    ▼
音声読み込み (librosa)
    │
    ▼
スペクトログラム生成 (STFT)
    │
    ▼
ピーク検出 (局所最大値)
    │
    ▼
ハッシュ生成 (アンカー・ターゲット)
    │
    ▼
指紋データベース保存
```

## 主要コンポーネント

### AudioFingerprinterクラス

中核的な音声処理コンポーネントです。

```python
class AudioFingerprinter:
    def __init__(self, **params):
        # 音声処理パラメータ
        self.sample_rate = params.get('sample_rate', 22050)
        self.n_fft = params.get('n_fft', 2048)
        self.hop_length = params.get('hop_length', 512)
        self.window = params.get('window', 'hann')
        
        # ピーク検出パラメータ
        self.peak_threshold = params.get('peak_threshold', 0.15)
        self.min_peak_distance = params.get('min_peak_distance', 10)
        
        # ハッシュ生成パラメータ
        self.target_zone_size = params.get('target_zone_size', 5)
        self.max_time_delta = params.get('max_time_delta', 200)
    
    def generate_fingerprints(self, audio_path):
        """音声ファイルから指紋を生成"""
        audio_data, sr = librosa.load(audio_path, sr=self.sample_rate)
        return self._process_audio_data(audio_data)
    
    def _process_audio_data(self, audio_data):
        """音声データから指紋を生成"""
        spectrogram = self._generate_spectrogram(audio_data)
        peaks = self._detect_peaks(spectrogram)
        fingerprints = self._generate_hashes(peaks)
        return fingerprints
```

### スペクトログラム生成

短時間フーリエ変換（STFT）を使用して音声信号を時間-周波数表現に変換します。

```python
def _generate_spectrogram(self, audio_data):
    """STFTによるスペクトログラム生成"""
    import librosa
    import numpy as np
    
    # STFT計算
    stft = librosa.stft(
        audio_data,
        n_fft=self.n_fft,
        hop_length=self.hop_length,
        window=self.window
    )
    
    # パワースペクトログラムに変換
    magnitude = np.abs(stft)
    
    # デシベルスケールに変換
    spectrogram_db = librosa.amplitude_to_db(magnitude, ref=np.max)
    
    return spectrogram_db
```

### ピーク検出

スペクトログラムから局所最大値を検出し、特徴的なスペクトルピークを特定します。

```python
def _detect_peaks(self, spectrogram):
    """局所最大値アルゴリズムによるピーク検出"""
    from scipy.ndimage import maximum_filter
    import numpy as np
    
    # 局所最大値フィルタを適用
    neighborhood_size = (self.peak_neighborhood_size, self.peak_neighborhood_size)
    local_maxima = maximum_filter(spectrogram, size=neighborhood_size) == spectrogram
    
    # 閾値を適用
    threshold_mask = spectrogram > self.peak_threshold
    
    # ピークマスクを作成
    peak_mask = local_maxima & threshold_mask
    
    # ピーク座標を取得
    peak_coords = np.where(peak_mask)
    peaks = list(zip(peak_coords[1], peak_coords[0]))  # (time, frequency)
    
    return peaks
```

### ハッシュ生成

アンカー・ターゲットピークペアリングによる一意の指紋ハッシュを生成します。

```python
def _generate_hashes(self, peaks):
    """アンカー・ターゲットペアリングによるハッシュ生成"""
    fingerprints = []
    
    for i, anchor_peak in enumerate(peaks):
        anchor_time, anchor_freq = anchor_peak
        
        # ターゲットゾーン内のピークを検索
        for j in range(i + 1, min(i + self.target_zone_size + 1, len(peaks))):
            target_peak = peaks[j]
            target_time, target_freq = target_peak
            
            # 時間差を計算
            time_delta = target_time - anchor_time
            
            # 最大時間差を超える場合はスキップ
            if time_delta > self.max_time_delta:
                break
            
            # ハッシュを生成
            hash_value = self._create_hash(anchor_freq, target_freq, time_delta)
            
            fingerprints.append({
                'hash': hash_value,
                'time_offset': anchor_time,
                'anchor_freq': anchor_freq,
                'target_freq': target_freq,
                'time_delta': time_delta
            })
    
    return fingerprints

def _create_hash(self, anchor_freq, target_freq, time_delta):
    """周波数ペアと時間差からハッシュを作成"""
    import hashlib
    
    # ハッシュ文字列を作成
    hash_string = f"{anchor_freq}|{target_freq}|{time_delta}"
    
    # SHA-1ハッシュを計算
    hash_object = hashlib.sha1(hash_string.encode())
    hash_hex = hash_object.hexdigest()
    
    # 32ビット整数に変換
    hash_int = int(hash_hex[:8], 16)
    
    return hash_int
```

## パフォーマンス最適化

### Numba JIT最適化

mimizamは、数値計算集約的な関数でNumba JIT最適化を活用し、大幅な性能向上を実現します。

| 最適化技術 | 性能向上 | 適用範囲 |
|-----------|---------|---------|
| **Numba JIT最適化** | 3-10倍高速化 | ピーク検出、ハッシュ生成 |
| **適応的パラメータ調整** | 音声特性に基づく最適化 | 全処理段階 |
| **パフォーマンス監視** | リアルタイム性能追跡 | システム全体 |

#### キーアルゴリズム

**Numba最適化ピーク検出**

```python
try:
    from numba import jit
    
    @jit(nopython=True)
    def _find_peaks_optimized(spectrogram, threshold, min_distance):
        """Numba最適化されたピーク検出アルゴリズム"""
        peaks = []
        rows, cols = spectrogram.shape
        
        for i in range(min_distance, rows - min_distance):
            for j in range(min_distance, cols - min_distance):
                if spectrogram[i, j] > threshold:
                    is_peak = True
                    
                    # 近傍をチェック
                    for di in range(-min_distance, min_distance + 1):
                        for dj in range(-min_distance, min_distance + 1):
                            if spectrogram[i + di, j + dj] > spectrogram[i, j]:
                                is_peak = False
                                break
                        if not is_peak:
                            break
                    
                    if is_peak:
                        peaks.append((j, i))  # (time, frequency)
        
        return peaks
    
    NUMBA_AVAILABLE = True
except ImportError:
    NUMBA_AVAILABLE = False

def _fallback_peak_detection(spectrogram, threshold, min_distance):
    """フォールバックピーク検出（Numba未使用）"""
    from scipy.ndimage import maximum_filter
    import numpy as np
    
    # 局所最大値フィルタを適用
    neighborhood_size = (min_distance, min_distance)
    local_maxima = maximum_filter(spectrogram, size=neighborhood_size) == spectrogram
    
    # 閾値を適用
    threshold_mask = spectrogram > threshold
    
    # ピークマスクを作成
    peak_mask = local_maxima & threshold_mask
    
    # ピーク座標を取得
    peak_coords = np.where(peak_mask)
    peaks = list(zip(peak_coords[1], peak_coords[0]))  # (time, frequency)
    
    return peaks
```

**ハッシュ生成プロセス**

```python
def _generate_hashes(self, peaks):
    """アンカー・ターゲットペアリングによるハッシュ生成"""
    fingerprints = []
    
    for i, anchor_peak in enumerate(peaks):
        anchor_time, anchor_freq = anchor_peak
        
        # ターゲットゾーン内のピークを検索
        for j in range(i + 1, min(i + self.target_zone_size + 1, len(peaks))):
            target_peak = peaks[j]
            target_time, target_freq = target_peak
            
            # 時間差を計算
            time_delta = target_time - anchor_time
            
            # 最大時間差を超える場合はスキップ
            if time_delta > self.max_time_delta:
                break
            
            # ハッシュを生成
            hash_value = self._create_hash(anchor_freq, target_freq, time_delta)
            
            fingerprints.append({
                'hash': hash_value,
                'time_offset': anchor_time,
                'anchor_freq': anchor_freq,
                'target_freq': target_freq,
                'time_delta': time_delta
            })
    
    return fingerprints
```

### 適応的パラメータ調整

音声特性に基づく自動パラメータ最適化システムにより、様々な音声コンテンツに対して最適な性能を実現します。

#### 音声特性分析

| 分析項目 | 測定方法 | 調整対象パラメータ |
|---------|---------|------------------|
| **動的範囲** | max(audio) - min(audio) | peak_threshold |
| **RMSエネルギー** | sqrt(mean(audio²)) | min_peak_distance |
| **ゼロ交差率** | 符号変化の頻度 | window_size |
| **スペクトル重心** | 周波数重心の計算 | target_zone_size |

```python
class AdaptiveParameterTuner:
    def __init__(self, fingerprinter):
        self.fingerprinter = fingerprinter
        self.optimization_history = []
    
    def analyze_audio_characteristics(self, audio_data):
        """包括的な音声特性分析"""
        import numpy as np
        import librosa
        
        # 基本統計量
        dynamic_range = np.max(audio_data) - np.min(audio_data)
        rms_energy = np.sqrt(np.mean(audio_data ** 2))
        
        # ゼロ交差率
        zero_crossings = np.sum(np.diff(np.sign(audio_data)) != 0)
        zero_crossing_rate = zero_crossings / len(audio_data)
        
        # スペクトル特性
        spectrogram = self.fingerprinter._generate_spectrogram(audio_data)
        spectral_centroid = np.mean(np.sum(spectrogram * np.arange(spectrogram.shape[0])[:, np.newaxis], axis=0) / np.sum(spectrogram, axis=0))
        
        # スペクトル密度
        spectral_density = np.mean(np.sum(spectrogram > -60, axis=0))  # -60dB以上の周波数成分
        
        # ノイズレベル推定
        noise_floor = np.percentile(spectrogram, 10)  # 下位10%をノイズフロアとして推定
        
        return {
            'dynamic_range': dynamic_range,
            'rms_energy': rms_energy,
            'zero_crossing_rate': zero_crossing_rate,
            'spectral_centroid': spectral_centroid,
            'spectral_density': spectral_density,
            'noise_floor': noise_floor
        }
    
    def adjust_parameters(self, characteristics):
        """音声特性に基づく最適パラメータ調整"""
        adjustments = {}
        
        # 動的範囲に基づく調整
        if characteristics['dynamic_range'] < 0.1:
            adjustments['peak_threshold'] = self.fingerprinter.peak_threshold * 0.7
        elif characteristics['dynamic_range'] > 0.8:
            adjustments['peak_threshold'] = self.fingerprinter.peak_threshold * 1.3
        
        # エネルギーレベルに基づく調整
        if characteristics['rms_energy'] < 0.01:
            adjustments['min_peak_distance'] = max(5, self.fingerprinter.min_peak_distance - 3)
        elif characteristics['rms_energy'] > 0.1:
            adjustments['min_peak_distance'] = self.fingerprinter.min_peak_distance + 3
        
        # スペクトル密度に基づく調整
        if characteristics['spectral_density'] < 50:
            adjustments['target_zone_size'] = max(3, self.fingerprinter.target_zone_size - 1)
        elif characteristics['spectral_density'] > 200:
            adjustments['target_zone_size'] = min(8, self.fingerprinter.target_zone_size + 1)
        
        # ノイズレベルに基づく調整
        if characteristics['noise_floor'] > -40:  # 高ノイズ環境
            adjustments['peak_threshold'] = adjustments.get('peak_threshold', self.fingerprinter.peak_threshold) * 1.2
            adjustments['min_peak_distance'] = adjustments.get('min_peak_distance', self.fingerprinter.min_peak_distance) + 2
        
        return adjustments
    
    def apply_adjustments(self, adjustments):
        """調整をfingerprinterに適用し、履歴を記録"""
        original_params = {}
        for param, value in adjustments.items():
            original_params[param] = getattr(self.fingerprinter, param)
            setattr(self.fingerprinter, param, value)
        
        # 最適化履歴を記録
        self.optimization_history.append({
            'original_params': original_params,
            'adjusted_params': adjustments,
            'timestamp': time.time()
        })
    
    def get_optimization_summary(self):
        """最適化履歴の要約を取得"""
        if not self.optimization_history:
            return "最適化履歴なし"
        
        return {
            'optimization_count': len(self.optimization_history),
            'most_recent': self.optimization_history[-1],
            'parameter_trends': self._analyze_parameter_trends()
        }
```

## 可視化機能

スペクトログラムとピーク検出結果の可視化機能を提供します。

```python
def visualize_fingerprinting_process(self, audio_path, output_path=None):
    """指紋生成プロセスの可視化"""
    import matplotlib.pyplot as plt
    import librosa
    import numpy as np
    
    # 音声データを読み込み
    audio_data, sr = librosa.load(audio_path, sr=self.sample_rate)
    
    # スペクトログラムを生成
    spectrogram = self._generate_spectrogram(audio_data)
    
    # ピークを検出
    peaks = self._detect_peaks(spectrogram)
    
    # 可視化
    fig, axes = plt.subplots(3, 1, figsize=(15, 12))
    
    # 1. 波形
    time_axis = np.linspace(0, len(audio_data) / sr, len(audio_data))
    axes[0].plot(time_axis, audio_data)
    axes[0].set_title('音声波形')
    axes[0].set_xlabel('時間 (秒)')
    axes[0].set_ylabel('振幅')
    
    # 2. スペクトログラム
    librosa.display.specshow(
        spectrogram,
        sr=sr,
        hop_length=self.hop_length,
        x_axis='time',
        y_axis='hz',
        ax=axes[1]
    )
    axes[1].set_title('スペクトログラム')
    
    # 3. ピーク検出結果
    librosa.display.specshow(
        spectrogram,
        sr=sr,
        hop_length=self.hop_length,
        x_axis='time',
        y_axis='hz',
        ax=axes[2]
    )
    
    # ピークをプロット
    if peaks:
        peak_times = [p[0] * self.hop_length / sr for p in peaks]
        peak_freqs = [p[1] * sr / self.n_fft for p in peaks]
        axes[2].scatter(peak_times, peak_freqs, c='red', s=10, alpha=0.7)
    
    axes[2].set_title('検出されたピーク')
    
    plt.tight_layout()
    
    if output_path:
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
    else:
        plt.show()
    
    return fig
```

## 品質評価

指紋品質の自動評価機能を提供します。

```python
def evaluate_fingerprint_quality(self, fingerprints):
    """指紋品質を評価"""
    if not fingerprints:
        return {
            'quality_score': 0.0,
            'fingerprint_count': 0,
            'density': 0.0,
            'time_distribution': 0.0
        }
    
    # 指紋数
    fingerprint_count = len(fingerprints)
    
    # 時間密度を計算
    time_offsets = [fp['time_offset'] for fp in fingerprints]
    time_span = max(time_offsets) - min(time_offsets) if time_offsets else 1
    density = fingerprint_count / max(time_span, 1)
    
    # 時間分布の均一性を評価
    time_bins = np.histogram(time_offsets, bins=10)[0]
    time_distribution = 1.0 - np.std(time_bins) / (np.mean(time_bins) + 1e-6)
    
    # 総合品質スコア
    quality_score = min(1.0, (
        0.4 * min(fingerprint_count / 100, 1.0) +
        0.3 * min(density / 10, 1.0) +
        0.3 * time_distribution
    ))
    
    return {
        'quality_score': quality_score,
        'fingerprint_count': fingerprint_count,
        'density': density,
        'time_distribution': time_distribution
    }
```

## 使用例

### 基本的な指紋生成

```python
from mimizam.audio_fingerprinter import AudioFingerprinter

# 指紋生成器を初期化
fingerprinter = AudioFingerprinter(
    sample_rate=22050,
    peak_threshold=0.15,
    min_peak_distance=10
)

# 音声ファイルから指紋を生成
fingerprints = fingerprinter.generate_fingerprints("song.wav")

print(f"生成された指紋数: {len(fingerprints)}")
for fp in fingerprints[:5]:  # 最初の5個を表示
    print(f"ハッシュ: {fp['hash']}, 時間: {fp['time_offset']}")
```

### 適応的パラメータ調整

```python
from mimizam.adaptive_parameters import AdaptiveParameterTuner

# 適応的調整器を初期化
tuner = AdaptiveParameterTuner(fingerprinter)

# 音声特性を分析
audio_data, sr = librosa.load("song.wav", sr=22050)
characteristics = tuner.analyze_audio_characteristics(audio_data)

# パラメータを調整
adjustments = tuner.adjust_parameters(characteristics)
tuner.apply_adjustments(adjustments)

# 調整後の指紋生成
fingerprints = fingerprinter.generate_fingerprints("song.wav")
```

### 可視化

```python
# 指紋生成プロセスを可視化
fingerprinter.visualize_fingerprinting_process(
    "song.wav",
    output_path="fingerprinting_process.png"
)

# 指紋品質を評価
quality = fingerprinter.evaluate_fingerprint_quality(fingerprints)
print(f"品質スコア: {quality['quality_score']:.3f}")
```

音声指紋エンジンは、mimizamシステムの中核となるコンポーネントであり、高精度な音声識別を実現するための基盤を提供します。
