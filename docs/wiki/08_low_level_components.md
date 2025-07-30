# 低レベルコンポーネント

このページでは、mimizamシステムの個別の低レベルコンポーネントについて説明します。これらのコンポーネントは、音声処理パイプラインに対する細かい制御を提供し、高レベルAPIを超えたカスタマイゼーションが必要な高度な使用例に対応します。

メインの`Mimizam`クラスとファクトリ関数による簡単な使用方法については、[高レベルAPI](./07_high_level_api.md)を参照してください。データベースバックエンド設定の詳細については、[データベースバックエンド](./09_database_backends.md)を参照してください。

## コンポーネントアーキテクチャ概要

低レベルコンポーネントは、各コンポーネントが特定の責任を持つモジュラー処理パイプラインを形成します：

```
AudioFingerprinter (メインオーケストレータ)
├── SpectrogramAnalyzer (スペクトログラム解析)
├── PeakDetector (ピーク検出)
├── HashGenerator (ハッシュ生成)
└── AdaptiveParameterTuner (適応パラメータ調整)

FingerprintDatabase (データベース抽象化)
├── DatabaseBackend (バックエンド実装)
├── FingerprintMatcher (マッチング処理)
└── PerformanceMonitor (パフォーマンス監視)
```

## 音声処理コンポーネント

### AudioFingerprinter

`AudioFingerprinter`クラスは音声指紋生成プロセスのメインオーケストレータとして機能します。

#### 初期化パラメータ

```python
class AudioFingerprinter:
    def __init__(
        self,
        min_amplitude: float = -60,
        n_fft: int = 2048,
        hop_length: int = 512,
        peak_neighborhood_size: int = 20,
        target_zone_size: int = 5,
        time_range: int = 200,
        enable_adaptive_params: bool = False
    ):
```

#### 主要メソッド

```python
def generate_fingerprints(self, audio_file_path: str) -> List[Tuple[str, float]]:
    """音声ファイルから指紋を生成"""
    
def _load_audio(self, file_path: str) -> Tuple[np.ndarray, int]:
    """音声ファイルを読み込み、正規化"""
    
def _compute_spectrogram(self, audio: np.ndarray, sr: int) -> np.ndarray:
    """スペクトログラムを計算"""
    
def _find_local_maxima(self, spectrogram: np.ndarray) -> List[Tuple[int, int]]:
    """スペクトログラムから局所最大値を検出"""
    
def _generate_hashes(self, peaks: List[Tuple[int, int]]) -> List[Tuple[str, float]]:
    """ピークからハッシュを生成"""
```

### SpectrogramAnalyzer

スペクトログラム解析の専用コンポーネント：

```python
class SpectrogramAnalyzer:
    def __init__(self, n_fft: int = 2048, hop_length: int = 512):
        self.n_fft = n_fft
        self.hop_length = hop_length
    
    def compute_spectrogram(self, audio: np.ndarray, sr: int) -> np.ndarray:
        """STFT計算とマグニチュードスペクトログラム生成"""
        
    def apply_window_function(self, audio: np.ndarray) -> np.ndarray:
        """窓関数の適用"""
        
    def normalize_spectrogram(self, spectrogram: np.ndarray) -> np.ndarray:
        """スペクトログラムの正規化"""
```

### PeakDetector

ピーク検出の専用コンポーネント：

```python
class PeakDetector:
    def __init__(self, min_amplitude: float = -60, neighborhood_size: int = 20):
        self.min_amplitude = min_amplitude
        self.neighborhood_size = neighborhood_size
    
    def find_peaks(self, spectrogram: np.ndarray) -> List[Peak]:
        """スペクトログラムからピークを検出"""
        
    def apply_adaptive_threshold(self, spectrogram: np.ndarray) -> np.ndarray:
        """適応閾値の適用"""
        
    def filter_peaks_by_prominence(self, peaks: List[Peak]) -> List[Peak]:
        """ピークの顕著性によるフィルタリング"""
```

### HashGenerator

ハッシュ生成の専用コンポーネント：

```python
class HashGenerator:
    def __init__(self, target_zone_size: int = 5, time_range: int = 200):
        self.target_zone_size = target_zone_size
        self.time_range = time_range
    
    def generate_hashes(self, peaks: List[Peak]) -> List[Fingerprint]:
        """ピークリストからハッシュを生成"""
        
    def create_anchor_target_pairs(self, peaks: List[Peak]) -> List[Tuple[Peak, Peak]]:
        """アンカー・ターゲットペアを作成"""
        
    def compute_hash(self, anchor: Peak, target: Peak) -> str:
        """ピークペアからSHA-256ハッシュを計算"""
```

## データベースコンポーネント

### FingerprintDatabase

データベース操作の抽象化層：

```python
class FingerprintDatabase:
    def __init__(self, backend: DatabaseBackend, fingerprinter: AudioFingerprinter):
        self.backend = backend
        self.fingerprinter = fingerprinter
    
    def add_song(self, file_path: str, title: str, artist: str) -> int:
        """楽曲をデータベースに追加"""
        
    def find_fingerprints_by_hashes(self, hashes: List[str]) -> List[Tuple[str, int, float]]:
        """ハッシュリストによる指紋検索"""
        
    def get_song_by_id(self, song_id: int) -> Optional[Song]:
        """IDによる楽曲取得"""
        
    def get_database_stats(self) -> Dict[str, Any]:
        """データベース統計情報を取得"""
```

### DatabaseBackend

データベースバックエンドの共通インターフェース：

