# 低レベルコンポーネント

このドキュメントでは、mimizamシステムの低レベルコンポーネントについて詳しく説明します。これらのコンポーネントは、高レベルAPIの基盤となる個別の機能モジュールです。

高レベルAPIについては、[高レベルAPI](./04_1_high_level_api.md)を参照してください。

## 概要

低レベルコンポーネントは、mimizamの内部実装を構成する個別のクラスとモジュールです。これらを直接使用することで、より細かい制御とカスタマイゼーションが可能になります。

## AudioFingerprinterクラス

### クラス定義

```python
class AudioFingerprinter:
    """
    音声指紋生成の中核クラス
    
    音声ファイルからスペクトログラムを生成し、ピークを検出して
    一意の指紋ハッシュを作成します。
    """
    
    def __init__(self, **params):
        """
        AudioFingerprinterを初期化
        
        Args:
            **params: 設定パラメータ
                - sample_rate (int): サンプリングレート（デフォルト: 22050）
                - n_fft (int): FFTサイズ（デフォルト: 2048）
                - hop_length (int): ホップ長（デフォルト: 512）
                - window (str): 窓関数（デフォルト: 'hann'）
                - peak_threshold (float): ピーク検出閾値（デフォルト: 0.15）
                - min_peak_distance (int): ピーク間最小距離（デフォルト: 10）
                - target_zone_size (int): ターゲットゾーンサイズ（デフォルト: 5）
                - max_time_delta (int): 最大時間差（デフォルト: 200）
        """
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
```

### 主要メソッド

#### generate_fingerprints()

```python
def generate_fingerprints(self, audio_path):
    """
    音声ファイルから指紋を生成
    
    Args:
        audio_path (str): 音声ファイルのパス
    
    Returns:
        list: 指紋のリスト
            各指紋は以下の辞書:
            - hash (int): ハッシュ値
            - time_offset (float): 時間オフセット
            - anchor_freq (int): アンカー周波数
            - target_freq (int): ターゲット周波数
            - time_delta (int): 時間差
    
    Raises:
        AudioProcessingError: 音声処理エラー
        FileNotFoundError: ファイルが見つからない
    
    Example:
        >>> fingerprinter = AudioFingerprinter()
        >>> fingerprints = fingerprinter.generate_fingerprints("song.wav")
        >>> print(f"生成された指紋数: {len(fingerprints)}")
    """
    import librosa
    
    try:
        # 音声ファイルを読み込み
        audio_data, sr = librosa.load(audio_path, sr=self.sample_rate)
        
        # 指紋を生成
        return self._process_audio_data(audio_data)
        
    except Exception as e:
        raise AudioProcessingError(f"指紋生成エラー: {e}")
```

#### generate_spectrogram()

```python
def generate_spectrogram(self, audio_path):
    """
    スペクトログラムを生成
    
    Args:
        audio_path (str): 音声ファイルのパス
    
    Returns:
        numpy.ndarray: スペクトログラム（周波数×時間）
    
    Example:
        >>> spectrogram = fingerprinter.generate_spectrogram("song.wav")
        >>> print(f"スペクトログラム形状: {spectrogram.shape}")
    """
    import librosa
    import numpy as np
    
    # 音声ファイルを読み込み
    audio_data, sr = librosa.load(audio_path, sr=self.sample_rate)
    
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

#### detect_peaks()

```python
def detect_peaks(self, audio_path):
    """
    ピークを検出
    
    Args:
        audio_path (str): 音声ファイルのパス
    
    Returns:
        list: ピーク座標のリスト
            各要素は (time_bin, frequency_bin) のタプル
    
    Example:
        >>> peaks = fingerprinter.detect_peaks("song.wav")
        >>> print(f"検出されたピーク数: {len(peaks)}")
        >>> for time, freq in peaks[:5]:
        ...     print(f"時間: {time}, 周波数: {freq}")
    """
    # スペクトログラムを生成
    spectrogram = self.generate_spectrogram(audio_path)
    
    # ピークを検出
    return self._detect_peaks_from_spectrogram(spectrogram)
