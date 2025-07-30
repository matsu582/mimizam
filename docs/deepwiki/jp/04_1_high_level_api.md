# 高レベルAPI

このドキュメントでは、mimizamの高レベルAPIについて詳しく説明します。Mimizamクラス、ファクトリ関数、便利メソッドなど、日常的な使用で最も重要なAPIコンポーネントを扱います。

低レベルコンポーネントについては、[低レベルコンポーネント](./04_2_low_level_components.md)を参照してください。

## 概要

高レベルAPIは、mimizamの機能を簡単に使用できるように設計された統合インターフェースです。複雑な内部実装を隠蔽し、直感的で使いやすいメソッドを提供します。

## Mimizamクラス

### クラス定義

```python
class Mimizam:
    """
    mimizam統合インターフェース
    
    音声指紋生成、データベース管理、楽曲識別の全機能を
    統合した高レベルインターフェースを提供します。
    """
    
    def __init__(self, fingerprinter, database):
        """
        Mimizamインスタンスを初期化
        
        Args:
            fingerprinter (AudioFingerprinter): 音声指紋生成器
            database (FingerprintDatabase): 指紋データベース
        """
        self.fingerprinter = fingerprinter
        self.database = database
```

### 楽曲管理メソッド

#### add_song()

```python
def add_song(self, audio_path, song_name, **metadata):
    """
    楽曲をデータベースに追加
    
    Args:
        audio_path (str): 音声ファイルのパス
        song_name (str): 楽曲名
        **metadata: 追加のメタデータ
            - artist (str): アーティスト名
            - album (str): アルバム名
            - duration (float): 再生時間（秒）
            - genre (str): ジャンル
            - year (int): リリース年
            - track_number (int): トラック番号
    
    Returns:
        int: 楽曲ID
    
    Raises:
        AudioProcessingError: 音声ファイルの読み込みまたは処理エラー
        DatabaseError: データベース操作エラー
        FileNotFoundError: 音声ファイルが見つからない
    
    Example:
        >>> mimizam = create_mimizam_sqlite("music.db")
        >>> song_id = mimizam.add_song(
        ...     "path/to/song.wav",
        ...     song_name="My Favorite Song",
        ...     artist="Artist Name",
        ...     album="Album Name",
        ...     year=2023
        ... )
        >>> print(f"楽曲ID: {song_id}")
    """
    try:
        # 音声ファイルの存在確認
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"音声ファイルが見つかりません: {audio_path}")
        
        # 指紋を生成
        fingerprints = self.fingerprinter.generate_fingerprints(audio_path)
        
        # メタデータに追加情報を設定
        metadata['file_path'] = audio_path
        if 'duration' not in metadata:
            metadata['duration'] = self._get_audio_duration(audio_path)
        
        # データベースに保存
        song_id = self.database.store_song(song_name, fingerprints, **metadata)
        
        return song_id
        
    except Exception as e:
        if isinstance(e, (AudioProcessingError, DatabaseError, FileNotFoundError)):
            raise
        else:
            raise AudioProcessingError(f"楽曲追加エラー: {e}")
```

#### get_song_info()

```python
def get_song_info(self, song_id):
    """
    楽曲情報を取得
    
    Args:
        song_id (int): 楽曲ID
    
    Returns:
        dict: 楽曲情報
            - id (int): 楽曲ID
            - name (str): 楽曲名
            - artist (str): アーティスト名
            - album (str): アルバム名
            - duration (float): 再生時間
            - file_path (str): ファイルパス
            - created_at (datetime): 作成日時
    
    Raises:
        DatabaseError: データベース操作エラー
        ValueError: 無効な楽曲ID
    
    Example:
        >>> song_info = mimizam.get_song_info(1)
        >>> print(f"楽曲名: {song_info['name']}")
        >>> print(f"アーティスト: {song_info['artist']}")
    """
    try:
        song_info = self.database.get_song_info(song_id)
        if not song_info:
            raise ValueError(f"楽曲ID {song_id} が見つかりません")
        return song_info
    except Exception as e:
        if isinstance(e, (DatabaseError, ValueError)):
            raise
        else:
            raise DatabaseError(f"楽曲情報取得エラー: {e}")
```

#### get_song_count()

```python
def get_song_count(self):
    """
    データベース内の楽曲数を取得
    
    Returns:
        int: 楽曲数
    
    Example:
        >>> count = mimizam.get_song_count()
        >>> print(f"データベース内楽曲数: {count}")
    """
    return self.database.get_song_count()
```

#### delete_song()

