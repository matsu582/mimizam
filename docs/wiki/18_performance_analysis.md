# パフォーマンス分析

このページでは、mimizamシステムの性能測定と分析手法について説明します。システムのボトルネックを特定し、パフォーマンスを継続的に監視するためのツールと技術を紹介します。

パフォーマンス最適化については、[パフォーマンス最適化](./16_performance_optimization.md)を参照してください。テスト手法については、[テストと開発](./17_testing_development.md)を参照してください。

## パフォーマンス分析の概要

### 分析対象領域

| 領域 | 測定指標 | 分析手法 |
|------|----------|----------|
| **音声処理** | 処理時間、メモリ使用量 | プロファイリング、ベンチマーク |
| **データベース** | クエリ時間、スループット | クエリ分析、インデックス効率 |
| **システム全体** | CPU使用率、I/O待機 | システム監視、リソース分析 |
| **ネットワーク** | レイテンシ、帯域幅 | ネットワーク監視 |

## プロファイリングツール

### cProfileを使用した詳細分析

```python
import cProfile
import pstats
import io
from mimizam import create_mimizam_sqlite

def profile_fingerprint_generation():
    """指紋生成のプロファイリング"""
    
    def fingerprint_task():
        """プロファイリング対象タスク"""
        with create_mimizam_sqlite(":memory:") as mimizam:
            song_id = mimizam.add_song(
                "test_audio.wav",
                "Test Song",
                "Test Artist"
            )
            return song_id
    
    # プロファイリング実行
    profiler = cProfile.Profile()
    profiler.enable()
    
    result = fingerprint_task()
    
    profiler.disable()
    
    # 結果分析
    s = io.StringIO()
    ps = pstats.Stats(profiler, stream=s)
    ps.sort_stats('cumulative')
    ps.print_stats(20)  # 上位20関数を表示
    
    print("プロファイリング結果:")
    print(s.getvalue())
    
    return result

if __name__ == "__main__":
    profile_fingerprint_generation()
```

### line_profilerによる行単位分析

```python
@profile
def detailed_fingerprint_analysis(audio_file):
    """行単位パフォーマンス分析"""
    import librosa
    import numpy as np
    
    # 音声読み込み
    audio, sr = librosa.load(audio_file)
    
    # スペクトログラム計算
    stft = librosa.stft(audio, n_fft=2048, hop_length=512)
    magnitude = np.abs(stft)
    
    # ピーク検出
    peaks = []
    for i in range(1, magnitude.shape[0] - 1):
        for j in range(1, magnitude.shape[1] - 1):
            if magnitude[i, j] > magnitude[i-1:i+2, j-1:j+2].max() * 0.9:
                peaks.append((i, j))
    
    return peaks

# 実行方法:
# kernprof -l -v performance_analysis.py
```

## メモリ分析

### memory_profilerによるメモリ使用量分析

```python
from memory_profiler import profile
import psutil
import os

@profile
def memory_analysis_fingerprinting():
    """メモリ使用量分析"""
    from mimizam import create_mimizam_sqlite
    
    # 初期メモリ使用量
    process = psutil.Process(os.getpid())
    initial_memory = process.memory_info().rss / 1024 / 1024
    
    print(f"初期メモリ使用量: {initial_memory:.1f}MB")
    
    # mimizam処理
    with create_mimizam_sqlite(":memory:") as mimizam:
        # 大きな音声ファイル処理
        song_id = mimizam.add_song(
            "large_audio_file.wav",
            "Large Song",
            "Test Artist"
        )
        
        # ピーク時メモリ使用量
        peak_memory = process.memory_info().rss / 1024 / 1024
        print(f"ピークメモリ使用量: {peak_memory:.1f}MB")
        
        # 識別処理
        result = mimizam.identify_audio("query.wav")
        
        # 最終メモリ使用量
        final_memory = process.memory_info().rss / 1024 / 1024
        print(f"最終メモリ使用量: {final_memory:.1f}MB")
    
    return song_id

# 実行方法:
# python -m memory_profiler performance_analysis.py
```

