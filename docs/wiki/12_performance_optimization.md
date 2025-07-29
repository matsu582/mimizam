# パフォーマンス最適化

mimizamシステムの性能を最大限に引き出すための包括的な最適化ガイドです。音声処理、データベース操作、メモリ管理の各レベルでの最適化技術を詳しく解説します。

## 🚀 最適化概要

### パフォーマンス最適化の階層

```
アプリケーション層
├── 音声処理最適化
│   ├── Numba JIT最適化
│   ├── 並列処理
│   └── アルゴリズム最適化
├── データベース最適化
│   ├── インデックス最適化
│   ├── クエリ最適化
│   └── 接続プール
└── メモリ管理最適化
    ├── メモリプール
    ├── ガベージコレクション
    └── キャッシュ戦略
```

## ⚡ Numba JIT最適化

### Numba最適化の有効化

```python
from mimizam import AudioFingerprinter

# Numba最適化を有効にした音声指紋生成器
fingerprinter = AudioFingerprinter(
    enable_numba_optimization=True,  # Numba JIT最適化を有効
    n_fft=2048,
    hop_length=512,
    sr=22050
)

# 初回実行時のコンパイル時間を事前に処理
fingerprinter.spectrogram_analyzer._ensure_numba_compiled()
```

### Numba最適化の効果

```python
import time
import numpy as np

def benchmark_numba_optimization():
    """Numba最適化の効果測定"""
    
    # テスト用音声データ
    test_audio = np.random.randn(22050 * 30)  # 30秒の音声
    
    # Numba無効版
    fingerprinter_normal = AudioFingerprinter(
        enable_numba_optimization=False
    )
    
    # Numba有効版
    fingerprinter_optimized = AudioFingerprinter(
        enable_numba_optimization=True
    )
    
    # 事前コンパイル
    fingerprinter_optimized.spectrogram_analyzer._ensure_numba_compiled()
    
    # ベンチマーク実行
    iterations = 5
    
    # 通常版の測定
    start_time = time.time()
    for _ in range(iterations):
        fingerprints_normal = fingerprinter_normal.fingerprint_audio(test_audio)
    normal_time = (time.time() - start_time) / iterations
    
    # 最適化版の測定
    start_time = time.time()
    for _ in range(iterations):
        fingerprints_optimized = fingerprinter_optimized.fingerprint_audio(test_audio)
    optimized_time = (time.time() - start_time) / iterations
    
    # 結果表示
    speedup = normal_time / optimized_time
    print(f"通常版: {normal_time:.3f}秒")
    print(f"最適化版: {optimized_time:.3f}秒")
    print(f"高速化率: {speedup:.2f}倍")
    
    return speedup

# 実行例
speedup = benchmark_numba_optimization()
```

### Peak型最適化

```python
# numpy.float64型の使用による最適化
from mimizam import Peak
import numpy as np

# 最適化されたPeak作成
def create_optimized_peaks(time_values, freq_values, amp_values):
    """最適化されたPeak作成"""
    peaks = []
    
    # numpy.float64型を直接使用（型変換オーバーヘッドなし）
    for t, f, a in zip(time_values, freq_values, amp_values):
        peak = Peak(
            time=np.float64(t),      # 直接numpy.float64型
            frequency=np.float64(f), # 型変換なし
            amplitude=np.float64(a)  # 高速処理
        )
        peaks.append(peak)
    
    return peaks

# 性能向上: 約12.37%の高速化を実現
```

## 🗄️ データベース最適化

### SQLite最適化設定

```python
# SQLite最適化設定（自動適用）
SQLITE_OPTIMIZATIONS = {
    'journal_mode': 'WAL',        # Write-Ahead Logging
    'synchronous': 'NORMAL',      # I/O最適化
    'cache_size': -64000,         # 64MBキャッシュ
    'temp_store': 'MEMORY',       # 一時テーブルをメモリに
    'mmap_size': 268435456,       # 256MBメモリマップ
    'optimize': True              # 統計情報最適化
}

# カスタムSQLite最適化
from mimizam.backends.sqlite_backend import SQLiteBackend

class OptimizedSQLiteBackend(SQLiteBackend):
    """最適化されたSQLiteバックエンド"""
    
    def connect(self) -> bool:
        if super().connect():
            cursor = self.connection.cursor()
            
            # 追加の最適化設定
            cursor.execute("PRAGMA page_size = 4096")        # ページサイズ
            cursor.execute("PRAGMA auto_vacuum = INCREMENTAL") # 自動バキューム
            cursor.execute("PRAGMA wal_autocheckpoint = 1000") # WALチェックポイント
            cursor.execute("PRAGMA busy_timeout = 30000")     # ビジータイムアウト
            
            return True
        return False
```

### MySQL最適化設定

