# パフォーマンス最適化

このページでは、mimizamシステムのパフォーマンスを向上させるための技術と戦略について説明します。音声処理の高速化、メモリ使用量の削減、データベース最適化などの実践的な手法を紹介します。

基本的な使用方法については、[基本的な使用例](./14_basic_usage_examples.md)を参照してください。システムアーキテクチャについては、[コアアーキテクチャ](./03_core_architecture.md)を参照してください。

## パフォーマンス最適化の概要

### 最適化対象領域

| 領域 | 最適化手法 | 期待効果 |
|------|-----------|----------|
| **音声処理** | Numba JIT、ベクトル化 | 10-100倍高速化 |
| **データベース** | インデックス、バッチ処理 | クエリ時間短縮 |
| **メモリ管理** | ストリーミング、キャッシュ | メモリ使用量削減 |
| **並列処理** | マルチプロセシング | CPU使用率向上 |

## Numba JIT最適化

### 現在の状況

mimizamでは、Numba JIT最適化は現在無効化されています。これは、期待された性能向上が得られず、ピークオーバーフロー問題が発生したためです。

### Numba最適化の実装例

```python
import numba
import numpy as np

@numba.jit(nopython=True)
def find_peaks_numba(spectrogram, min_amplitude, neighborhood_size):
    """Numba最適化されたピーク検出"""
    rows, cols = spectrogram.shape
    peaks = []
    
    for i in range(neighborhood_size, rows - neighborhood_size):
        for j in range(neighborhood_size, cols - neighborhood_size):
            if spectrogram[i, j] < min_amplitude:
                continue
            
            # 近傍での最大値チェック
            is_peak = True
            for di in range(-neighborhood_size, neighborhood_size + 1):
                for dj in range(-neighborhood_size, neighborhood_size + 1):
                    if spectrogram[i + di, j + dj] > spectrogram[i, j]:
                        is_peak = False
                        break
                if not is_peak:
                    break
            
            if is_peak:
                peaks.append((i, j))
    
    return peaks

def enable_numba_optimization():
    """Numba最適化の有効化（実験的）"""
    # 注意: 現在は無効化されています
    import os
    os.environ['NUMBA_DISABLE_JIT'] = '0'
    os.environ['NUMBA_NUM_THREADS'] = '4'
    os.environ['NUMBA_CACHE_DIR'] = '/tmp/numba_cache'
```

## メモリ最適化

### ストリーミング処理

```python
def process_large_audio_streaming(file_path, chunk_size=44100*10):
    """大きな音声ファイルのストリーミング処理"""
    import librosa
    
    # 音声ファイル情報取得
    duration = librosa.get_duration(filename=file_path)
    sr = librosa.get_samplerate(file_path)
    
    total_chunks = int(duration * sr / chunk_size) + 1
    all_fingerprints = []
    
    for i in range(total_chunks):
        start_sample = i * chunk_size
        
        # チャンクを読み込み
        audio_chunk, _ = librosa.load(
            file_path,
            sr=sr,
            offset=start_sample / sr,
            duration=chunk_size / sr
        )
        
        # チャンクの指紋生成
        chunk_fingerprints = generate_fingerprints_chunk(audio_chunk, sr, start_sample / sr)
        all_fingerprints.extend(chunk_fingerprints)
        
        # メモリ解放
        del audio_chunk
    
    return all_fingerprints

def generate_fingerprints_chunk(audio_chunk, sr, time_offset):
    """音声チャンクから指紋を生成"""
    # 実装は省略
    pass
```

### メモリプール

```python
class AudioMemoryPool:
    """音声処理用メモリプール"""
    
    def __init__(self, pool_size=10):
        self.pool = []
        self.pool_size = pool_size
    
    def get_buffer(self, size):
        """バッファを取得"""
        for i, buffer in enumerate(self.pool):
            if len(buffer) >= size:
                return self.pool.pop(i)
        
        # 新しいバッファを作成
        return np.zeros(size, dtype=np.float32)
    
    def return_buffer(self, buffer):
        """バッファを返却"""
        if len(self.pool) < self.pool_size:
            buffer.fill(0)  # クリア
            self.pool.append(buffer)

# グローバルメモリプール
memory_pool = AudioMemoryPool()
```

## データベース最適化

### インデックス最適化

```python
def optimize_database_indices(backend):
    """データベースインデックスの最適化"""
    
    if backend.backend_type == 'sqlite':
        # SQLite最適化
        backend.execute_query("ANALYZE")
        backend.execute_query("REINDEX")
        backend.execute_query("PRAGMA optimize")
        
    elif backend.backend_type == 'mysql':
        # MySQL最適化
        backend.execute_query("ANALYZE TABLE songs, fingerprints")
        backend.execute_query("OPTIMIZE TABLE songs, fingerprints")
        
    elif backend.backend_type == 'postgresql':
        # PostgreSQL最適化
        backend.execute_query("ANALYZE songs, fingerprints")
        backend.execute_query("VACUUM ANALYZE songs, fingerprints")
        
    elif backend.backend_type == 'elasticsearch':
        # Elasticsearch最適化
        backend.force_merge("songs", max_num_segments=1)
        backend.force_merge("fingerprints", max_num_segments=5)
```

