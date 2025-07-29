# システムアーキテクチャ

mimizamは、音声指紋生成と識別のためのシンプルで効率的なシステムです。本ドキュメントでは、システム全体の構成と各コンポーネントの役割について説明します。

## 🏗️ 全体アーキテクチャ

mimizamは4つの主要レイヤーで構成されています：

```
┌─────────────────────────────────────────────────────────────┐
│                    アプリケーション層                        │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │   CLI ツール    │  │  デモアプリ     │  │  カスタムアプリ │ │
│  │ video_search.py │  │ mimizam_demo.py │  │   (ユーザー)    │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                                │
┌─────────────────────────────────────────────────────────────┐
│                    統合API層                                │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │                 Mimizam クラス                          │ │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐      │ │
│  │  │  add_song   │  │ search_song │  │ identify_audio  │  │ │
│  │  └─────────────┘  └─────────────┘  └─────────────┘      │ │
│  └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                                │
┌─────────────────────────────────────────────────────────────┐
│                   コア処理層                                │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │AudioFingerprinter│  │FingerprintDatabase│ │FingerprintMatcher│ │
│  │                 │  │                 │  │                 │ │
│  │SpectrogramAnalyzer│ │                 │  │                 │ │
│  │HashGenerator    │  │                 │  │                 │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                                │
┌─────────────────────────────────────────────────────────────┐
│                  データベース層                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────┐ │
│  │SQLiteBackend│  │MySQLBackend │  │PostgreSQLBE │  │ElasticBE│ │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────┘ │
└─────────────────────────────────────────────────────────────┘
```

## 🎯 レイヤー別詳細

### 1. アプリケーション層

ユーザーが直接操作するインターフェースです：

- **CLI ツール**: コマンドラインから音声検索を実行
- **デモアプリ**: 基本機能を試すためのサンプルアプリケーション
- **カスタムアプリ**: ユーザーが作成する独自のアプリケーション

### 2. 統合API層

**Mimizam クラス**が中核となり、全てのデータベースバックエンドに対して一貫したインターフェースを提供します。

主要メソッド：
- `add_song()`: 楽曲をデータベースに追加
- `search_song()`: 音声検索を実行
- `identify_audio()`: 音声を識別
- `get_song()`: 楽曲情報を取得
- `delete_song()`: 楽曲を削除

**ファクトリ関数**により、データベースの種類に応じたインスタンスを簡単に作成できます：
- `create_mimizam_sqlite()`: SQLite用
- `create_mimizam_mysql()`: MySQL用
- `create_mimizam_postgresql()`: PostgreSQL用

### 3. コア処理層

音声処理の核となる3つのコンポーネント：

#### AudioFingerprinter
- 音声ファイルの読み込み
- スペクトログラム解析
- 音声指紋の生成
- 可視化機能

#### FingerprintDatabase
- データベース操作の統合管理
- 楽曲と指紋の保存・検索
- バックエンド間の差異を吸収

#### FingerprintMatcher
- 指紋マッチングの実行
- スコアリングアルゴリズム
- 結果の信頼度計算

### 4. データベース層

各データベースシステムに特化した実装：

- **SQLiteBackend**: ファイルベース、軽量（開発・小規模用途）
- **MySQLBackend**: 高性能、スケーラブル（本番環境）
- **PostgreSQLBackend**: 堅牢、機能豊富（複雑なクエリ）
- **ElasticsearchBackend**: 全文検索、分散処理（大規模検索）
    config = create_sqlite_config(db_path)
    database = FingerprintDatabase(config)
    fingerprinter = AudioFingerprinter(**kwargs)
    return Mimizam(database, fingerprinter)
```

### 3. コア処理層

#### AudioFingerprinter
音声指紋生成の中核コンポーネント：

```python
class AudioFingerprinter:
    """音声指紋生成器"""
    
    def __init__(self, n_fft=2048, hop_length=512, **kwargs):
        self.spectrogram_analyzer = SpectrogramAnalyzer(n_fft, hop_length)
        self.hash_generator = HashGenerator(**kwargs)
    
    def fingerprint_audio(self, audio: np.ndarray) -> List[Fingerprint]:
        """音声から指紋を生成"""
        # 1. スペクトログラム生成
        spectrogram = self.spectrogram_analyzer.compute_spectrogram(audio)
        
        # 2. ピーク検出
        peaks = self.spectrogram_analyzer.detect_peaks(spectrogram)
        
        # 3. ハッシュ生成
        fingerprints = self.hash_generator.generate_fingerprints(peaks)
        
        return fingerprints