```

### 内部メソッド

#### _process_audio_data()

```python
def _process_audio_data(self, audio_data):
    """音声データから指紋を生成する内部メソッド"""
    # スペクトログラムを生成
    spectrogram = self._generate_spectrogram_from_data(audio_data)
    
    # ピークを検出
    peaks = self._detect_peaks_from_spectrogram(spectrogram)
    
    # ハッシュを生成
    fingerprints = self._generate_hashes(peaks)
    
    return fingerprints
```

#### _detect_peaks_from_spectrogram()

```python
def _detect_peaks_from_spectrogram(self, spectrogram):
    """スペクトログラムからピークを検出"""
    from scipy.ndimage import maximum_filter
    import numpy as np
    
    # 局所最大値フィルタを適用
    neighborhood_size = (self.min_peak_distance, self.min_peak_distance)
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

## FingerprintDatabaseクラス

### クラス定義

```python
class FingerprintDatabase:
    """
    指紋データベースの統合インターフェース
    
    異なるデータベースバックエンドに対する統一されたインターフェースを提供し、
    指紋の保存、検索、楽曲管理機能を実装します。
    """
    
    def __init__(self, backend):
        """
        FingerprintDatabaseを初期化
        
        Args:
            backend (DatabaseBackend): データベースバックエンド
        """
        self.backend = backend
        self.backend.connect()
        self.backend.create_tables()
```

### 主要メソッド

#### store_song()

```python
def store_song(self, song_name, fingerprints, **metadata):
    """
    楽曲と指紋をデータベースに保存
    
    Args:
        song_name (str): 楽曲名
        fingerprints (list): 指紋のリスト
        **metadata: 楽曲のメタデータ
    
    Returns:
        int: 楽曲ID
    
    Raises:
        DatabaseError: データベース操作エラー
    
    Example:
        >>> database = FingerprintDatabase(backend)
        >>> song_id = database.store_song(
        ...     "My Song",
        ...     fingerprints,
        ...     artist="Artist Name",
        ...     album="Album Name"
        ... )
    """
    try:
        # 楽曲情報を挿入
        song_id = self.backend.insert_song(song_name, **metadata)
        
        # 指紋を挿入
        self.backend.insert_fingerprints(song_id, fingerprints)
        
        return song_id
        
    except Exception as e:
        raise DatabaseError(f"楽曲保存エラー: {e}")
```

#### search_fingerprints()

```python
def search_fingerprints(self, query_fingerprints):
    """
    指紋を検索してマッチを取得
    
    Args:
        query_fingerprints (list): クエリ指紋のリスト
    
    Returns:
        dict: マッチした楽曲の辞書
            キー: 楽曲ID
            値: マッチした指紋のリスト
    
    Raises:
        DatabaseError: データベース操作エラー
    
    Example:
        >>> matches = database.search_fingerprints(query_fingerprints)
        >>> for song_id, match_list in matches.items():
        ...     print(f"楽曲ID {song_id}: {len(match_list)} マッチ")
    """
    try:
        return self.backend.search_fingerprints(query_fingerprints)
    except Exception as e:
        raise DatabaseError(f"指紋検索エラー: {e}")
```

## DatabaseBackendクラス（抽象基底クラス）

### クラス定義

