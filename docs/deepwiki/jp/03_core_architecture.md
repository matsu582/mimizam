# コアアーキテクチャ

> 関連するソースファイル

このドキュメントでは、mimizamシステムの全体的なアーキテクチャと主要コンポーネントについて詳しく説明します。システムの設計原則、コンポーネント間の相互作用、データフローについて包括的に解説します。

個別コンポーネントの詳細については、以下を参照してください：
- [音声指紋エンジン](./03_1_audio_fingerprinting_engine.md) - 音声処理とスペクトログラム解析
- [データベース層](./03_2_database_layer.md) - データベース抽象化とバックエンド
- [マッチング・識別システム](./03_3_matching_identification.md) - 検索とスコアリング

## システム概要

mimizamアーキテクチャは、音声指紋と識別機能を提供するために連携する4つの主要な層で構成されています：

### 高レベルシステムアーキテクチャ

mimizamは、統合されたMimizamクラスとファクトリ関数を通じて、シンプルで一貫したインターフェースを提供します。

| アーキテクチャ層 | 説明 |
|----------------|------|
| **高レベルAPI** | 統合されたMimizamクラスとファクトリ関数 |
| **コア処理パイプライン** | STFT、ピーク検出、ハッシュ生成の段階的処理 |
| **コンポーネントアーキテクチャ** | AudioFingerprinter、SpectrogramAnalyzer、HashGeneratorの連携 |
| **データフローアーキテクチャ** | 音声データの変換段階と処理フロー |

### コア処理パイプライン

```
┌─────────────────────────────────────────────────────────────┐
│                    入力層                                   │
├─────────────────────────────────────────────────────────────┤
│              生音声ファイル                                 │
└─────────────────────────────────────────────────────────────┘
                              │
                        numpy配列音声信号
                              │
┌─────────────────────────────────────────────────────────────┐
│                  適応的インテリジェンス                      │
├─────────────────────────────────────────────────────────────┤
│              AdaptiveParameterTuner                         │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                  音声指紋処理                               │
├─────────────────────────────────────────────────────────────┤
│  スペクトログラム  │  ピーク検出  │  ハッシュ生成           │
│     生成          │             │                         │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                  データベース層                             │
├─────────────────────────────────────────────────────────────┤
│  指紋保存とマッチング                                       │
└─────────────────────────────────────────────────────────────┘
```

## 主要コンポーネント

### 1. アプリケーション層

#### CLIツール
コマンドライン経由でmimizamの機能にアクセスするためのツールです。

```bash
# 楽曲の追加
python -m mimizam add-song song.wav --name "楽曲名"

# 音声識別
python -m mimizam identify query.wav

# データベース統計
python -m mimizam stats
```

#### デモアプリケーション
mimizamの機能を実演するサンプルアプリケーションです。

```python
# examples/mimizam_demo.py
from mimizam import create_mimizam_sqlite

def demo_basic_usage():
    mimizam = create_mimizam_sqlite("demo.db")
    
    # デモ楽曲の追加
    mimizam.add_song("demo_song.wav", song_name="デモ楽曲")
    
    # 識別テスト
    matches = mimizam.identify("test_clip.wav")
    return matches
```

### 2. 統合API層

#### Mimizamクラス
全ての機能を統合した高レベルインターフェースです。

```python
class Mimizam:
    def __init__(self, fingerprinter, database):
        self.fingerprinter = fingerprinter
        self.database = database
    
    def add_song(self, audio_path, song_name, **metadata):
        """楽曲をデータベースに追加"""
        
    def identify(self, audio_path, threshold=0.1):
        """音声ファイルから楽曲を識別"""
        
    def get_song_count(self):
        """データベース内の楽曲数を取得"""
```

#### ファクトリ関数
各データベースバックエンドに対応した便利な作成関数です。

```python
def create_mimizam_sqlite(db_path, **params):
    """SQLiteバックエンドでMimizamインスタンスを作成"""
    
def create_mimizam_mysql(host, user, password, database, **params):
    """MySQLバックエンドでMimizamインスタンスを作成"""
    
def create_mimizam_postgresql(host, user, password, database, **params):
    """PostgreSQLバックエンドでMimizamインスタンスを作成"""
    
def create_mimizam_elasticsearch(host, port, index_name, **params):
    """ElasticsearchバックエンドでMimizamインスタンスを作成"""
```

### 3. コア処理層

#### AudioFingerprinter
音声ファイルから指紋を生成する中核コンポーネントです。

```python
class AudioFingerprinter:
    def __init__(self, **params):
        self.sample_rate = params.get('sample_rate', 22050)
        self.n_fft = params.get('n_fft', 2048)
        self.hop_length = params.get('hop_length', 512)
    
    def generate_fingerprints(self, audio_path):
        """音声ファイルから指紋を生成"""
        
    def generate_spectrogram(self, audio_data):
        """スペクトログラムを生成"""
        
    def detect_peaks(self, spectrogram):
        """スペクトログラムからピークを検出"""
```

#### FingerprintDatabase
指紋の保存と検索を管理するコンポーネントです。

