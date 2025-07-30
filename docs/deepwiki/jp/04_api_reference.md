# APIリファレンス

> 関連するソースファイル

このドキュメントでは、mimizamシステムの完全なAPIリファレンスを提供します。高レベルAPI、低レベルコンポーネント、ファクトリ関数、設定オプションについて詳しく説明します。

詳細な実装については、以下を参照してください：
- [高レベルAPI](./04_1_high_level_api.md) - Mimizamクラスとファクトリ関数
- [低レベルコンポーネント](./04_2_low_level_components.md) - 個別コンポーネントの詳細

## API概要

mimizamは、使いやすさと柔軟性のバランスを取った階層化されたAPIを提供します。各レベルは特定の用途と技術的要求に対応しています。

### API階層アーキテクチャ

```
┌─────────────────────────────────────────────────────────────┐
│                    高レベルAPI                              │
├─────────────────────────────────────────────────────────────┤
│  Mimizamクラス  │  ファクトリ関数  │  便利メソッド          │
│  • 統合インターフェース • 簡単セットアップ • 自動設定      │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                   中レベルAPI                               │
├─────────────────────────────────────────────────────────────┤
│ AudioFingerprinter │ FingerprintDatabase │ MatchingEngine   │
│ • カスタム設定 • 詳細制御 • パフォーマンス調整            │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                   低レベルAPI                               │
├─────────────────────────────────────────────────────────────┤
│ DatabaseBackend │ SpectrogramAnalyzer │ HashGenerator      │
│ • 完全制御 • 拡張開発 • アルゴリズム実装                  │
└─────────────────────────────────────────────────────────────┘
```

### API使用レベルの選択指針

| レベル | 対象ユーザー | 用途 | 技術的要求 |
|--------|-------------|------|-----------|
| **高レベル** | 一般開発者 | 迅速なプロトタイピング、標準的な音声識別 | 基本的なPython知識 |
| **中レベル** | 経験豊富な開発者 | カスタマイズされたソリューション、性能最適化 | 音声処理の理解 |
| **低レベル** | 専門家、研究者 | アルゴリズム研究、新機能開発 | 深い技術的専門知識 |

## 主要クラスとメソッド

### Mimizamクラス

統合インターフェースを提供するメインクラスです。

```python
class Mimizam:
    """mimizam統合インターフェース"""
    
    def __init__(self, fingerprinter, database):
        """
        Mimizamインスタンスを初期化
        
        Args:
            fingerprinter: AudioFingerprinterインスタンス
            database: FingerprintDatabaseインスタンス
        """
    
    def add_song(self, audio_path, song_name, **metadata):
        """
        楽曲をデータベースに追加
        
        Args:
            audio_path (str): 音声ファイルのパス
            song_name (str): 楽曲名
            **metadata: 追加のメタデータ（artist, album, etc.）
            
        Returns:
            int: 楽曲ID
            
        Raises:
            AudioProcessingError: 音声処理エラー
            DatabaseError: データベースエラー
        """
    
    def identify(self, audio_path, threshold=None):
        """
        音声ファイルから楽曲を識別
        
        Args:
            audio_path (str): 識別する音声ファイルのパス
            threshold (float, optional): マッチング閾値
            
        Returns:
            list: マッチした楽曲のリスト
        """
    
    def identify_audio_data(self, audio_data, sample_rate):
        """
        音声データから楽曲を識別
        
        Args:
            audio_data (numpy.ndarray): 音声データ
            sample_rate (int): サンプリングレート
            
        Returns:
            list: マッチした楽曲のリスト
        """
    
    def get_song_count(self):
        """
        データベース内の楽曲数を取得
        
        Returns:
            int: 楽曲数
        """
    
    def get_song_info(self, song_id):
        """
        楽曲情報を取得
        
        Args:
            song_id (int): 楽曲ID
            
        Returns:
            dict: 楽曲情報
        """
    
    def delete_song(self, song_id):
        """
        楽曲を削除
        
        Args:
            song_id (int): 削除する楽曲ID
            
        Returns:
            bool: 削除成功フラグ
        """
    
    def generate_spectrogram(self, audio_path):
        """
        スペクトログラムを生成
        
        Args:
            audio_path (str): 音声ファイルのパス
            
        Returns:
            numpy.ndarray: スペクトログラム
        """
    
    def detect_peaks(self, audio_path):
        """
        ピークを検出
        
        Args:
            audio_path (str): 音声ファイルのパス
            
        Returns:
            list: 検出されたピーク座標
        """
```