```python
def delete_song(self, song_id):
    """
    楽曲を削除
    
    Args:
        song_id (int): 削除する楽曲ID
    
    Returns:
        bool: 削除成功フラグ
    
    Raises:
        DatabaseError: データベース操作エラー
        ValueError: 無効な楽曲ID
    
    Example:
        >>> success = mimizam.delete_song(1)
        >>> if success:
        ...     print("楽曲を削除しました")
    """
    try:
        return self.database.delete_song(song_id)
    except Exception as e:
        if isinstance(e, (DatabaseError, ValueError)):
            raise
        else:
            raise DatabaseError(f"楽曲削除エラー: {e}")
```

### 音声識別メソッド

#### identify()

```python
def identify(self, audio_path, threshold=None):
    """
    音声ファイルから楽曲を識別
    
    Args:
        audio_path (str): 識別する音声ファイルのパス
        threshold (float, optional): マッチング閾値
    
    Returns:
        list: マッチした楽曲のリスト
            各要素は以下の辞書:
            - song_id (int): 楽曲ID
            - song_name (str): 楽曲名
            - artist (str): アーティスト名
            - album (str): アルバム名
            - score (float): マッチスコア
            - confidence (float): 信頼度
            - match_count (int): マッチ数
            - time_offset (float): 時間オフセット
    
    Raises:
        AudioProcessingError: 音声処理エラー
        FileNotFoundError: 音声ファイルが見つからない
    
    Example:
        >>> matches = mimizam.identify("query.wav")
        >>> if matches:
        ...     best_match = matches[0]
        ...     print(f"識別結果: {best_match['song_name']}")
        ...     print(f"信頼度: {best_match['confidence']:.3f}")
        ... else:
        ...     print("マッチする楽曲が見つかりませんでした")
    """
    try:
        # 音声ファイルの存在確認
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"音声ファイルが見つかりません: {audio_path}")
        
        # 指紋を生成
        query_fingerprints = self.fingerprinter.generate_fingerprints(audio_path)
        
        # 識別を実行
        return self._identify_fingerprints(query_fingerprints, threshold)
        
    except Exception as e:
        if isinstance(e, (AudioProcessingError, FileNotFoundError)):
            raise
        else:
            raise AudioProcessingError(f"音声識別エラー: {e}")
```

#### identify_audio_data()

```python
def identify_audio_data(self, audio_data, sample_rate, threshold=None):
    """
    音声データから楽曲を識別
    
    Args:
        audio_data (numpy.ndarray): 音声データ
        sample_rate (int): サンプリングレート
        threshold (float, optional): マッチング閾値
    
    Returns:
        list: マッチした楽曲のリスト
    
    Raises:
        AudioProcessingError: 音声処理エラー
        ValueError: 無効な音声データ
    
    Example:
        >>> import librosa
        >>> audio_data, sr = librosa.load("query.wav")
        >>> matches = mimizam.identify_audio_data(audio_data, sr)
    """
    try:
        if audio_data is None or len(audio_data) == 0:
            raise ValueError("無効な音声データです")
        
        # 指紋を生成
        query_fingerprints = self.fingerprinter.generate_fingerprints_from_data(
            audio_data, sample_rate
        )
        
        # 識別を実行
        return self._identify_fingerprints(query_fingerprints, threshold)
        
    except Exception as e:
        if isinstance(e, (AudioProcessingError, ValueError)):
            raise
        else:
            raise AudioProcessingError(f"音声データ識別エラー: {e}")
```

### 可視化メソッド

#### generate_spectrogram()

```python
def generate_spectrogram(self, audio_path):
    """
    スペクトログラムを生成
    
    Args:
        audio_path (str): 音声ファイルのパス
    
    Returns:
        numpy.ndarray: スペクトログラム（時間×周波数）
    
    Raises:
        AudioProcessingError: 音声処理エラー
        FileNotFoundError: 音声ファイルが見つからない
    
    Example:
        >>> spectrogram = mimizam.generate_spectrogram("song.wav")
        >>> print(f"スペクトログラム形状: {spectrogram.shape}")
    """
    try:
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"音声ファイルが見つかりません: {audio_path}")
        
        return self.fingerprinter.generate_spectrogram(audio_path)
        
    except Exception as e:
        if isinstance(e, (AudioProcessingError, FileNotFoundError)):
            raise
        else:
            raise AudioProcessingError(f"スペクトログラム生成エラー: {e}")
```

#### detect_peaks()