```python
from abc import ABC, abstractmethod

class DatabaseBackend(ABC):
    """
    データベースバックエンドの抽象基底クラス
    
    全てのデータベースバックエンドが実装する必要がある
    共通インターフェースを定義します。
    """
    
    @abstractmethod
    def connect(self):
        """データベースに接続"""
        pass
    
    @abstractmethod
    def disconnect(self):
        """データベース接続を切断"""
        pass
    
    @abstractmethod
    def create_tables(self):
        """必要なテーブルを作成"""
        pass
    
    @abstractmethod
    def insert_song(self, song_name, **metadata):
        """楽曲情報を挿入"""
        pass
    
    @abstractmethod
    def insert_fingerprints(self, song_id, fingerprints):
        """指紋を挿入"""
        pass
    
    @abstractmethod
    def search_fingerprints(self, fingerprints):
        """指紋を検索"""
        pass
    
    @abstractmethod
    def get_song_info(self, song_id):
        """楽曲情報を取得"""
        pass
    
    @abstractmethod
    def get_song_count(self):
        """楽曲数を取得"""
        pass
    
    @abstractmethod
    def delete_song(self, song_id):
        """楽曲を削除"""
        pass
```

## MatchingEngineクラス

### クラス定義

```python
class MatchingEngine:
    """
    音声マッチング・識別エンジン
    
    クエリ指紋をデータベース内の指紋と照合し、
    最適なマッチを特定します。
    """
    
    def __init__(self, database, scoring_method='weighted'):
        """
        MatchingEngineを初期化
        
        Args:
            database (FingerprintDatabase): 指紋データベース
            scoring_method (str): スコアリング手法
                - 'basic': 基本的なマッチ数ベース
                - 'weighted': 時間一貫性を考慮した重み付き
                - 'statistical': 統計的手法による高度なスコアリング
        """
        self.database = database
        self.scoring_method = scoring_method
        self.match_threshold = 0.1
        self.max_matches = 10
```

### 主要メソッド

#### identify_audio()

```python
def identify_audio(self, query_fingerprints):
    """
    音声を識別
    
    Args:
        query_fingerprints (list): クエリ指紋のリスト
    
    Returns:
        list: マッチした楽曲のリスト
            各要素は以下の辞書:
            - song_id (int): 楽曲ID
            - song_name (str): 楽曲名
            - artist (str): アーティスト名
            - score (float): マッチスコア
            - confidence (float): 信頼度
            - match_count (int): マッチ数
    
    Example:
        >>> engine = MatchingEngine(database)
        >>> results = engine.identify_audio(query_fingerprints)
        >>> if results:
        ...     best_match = results[0]
        ...     print(f"識別結果: {best_match['song_name']}")
    """
    # 1. データベース検索
    raw_matches = self.database.search_fingerprints(query_fingerprints)
    
    # 2. 時間オフセット分析
    analyzed_matches = self._analyze_time_offsets(raw_matches, query_fingerprints)
    
    # 3. スコアリング
    scored_matches = self._score_matches(analyzed_matches)
    
    # 4. 結果フィルタリングとランキング
    final_results = self._rank_and_filter_results(scored_matches)
    
    return final_results
```

## SpectrogramAnalyzerクラス

### クラス定義

```python
class SpectrogramAnalyzer:
    """
    スペクトログラム解析専用クラス
    
    音声信号の時間-周波数解析を担当し、
    スペクトログラム生成と前処理を行います。
    """
    
    def __init__(self, sample_rate=22050, n_fft=2048, hop_length=512):
        """
        SpectrogramAnalyzerを初期化
        
        Args:
            sample_rate (int): サンプリングレート
            n_fft (int): FFTサイズ
            hop_length (int): ホップ長
        """
        self.sample_rate = sample_rate
        self.n_fft = n_fft
        self.hop_length = hop_length
```

### 主要メソッド

#### analyze_audio()