## ファクトリ関数

各データベースバックエンドに対応した便利な作成関数です。

### SQLiteファクトリ

```python
def create_mimizam_sqlite(db_path, **params):
    """
    SQLiteバックエンドでMimizamインスタンスを作成
    
    Args:
        db_path (str): SQLiteデータベースファイルのパス
        **params: AudioFingerprinterのパラメータ
        
    Returns:
        Mimizam: 設定済みのMimizamインスタンス
        
    Example:
        >>> mimizam = create_mimizam_sqlite("music.db")
        >>> mimizam = create_mimizam_sqlite(
        ...     "music.db",
        ...     sample_rate=22050,
        ...     peak_threshold=0.15
        ... )
    """
```

### MySQLファクトリ

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
    """
```

### PostgreSQLファクトリ

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
        ...     database="music_db",
        ...     sslmode="require"
        ... )
    """
```

### Elasticsearchファクトリ

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
        ...     ]
        ... )
    """
```

## 設定パラメータ

### 音声処理パラメータ

```python
AUDIO_PARAMS = {
    'sample_rate': 22050,           # サンプリングレート (Hz)
    'n_fft': 2048,                  # FFTサイズ
    'hop_length': 512,              # ホップ長
    'window': 'hann',               # 窓関数
}
```

### ピーク検出パラメータ

```python
PEAK_DETECTION_PARAMS = {
    'peak_threshold': 0.15,         # ピーク検出閾値
    'min_peak_distance': 10,        # ピーク間最小距離
    'peak_neighborhood_size': 20,   # ピーク近傍サイズ
}
```

### ハッシュ生成パラメータ

```python
HASH_GENERATION_PARAMS = {
    'target_zone_size': 5,          # ターゲットゾーンサイズ
    'max_time_delta': 200,          # 最大時間差
    'hash_time_quantization': 1,    # 時間量子化
}
```

### マッチングパラメータ

```python
MATCHING_PARAMS = {
    'match_threshold': 0.1,         # マッチング閾値
    'max_matches': 10,              # 最大マッチ数
    'scoring_method': 'weighted',   # スコアリング手法
}
```

## データ構造

### 指紋データ構造

```python
fingerprint = {
    'hash': int,                    # ハッシュ値
    'time_offset': float,           # 時間オフセット
    'anchor_freq': int,             # アンカー周波数
    'target_freq': int,             # ターゲット周波数
    'time_delta': int,              # 時間差
}
```

### マッチ結果データ構造

```python
match_result = {
    'song_id': int,                 # 楽曲ID
    'song_name': str,               # 楽曲名
    'artist': str,                  # アーティスト名
    'album': str,                   # アルバム名
    'score': float,                 # マッチスコア
    'match_count': int,             # マッチ数
    'confidence': float,            # 信頼度
    'time_offset': float,           # 時間オフセット
    'method': str,                  # スコアリング手法
}
```

### 楽曲情報データ構造

```python
song_info = {
    'id': int,                      # 楽曲ID
    'name': str,                    # 楽曲名
    'artist': str,                  # アーティスト名
    'album': str,                   # アルバム名
    'duration': float,              # 再生時間（秒）
    'file_path': str,               # ファイルパス
    'created_at': datetime,         # 作成日時
}
```

## エラーハンドリング

### 例外クラス

```python
class MimizamError(Exception):
    """mimizam基底例外"""
    pass

class AudioProcessingError(MimizamError):
    """音声処理関連エラー"""
    pass

class DatabaseError(MimizamError):
    """データベース関連エラー"""
    pass

class FingerprintError(MimizamError):
    """指紋生成関連エラー"""
    pass

class MatchingError(MimizamError):
    """マッチング関連エラー"""
    pass
```