```python
def detect_peaks(self, audio_path):
    """
    ピークを検出
    
    Args:
        audio_path (str): 音声ファイルのパス
    
    Returns:
        list: 検出されたピーク座標のリスト
            各要素は (time, frequency) のタプル
    
    Raises:
        AudioProcessingError: 音声処理エラー
        FileNotFoundError: 音声ファイルが見つからない
    
    Example:
        >>> peaks = mimizam.detect_peaks("song.wav")
        >>> print(f"検出されたピーク数: {len(peaks)}")
        >>> for time, freq in peaks[:5]:
        ...     print(f"時間: {time}, 周波数: {freq}")
    """
    try:
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"音声ファイルが見つかりません: {audio_path}")
        
        return self.fingerprinter.detect_peaks(audio_path)
        
    except Exception as e:
        if isinstance(e, (AudioProcessingError, FileNotFoundError)):
            raise
        else:
            raise AudioProcessingError(f"ピーク検出エラー: {e}")
```

## ファクトリ関数

### create_mimizam_sqlite()

```python
def create_mimizam_sqlite(db_path, **params):
    """
    SQLiteバックエンドでMimizamインスタンスを作成
    
    Args:
        db_path (str): SQLiteデータベースファイルのパス
        **params: AudioFingerprinterのパラメータ
            - sample_rate (int): サンプリングレート（デフォルト: 22050）
            - n_fft (int): FFTサイズ（デフォルト: 2048）
            - hop_length (int): ホップ長（デフォルト: 512）
            - peak_threshold (float): ピーク検出閾値（デフォルト: 0.15）
            - min_peak_distance (int): ピーク間最小距離（デフォルト: 10）
            - target_zone_size (int): ターゲットゾーンサイズ（デフォルト: 5）
            - max_time_delta (int): 最大時間差（デフォルト: 200）
    
    Returns:
        Mimizam: 設定済みのMimizamインスタンス
    
    Example:
        >>> # 基本的な使用
        >>> mimizam = create_mimizam_sqlite("music.db")
        >>> 
        >>> # カスタムパラメータ
        >>> mimizam = create_mimizam_sqlite(
        ...     "music.db",
        ...     sample_rate=44100,
        ...     peak_threshold=0.1,
        ...     target_zone_size=3
        ... )
    """
    from mimizam.backends.sqlite_backend import SQLiteBackend
    from mimizam.audio_fingerprinter import AudioFingerprinter
    from mimizam.fingerprint_database import FingerprintDatabase
    
    # バックエンドを作成
    backend = SQLiteBackend(db_path)
    
    # 指紋生成器を作成
    fingerprinter = AudioFingerprinter(**params)
    
    # データベースを作成
    database = FingerprintDatabase(backend)
    
    # Mimizamインスタンスを作成
    return Mimizam(fingerprinter, database)
```

### create_mimizam_mysql()

```python
def create_mimizam_mysql(host, user, password, database, port=3306, **params):
    """
    MySQLバックエンドでMimizamインスタンスを作成
    
    Args:
        host (str): MySQLサーバーのホスト
        user (str): ユーザー名
        password (str): パスワード
        database (str): データベース名
        port (int, optional): ポート番号（デフォルト: 3306）
        **params: AudioFingerprinterのパラメータ
    
    Returns:
        Mimizam: 設定済みのMimizamインスタンス
    
    Example:
        >>> mimizam = create_mimizam_mysql(
        ...     host="localhost",
        ...     user="mimizam_user",
        ...     password="secure_password",
        ...     database="music_db"
        ... )
        >>> 
        >>> # SSL接続
        >>> mimizam = create_mimizam_mysql(
        ...     host="mysql.example.com",
        ...     user="mimizam_user",
        ...     password="secure_password",
        ...     database="music_db",
        ...     ssl_disabled=False,
        ...     ssl_ca="/path/to/ca.pem"
        ... )
    """
    from mimizam.backends.mysql_backend import MySQLBackend
    from mimizam.audio_fingerprinter import AudioFingerprinter
    from mimizam.fingerprint_database import FingerprintDatabase
    
    # バックエンドを作成
    backend = MySQLBackend(host, user, password, database, port)
    
    # 指紋生成器を作成
    fingerprinter = AudioFingerprinter(**params)
    
    # データベースを作成
    database = FingerprintDatabase(backend)
    
    # Mimizamインスタンスを作成
    return Mimizam(fingerprinter, database)
```

### create_mimizam_postgresql()

