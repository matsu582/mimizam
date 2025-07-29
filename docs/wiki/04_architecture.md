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
│  │  │create_sqlite│  │create_mysql │  │create_postgresql│  │ │
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

## 📊 パフォーマンス考慮事項

### メモリ管理

```python
from mimizam import AudioFingerprinter
import librosa
import numpy as np

def process_large_audio_file(file_path: str, chunk_duration: int = 30):
    """大きな音声ファイルをチャンク単位で処理"""
    
    fingerprinter = AudioFingerprinter()
    
    # 音声ファイルの情報を取得
    duration = librosa.get_duration(filename=file_path)
    sr = 22050
    
    all_fingerprints = []
    
    # チャンク単位で処理
    for start_time in range(0, int(duration), chunk_duration):
        end_time = min(start_time + chunk_duration, duration)
        
        # チャンクを読み込み
        audio_chunk, _ = librosa.load(
            file_path, 
            sr=sr, 
            offset=start_time, 
            duration=chunk_duration
        )
        
        # フィンガープリント生成
        chunk_fingerprints = fingerprinter.fingerprint_audio(audio_chunk)
        
        # 時間オフセットを調整
        for fp in chunk_fingerprints:
            fp.time_offset += start_time
        
        all_fingerprints.extend(chunk_fingerprints)
        
        print(f"処理完了: {start_time}-{end_time}秒 ({len(chunk_fingerprints)}個のフィンガープリント)")
    
    return all_fingerprints
```

### バッチ処理

複数ファイルの効率的な処理：

```python
from mimizam import create_mimizam_sqlite
import os

def process_multiple_files(file_paths: list):
    """複数ファイルのバッチ処理"""
    
    mimizam = create_mimizam_sqlite("batch_processing.db")
    results = []
    
    for file_path in file_paths:
        try:
            # ファイル名から基本情報を推測
            filename = os.path.splitext(os.path.basename(file_path))[0]
            song_id = mimizam.add_song(file_path, filename, "Unknown")
            results.append({'success': True, 'song_id': song_id, 'file_path': file_path})
        except Exception as e:
            results.append({'success': False, 'error': str(e), 'file_path': file_path})
    
    mimizam.close()
    return results
```

## 🔒 セキュリティアーキテクチャ

### データ保護

```python
def create_secure_database_config(config_dict: dict) -> dict:
    """セキュアなデータベース設定を作成"""
    from mimizam import DatabaseConfig
    
    # セキュリティ設定を追加
    secure_config = config_dict.copy()
    secure_config.update({
        'use_ssl': True,
        'ssl_verify': True,
        'connection_timeout': 30
    })
    
    return secure_config
    
    def sanitize_input(self, user_input: str) -> str:
        """入力サニタイゼーション"""
        # SQLインジェクション対策
        return user_input.replace("'", "''").replace(";", "")
```

## 🔗 拡張性

### 拡張性

mimizamは複数のデータベースバックエンドをサポートし、新しいバックエンドの追加も可能です：

```python
from mimizam.database_base import DatabaseBackend, DatabaseConfig

# カスタムバックエンドの実装例（概念的）
def create_custom_backend_config(backend_type: str) -> dict:
    """カスタムバックエンド設定を作成"""
    
    # 実際のmimizamバックエンドを使用
    if backend_type == 'sqlite':
        from mimizam import create_sqlite_config
        return create_sqlite_config('custom.db')
    elif backend_type == 'mysql':
        from mimizam import create_mysql_config
        return create_mysql_config(
            host='localhost',
            database='custom_db',
            username='user',
            password='password'
        )
    else:
        # デフォルトはSQLite
        from mimizam import create_sqlite_config
        return create_sqlite_config('default.db')

# 使用例
def setup_custom_backend(backend_type: str):
    """カスタムバックエンドのセットアップ"""
    config = create_custom_backend_config(backend_type)
    
    from mimizam import Mimizam
    mimizam = Mimizam(config)
    
    return mimizam
        return True
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
- 適応的パラメータ調整
- メモリ効率的な処理
- Numba JIT最適化

### 4. 保守性
- 明確なコード構造
- 包括的なテストスイート
- 詳細なドキュメント