### メモリリーク検出

```python
import gc
import tracemalloc

def detect_memory_leaks():
    """メモリリーク検出"""
    
    # メモリトレース開始
    tracemalloc.start()
    
    # 初期スナップショット
    snapshot1 = tracemalloc.take_snapshot()
    
    # 繰り返し処理（メモリリークの可能性がある処理）
    for i in range(100):
        with create_mimizam_sqlite(":memory:") as mimizam:
            mimizam.add_song(f"test_{i}.wav", f"Song {i}", "Artist")
            mimizam.identify_audio("query.wav")
    
    # 最終スナップショット
    snapshot2 = tracemalloc.take_snapshot()
    
    # メモリ使用量の差分を分析
    top_stats = snapshot2.compare_to(snapshot1, 'lineno')
    
    print("メモリ使用量増加上位10:")
    for stat in top_stats[:10]:
        print(stat)
    
    # ガベージコレクション実行
    collected = gc.collect()
    print(f"ガベージコレクション: {collected} オブジェクト回収")
    
    tracemalloc.stop()

if __name__ == "__main__":
    detect_memory_leaks()
```

## ベンチマーク測定

### 処理時間ベンチマーク

```python
import time
import statistics
from contextlib import contextmanager

@contextmanager
def timer():
    """処理時間測定コンテキストマネージャー"""
    start_time = time.perf_counter()
    yield
    end_time = time.perf_counter()
    print(f"実行時間: {end_time - start_time:.3f}秒")

def benchmark_fingerprint_generation():
    """指紋生成ベンチマーク"""
    
    test_files = [
        "test_audio_10sec.wav",
        "test_audio_30sec.wav", 
        "test_audio_60sec.wav",
        "test_audio_180sec.wav"
    ]
    
    results = {}
    
    for test_file in test_files:
        print(f"\nベンチマーク: {test_file}")
        
        times = []
        
        # 5回実行して平均を取る
        for i in range(5):
            with create_mimizam_sqlite(":memory:") as mimizam:
                start_time = time.perf_counter()
                
                song_id = mimizam.add_song(
                    test_file,
                    f"Test Song {i}",
                    "Benchmark Artist"
                )
                
                end_time = time.perf_counter()
                times.append(end_time - start_time)
        
        # 統計計算
        avg_time = statistics.mean(times)
        std_dev = statistics.stdev(times) if len(times) > 1 else 0
        min_time = min(times)
        max_time = max(times)
        
        results[test_file] = {
            'average': avg_time,
            'std_dev': std_dev,
            'min': min_time,
            'max': max_time,
            'times': times
        }
        
        print(f"平均時間: {avg_time:.3f}秒 (±{std_dev:.3f})")
        print(f"最小時間: {min_time:.3f}秒")
        print(f"最大時間: {max_time:.3f}秒")
    
    return results

def benchmark_identification_speed():
    """識別速度ベンチマーク"""
    
    # データベース準備
    with create_mimizam_sqlite("benchmark.db") as mimizam:
        # 複数楽曲を追加
        for i in range(50):
            mimizam.add_song(
                f"reference_{i}.wav",
                f"Reference Song {i}",
                f"Artist {i % 10}"
            )
        
        # 識別ベンチマーク
        query_files = [
            "query_5sec.wav",
            "query_10sec.wav",
            "query_15sec.wav",
            "query_30sec.wav"
        ]
        
        for query_file in query_files:
            print(f"\n識別ベンチマーク: {query_file}")
            
            times = []
            
            for i in range(10):
                start_time = time.perf_counter()
                result = mimizam.identify_audio(query_file)
                end_time = time.perf_counter()
                
                times.append(end_time - start_time)
            
            avg_time = statistics.mean(times)
            print(f"平均識別時間: {avg_time:.3f}秒")

if __name__ == "__main__":
    benchmark_fingerprint_generation()
    benchmark_identification_speed()
```