```python
def create_mimizam_postgresql(host, user, password, database, port=5432, **params):
    """
    PostgreSQLバックエンドでMimizamインスタンスを作成
    
    Args:
        host (str): PostgreSQLサーバーのホスト
        user (str): ユーザー名
        password (str): パスワード
        database (str): データベース名
        port (int, optional): ポート番号（デフォルト: 5432）
        **params: AudioFingerprinterのパラメータ
    
    Returns:
        Mimizam: 設定済みのMimizamインスタンス
    
    Example:
        >>> mimizam = create_mimizam_postgresql(
        ...     host="postgres.example.com",
        ...     user="mimizam_user",
        ...     password="secure_password",
        ...     database="music_db"
        ... )
        >>> 
        >>> # SSL接続
        >>> mimizam = create_mimizam_postgresql(
        ...     host="postgres.example.com",
        ...     user="mimizam_user",
        ...     password="secure_password",
        ...     database="music_db",
        ...     sslmode="require"
        ... )
    """
    from mimizam.backends.postgresql_backend import PostgreSQLBackend
    from mimizam.audio_fingerprinter import AudioFingerprinter
    from mimizam.fingerprint_database import FingerprintDatabase
    
    # バックエンドを作成
    backend = PostgreSQLBackend(host, user, password, database, port)
    
    # 指紋生成器を作成
    fingerprinter = AudioFingerprinter(**params)
    
    # データベースを作成
    database = FingerprintDatabase(backend)
    
    # Mimizamインスタンスを作成
    return Mimizam(fingerprinter, database)
```

### create_mimizam_elasticsearch()

```python
def create_mimizam_elasticsearch(hosts, index_name="mimizam", **params):
    """
    ElasticsearchバックエンドでMimizamインスタンスを作成
    
    Args:
        hosts (str or list): Elasticsearchホスト
        index_name (str, optional): インデックス名（デフォルト: "mimizam"）
        **params: AudioFingerprinterのパラメータ
    
    Returns:
        Mimizam: 設定済みのMimizamインスタンス
    
    Example:
        >>> # 単一ノード
        >>> mimizam = create_mimizam_elasticsearch(
        ...     hosts="localhost:9200",
        ...     index_name="music_fingerprints"
        ... )
        >>> 
        >>> # 複数ノード
        >>> mimizam = create_mimizam_elasticsearch(
        ...     hosts=[
        ...         {"host": "es1.example.com", "port": 9200},
        ...         {"host": "es2.example.com", "port": 9200}
        ...     ],
        ...     index_name="music_fingerprints"
        ... )
        >>> 
        >>> # 認証付き
        >>> mimizam = create_mimizam_elasticsearch(
        ...     hosts="es.example.com:9200",
        ...     index_name="music_fingerprints",
        ...     username="elastic",
        ...     password="password",
        ...     use_ssl=True
        ... )
    """
    from mimizam.backends.elasticsearch_backend import ElasticsearchBackend
    from mimizam.audio_fingerprinter import AudioFingerprinter
    from mimizam.fingerprint_database import FingerprintDatabase
    
    # バックエンドを作成
    backend = ElasticsearchBackend(hosts, index_name)
    
    # 指紋生成器を作成
    fingerprinter = AudioFingerprinter(**params)
    
    # データベースを作成
    database = FingerprintDatabase(backend)
    
    # Mimizamインスタンスを作成
    return Mimizam(fingerprinter, database)
```

## 便利メソッド

### バッチ処理

```python
def batch_add_songs(mimizam, file_list, progress_callback=None):
    """
    複数の楽曲をバッチで追加
    
    Args:
        mimizam (Mimizam): Mimizamインスタンス
        file_list (list): 音声ファイルパスのリスト
        progress_callback (callable, optional): 進捗コールバック関数
    
    Returns:
        dict: 処理結果
            - success_count (int): 成功数
            - error_count (int): エラー数
            - errors (list): エラー詳細
    
    Example:
        >>> files = ["song1.wav", "song2.mp3", "song3.flac"]
        >>> 
        >>> def progress(current, total, filename):
        ...     print(f"処理中 {current}/{total}: {filename}")
        >>> 
        >>> result = batch_add_songs(mimizam, files, progress)
        >>> print(f"成功: {result['success_count']}, エラー: {result['error_count']}")
    """
    import os
    
    success_count = 0
    error_count = 0
    errors = []
    
    for i, filepath in enumerate(file_list):
        try:
            if progress_callback:
                progress_callback(i + 1, len(file_list), os.path.basename(filepath))
            
            song_name = os.path.splitext(os.path.basename(filepath))[0]
            mimizam.add_song(filepath, song_name=song_name)
            success_count += 1
            
        except Exception as e:
            error_count += 1
            errors.append({
                'file': filepath,
                'error': str(e)
            })
    
    return {
        'success_count': success_count,
        'error_count': error_count,
        'errors': errors
    }
```

### 統計情報