```python
def analyze_audio(self, audio_data):
    """
    音声データを解析
    
    Args:
        audio_data (numpy.ndarray): 音声データ
    
    Returns:
        dict: 解析結果
            - spectrogram (numpy.ndarray): スペクトログラム
            - frequencies (numpy.ndarray): 周波数軸
            - times (numpy.ndarray): 時間軸
            - characteristics (dict): 音声特性
    
    Example:
        >>> analyzer = SpectrogramAnalyzer()
        >>> result = analyzer.analyze_audio(audio_data)
        >>> print(f"スペクトログラム形状: {result['spectrogram'].shape}")
    """
    import librosa
    import numpy as np
    
    # STFT計算
    stft = librosa.stft(
        audio_data,
        n_fft=self.n_fft,
        hop_length=self.hop_length
    )
    
    # スペクトログラム生成
    magnitude = np.abs(stft)
    spectrogram_db = librosa.amplitude_to_db(magnitude, ref=np.max)
    
    # 軸情報を生成
    frequencies = librosa.fft_frequencies(sr=self.sample_rate, n_fft=self.n_fft)
    times = librosa.frames_to_time(
        np.arange(spectrogram_db.shape[1]),
        sr=self.sample_rate,
        hop_length=self.hop_length
    )
    
    # 音声特性を分析
    characteristics = self._analyze_characteristics(audio_data, spectrogram_db)
    
    return {
        'spectrogram': spectrogram_db,
        'frequencies': frequencies,
        'times': times,
        'characteristics': characteristics
    }
```

## HashGeneratorクラス

### クラス定義

```python
class HashGenerator:
    """
    ハッシュ生成専用クラス
    
    ピーク座標から一意の指紋ハッシュを生成します。
    """
    
    def __init__(self, target_zone_size=5, max_time_delta=200):
        """
        HashGeneratorを初期化
        
        Args:
            target_zone_size (int): ターゲットゾーンサイズ
            max_time_delta (int): 最大時間差
        """
        self.target_zone_size = target_zone_size
        self.max_time_delta = max_time_delta
```

### 主要メソッド

#### generate_hashes()

```python
def generate_hashes(self, peaks):
    """
    ピークからハッシュを生成
    
    Args:
        peaks (list): ピーク座標のリスト
            各要素は (time, frequency) のタプル
    
    Returns:
        list: 指紋ハッシュのリスト
            各要素は以下の辞書:
            - hash (int): ハッシュ値
            - time_offset (float): 時間オフセット
            - anchor_freq (int): アンカー周波数
            - target_freq (int): ターゲット周波数
            - time_delta (int): 時間差
    
    Example:
        >>> generator = HashGenerator()
        >>> hashes = generator.generate_hashes(peaks)
        >>> print(f"生成されたハッシュ数: {len(hashes)}")
    """
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

## AdaptiveParameterTunerクラス

### クラス定義

```python
class AdaptiveParameterTuner:
    """
    適応的パラメータ調整クラス
    
    音声特性に基づいてシステムパラメータを自動調整します。
    """
    
    def __init__(self, fingerprinter):
        """
        AdaptiveParameterTunerを初期化
        
        Args:
            fingerprinter (AudioFingerprinter): 音声指紋生成器
        """
        self.fingerprinter = fingerprinter
        self.adjustment_history = []
```

### 主要メソッド

#### tune_parameters()

```python
def tune_parameters(self, audio_data):
    """
    音声データに基づいてパラメータを調整
    
    Args:
        audio_data (numpy.ndarray): 音声データ
    
    Returns:
        dict: 調整されたパラメータ
    
    Example:
        >>> tuner = AdaptiveParameterTuner(fingerprinter)
        >>> adjusted_params = tuner.tune_parameters(audio_data)
        >>> print(f"調整されたパラメータ: {adjusted_params}")
    """
    # 音声特性を分析
    characteristics = self._analyze_audio_characteristics(audio_data)
    
    # パラメータを調整
    adjustments = self._calculate_adjustments(characteristics)
    
    # 調整を適用
    self._apply_adjustments(adjustments)
    
    # 履歴を記録
    self.adjustment_history.append({
        'characteristics': characteristics,
        'adjustments': adjustments,
        'timestamp': time.time()
    })
    
    return adjustments