## システムリソース監視

### リアルタイム監視

```python
import psutil
import threading
import time
import matplotlib.pyplot as plt
from collections import deque

class SystemMonitor:
    """システムリソース監視クラス"""
    
    def __init__(self, max_samples=100):
        self.max_samples = max_samples
        self.cpu_data = deque(maxlen=max_samples)
        self.memory_data = deque(maxlen=max_samples)
        self.disk_io_data = deque(maxlen=max_samples)
        self.timestamps = deque(maxlen=max_samples)
        self.monitoring = False
        self.monitor_thread = None
    
    def start_monitoring(self, interval=1.0):
        """監視開始"""
        self.monitoring = True
        self.monitor_thread = threading.Thread(
            target=self._monitor_loop, 
            args=(interval,)
        )
        self.monitor_thread.start()
    
    def stop_monitoring(self):
        """監視停止"""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join()
    
    def _monitor_loop(self, interval):
        """監視ループ"""
        while self.monitoring:
            timestamp = time.time()
            
            # CPU使用率
            cpu_percent = psutil.cpu_percent(interval=None)
            
            # メモリ使用率
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            
            # ディスクI/O
            disk_io = psutil.disk_io_counters()
            disk_io_rate = disk_io.read_bytes + disk_io.write_bytes
            
            # データ保存
            self.timestamps.append(timestamp)
            self.cpu_data.append(cpu_percent)
            self.memory_data.append(memory_percent)
            self.disk_io_data.append(disk_io_rate)
            
            time.sleep(interval)
    
    def get_current_stats(self):
        """現在の統計情報を取得"""
        if not self.cpu_data:
            return None
        
        return {
            'cpu_percent': self.cpu_data[-1],
            'memory_percent': self.memory_data[-1],
            'disk_io_rate': self.disk_io_data[-1],
            'timestamp': self.timestamps[-1]
        }
    
    def plot_metrics(self):
        """メトリクスをプロット"""
        if len(self.timestamps) < 2:
            print("データが不足しています")
            return
        
        fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(12, 8))
        
        times = list(self.timestamps)
        
        # CPU使用率
        ax1.plot(times, list(self.cpu_data), 'b-', label='CPU使用率')
        ax1.set_ylabel('CPU (%)')
        ax1.set_title('システムリソース監視')
        ax1.legend()
        ax1.grid(True)
        
        # メモリ使用率
        ax2.plot(times, list(self.memory_data), 'r-', label='メモリ使用率')
        ax2.set_ylabel('メモリ (%)')
        ax2.legend()
        ax2.grid(True)
        
        # ディスクI/O
        ax3.plot(times, list(self.disk_io_data), 'g-', label='ディスクI/O')
        ax3.set_ylabel('バイト/秒')
        ax3.set_xlabel('時間')
        ax3.legend()
        ax3.grid(True)
        
        plt.tight_layout()
        plt.savefig('system_metrics.png')
        plt.show()

def monitor_mimizam_performance():
    """mimizam処理中のシステム監視"""
    
    monitor = SystemMonitor()
    
    # 監視開始
    monitor.start_monitoring(interval=0.5)
    
    try:
        # mimizam処理実行
        with create_mimizam_sqlite("monitored.db") as mimizam:
            print("楽曲追加開始...")
            
            for i in range(10):
                mimizam.add_song(
                    f"test_song_{i}.wav",
                    f"Song {i}",
                    f"Artist {i}"
                )
                
                # 現在の統計表示
                stats = monitor.get_current_stats()
                if stats:
                    print(f"楽曲 {i}: CPU {stats['cpu_percent']:.1f}%, "
                          f"メモリ {stats['memory_percent']:.1f}%")
            
            print("識別処理開始...")
            
            for i in range(5):
                result = mimizam.identify_audio(f"query_{i}.wav")
                
                stats = monitor.get_current_stats()
                if stats:
                    print(f"識別 {i}: CPU {stats['cpu_percent']:.1f}%, "
                          f"メモリ {stats['memory_percent']:.1f}%")
    
    finally:
        # 監視停止
        monitor.stop_monitoring()
        
        # 結果プロット
        monitor.plot_metrics()

if __name__ == "__main__":
    monitor_mimizam_performance()
```