### バッチ処理最適化

```python
def batch_insert_fingerprints(backend, fingerprints, batch_size=1000):
    """指紋のバッチ挿入最適化"""
    
    total_fingerprints = len(fingerprints)
    
    for i in range(0, total_fingerprints, batch_size):
        batch = fingerprints[i:i + batch_size]
        
        if backend.backend_type == 'sqlite':
            # SQLite用バッチ挿入
            query = "INSERT INTO fingerprints (song_id, hash, time_offset) VALUES (?, ?, ?)"
            backend.execute_many(query, batch)
            
        elif backend.backend_type in ['mysql', 'postgresql']:
            # MySQL/PostgreSQL用バッチ挿入
            placeholders = ','.join(['(%s, %s, %s)'] * len(batch))
            query = f"INSERT INTO fingerprints (song_id, hash, time_offset) VALUES {placeholders}"
            flat_batch = [item for sublist in batch for item in sublist]
            backend.execute_query(query, flat_batch)
            
        elif backend.backend_type == 'elasticsearch':
            # Elasticsearch用バルク挿入
            bulk_docs = []
            for song_id, hash_value, time_offset in batch:
                bulk_docs.append({
                    "_index": "fingerprints",
                    "_source": {
                        "song_id": song_id,
                        "hash": hash_value,
                        "time_offset": time_offset
                    }
                })
            backend.bulk_index(bulk_docs)
```

## 並列処理

### マルチプロセシング

```python
from multiprocessing import Pool, cpu_count
import functools

def parallel_fingerprint_generation(file_paths, num_processes=None):
    """並列指紋生成"""
    
    if num_processes is None:
        num_processes = min(cpu_count(), len(file_paths))
    
    def process_single_file(file_path):
        """単一ファイルの処理"""
        try:
            fingerprinter = AudioFingerprinter()
            fingerprints = fingerprinter.generate_fingerprints(file_path)
            return file_path, fingerprints, None
        except Exception as e:
            return file_path, None, str(e)
    
    with Pool(processes=num_processes) as pool:
        results = pool.map(process_single_file, file_paths)
    
    return results

def parallel_audio_identification(query_files, mimizam_instance, num_processes=None):
    """並列音声識別"""
    
    if num_processes is None:
        num_processes = min(cpu_count(), len(query_files))
    
    def identify_single_audio(query_file):
        """単一音声の識別"""
        try:
            result = mimizam_instance.identify_audio(query_file)
            return query_file, result, None
        except Exception as e:
            return query_file, None, str(e)
    
    with Pool(processes=num_processes) as pool:
        results = pool.map(identify_single_audio, query_files)
    
    return results
```

### 非同期処理

```python
import asyncio
import aiofiles

async def async_fingerprint_generation(file_paths):
    """非同期指紋生成"""
    
    async def process_file(file_path):
        """非同期ファイル処理"""
        try:
            # 非同期でファイル読み込み
            async with aiofiles.open(file_path, 'rb') as f:
                audio_data = await f.read()
            
            # 指紋生成（CPU集約的なので別スレッドで実行）
            loop = asyncio.get_event_loop()
            fingerprints = await loop.run_in_executor(
                None, 
                generate_fingerprints_from_data, 
                audio_data
            )
            
            return file_path, fingerprints
            
        except Exception as e:
            return file_path, None
    
    # 並行実行
    tasks = [process_file(file_path) for file_path in file_paths]
    results = await asyncio.gather(*tasks)
    
    return results

def generate_fingerprints_from_data(audio_data):
    """音声データから指紋を生成"""
    # 実装は省略
    pass
```

## キャッシュ戦略

### LRUキャッシュ

```python
from functools import lru_cache
import hashlib

class FingerprintCache:
    """指紋キャッシュシステム"""
    
    def __init__(self, max_size=1000):
        self.cache = {}
        self.access_order = []
        self.max_size = max_size
    
    def get_file_hash(self, file_path):
        """ファイルハッシュを計算"""
        hasher = hashlib.md5()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
    
    def get_fingerprints(self, file_path):
        """キャッシュから指紋を取得"""
        file_hash = self.get_file_hash(file_path)
        
        if file_hash in self.cache:
            # アクセス順序を更新
            self.access_order.remove(file_hash)
            self.access_order.append(file_hash)
            return self.cache[file_hash]
        
        return None
    
    def store_fingerprints(self, file_path, fingerprints):
        """指紋をキャッシュに保存"""
        file_hash = self.get_file_hash(file_path)
        
        # キャッシュサイズ制限
        if len(self.cache) >= self.max_size:
            # 最も古いエントリを削除
            oldest_hash = self.access_order.pop(0)
            del self.cache[oldest_hash]
        
        self.cache[file_hash] = fingerprints
        self.access_order.append(file_hash)

# グローバルキャッシュ
fingerprint_cache = FingerprintCache()

@lru_cache(maxsize=128)
def cached_spectrogram_computation(audio_hash, n_fft, hop_length):
    """スペクトログラム計算のキャッシュ"""
    # 実装は省略
    pass
```