```python
def get_database_statistics(mimizam):
    """
    データベース統計情報を取得
    
    Args:
        mimizam (Mimizam): Mimizamインスタンス
    
    Returns:
        dict: 統計情報
            - song_count (int): 楽曲数
            - fingerprint_count (int): 指紋数
            - avg_fingerprints_per_song (float): 楽曲あたり平均指紋数
            - database_size (str): データベースサイズ
    
    Example:
        >>> stats = get_database_statistics(mimizam)
        >>> print(f"楽曲数: {stats['song_count']}")
        >>> print(f"指紋数: {stats['fingerprint_count']}")
    """
    song_count = mimizam.get_song_count()
    
    # データベース固有の統計を取得
    db_stats = mimizam.database.get_statistics()
    
    fingerprint_count = db_stats.get('fingerprint_count', 0)
    avg_fingerprints = fingerprint_count / song_count if song_count > 0 else 0
    
    return {
        'song_count': song_count,
        'fingerprint_count': fingerprint_count,
        'avg_fingerprints_per_song': avg_fingerprints,
        'database_size': db_stats.get('database_size', 'Unknown'),
        'backend_type': db_stats.get('backend_type', 'Unknown')
    }
```

## 使用例

### 基本的な使用例

```python
from mimizam import create_mimizam_sqlite

# インスタンス作成
mimizam = create_mimizam_sqlite("music.db")

# 楽曲追加
song_id = mimizam.add_song(
    "path/to/song.wav",
    song_name="My Favorite Song",
    artist="Artist Name",
    album="Album Name"
)
print(f"楽曲ID: {song_id}")

# 音声識別
matches = mimizam.identify("path/to/query.wav")

if matches:
    best_match = matches[0]
    print(f"識別結果: {best_match['song_name']}")
    print(f"アーティスト: {best_match['artist']}")
    print(f"信頼度: {best_match['confidence']:.3f}")
else:
    print("マッチする楽曲が見つかりませんでした")

# 統計情報
print(f"データベース内楽曲数: {mimizam.get_song_count()}")
```

### 高度な使用例

```python
import os
from mimizam import create_mimizam_mysql

# MySQL接続
mimizam = create_mimizam_mysql(
    host="localhost",
    user="mimizam_user",
    password="secure_password",
    database="music_production",
    # カスタムパラメータ
    sample_rate=44100,
    peak_threshold=0.1,
    target_zone_size=3
)

# バッチ処理
music_dir = "path/to/music/collection"
audio_files = []

for root, dirs, files in os.walk(music_dir):
    for file in files:
        if file.endswith(('.wav', '.mp3', '.flac')):
            audio_files.append(os.path.join(root, file))

def show_progress(current, total, filename):
    percent = (current / total) * 100
    print(f"[{percent:5.1f}%] {filename}")

result = batch_add_songs(mimizam, audio_files, show_progress)
print(f"処理完了: 成功 {result['success_count']}, エラー {result['error_count']}")

# エラー詳細表示
for error in result['errors']:
    print(f"エラー: {error['file']} - {error['error']}")

# 統計情報
stats = get_database_statistics(mimizam)
print(f"データベース統計:")
print(f"  楽曲数: {stats['song_count']}")
print(f"  指紋数: {stats['fingerprint_count']}")
print(f"  平均指紋数/楽曲: {stats['avg_fingerprints_per_song']:.1f}")
```

### 可視化例

```python
import matplotlib.pyplot as plt
import numpy as np

# スペクトログラムとピーク検出の可視化
spectrogram = mimizam.generate_spectrogram("song.wav")
peaks = mimizam.detect_peaks("song.wav")

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8))

# スペクトログラム表示
im = ax1.imshow(spectrogram, aspect='auto', origin='lower', cmap='viridis')
ax1.set_title('スペクトログラム')
ax1.set_ylabel('周波数')
plt.colorbar(im, ax=ax1)

# ピーク検出結果表示
ax2.imshow(spectrogram, aspect='auto', origin='lower', cmap='viridis', alpha=0.7)
if peaks:
    peak_times = [p[0] for p in peaks]
    peak_freqs = [p[1] for p in peaks]
    ax2.scatter(peak_times, peak_freqs, c='red', s=10, alpha=0.8)

ax2.set_title('検出されたピーク')
ax2.set_xlabel('時間')
ax2.set_ylabel('周波数')

plt.tight_layout()
plt.show()

print(f"検出されたピーク数: {len(peaks)}")
```

高レベルAPIにより、mimizamの強力な機能を簡単に利用できます。ファクトリ関数を使用することで、異なるデータベースバックエンド間での切り替えも容易に行えます。