```python
class FingerprintDatabase:
    def __init__(self, backend):
        self.backend = backend
    
    def store_fingerprints(self, song_id, fingerprints):
        """指紋をデータベースに保存"""
        
    def search_fingerprints(self, query_fingerprints):
        """指紋を検索してマッチを取得"""
        
    def get_song_info(self, song_id):
        """楽曲情報を取得"""
```

#### AdaptiveParameters
音声特性に基づいてパラメータを自動調整するコンポーネントです。

```python
class AdaptiveParameters:
    def analyze_audio_characteristics(self, audio_data):
        """音声特性を分析"""
        
    def adjust_parameters(self, characteristics):
        """特性に基づいてパラメータを調整"""
        
    def get_optimized_config(self):
        """最適化された設定を取得"""
```

### 4. データベース層

#### 抽象基底クラス
全てのデータベースバックエンドが実装する共通インターフェースです。

```python
from abc import ABC, abstractmethod

class DatabaseBackend(ABC):
    @abstractmethod
    def connect(self):
        """データベースに接続"""
        
    @abstractmethod
    def create_tables(self):
        """必要なテーブルを作成"""
        
    @abstractmethod
    def insert_song(self, song_name, **metadata):
        """楽曲情報を挿入"""
        
    @abstractmethod
    def insert_fingerprints(self, song_id, fingerprints):
        """指紋を挿入"""
        
    @abstractmethod
    def search_fingerprints(self, fingerprints):
        """指紋を検索"""
```

#### 具体的なバックエンド実装

```python
# SQLiteバックエンド
class SQLiteBackend(DatabaseBackend):
    def __init__(self, db_path):
        self.db_path = db_path
        self.connection = None

# MySQLバックエンド
class MySQLBackend(DatabaseBackend):
    def __init__(self, host, user, password, database):
        self.config = {
            'host': host,
            'user': user,
            'password': password,
            'database': database
        }

# PostgreSQLバックエンド
class PostgreSQLBackend(DatabaseBackend):
    def __init__(self, host, user, password, database):
        self.connection_string = f"postgresql://{user}:{password}@{host}/{database}"

# Elasticsearchバックエンド
class ElasticsearchBackend(DatabaseBackend):
    def __init__(self, host, port, index_name):
        self.client = Elasticsearch([{'host': host, 'port': port}])
        self.index_name = index_name
```

## データフロー

### 楽曲追加プロセス

```
音声ファイル
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
データベース保存
```

### 音声識別プロセス

```
クエリ音声
    │
    ▼
指紋生成 (上記と同様)
    │
    ▼
データベース検索
    │
    ▼
マッチング・スコアリング
    │
    ▼
結果ランキング
    │
    ▼
識別結果
```

## 設定管理

### パラメータ設定
システム全体の動作は、設定パラメータによって制御されます。

```python
# デフォルト設定
DEFAULT_CONFIG = {
    # 音声処理パラメータ
    'sample_rate': 22050,
    'n_fft': 2048,
    'hop_length': 512,
    'window': 'hann',
    
    # ピーク検出パラメータ
    'peak_threshold': 0.15,
    'min_peak_distance': 10,
    'peak_neighborhood_size': 20,
    
    # ハッシュ生成パラメータ
    'target_zone_size': 5,
    'max_time_delta': 200,
    'hash_time_quantization': 1,
    
    # 識別パラメータ
    'match_threshold': 0.1,
    'max_matches': 10
}
```

### 適応的設定
音声特性に基づく自動パラメータ調整：

```python
def adapt_parameters(audio_characteristics):
    """音声特性に基づいてパラメータを調整"""
    config = DEFAULT_CONFIG.copy()
    
    # 動的範囲に基づく調整
    if audio_characteristics['dynamic_range'] < 20:
        config['peak_threshold'] *= 0.8
    
    # ノイズレベルに基づく調整
    if audio_characteristics['noise_level'] > 0.1:
        config['min_peak_distance'] *= 1.2
    
    return config
```

## エラーハンドリング

### 例外階層
```python
class MimizamError(Exception):
    """mimizam基底例外"""

class AudioProcessingError(MimizamError):
    """音声処理関連エラー"""

class DatabaseError(MimizamError):
    """データベース関連エラー"""

class FingerprintError(MimizamError):
    """指紋生成関連エラー"""
```

### エラー処理戦略
```python
def robust_add_song(mimizam, audio_path, song_name):
    """堅牢な楽曲追加処理"""
    try:
        mimizam.add_song(audio_path, song_name=song_name)
        return True
    except AudioProcessingError as e:
        logger.error(f"音声処理エラー: {e}")
        return False
    except DatabaseError as e:
        logger.error(f"データベースエラー: {e}")
        return False
    except Exception as e:
        logger.error(f"予期しないエラー: {e}")
        return False
```

## パフォーマンス考慮事項

### メモリ管理
- **音声ファイル読み込み**: `librosa.load()`により音声ファイル全体をメモリに読み込み
- **スペクトログラム処理**: 大容量ファイルでは段階的な処理を実装
- **指紋キャッシュ**: 頻繁にアクセスされる指紋のメモリキャッシュ