## データベースパフォーマンス分析

### クエリ分析

```python
import sqlite3
import time

def analyze_database_performance():
    """データベースパフォーマンス分析"""
    
    def execute_with_timing(cursor, query, params=()):
        """クエリ実行時間測定"""
        start_time = time.perf_counter()
        cursor.execute(query, params)
        result = cursor.fetchall()
        end_time = time.perf_counter()
        
        return result, end_time - start_time
    
    # データベース接続
    conn = sqlite3.connect("performance_test.db")
    cursor = conn.cursor()
    
    # テストクエリ
    queries = [
        ("楽曲数カウント", "SELECT COUNT(*) FROM songs"),
        ("指紋数カウント", "SELECT COUNT(*) FROM fingerprints"),
        ("ハッシュ検索", "SELECT * FROM fingerprints WHERE hash = ?", ("test_hash",)),
        ("楽曲ID検索", "SELECT * FROM fingerprints WHERE song_id = ?", (1,)),
        ("複合検索", """
            SELECT s.title, s.artist, COUNT(f.id) as fingerprint_count
            FROM songs s
            LEFT JOIN fingerprints f ON s.id = f.song_id
            GROUP BY s.id
            ORDER BY fingerprint_count DESC
            LIMIT 10
        """),
    ]
    
    print("データベースクエリ性能分析:")
    print("-" * 50)
    
    for query_name, query, *params in queries:
        query_params = params[0] if params else ()
        
        # 複数回実行して平均を取る
        times = []
        for _ in range(5):
            _, exec_time = execute_with_timing(cursor, query, query_params)
            times.append(exec_time)
        
        avg_time = sum(times) / len(times)
        min_time = min(times)
        max_time = max(times)
        
        print(f"{query_name}:")
        print(f"  平均時間: {avg_time*1000:.2f}ms")
        print(f"  最小時間: {min_time*1000:.2f}ms")
        print(f"  最大時間: {max_time*1000:.2f}ms")
        print()
    
    # インデックス効率分析
    print("インデックス効率分析:")
    print("-" * 30)
    
    # EXPLAIN QUERY PLANでクエリプランを確認
    explain_queries = [
        "SELECT * FROM fingerprints WHERE hash = 'test_hash'",
        "SELECT * FROM fingerprints WHERE song_id = 1",
        "SELECT * FROM songs WHERE title LIKE '%test%'",
    ]
    
    for query in explain_queries:
        cursor.execute(f"EXPLAIN QUERY PLAN {query}")
        plan = cursor.fetchall()
        
        print(f"クエリ: {query}")
        for row in plan:
            print(f"  プラン: {row}")
        print()
    
    conn.close()

if __name__ == "__main__":
    analyze_database_performance()
```

## 継続的パフォーマンス監視

### 自動ベンチマーク