```

## 使用例

### 低レベルコンポーネントの直接使用

```python
from mimizam.audio_fingerprinter import AudioFingerprinter
from mimizam.backends.sqlite_backend import SQLiteBackend
from mimizam.fingerprint_database import FingerprintDatabase
from mimizam.matching_engine import MatchingEngine

# 個別コンポーネントを初期化
fingerprinter = AudioFingerprinter(
    sample_rate=22050,
    peak_threshold=0.15,
    target_zone_size=5
)

backend = SQLiteBackend("music.db")
database = FingerprintDatabase(backend)
matching_engine = MatchingEngine(database, scoring_method='weighted')

# 音声指紋を生成
fingerprints = fingerprinter.generate_fingerprints("song.wav")
print(f"生成された指紋数: {len(fingerprints)}")

# データベースに保存
song_id = database.store_song("My Song", fingerprints, artist="Artist")
print(f"楽曲ID: {song_id}")

# 音声を識別
query_fingerprints = fingerprinter.generate_fingerprints("query.wav")
matches = matching_engine.identify_audio(query_fingerprints)

for match in matches:
    print(f"マッチ: {match['song_name']} (スコア: {match['score']:.3f})")
```

### カスタムスコアリング手法の実装

```python
class CustomMatchingEngine(MatchingEngine):
    """カスタムスコアリング手法を実装したマッチングエンジン"""
    
    def _custom_scoring(self, matches):
        """カスタムスコアリング手法"""
        scored_results = []
        
        for song_id, match_data in matches.items():
            time_pairs = match_data['time_pairs']
            
            # カスタムスコア計算ロジック
            base_score = len(time_pairs)
            
            # 時間分布の均一性を評価
            if len(time_pairs) > 1:
                time_offsets = [pair['query_time'] for pair in time_pairs]
                time_span = max(time_offsets) - min(time_offsets)
                distribution_score = time_span / len(time_pairs) if time_span > 0 else 1
            else:
                distribution_score = 1
            
            # 最終スコア
            final_score = base_score * distribution_score
            
            scored_results.append({
                'song_id': song_id,
                'score': final_score,
                'match_count': len(time_pairs),
                'distribution_score': distribution_score,
                'method': 'custom'
            })
        
        return scored_results

# カスタムエンジンを使用
custom_engine = CustomMatchingEngine(database, scoring_method='custom')
results = custom_engine.identify_audio(query_fingerprints)
```

### 専用解析ツールの使用

```python
from mimizam.spectrogram_analyzer import SpectrogramAnalyzer
from mimizam.hash_generator import HashGenerator
from mimizam.adaptive_parameter_tuner import AdaptiveParameterTuner

# 専用解析ツールを初期化
analyzer = SpectrogramAnalyzer(sample_rate=22050)
hash_generator = HashGenerator(target_zone_size=5)
tuner = AdaptiveParameterTuner(fingerprinter)

# 音声データを読み込み
import librosa
audio_data, sr = librosa.load("song.wav", sr=22050)

# スペクトログラム解析
analysis_result = analyzer.analyze_audio(audio_data)
spectrogram = analysis_result['spectrogram']
characteristics = analysis_result['characteristics']

print(f"音声特性: {characteristics}")

# 適応的パラメータ調整
adjusted_params = tuner.tune_parameters(audio_data)
print(f"調整されたパラメータ: {adjusted_params}")

# ピーク検出とハッシュ生成
peaks = fingerprinter._detect_peaks_from_spectrogram(spectrogram)
hashes = hash_generator.generate_hashes(peaks)

print(f"検出されたピーク数: {len(peaks)}")
print(f"生成されたハッシュ数: {len(hashes)}")
```

低レベルコンポーネントを直接使用することで、mimizamシステムの詳細な制御とカスタマイゼーションが可能になります。これらのコンポーネントは、特定の要件に合わせた独自の音声指紋システムを構築する際の基盤として活用できます。
