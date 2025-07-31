# 音声フィンガープリンティングエンジン

## 概要

音声フィンガープリンティングエンジンは、mimizamシステムの中核コンポーネントであり、生の音声データを一意の識別可能なフィンガープリントに変換する役割を担います。このエンジンは、Shazamのような商用音楽識別システムで使用されている実証済みのアルゴリズムに基づいて設計されています。

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
            'latest_adjustments': self.optimization_history[-1]['adjusted_params'] if self.optimization_history else {},
            'performance_improvements': self._calculate_performance_improvements()
        }
    
    def _calculate_performance_improvements(self):
        """パフォーマンス改善の計算"""
        if len(self.optimization_history) < 2:
            return "十分なデータなし"
        
        # 最新と最初の最適化を比較
        first_optimization = self.optimization_history[0]
        latest_optimization = self.optimization_history[-1]
        
        improvements = {}
        for param in latest_optimization['adjusted_params']:
            if param in first_optimization['original_params']:
                original_value = first_optimization['original_params'][param]
                current_value = latest_optimization['adjusted_params'][param]
                improvement_ratio = current_value / original_value if original_value != 0 else 1.0
                improvements[param] = f"{improvement_ratio:.2f}x"
        
        return improvements
```

## 使用例とベンチマーク

### 基本的な使用例

```python
# 基本的なAudioFingerprinter使用例
fingerprinter = AudioFingerprinter(
    sample_rate=22050,
    n_fft=2048,
    hop_length=512,
    peak_threshold=0.15,
    enable_adaptive_parameters=True
)

# 単一ファイルの処理
fingerprints = fingerprinter.generate_fingerprints("song.wav")
print(f"Generated {len(fingerprints)} fingerprints")

# フィンガープリントの詳細表示
for i, fp in enumerate(fingerprints[:5]):  # 最初の5個を表示
    print(f"Fingerprint {i+1}:")
    print(f"  Hash: {fp['hash']}")
    print(f"  Time Offset: {fp['time_offset']:.3f}s")
    print(f"  Anchor Freq: {fp['anchor_freq']}")
    print(f"  Target Freq: {fp['target_freq']}")
```

### 適応的パラメータ調整の使用例

```python
# 適応的パラメータ調整を使用した高度な処理
fingerprinter = AudioFingerprinter()
tuner = AdaptiveParameterTuner(fingerprinter)

# 音声ファイルを読み込み
audio_data, sr = librosa.load("complex_song.wav", sr=22050)

# 音声特性を分析
characteristics = tuner.analyze_audio_characteristics(audio_data)
print("音声特性分析結果:")
for key, value in characteristics.items():
    print(f"  {key}: {value:.4f}")

# パラメータを調整
adjustments = tuner.adjust_parameters(characteristics)
tuner.apply_adjustments(adjustments)

print("適用された調整:")
for param, value in adjustments.items():
    print(f"  {param}: {value}")

# 最適化されたパラメータでフィンガープリント生成
fingerprints = fingerprinter._process_audio_data(audio_data)
print(f"最適化後のフィンガープリント数: {len(fingerprints)}")

# 最適化履歴の確認
summary = tuner.get_optimization_summary()
print("最適化サマリー:", summary)
```

### パフォーマンス比較とベンチマーク

```python
import time
import numpy as np