```python
class DatabaseBackend:
    def connect(self) -> None:
        """データベース接続を確立"""
        
    def disconnect(self) -> None:
        """データベース接続を切断"""
        
    def execute_query(self, query: str, params: Tuple = ()) -> Any:
        """SQLクエリを実行"""
        
    def execute_many(self, query: str, params_list: List[Tuple]) -> None:
        """バッチクエリを実行"""
        
    def begin_transaction(self) -> None:
        """トランザクション開始"""
        
    def commit_transaction(self) -> None:
        """トランザクションコミット"""
        
    def rollback_transaction(self) -> None:
        """トランザクションロールバック"""
```

### FingerprintMatcher

マッチング処理の専用コンポーネント：

```python
class FingerprintMatcher:
    def __init__(self, database: FingerprintDatabase):
        self.database = database
        self.fingerprinter = database.fingerprinter
    
    def identify_audio(self, audio_file_path: str, min_confidence: float = 0.3) -> Optional[Tuple[Song, float]]:
        """音声ファイルから楽曲を識別"""
        
    def search_song(self, audio_file_path: str, min_confidence: float = 0.2, top_k: int = 10) -> List[Dict[str, Any]]:
        """複数の候補楽曲を検索"""
        
    def _calculate_confidence_score(self, song_id: int, matches: List[Tuple[float, float]]) -> float:
        """信頼度スコアを計算"""
```

## 適応処理コンポーネント

### AdaptiveParameterTuner

音声特性に基づく動的パラメータ調整：

```python
class AdaptiveParameterTuner:
    def __init__(self):
        self.audio_characteristics = {}
    
    def analyze_audio_characteristics(self, audio: np.ndarray, sr: int) -> Dict[str, float]:
        """音声の特性を分析"""
        
    def tune_parameters(self, audio: np.ndarray, sr: int) -> Dict[str, Any]:
        """音声特性に基づいてパラメータを調整"""
        
    def get_rms_energy(self, audio: np.ndarray) -> float:
        """RMSエネルギーを計算"""
        
    def get_spectral_entropy(self, spectrogram: np.ndarray) -> float:
        """スペクトラルエントロピーを計算"""
        
    def estimate_tempo(self, audio: np.ndarray, sr: int) -> float:
        """テンポを推定"""
```

### PerformanceMonitor

システムパフォーマンスの監視：

```python
class PerformanceMonitor:
    def __init__(self):
        self.metrics = {}
        self.timings = {}
    
    def start_timing(self, operation: str) -> None:
        """操作のタイミング開始"""
        
    def end_timing(self, operation: str) -> float:
        """操作のタイミング終了と時間返却"""
        
    def record_metric(self, name: str, value: float) -> None:
        """メトリクスを記録"""
        
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
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return {
            'time': self.time,
            'frequency': self.frequency,
            'amplitude': self.amplitude
        }
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
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return {
            'hash': self.hash,
            'time_offset': self.time_offset,
            'anchor_time': self.anchor_time,
            'target_time': self.target_time,
            'freq_delta': self.freq_delta
        }
```

### Song

楽曲メタデータを表現するデータクラス：

```python
@dataclass
class Song:
    id: int
    title: str
    artist: str
    duration: Optional[float] = None
    file_path: Optional[str] = None
    created_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return {
            'id': self.id,
            'title': self.title,
            'artist': self.artist,
            'duration': self.duration,
            'file_path': self.file_path,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
```

## カスタムコンポーネントの作成

### カスタムピーク検出器

```python
class CustomPeakDetector(PeakDetector):
    def __init__(self, custom_threshold: float = 0.5):
        super().__init__()
        self.custom_threshold = custom_threshold
    
    def find_peaks(self, spectrogram: np.ndarray) -> List[Peak]:
        """カスタムピーク検出アルゴリズム"""
        # カスタム実装
        pass
```

### カスタムハッシュ生成器

```python
class CustomHashGenerator(HashGenerator):
    def compute_hash(self, anchor: Peak, target: Peak) -> str:
        """カスタムハッシュアルゴリズム"""
        # カスタム実装
        pass
```

### カスタムデータベースバックエンド

```python
class CustomDatabaseBackend(DatabaseBackend):
    def __init__(self, connection_string: str):
        self.connection_string = connection_string
    
    def connect(self) -> None:
        """カスタムデータベース接続"""
        # カスタム実装
        pass
```

## 高度な使用例

### カスタム音声処理パイプライン

```python
def create_custom_fingerprinter():
    # カスタムコンポーネントを組み合わせ
    spectrogram_analyzer = SpectrogramAnalyzer(n_fft=4096, hop_length=256)
    peak_detector = CustomPeakDetector(custom_threshold=0.7)
    hash_generator = CustomHashGenerator(target_zone_size=10)
    
    fingerprinter = AudioFingerprinter()
    fingerprinter.spectrogram_analyzer = spectrogram_analyzer
    fingerprinter.peak_detector = peak_detector
    fingerprinter.hash_generator = hash_generator
    
    return fingerprinter
```

### パフォーマンス監視付きシステム

```python
def create_monitored_system():
    # パフォーマンス監視付きシステム
    monitor = PerformanceMonitor()
    
    fingerprinter = AudioFingerprinter()
    fingerprinter.performance_monitor = monitor
    
    database = FingerprintDatabase(backend, fingerprinter)
    database.performance_monitor = monitor
    
    return Mimizam(database), monitor
```

## 関連ドキュメント

- [高レベルAPI](./07_high_level_api.md) - 簡単な使用方法
- [音声指紋エンジン](./04_audio_fingerprinting_engine.md) - 音声処理の詳細
- [データベース層](./05_database_layer.md) - データベース抽象化
- [マッチング・識別システム](./06_matching_identification.md) - 検索とスコアリング
- [パフォーマンス最適化](./16_performance_optimization.md) - 高速化技術