## プロファイリングと監視

### パフォーマンス監視

```python
import time
import psutil
import threading
from collections import defaultdict

class PerformanceMonitor:
    """パフォーマンス監視システム"""
    
    def __init__(self):
        self.metrics = defaultdict(list)
        self.start_times = {}
        self.monitoring = False
        self.monitor_thread = None
    
    def start_monitoring(self, interval=1.0):
        """監視開始"""
        self.monitoring = True
        self.monitor_thread = threading.Thread(target=self._monitor_system, args=(interval,))
        self.monitor_thread.start()
    
    def stop_monitoring(self):
        """監視停止"""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join()
    
    def _monitor_system(self, interval):
        """システム監視ループ"""
        while self.monitoring:
            # CPU使用率
            cpu_percent = psutil.cpu_percent()
            self.metrics['cpu_percent'].append(cpu_percent)
            
            # メモリ使用率
            memory = psutil.virtual_memory()
            self.metrics['memory_percent'].append(memory.percent)
            self.metrics['memory_used_mb'].append(memory.used / 1024 / 1024)
            
            time.sleep(interval)
    
    def start_timer(self, operation):
        """タイマー開始"""
        self.start_times[operation] = time.time()
    
    def end_timer(self, operation):
        """タイマー終了"""
        if operation in self.start_times:
            duration = time.time() - self.start_times[operation]
            self.metrics[f'{operation}_duration'].append(duration)
            del self.start_times[operation]
            return duration
        return None
    
    def get_statistics(self):
        """統計情報を取得"""
        stats = {}
        
        for metric, values in self.metrics.items():
            if values:
                stats[metric] = {
                    'count': len(values),
                    'mean': sum(values) / len(values),
                    'min': min(values),
                    'max': max(values)
                }
        
        return stats

# グローバル監視インスタンス
performance_monitor = PerformanceMonitor()
```

### プロファイリング

```python
import cProfile
import pstats
from functools import wraps

def profile_function(func):
    """関数プロファイリングデコレータ"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        profiler = cProfile.Profile()
        profiler.enable()
        
        try:
            result = func(*args, **kwargs)
        finally:
            profiler.disable()
            
            # プロファイル結果を表示
            stats = pstats.Stats(profiler)
            stats.sort_stats('cumulative')
            stats.print_stats(10)  # 上位10関数を表示
        
        return result
    
    return wrapper

@profile_function
def profile_fingerprint_generation(file_path):
    """指紋生成のプロファイリング"""
    fingerprinter = AudioFingerprinter()
    return fingerprinter.generate_fingerprints(file_path)
```

## 実用的な最適化例

### 高速化設定

```python
def create_optimized_mimizam():
    """最適化されたmimizamインスタンスを作成"""
    
    # 高速処理用パラメータ
    config = {
        'n_fft': 1024,           # 小さなFFTサイズ
        'hop_length': 512,       # 大きなホップ長
        'min_amplitude': -50,    # 緩い閾値
        'peak_neighborhood_size': 10,  # 小さな近傍サイズ
        'enable_adaptive_params': True,  # 適応パラメータ
        'debug': False           # デバッグ無効
    }
    
    return create_mimizam_sqlite("optimized.db", **config)

def benchmark_performance():
    """パフォーマンスベンチマーク"""
    
    test_files = ["test1.wav", "test2.wav", "test3.wav"]
    
    # 標準設定
    print("標準設定でのテスト:")
    standard_mimizam = create_mimizam_sqlite("standard.db")
    
    start_time = time.time()
    for file_path in test_files:
        standard_mimizam.add_song(file_path, f"Song {file_path}", "Test Artist")
    standard_time = time.time() - start_time
    
    # 最適化設定
    print("最適化設定でのテスト:")
    optimized_mimizam = create_optimized_mimizam()
    
    start_time = time.time()
    for file_path in test_files:
        optimized_mimizam.add_song(file_path, f"Song {file_path}", "Test Artist")
    optimized_time = time.time() - start_time
    
    print(f"標準設定: {standard_time:.2f}秒")
    print(f"最適化設定: {optimized_time:.2f}秒")
    print(f"高速化率: {standard_time / optimized_time:.1f}倍")
```

## 関連ドキュメント

- [コアアーキテクチャ](./03_core_architecture.md) - システム全体の構成
- [音声指紋エンジン](./04_audio_fingerprinting_engine.md) - 音声処理の詳細
- [データベースバックエンド](./09_database_backends.md) - データベース最適化
- [基本的な使用例](./14_basic_usage_examples.md) - 実践的な使用方法
- [パフォーマンス分析](./18_performance_analysis.md) - 性能測定と分析
