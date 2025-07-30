# 音声指紋エンジン

このページでは、mimizamシステムの音声指紋生成を担当する個別の低レベルコンポーネントについて説明します。これらのコンポーネントは、音声処理パイプラインに対する細かい制御を提供し、高レベルAPIを超えたカスタマイゼーションが必要な高度な使用例に対応します。

メインの`Mimizam`クラスとファクトリ関数による簡単な使用方法については、[高レベルAPI](./07_high_level_api.md)を参照してください。データベースバックエンド設定の詳細については、[データベースバックエンド](./09_database_backends.md)を参照してください。

## コンポーネントアーキテクチャ概要

低レベルコンポーネントは、各コンポーネントが特定の責任を持つモジュラー処理パイプラインを形成します：

```
AudioFingerprinter (メインオーケストレータ)
├── SpectrogramAnalyzer (スペクトログラム解析、ピーク検出、ハッシュ生成を統制)
├── ピーク検出とハッシュ生成を統制
└── ハッシュ生成プロセス
```

## 音声処理コンポーネント

### AudioFingerprinter

`AudioFingerprinter`クラスは音声指紋生成プロセスのメインオーケストレータとして機能します。スペクトログラム解析、ピーク検出、ハッシュ生成の間の相互作用を統制します。

#### クラス定義と初期化

| パラメータ | 型 | デフォルト | 説明 |
|-----------|---|----------|------|
| `min_amplitude` | float | -60 | 最小振幅閾値 (dB) |
| `n_fft` | int | 2048 | FFTウィンドウサイズ |
| `hop_length` | int | 512 | ホップ長（サンプル数） |
| `peak_neighborhood_size` | int | 20 | ピーク検出の近傍サイズ |
| `target_zone_size` | int | 5 | ターゲットゾーンサイズ |
| `time_range` | int | 200 | 時間範囲（フレーム数） |
| `enable_adaptive_params` | bool | False | 適応パラメータ調整を有効化 |

#### 主要メソッド

```python
def generate_fingerprints(self, audio_file_path: str) -> List[Tuple[str, float]]:
    """音声ファイルから指紋を生成"""
    
def _load_audio(self, file_path: str) -> Tuple[np.ndarray, int]:
    """音声ファイルを読み込み、正規化"""
    
def _find_local_maxima(self, spectrogram: np.ndarray) -> List[Tuple[int, int]]:
    """スペクトログラムから局所最大値を検出"""
```

### SpectrogramAnalyzer

`SpectrogramAnalyzer`は短時間フーリエ変換（STFT）の計算とスペクトラル解析を処理します。

#### 処理パイプライン

1. **音声前処理**: 音声信号の正規化とウィンドウ適用
2. **STFT計算**: `scipy.fft`を使用した時間-周波数変換
3. **マグニチュードスペクトログラム**: パワースペクトル密度の計算
4. **ピーク検出**: 適応閾値を使用した局所最大値の抽出

#### 主要メソッド

```python
def compute_spectrogram(self, audio: np.ndarray, sr: int) -> np.ndarray:
    """音声信号からスペクトログラムを計算"""
    
def find_peaks(self, spectrogram: np.ndarray) -> List[Peak]:
    """スペクトログラムからピークを検出"""
```

### Numba最適化

重要な数値計算ループは、パフォーマンス向上のためにNumba JITコンパイルを使用します：

```python
@numba.jit(nopython=True)
def _find_peaks_numba(spectrogram, min_amplitude, neighborhood_size):
    """Numba最適化されたピーク検出"""
```

### HashGenerator

`HashGenerator`はピークペアからSHA-256ハッシュを生成する責任を持ちます。

#### ハッシュ生成プロセス

1. **アンカー・ターゲットペアリング**: 時間窓内でのピーク関係の組み合わせ
2. **特徴抽出**: 周波数差、時間差、アンカー時間の計算
3. **ハッシュ生成**: SHA-256を使用した暗号学的ハッシュ作成

#### 設定パラメータ

```python
def generate_hashes(self, peaks: List[Peak]) -> List[Tuple[str, float]]:
    """ピークリストからハッシュを生成"""
    
def _create_anchor_target_pairs(self, peaks: List[Peak]) -> List[Tuple[Peak, Peak]]:
    """アンカー・ターゲットペアを作成"""
```

## 適応インテリジェンスコンポーネント

### AdaptiveParameterTuner

`AdaptiveParameterTuner`クラスは、リアルタイムの音声特性に基づいて処理パラメータを動的に調整します。

#### 音声特性分析

```python
def analyze_audio_characteristics(self, audio: np.ndarray, sr: int) -> Dict[str, float]:
    """音声の特性を分析"""
    
def get_rms_energy(self, audio: np.ndarray) -> float:
    """RMSエネルギーを計算"""
    
def get_spectral_entropy(self, spectrogram: np.ndarray) -> float:
    """スペクトラルエントロピーを計算"""
```

#### 分析される特性

| 特性 | 説明 | 用途 |
|------|------|------|
| **RMSエネルギー** | 音声信号の平均二乗平方根エネルギー | ノイズレベルに基づく振幅閾値調整 |
| **スペクトラルエントロピー** | 周波数分布の複雑さ測定 | 調和的vs.ノイズの多いコンテンツの検出 |
| **テンポ推定** | 音楽のビート検出 | ジャンル特性に基づく時間窓調整 |

#### 主要メソッド

```python
def tune_parameters(self, audio: np.ndarray, sr: int) -> Dict[str, Any]:
    """音声特性に基づいてパラメータを調整"""
    
def _adjust_amplitude_threshold(self, rms_energy: float) -> float:
    """RMSエネルギーに基づいて振幅閾値を調整"""
    
def _adjust_peak_sensitivity(self, spectral_entropy: float) -> int:
    """スペクトラルエントロピーに基づいてピーク感度を調整"""
```

### PerformanceMonitor

システムパフォーマンスの追跡と分析を行います。

#### 追跡される指標

| 指標 | 説明 |
|------|------|
| **処理時間** | 各段階での実行時間 |
| **メモリ使用量** | ピーク時とアイドル時のメモリ消費 |
| **指紋生成率** | 秒あたりの生成指紋数 |
| **ピーク検出効率** | 検出されたピーク数と処理時間の比率 |

#### 主要メソッド

```python
def start_timing(self, operation: str) -> None:
    """操作のタイミング開始"""
    
def end_timing(self, operation: str) -> float:
    """操作のタイミング終了と時間返却"""
    
def get_performance_report(self) -> Dict[str, Any]:
    """パフォーマンスレポートを生成"""
```

## データ構造

### Peak

ピーク情報を表現するデータクラス：

```python
@dataclass
class Peak:
    time: int      # 時間インデックス（フレーム）
    frequency: int # 周波数インデックス（ビン）
    amplitude: float # 振幅値
```

### Fingerprint

生成された指紋を表現するデータクラス：

```python
@dataclass  
class Fingerprint:
    hash: str           # SHA-256ハッシュ文字列
    time_offset: float  # 音声内での時間オフセット（秒）
    anchor_time: int    # アンカーピークの時間
    target_time: int    # ターゲットピークの時間
    freq_delta: int     # 周波数差
```

## 関連ドキュメント

- [コアアーキテクチャ](./03_core_architecture.md) - システム全体の構成
- [データベース層](./05_database_layer.md) - データベース抽象化
- [高レベルAPI](./07_high_level_api.md) - 簡単な使用方法
- [パフォーマンス最適化](./16_performance_optimization.md) - 高速化技術