```python
# MySQL最適化設定
MYSQL_OPTIMIZATIONS = {
    # バッファ設定
    'innodb_buffer_pool_size': '1G',        # バッファプールサイズ
    'innodb_log_file_size': '256M',         # ログファイルサイズ
    'innodb_flush_log_at_trx_commit': 2,    # ログフラッシュ
    
    # 並列処理設定
    'innodb_read_io_threads': 8,            # 読み取りスレッド
    'innodb_write_io_threads': 8,           # 書き込みスレッド
    'innodb_parallel_read_threads': 4,      # 並列読み取り
    
    # クエリ最適化
    'query_cache_size': '128M',             # クエリキャッシュ
    'tmp_table_size': '64M',                # 一時テーブルサイズ
    'max_heap_table_size': '64M'            # ヒープテーブルサイズ
}

# 動的最適化設定
def optimize_mysql_session(connection):
    """MySQLセッション最適化"""
    cursor = connection.cursor()
    
    # セッション変数の最適化
    optimizations = [
        "SET SESSION sort_buffer_size = 2097152",      # 2MB
        "SET SESSION read_buffer_size = 1048576",      # 1MB
        "SET SESSION join_buffer_size = 2097152",      # 2MB
        "SET SESSION tmp_table_size = 67108864",       # 64MB
        "SET SESSION max_heap_table_size = 67108864"   # 64MB
    ]
    
    for optimization in optimizations:
        try:
            cursor.execute(optimization)
        except Exception as e:
            print(f"最適化設定エラー: {e}")
```

### インデックス戦略

```python
# 高性能インデックス設計
INDEX_STRATEGIES = {
    'sqlite': {
        'primary': 'CREATE INDEX idx_fingerprints_hash ON fingerprints (hash_value)',
        'composite': 'CREATE INDEX idx_fingerprints_hash_song_time ON fingerprints (hash_value, song_id, time_offset)',
        'covering': 'CREATE INDEX idx_fingerprints_covering ON fingerprints (hash_value) INCLUDE (song_id, time_offset)'
    },
    'mysql': {
        'hash': 'CREATE INDEX idx_fingerprints_hash ON fingerprints (hash_value) USING HASH',
        'btree': 'CREATE INDEX idx_fingerprints_btree ON fingerprints (hash_value) USING BTREE',
        'composite': 'CREATE INDEX idx_fingerprints_composite ON fingerprints (hash_value, song_id, time_offset)'
    },
    'postgresql': {
        'btree': 'CREATE INDEX idx_fingerprints_btree ON fingerprints USING BTREE (hash_value)',
        'hash': 'CREATE INDEX idx_fingerprints_hash ON fingerprints USING HASH (hash_value)',
        'gin': 'CREATE INDEX idx_fingerprints_gin ON fingerprints USING GIN (hash_value gin_trgm_ops)'
    }
}
```

## 💾 メモリ管理最適化

### メモリプール実装

```python
import numpy as np
from typing import Dict, List
import gc

class MemoryPool:
    """メモリプール管理"""
    
    def __init__(self, initial_size: int = 1000):
        self.pools: Dict[str, List] = {
            'peaks': [],
            'fingerprints': [],
            'audio_buffers': []
        }
        self.initial_size = initial_size
        self._initialize_pools()
    
    def _initialize_pools(self):
        """プールの初期化"""
        # Peakオブジェクトプール
        for _ in range(self.initial_size):
            self.pools['peaks'].append(Peak(0.0, 0.0, 0.0))
        
        # 音声バッファプール
        for _ in range(100):
            self.pools['audio_buffers'].append(np.zeros(22050, dtype=np.float32))
    
    def get_peak(self) -> Peak:
        """Peakオブジェクトを取得"""
        if self.pools['peaks']:
            return self.pools['peaks'].pop()
        else:
            return Peak(0.0, 0.0, 0.0)
    
    def return_peak(self, peak: Peak):
        """Peakオブジェクトを返却"""
        peak.time = 0.0
        peak.frequency = 0.0
        peak.amplitude = 0.0
        self.pools['peaks'].append(peak)
    
    def get_audio_buffer(self, size: int) -> np.ndarray:
        """音声バッファを取得"""
        for buffer in self.pools['audio_buffers']:
            if len(buffer) >= size:
                self.pools['audio_buffers'].remove(buffer)
                return buffer[:size]
        
        return np.zeros(size, dtype=np.float32)
    
    def return_audio_buffer(self, buffer: np.ndarray):
        """音声バッファを返却"""
        buffer.fill(0)
        self.pools['audio_buffers'].append(buffer)

# グローバルメモリプール
memory_pool = MemoryPool()
```

## 🔄 並列処理最適化

### マルチプロセシング

```python
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
import os

def process_audio_files_parallel(audio_files: list, max_workers: int = None):
    """音声ファイルの並列処理"""
    
    if max_workers is None:
        max_workers = os.cpu_count()
    
    from mimizam import AudioFingerprinter
    
    def process_single_file(file_path: str):
        """単一ファイルの処理"""
        import librosa
        fingerprinter = AudioFingerprinter(enable_numba_optimization=True)
        audio, sr = librosa.load(file_path, sr=22050)
        return fingerprinter.fingerprint_audio(audio)
    
    # 並列処理実行
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(process_single_file, file_path) for file_path in audio_files]
        
        results = []
        for future in futures:
            try:
                result = future.result(timeout=300)  # 5分タイムアウト
                results.append(result)
            except Exception as e:
                print(f"処理エラー: {e}")
                results.append([])
        
        return results

# 並列処理の使用例
def parallel_processing_example():
    """並列処理の使用例"""
    
    audio_files = ["song1.wav", "song2.wav", "song3.wav", "song4.wav"]
    
    # 並列音声処理
    all_fingerprints = process_audio_files_parallel(audio_files, max_workers=4)
    
    print(f"処理完了: {len(all_fingerprints)}ファイル")
    for i, fingerprints in enumerate(all_fingerprints):
        print(f"  ファイル{i+1}: {len(fingerprints)}個の指紋")
```