### 処理最適化
- **Numba JIT最適化**: 数値計算集約的な関数で利用可能
- **ベクトル化**: NumPy配列操作による高速化
- **並列処理**: バッチ処理での複数ファイル同時処理

### データベース最適化
- **インデックス戦略**: 指紋検索用の最適化されたインデックス
- **接続プール**: データベース接続の効率的な管理
- **クエリ最適化**: データベース固有の最適化技術

## 拡張性

### 新しいデータベースバックエンドの追加
```python
class RedisBackend(DatabaseBackend):
    """Redis用の新しいバックエンド実装例"""
    
    def __init__(self, host, port, db):
        import redis
        self.client = redis.Redis(host=host, port=port, db=db)
    
    def connect(self):
        return self.client.ping()
    
    def create_tables(self):
        # Redisではテーブル作成は不要
        pass
    
    def insert_song(self, song_name, **metadata):
        song_id = self.client.incr('song_counter')
        song_key = f'song:{song_id}'
        self.client.hset(song_key, mapping={
            'name': song_name,
            **metadata
        })
        return song_id
    
    def insert_fingerprints(self, song_id, fingerprints):
        for fp in fingerprints:
            fp_key = f'fp:{fp["hash"]}'
            self.client.sadd(fp_key, f'{song_id}:{fp["time_offset"]}')
    
    def search_fingerprints(self, fingerprints):
        matches = {}
        for fp in fingerprints:
            fp_key = f'fp:{fp["hash"]}'
            results = self.client.smembers(fp_key)
            for result in results:
                song_id, time_offset = result.decode().split(':')
                song_id = int(song_id)
                time_offset = float(time_offset)
                
                if song_id not in matches:
                    matches[song_id] = []
                matches[song_id].append({
                    'time_offset': time_offset,
                    'query_time': fp['time_offset']
                })
        
        return matches

### 拡張可能なアーキテクチャ

mimizamのアーキテクチャは、新しいデータベースバックエンドやアルゴリズムの追加を容易にする設計となっています。

#### カスタムバックエンドの統合
新しいデータベースシステム（Redis、MongoDB等）は、統一されたインターフェースを通じて簡単に統合できます。各バックエンドは独自の最適化戦略を実装しながら、アプリケーション層には一貫したAPIを提供します。

#### アルゴリズムの拡張性
音声指紋生成アルゴリズムは、MFCC特徴量ベースの手法や機械学習アプローチなど、様々な技術的アプローチに対応できる柔軟な設計となっています。

## セキュリティとプライバシー

### データ保護戦略
- **指紋の匿名化**: 元の音声ファイルを復元できないよう設計された一方向変換
- **メタデータの暗号化**: 機密性の高い楽曲情報の保護機能
- **アクセス制御**: データベースレベルでの細かな権限管理

### プライバシー保護機能
システムは、指紋データの追加ハッシュ化により、プライバシー保護を強化します。この機能により、元の音声データへの逆算を防ぎながら、識別精度を維持します。

## まとめ

mimizamのコアアーキテクチャは、以下の主要な特徴を持つ包括的な音声指紋システムです：

### 主要な強み
1. **モジュラー設計**: 各コンポーネントが独立して動作し、拡張が容易
2. **マルチバックエンド対応**: SQLite、MySQL、PostgreSQL、Elasticsearchをサポート
3. **適応的処理**: 音声特性に基づく自動パラメータ調整
4. **高性能**: Numba JIT最適化と並列処理による高速化
5. **堅牢性**: 包括的なエラーハンドリングと例外処理

### 技術的優位性
- **Shazam互換アルゴリズム**: 実証済みの音声指紋技術
- **スケーラブル設計**: 大規模データベースに対応
- **リアルタイム処理**: ストリーミング音声の即座識別
- **拡張可能**: カスタムアルゴリズムとバックエンドの追加が容易

### 将来の発展方向
- 機械学習アルゴリズムの統合
- クラウドネイティブアーキテクチャへの移行
- 分散処理システムの実装
- 音声以外のメディア対応

このアーキテクチャにより、mimizamは研究用途から商用システムまで、幅広い要求に対応できる柔軟で高性能な音声指紋システムを提供します。

### システム統合と展開

mimizamのアーキテクチャは、様々な展開シナリオに対応できる柔軟性を提供します：

#### 展開オプション
- **開発環境**: SQLiteバックエンドによる軽量な開発とテスト
- **本番環境**: MySQL/PostgreSQLによる高性能なデータ処理
- **分散環境**: Elasticsearchによるスケーラブルな検索機能
- **クラウド環境**: マネージドデータベースサービスとの統合

#### パフォーマンス最適化
システムは、適応的パラメータ調整とNumba JIT最適化により、様々な音声特性と処理要件に対して最適なパフォーマンスを提供します。

このアーキテクチャにより、mimizamは研究用途から商用システムまで、幅広い要求に対応できる柔軟で高性能な音声指紋システムを提供します。