```python
import json
import datetime
from pathlib import Path

class PerformanceBenchmark:
    """継続的パフォーマンスベンチマーク"""
    
    def __init__(self, results_file="benchmark_results.json"):
        self.results_file = Path(results_file)
        self.results = self._load_results()
    
    def _load_results(self):
        """過去の結果を読み込み"""
        if self.results_file.exists():
            with open(self.results_file, 'r') as f:
                return json.load(f)
        return []
    
    def _save_results(self):
        """結果を保存"""
        with open(self.results_file, 'w') as f:
            json.dump(self.results, f, indent=2)
    
    def run_benchmark(self):
        """ベンチマーク実行"""
        timestamp = datetime.datetime.now().isoformat()
        
        # 指紋生成ベンチマーク
        fingerprint_time = self._benchmark_fingerprint_generation()
        
        # 識別ベンチマーク
        identification_time = self._benchmark_identification()
        
        # メモリ使用量ベンチマーク
        memory_usage = self._benchmark_memory_usage()
        
        # 結果記録
        result = {
            'timestamp': timestamp,
            'fingerprint_generation_time': fingerprint_time,
            'identification_time': identification_time,
            'memory_usage_mb': memory_usage,
            'version': self._get_version()
        }
        
        self.results.append(result)
        self._save_results()
        
        return result
    
    def _benchmark_fingerprint_generation(self):
        """指紋生成ベンチマーク"""
        with create_mimizam_sqlite(":memory:") as mimizam:
            start_time = time.perf_counter()
            
            mimizam.add_song(
                "benchmark_audio.wav",
                "Benchmark Song",
                "Benchmark Artist"
            )
            
            end_time = time.perf_counter()
            return end_time - start_time
    
    def _benchmark_identification(self):
        """識別ベンチマーク"""
        with create_mimizam_sqlite(":memory:") as mimizam:
            # 楽曲追加
            mimizam.add_song("reference.wav", "Reference", "Artist")
            
            # 識別測定
            start_time = time.perf_counter()
            result = mimizam.identify_audio("query.wav")
            end_time = time.perf_counter()
            
            return end_time - start_time
    
    def _benchmark_memory_usage(self):
        """メモリ使用量ベンチマーク"""
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss
        
        with create_mimizam_sqlite(":memory:") as mimizam:
            mimizam.add_song("benchmark_audio.wav", "Test", "Artist")
            peak_memory = process.memory_info().rss
        
        return (peak_memory - initial_memory) / 1024 / 1024
    
    def _get_version(self):
        """バージョン情報取得"""
        try:
            import mimizam
            return getattr(mimizam, '__version__', 'unknown')
        except:
            return 'unknown'
    
    def analyze_trends(self):
        """パフォーマンストレンド分析"""
        if len(self.results) < 2:
            print("トレンド分析には最低2回の測定が必要です")
            return
        
        print("パフォーマンストレンド分析:")
        print("-" * 40)
        
        # 最新と最古の結果を比較
        latest = self.results[-1]
        oldest = self.results[0]
        
        metrics = [
            ('指紋生成時間', 'fingerprint_generation_time'),
            ('識別時間', 'identification_time'),
            ('メモリ使用量', 'memory_usage_mb')
        ]
        
        for metric_name, metric_key in metrics:
            latest_value = latest[metric_key]
            oldest_value = oldest[metric_key]
            
            change = ((latest_value - oldest_value) / oldest_value) * 100
            
            print(f"{metric_name}:")
            print(f"  最古: {oldest_value:.3f}")
            print(f"  最新: {latest_value:.3f}")
            print(f"  変化: {change:+.1f}%")
            print()

def run_continuous_benchmark():
    """継続的ベンチマーク実行"""
    benchmark = PerformanceBenchmark()
    
    print("ベンチマーク実行中...")
    result = benchmark.run_benchmark()
    
    print("ベンチマーク結果:")
    print(f"指紋生成時間: {result['fingerprint_generation_time']:.3f}秒")
    print(f"識別時間: {result['identification_time']:.3f}秒")
    print(f"メモリ使用量: {result['memory_usage_mb']:.1f}MB")
    
    # トレンド分析
    benchmark.analyze_trends()

if __name__ == "__main__":
    run_continuous_benchmark()
```

## 関連ドキュメント

- [パフォーマンス最適化](./16_performance_optimization.md) - 高速化技術
- [テストと開発](./17_testing_development.md) - テスト手法
- [コアアーキテクチャ](./03_core_architecture.md) - システム全体の構成
- [データベースバックエンド](./09_database_backends.md) - データベース性能