def benchmark_fingerprinting_methods():
    """異なる設定でのフィンガープリンティング性能を比較"""
    
    # テスト用音声データ生成
    duration = 30  # 30秒
    sample_rate = 22050
    t = np.linspace(0, duration, duration * sample_rate)
    test_audio = np.sin(2 * np.pi * 440 * t) + 0.5 * np.sin(2 * np.pi * 880 * t)
    
    # 異なる設定でのテスト
    configurations = [
        {"name": "標準設定", "params": {}},
        {"name": "高精度設定", "params": {"n_fft": 4096, "hop_length": 256, "peak_threshold": 0.1}},
        {"name": "高速設定", "params": {"n_fft": 1024, "hop_length": 1024, "peak_threshold": 0.2}},
        {"name": "適応的設定", "params": {"enable_adaptive_parameters": True}}
    ]
    
    results = []
    
    for config in configurations:
        fingerprinter = AudioFingerprinter(**config["params"])
        
        # 処理時間測定
        start_time = time.time()
        fingerprints = fingerprinter._process_audio_data(test_audio)
        processing_time = time.time() - start_time
        
        results.append({
            "configuration": config["name"],
            "processing_time": processing_time,
            "fingerprint_count": len(fingerprints),
            "fingerprints_per_second": len(fingerprints) / processing_time
        })
    
    # 結果表示
    print("フィンガープリンティング性能比較:")
    print("-" * 80)
    print(f"{'設定':<15} {'処理時間(s)':<12} {'FP数':<8} {'FP/秒':<10}")
    print("-" * 80)
    
    for result in results:
        print(f"{result['configuration']:<15} "
              f"{result['processing_time']:<12.3f} "
              f"{result['fingerprint_count']:<8} "
              f"{result['fingerprints_per_second']:<10.1f}")

# ベンチマーク実行
benchmark_fingerprinting_methods()
```

### 大容量ファイル処理の例

```python
def process_large_audio_file(file_path, chunk_duration=60):
    """大容量音声ファイルをチャンク単位で処理"""
    fingerprinter = AudioFingerprinter()
    
    # ファイル情報取得
    total_duration = librosa.get_duration(filename=file_path)
    print(f"総再生時間: {total_duration:.1f}秒")
    
    all_fingerprints = []
    chunk_count = 0
    
    # チャンク単位で処理
    for start_time in range(0, int(total_duration), chunk_duration):
        end_time = min(start_time + chunk_duration, total_duration)
        
        # チャンク読み込み
        audio_chunk, sr = librosa.load(
            file_path,
            sr=fingerprinter.sample_rate,
            offset=start_time,
            duration=end_time - start_time
        )
        
        # フィンガープリント生成
        chunk_fingerprints = fingerprinter._process_audio_data(audio_chunk)
        
        # 時間オフセット調整
        for fp in chunk_fingerprints:
            fp['time_offset'] += start_time
        
        all_fingerprints.extend(chunk_fingerprints)
        chunk_count += 1
        
        print(f"チャンク {chunk_count}: {start_time}s-{end_time}s, "
              f"{len(chunk_fingerprints)} フィンガープリント生成")
    
    print(f"処理完了: 総フィンガープリント数 {len(all_fingerprints)}")
    return all_fingerprints

# 使用例
# large_fingerprints = process_large_audio_file("long_song.wav", chunk_duration=30)
```

## 技術仕様とパラメータ詳細

### デフォルトパラメータ設定

| パラメータ | デフォルト値 | 説明 | 推奨範囲 |
|-----------|-------------|------|---------|
| **sample_rate** | 22050 | サンプリングレート (Hz) | 16000-44100 |
| **n_fft** | 2048 | FFTウィンドウサイズ | 1024-8192 |
| **hop_length** | 512 | ホップ長 | 256-1024 |
| **window** | 'hann' | 窓関数 | 'hann', 'hamming', 'blackman' |
| **peak_threshold** | 0.15 | ピーク検出しきい値 | 0.05-0.3 |
| **min_peak_distance** | 10 | 最小ピーク間距離 | 5-20 |
| **target_zone_size** | 5 | ターゲットゾーンサイズ | 3-10 |
| **max_time_delta** | 200 | 最大時間差 | 100-500 |

### 音声品質別推奨設定

#### 高品質スタジオ録音
```python
studio_params = {
    'sample_rate': 44100,
    'n_fft': 4096,
    'hop_length': 256,
    'peak_threshold': 0.1,
    'target_zone_size': 8,
    'max_time_delta': 300
}
```

#### 圧縮音声（MP3等）
```python
compressed_params = {
    'sample_rate': 22050,
    'n_fft': 2048,
    'hop_length': 512,
    'peak_threshold': 0.15,
    'target_zone_size': 5,
    'max_time_delta': 200
}
```

#### ライブ録音・ノイズあり
```python
live_params = {
    'sample_rate': 22050,
    'n_fft': 2048,
    'hop_length': 512,
    'peak_threshold': 0.25,
    'min_peak_distance': 15,
    'target_zone_size': 4,
    'max_time_delta': 150
}
```

### エラーハンドリングと例外処理

```python
class AudioFingerprintingError(Exception):
    """音声フィンガープリンティング関連の基底例外"""
    pass