```

#### FingerprintDatabase
データベース操作の統合インターフェース：

```python
class FingerprintDatabase:
    """指紋データベース統合インターフェース"""
    
    def __init__(self, config: DatabaseConfig):
        self.backend = self._create_backend(config)
        self.matcher = FingerprintMatcher()
    
    def add_song(self, title: str, artist: str, file_path: str) -> int:
        """楽曲をデータベースに追加"""
        return self.backend.add_song(title, artist, file_path)
    
    def search_fingerprints(self, query_fingerprints: List[Fingerprint]) -> List[Dict]:
        """指紋検索とマッチング"""
        # 1. データベース検索
        raw_matches = self.backend.find_matches(query_fingerprints)
        
        # 2. スコアリング
        scored_results = self.matcher.score_matches(raw_matches)
        
        return scored_results
```

#### FingerprintMatcher
指紋マッチングとスコアリング：

```python
class FingerprintMatcher:
    """指紋マッチングエンジン"""
    
    def score_matches(self, raw_matches: Dict, scoring_method: str = 'hybrid') -> List[Dict]:
        """マッチ結果のスコアリング"""
        if scoring_method == 'histogram':
            return self._histogram_scoring(raw_matches)
        elif scoring_method == 'detailed':
            return self._detailed_scoring(raw_matches)
        else:  # hybrid
            return self._hybrid_scoring(raw_matches)