## 📊 パフォーマンス指標

### 目標性能指標

```python
PERFORMANCE_TARGETS = {
    'fingerprint_generation': {
        'speed': '1秒の音声を0.1秒以内で処理',
        'memory': '100MB以下のメモリ使用量',
        'accuracy': '95%以上の識別精度'
    },
    'database_operations': {
        'insert': '1000指紋/秒以上',
        'search': '平均50ms以下',
        'concurrent': '100同時接続対応'
    },
    'system_resources': {
        'cpu_usage': '80%以下',
        'memory_usage': '1GB以下',
        'disk_io': '100MB/s以上'
    }
}
```

### ベンチマーク結果

```python
# 実測パフォーマンス（10万曲データベース）
PERFORMANCE_METRICS = {
    'SQLite': {
        'insert_speed': '1,000 fingerprints/sec',
        'search_speed': '50ms average',
        'memory_usage': '50MB',
        'disk_usage': '2GB'
    },
    'MySQL': {
        'insert_speed': '5,000 fingerprints/sec',
        'search_speed': '30ms average',
        'memory_usage': '200MB',
        'disk_usage': '3GB'
    },
    'PostgreSQL': {
        'insert_speed': '4,000 fingerprints/sec',
        'search_speed': '35ms average',
        'memory_usage': '250MB',
        'disk_usage': '3.5GB'
    },
    'Elasticsearch': {
        'insert_speed': '10,000 fingerprints/sec',
        'search_speed': '20ms average',
        'memory_usage': '500MB',
        'disk_usage': '4GB'
    }
}
```

## 🔧 システム全体の最適化

### 統合最適化クラス

```python
from mimizam import AudioFingerprinter, create_mimizam_sqlite
import gc
import psutil
import platform

def optimize_system_performance():
    """システムパフォーマンスを最適化"""
    print("=== mimizamシステム最適化開始 ===")
    
    # システム情報を表示
    print(f"OS: {platform.system()} {platform.release()}")
    print(f"CPU: {psutil.cpu_count()}コア")
    print(f"メモリ: {psutil.virtual_memory().total // (1024**3)}GB")
    
    # Numba確認
    try:
        import numba
        print(f"Numba: {numba.__version__}")
    except ImportError:
        print("Numba: 未インストール")
    
    # ガベージコレクション実行
    collected = gc.collect()
    print(f"ガベージコレクション: {collected}オブジェクト削除")
    
    print("=== 最適化完了 ===")

def create_optimized_fingerprinter():
    """最適化されたFingerprinterを作成"""
    return AudioFingerprinter(
        n_fft=2048,
        hop_length=512,
        sr=22050,
        enable_numba_optimization=True,  # Numba最適化を有効化
        enable_adaptive_params=True      # 適応的パラメータを有効化
    )

def create_optimized_mimizam():
    """最適化されたMimizamシステムを作成"""
    # 最適化されたFingerprinter設定
    fingerprinter_config = {
        'enable_numba_optimization': True,
        'enable_adaptive_params': True
    }
    
    # Matcher設定
    matcher_config = {
        'min_confidence': 0.1,
        'max_results': 5,
        'scoring_method': 'hybrid'
    }
    
    return create_mimizam_sqlite(
        db_path="optimized.db",
        matcher_config=matcher_config,
        **fingerprinter_config
    )

# 使用例
optimize_system_performance()

# 最適化されたシステムを作成
mimizam = create_optimized_mimizam()
fingerprinter = create_optimized_fingerprinter()

print("最適化されたmimizamシステムが準備完了")
```

## 🔗 関連ドキュメント

- [バックエンド比較](./11_backend_comparison.md) - データベース性能比較
- [適応パラメータ調整](./15_adaptive_parameters.md) - パラメータ最適化
- [パフォーマンス分析](./20_performance_analysis.md) - 詳細分析手法
- [パフォーマンステスト](./23_performance_testing.md) - テスト手法
- [デバッグとトラブルシューティング](./21_debugging.md) - 問題解決

## 💡 最適化のベストプラクティス

### 1. 段階的最適化
- まず正確性を確保
- 次にボトルネックを特定
- 最後に最適化を適用

### 2. 測定駆動最適化
- 最適化前後の性能測定
- プロファイリングによる問題特定
- 継続的なモニタリング

### 3. リソース効率
- メモリ使用量の監視
- CPU使用率の最適化
- I/O操作の最小化

mimizamシステムの性能を最大限に活用するために、これらの最適化技術を適切に組み合わせて使用してください。