class InvalidAudioFormatError(AudioFingerprintingError):
    """無効な音声形式エラー"""
    pass

class InsufficientAudioDataError(AudioFingerprintingError):
    """音声データ不足エラー"""
    pass

def robust_fingerprint_generation(audio_path, max_retries=3):
    """堅牢なフィンガープリント生成（エラー処理付き）"""
    fingerprinter = AudioFingerprinter()
    
    for attempt in range(max_retries):
        try:
            # 音声ファイル存在確認
            if not os.path.exists(audio_path):
                raise FileNotFoundError(f"音声ファイルが見つかりません: {audio_path}")
            
            # 音声読み込み
            audio_data, sr = librosa.load(audio_path, sr=fingerprinter.sample_rate)
            
            # 音声データ検証
            if len(audio_data) < fingerprinter.sample_rate:  # 1秒未満
                raise InsufficientAudioDataError("音声データが短すぎます（最低1秒必要）")
            
            if np.max(np.abs(audio_data)) < 0.001:  # 音量が小さすぎる
                raise InvalidAudioFormatError("音声レベルが低すぎます")
            
            # フィンガープリント生成
            fingerprints = fingerprinter._process_audio_data(audio_data)
            
            if len(fingerprints) < 10:  # フィンガープリント数が少なすぎる
                raise InsufficientAudioDataError("生成されたフィンガープリント数が不足しています")
            
            return fingerprints
            
        except (librosa.LibrosaError, ValueError) as e:
            if attempt == max_retries - 1:
                raise InvalidAudioFormatError(f"音声ファイル読み込みエラー: {e}")
            print(f"リトライ {attempt + 1}/{max_retries}: {e}")
            time.sleep(1)
        
        except Exception as e:
            if attempt == max_retries - 1:
                raise AudioFingerprintingError(f"予期しないエラー: {e}")
            print(f"リトライ {attempt + 1}/{max_retries}: {e}")
            time.sleep(1)
    
    raise AudioFingerprintingError("最大リトライ回数に達しました")
```

## まとめ

音声フィンガープリンティングエンジンは、mimizamシステムの中核を成す高度な音声処理コンポーネントです。主な特徴：

### 技術的優位性
- **実証済みアルゴリズム**: Shazam互換の音声フィンガープリンティング
- **適応的処理**: 音声品質に応じた自動パラメータ調整
- **高性能最適化**: Numba JIT最適化による高速処理
- **スケーラブル設計**: 並列処理とストリーミング処理対応

### 主要機能
- STFT基盤のスペクトログラム生成
- 局所最大値によるピーク検出
- アンカー・ターゲット方式のハッシュ生成
- 音声品質に基づく適応的パラメータ調整

### パフォーマンス特性
- 標準的な楽曲（3-4分）で数千のフィンガープリント生成
- JIT最適化により2-5倍の処理速度向上
- 並列処理による複数ファイル同時処理
- 大容量ファイルのストリーミング処理対応

### 実用性
- 多様な音声品質に対応する適応的パラメータ調整
- 包括的なエラーハンドリングと例外処理
- 詳細なパフォーマンス監視とベンチマーク機能
- 柔軟な設定オプションと使いやすいAPI

このエンジンにより、mimizamは高精度で高速な音声識別機能を実現し、研究用途から商用システムまで幅広い要求に対応できます。

ソース: src/audio_fingerprinter.py 1-392, src/adaptive_parameters.py 1-200, src/spectrogram_analyzer.py 1-150, src/peak_detector.py 1-100
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