```

### 4. データベース層

#### バックエンド実装
各データベースシステムに特化した実装：

```python
class SQLiteBackend(DatabaseBackend):
    """SQLite バックエンド実装"""
    
    def create_tables(self):
        """テーブル作成"""
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS songs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                artist TEXT NOT NULL,
                file_path TEXT NOT NULL,
                album TEXT,
                meta TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS fingerprints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                song_id INTEGER NOT NULL,
                hash_value TEXT NOT NULL,
                time_offset REAL NOT NULL,
                FOREIGN KEY (song_id) REFERENCES songs (id)
            )
        """)
```

## 🔄 データフロー

### 楽曲追加フロー

```
音声ファイル
    │
    ▼
┌─────────────────┐
│ 音声読み込み     │ ← librosa
│ (load_audio)    │
└─────────────────┘
    │
    ▼
┌─────────────────┐
│スペクトログラム  │ ← STFT
│生成             │
└─────────────────┘
    │
    ▼
┌─────────────────┐
│ピーク検出       │ ← 局所最大値検出
│                │
└─────────────────┘
    │
    ▼
┌─────────────────┐
│ハッシュ生成     │ ← アンカー・ターゲット方式
│                │
└─────────────────┘
    │
    ▼
┌─────────────────┐
│データベース保存  │ ← SQLite/MySQL/PostgreSQL/Elasticsearch
│                │
└─────────────────┘
```

### 音声検索フロー

```
クエリ音声
    │
    ▼
┌─────────────────┐
│指紋生成         │ ← 楽曲追加と同じプロセス
│                │
└─────────────────┘
    │
    ▼
┌─────────────────┐
│データベース検索  │ ← ハッシュマッチング
│                │
└─────────────────┘
    │
    ▼
┌─────────────────┐
│マッチングと     │ ← 時間アライメント
│スコアリング     │   信頼度計算
└─────────────────┘
    │
    ▼
┌─────────────────┐
│結果ランキング   │ ← 信頼度順ソート
│                │
└─────────────────┘
    │
    ▼
検索結果
```

## 🧩 コンポーネント間の相互作用

### SpectrogramAnalyzer と HashGenerator

```python
class SpectrogramAnalyzer:
    """スペクトログラム解析"""
    
    def compute_spectrogram(self, audio: np.ndarray) -> np.ndarray:
        """STFT によるスペクトログラム生成"""
        return librosa.stft(audio, n_fft=self.n_fft, hop_length=self.hop_length)
    
    def detect_peaks(self, spectrogram: np.ndarray) -> List[Peak]:
        """局所最大値検出"""
        # 近傍での最大値検出
        # 閾値フィルタリング
        # Peak オブジェクト生成
        pass

class HashGenerator:
    """ハッシュ生成器"""
    
    def generate_fingerprints(self, peaks: List[Peak]) -> List[Fingerprint]:
        """アンカー・ターゲット方式でハッシュ生成"""
        fingerprints = []
        for anchor in peaks:
            targets = self._find_targets(anchor, peaks)
            for target in targets:
                hash_value = self._compute_hash(anchor, target)
                fingerprint = Fingerprint(hash_value, anchor.time)
                fingerprints.append(fingerprint)
        return fingerprints
```

### AdaptiveParameterTuner との連携

```python
class AdaptiveParameterTuner:
    """適応パラメータ調整"""
    
    def optimize_for_audio(self, audio: np.ndarray) -> dict:
        """音声特性に応じたパラメータ最適化"""
        # 音声特性分析
        characteristics = self._analyze_audio(audio)
        
        # パラメータ調整
        if characteristics['complexity'] > 0.8:
            return {'min_amplitude': -70, 'peak_neighborhood_size': 30}
        elif characteristics['noise_level'] > 0.5:
            return {'min_amplitude': -40, 'peak_neighborhood_size': 15}
        else:
            return {}  # デフォルト設定
```

## 🔧 設定管理アーキテクチャ

### 階層的設定システム

```python
# 1. デフォルト設定
DEFAULT_CONFIG = {
    'fingerprinter': {
        'n_fft': 2048,
        'hop_length': 512,
        'min_amplitude': -60
    },
    'matcher': {
        'time_tolerance': 0.1,
        'freq_tolerance': 50
    }
}

# 2. プロファイル設定
PROFILE_CONFIGS = {
    'high_precision': {
        'fingerprinter': {'n_fft': 4096, 'min_amplitude': -70},
        'matcher': {'time_tolerance': 0.05}
    },
    'high_speed': {
        'fingerprinter': {'n_fft': 1024, 'min_amplitude': -40},
        'matcher': {'time_tolerance': 0.2}
    }
}

# 3. ユーザー設定
USER_CONFIG = {
    'fingerprinter': {'debug': True},
    'matcher': {'scoring_method': 'hybrid'}
}

# 4. 設定マージ
final_config = merge_configs(DEFAULT_CONFIG, PROFILE_CONFIGS['balanced'], USER_CONFIG)
```

## 📊 パフォーマンス最適化

mimizamは音声指紋生成とマッチング処理において、以下の実装された最適化機能を提供します：

### Numba JIT最適化

ピーク検出処理の高速化：

```python
from mimizam import AudioFingerprinter

# Numba JIT最適化を有効化
fingerprinter = AudioFingerprinter(enable_numba_optimization=True)

# 初回実行時に自動的にJITコンパイルが実行される
fingerprints = fingerprinter.fingerprint_file("audio.wav")
```

**技術詳細:**
- `_numba_optimized_peak_detection`関数でスペクトログラムピーク検出を高速化
- 初期化時にダミーデータで事前コンパイルを実行し、実行時遅延を回避
- `@njit(cache=True)`によるキャッシュ機能でコンパイル結果を再利用

### 適応的パラメータ調整

音声特性に基づく動的パラメータ最適化：

```python
from mimizam import AudioFingerprinter

# 適応的パラメータ調整を有効化
fingerprinter = AudioFingerprinter(enable_adaptive_params=True)

# 音声特性を自動分析してパラメータを最適化
fingerprints = fingerprinter.fingerprint_file("audio.wav", debug=True)
```

**最適化項目:**
- 静寂比率に基づく振幅閾値調整
- スペクトルエントロピーによる複雑度対応
- テンポ検出による時間パラメータ調整
- 音声継続時間による処理パラメータ最適化

### パフォーマンス監視

処理時間とリソース使用量の監視：

```python
from mimizam import AudioFingerprinter

fingerprinter = AudioFingerprinter(enable_adaptive_params=True)

# パフォーマンス監視が自動的に有効化される
fingerprints = fingerprinter.fingerprint_file("audio.wav")

# パフォーマンス統計を取得
if fingerprinter.performance_monitor:
    summary = fingerprinter.performance_monitor.get_performance_summary()
    print(summary)
```

### データベース最適化

SQLiteバックエンドでの最適化設定：

- **WALモード**: 読み取り時のブロック回避
- **メモリマップ**: 256MBメモリマップによる高速アクセス
- **キャッシュ設定**: 64MBキャッシュサイズ
- **バッチクエリ**: IN句を使用した効率的な検索
- **複合インデックス**: ハッシュ値、楽曲ID、時間オフセットの複合インデックス

```python
from mimizam import create_mimizam_sqlite

# 最適化設定は自動的に適用される
mimizam = create_mimizam_sqlite("optimized.db")
```


## 🔗 拡張性

### 新しいデータベースバックエンドの追加

mimizamは新しいデータベースバックエンドの追加をサポートしています。以下はRedisバックエンドを追加する例です：

```python
from mimizam.database_base import DatabaseBackend, DatabaseConfig
import redis
import json
from typing import List, Dict, Any

class RedisBackend(DatabaseBackend):
    """Redis バックエンド実装"""
    
    def __init__(self, config: DatabaseConfig):
        super().__init__(config)
        self.redis_client = redis.Redis(
            host=config.host,
            port=config.port or 6379,
            db=config.database or 0,
            password=config.password
        )
        self.song_counter_key = "mimizam:song_counter"
        self.songs_key = "mimizam:songs"
        self.fingerprints_key = "mimizam:fingerprints"
    
    def create_tables(self):
        """Redis用の初期化（テーブル作成は不要）"""
        # Redisでは明示的なテーブル作成は不要
        # カウンターを初期化
        if not self.redis_client.exists(self.song_counter_key):
            self.redis_client.set(self.song_counter_key, 0)
    
    def add_song(self, title: str, artist: str, file_path: str, 
                 album: str = None, meta: str = None) -> int:
        """楽曲をRedisに追加"""
        song_id = self.redis_client.incr(self.song_counter_key)
        
        song_data = {
            'id': song_id,
            'title': title,
            'artist': artist,
            'file_path': file_path,
            'album': album,
            'meta': meta
        }
        
        # ハッシュとして保存
        self.redis_client.hset(
            f"{self.songs_key}:{song_id}",
            mapping={k: json.dumps(v) for k, v in song_data.items()}
        )
        
        return song_id
    
    def add_fingerprints(self, song_id: int, fingerprints: List[Any]):
        """指紋をRedisに追加"""
        for fp in fingerprints:
            # ハッシュ値をキーとして使用
            hash_key = f"{self.fingerprints_key}:{fp.hash_value}"
            
            # 同じハッシュ値の指紋をリストとして保存
            fingerprint_data = {
                'song_id': song_id,
                'time_offset': fp.time_offset
            }
            
            self.redis_client.lpush(hash_key, json.dumps(fingerprint_data))
    
    def find_matches(self, query_fingerprints: List[Any]) -> Dict[int, List[Dict]]:
        """指紋マッチングを実行"""
        matches = {}
        
        for fp in query_fingerprints:
            hash_key = f"{self.fingerprints_key}:{fp.hash_value}"
            
            # マッチする指紋を取得
            stored_fps = self.redis_client.lrange(hash_key, 0, -1)
            
            for stored_fp_json in stored_fps:
                stored_fp = json.loads(stored_fp_json)
                song_id = stored_fp['song_id']
                
                if song_id not in matches:
                    matches[song_id] = []
                
                matches[song_id].append({
                    'query_time': fp.time_offset,
                    'stored_time': stored_fp['time_offset'],
                    'hash_value': fp.hash_value
                })
        
        return matches
    
    def get_song(self, song_id: int) -> Dict[str, Any]:
        """楽曲情報を取得"""
        song_data = self.redis_client.hgetall(f"{self.songs_key}:{song_id}")
        
        if not song_data:
            return None
        
        # JSON文字列をデコード
        return {k.decode(): json.loads(v.decode()) 
                for k, v in song_data.items()}
    
    def close(self):
        """接続を閉じる"""
        self.redis_client.close()

# Redis設定の作成
def create_redis_config(host: str = 'localhost', port: int = 6379, 
                       database: int = 0, password: str = None) -> DatabaseConfig:
    """Redis用の設定を作成"""
    return DatabaseConfig(
        backend='redis',
        host=host,
        port=port,
        database=database,
        password=password
    )

# 使用例
def create_mimizam_redis(host: str = 'localhost', port: int = 6379,
                        database: int = 0, password: str = None):
    """Redis版Mimizamインスタンスを作成"""
    from mimizam import AudioFingerprinter, FingerprintDatabase
    
    config = create_redis_config(host, port, database, password)
    redis_backend = RedisBackend(config)
    
    database = FingerprintDatabase(redis_backend)
    fingerprinter = AudioFingerprinter()
    
    from mimizam import Mimizam
    return Mimizam(database, fingerprinter)
```

## 🔗 関連ドキュメント

- [データベース設定](./05_database_setup.md) - データベース層の詳細
- [基本的な使用例](./06_basic_examples.md) - 実践的なサンプルコード
- [FAQ](./07_faq.md) - よくある質問とトラブルシューティング

## 💡 設計原則

### 1. 関心の分離
- 各レイヤーは明確な責任を持つ
- コンポーネント間の依存関係を最小化
- インターフェースを通じた疎結合

### 2. 拡張性
- プラグインアーキテクチャによる機能拡張
- 設定システムによるカスタマイズ
- 新しいバックエンドの容易な追加

### 3. 性能
- Numba JIT最適化によるピーク検出高速化
- 適応的パラメータ調整による音声特性対応
- パフォーマンス監視による処理時間追跡
- データベース最適化による高速検索

### 4. 保守性
- 明確なコード構造
- 包括的なテストスイート
- 詳細なドキュメント