### エラー処理例

```python
try:
    mimizam = create_mimizam_sqlite("music.db")
    mimizam.add_song("song.wav", song_name="Test Song")
    matches = mimizam.identify("query.wav")
except AudioProcessingError as e:
    print(f"音声処理エラー: {e}")
except DatabaseError as e:
    print(f"データベースエラー: {e}")
except MimizamError as e:
    print(f"mimizamエラー: {e}")
except Exception as e:
    print(f"予期しないエラー: {e}")
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

# 音声識別
matches = mimizam.identify("path/to/query.wav")

# 結果表示
for match in matches:
    print(f"楽曲: {match['song_name']}")
    print(f"スコア: {match['score']:.3f}")
```

### カスタムパラメータ使用例

```python
# カスタムパラメータでインスタンス作成
mimizam = create_mimizam_sqlite(
    "music.db",
    sample_rate=44100,
    peak_threshold=0.1,
    target_zone_size=3,
    match_threshold=0.05
)

# バッチ処理
import os

music_dir = "path/to/music"
for filename in os.listdir(music_dir):
    if filename.endswith(('.wav', '.mp3')):
        filepath = os.path.join(music_dir, filename)
        song_name = os.path.splitext(filename)[0]
        
        try:
            mimizam.add_song(filepath, song_name=song_name)
            print(f"追加完了: {song_name}")
        except Exception as e:
            print(f"エラー {filename}: {e}")
```

### 高度な使用例

```python
# 複数データベースバックエンドの使用
sqlite_mimizam = create_mimizam_sqlite("test.db")
mysql_mimizam = create_mimizam_mysql(
    host="localhost",
    user="user",
    password="password",
    database="music_db"
)

# 可視化
import matplotlib.pyplot as plt

spectrogram = mimizam.generate_spectrogram("song.wav")
peaks = mimizam.detect_peaks("song.wav")

plt.figure(figsize=(12, 6))
plt.imshow(spectrogram, aspect='auto', origin='lower')
plt.scatter([p[0] for p in peaks], [p[1] for p in peaks], 
           c='red', s=10, alpha=0.7)
plt.title('スペクトログラムとピーク検出結果')
plt.show()

# 統計情報
print(f"データベース内楽曲数: {mimizam.get_song_count()}")

# 楽曲情報取得
song_info = mimizam.get_song_info(song_id)
print(f"楽曲情報: {song_info}")
```

## パフォーマンス考慮事項

### メモリ使用量

- 音声ファイルは`librosa.load()`により全体がメモリに読み込まれます
- 大容量ファイルの処理時はメモリ使用量に注意してください
- バッチ処理時は適切な間隔でガベージコレクションを実行してください

### 処理速度

- SQLiteは軽量ですが、大規模データには不向きです
- MySQL/PostgreSQLは本番環境での高速処理に適しています
- Elasticsearchは分散環境での大規模検索に最適です

### 最適化のヒント

```python
# 1. 適切なパラメータ設定
mimizam = create_mimizam_sqlite(
    "music.db",
    peak_threshold=0.15,    # 高すぎると精度低下、低すぎると処理遅延
    target_zone_size=5      # 大きすぎるとノイズ増加
)

# 2. バッチ処理での効率化
def batch_add_songs(mimizam, file_list, batch_size=10):
    for i in range(0, len(file_list), batch_size):
        batch = file_list[i:i + batch_size]
        for filepath in batch:
            mimizam.add_song(filepath, song_name=os.path.basename(filepath))
        
        # 定期的にガベージコレクション
        if i % 100 == 0:
            import gc
            gc.collect()

# 3. 接続プールの使用（MySQL/PostgreSQL）
mimizam = create_mimizam_mysql(
    host="localhost",
    user="user",
    password="password",
    database="music_db",
    pool_size=10,           # 接続プールサイズ
    pool_recycle=3600       # 接続リサイクル時間
)
```

このAPIリファレンスにより、mimizamの全機能を効果的に活用できます。詳細な実装例については、個別のAPIドキュメントを参照してください。
