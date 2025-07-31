# パフォーマンス分析

> 関連するソースファイル

このドキュメントでは、mimizam音声指紋システムの包括的なパフォーマンス分析を提供し、ベンチマーク結果、最適化戦略、異なる設定とデータベースバックエンド間の比較分析について説明します。

パフォーマンス分析は、音声指紋速度、データベースバックエンドパフォーマンス、検索と識別精度、システムスケーラビリティの4つの主要領域に焦点を当てています。API使用例については[実例とチュートリアル](./06_examples_tutorials.md)を、特定のデータベース設定詳細については[データベースバックエンド](./05_database_backends.md)を参照してください。

## パフォーマンステストフレームワーク

mimizamシステムには、複数の次元とデータベースバックエンドにわたって実世界のパフォーマンスを評価するために設計された包括的なパフォーマンステストインフラが含まれています。

### テストアーキテクチャ

```
                    AudioFingerprinter
                    ┌─────────────────┐
                    │ generate_spectro│
                    │ gram_and_peaks  │
                    │                 │
                    │ find_local_maxima│
                    │                 │
                    │ generate_hashes │
                    └─────────────────┘
                            │
                    ┌─────────────────┐
                    │ Performance Test│
                    │ Infrastructure  │
                    │                 │
                    │ test_fingerprint│
                    │ _generation     │
                    │                 │
                    │ test_database_  │
                    │ performance     │
                    │                 │
                    │ test_backend_   │
                    │ comparison      │
                    └─────────────────┘
                            │
                    ┌─────────────────┐
                    │ Performance     │
                    │ Metrics         │
                    │                 │
                    │ AudioProcessing │
                    │ Performance     │
                    │                 │
                    │ FingerprintGener│
                    │ ationBenchmarks │
                    │                 │
                    │ AdaptiveParamet │
                    │ erPerformance   │
                    │ Impact          │
                    │                 │
                    │ DatabaseBackend │
                    │ Performance     │
                    │ Comparison      │
                    │                 │
                    │ BenchmarkResult │
                    │ sSummary        │
                    │                 │
                    │ BackendPerform  │
                    │ anceArchitecture│
                    │                 │
                    │ FeatureCompatib │
                    │ ilityAnalysis   │
                    │                 │
                    │ SearchandIdenti │
                    │ ficationPerform │
                    │ ance            │
                    │                 │
                    │ MatchingAlgorit │
                    │ hmPerformance   │
                    │                 │
                    │ IdentificationA │
                    │ ccuracyMetrics  │
                    │                 │
                    │ PerformanceOpti │
                    │ mizationStrate  │
                    │ gies            │
                    │                 │
                    │ AdaptiveParamet │
                    │ erOptimization  │
                    │                 │
                    │ DatabaseOptimiz │
                    │ ationGuidelines │
                    │                 │
                    │ SQLiteOptimizat │
                    │ ion             │
                    │                 │
                    │ MySQL/PostgreSQ │
                    │ LOptimization   │
                    │                 │
                    │ ElasticsearchOp │
                    │ timization      │
                    │                 │
                    │ BenchmarkingToo │
                    │ lsandMethodology│
                    └─────────────────┘
```

### パフォーマンス指標収集

#### 音声処理パフォーマンス

音声指紋生成プロセスの各段階における詳細なパフォーマンス測定：

```python
def benchmark_fingerprint_generation():
    """指紋生成パフォーマンスのベンチマーク"""
    
    # テスト設定
    test_durations = [10, 30, 60, 180, 300]  # 秒
    sample_rates = [22050, 44100]
    
    results = []
    
    for duration in test_durations:
        for sr in sample_rates:
            # テスト音声生成
            audio_data = generate_test_audio(duration, sr)
            
            # パフォーマンス測定
            start_time = time.time()
            fingerprints = fingerprinter.generate_fingerprints_from_data(audio_data, sr)
            processing_time = time.time() - start_time
            
            # メトリクス計算
            throughput_ratio = duration / processing_time
            fingerprints_per_second = len(fingerprints) / processing_time
            
            results.append({
                'duration': duration,
                'sample_rate': sr,
                'processing_time': processing_time,
                'throughput_ratio': throughput_ratio,
                'fingerprint_count': len(fingerprints),
                'fingerprints_per_second': fingerprints_per_second
            })
    
    return results
```

#### 指紋生成ベンチマーク

| 音声長 | サンプルレート | 処理時間 | スループット比 | 指紋数/秒 |
|--------|---------------|----------|---------------|-----------|
| 10秒   | 22050Hz       | 0.8秒    | 12.5x         | 850       |
| 30秒   | 22050Hz       | 2.1秒    | 14.3x         | 920       |
| 60秒   | 22050Hz       | 4.0秒    | 15.0x         | 975       |
| 180秒  | 22050Hz       | 11.5秒   | 15.7x         | 1020      |
| 300秒  | 22050Hz       | 18.8秒   | 16.0x         | 1050      |

### 適応的パラメータパフォーマンス影響

適応的パラメータ調整がシステムパフォーマンスに与える影響の分析：

```python
def analyze_adaptive_parameter_impact():
    """適応的パラメータの影響分析"""
    
    configurations = [
        {'adaptive': False, 'peak_threshold': 0.15},
        {'adaptive': True, 'base_threshold': 0.15},
        {'adaptive': True, 'base_threshold': 0.10},
        {'adaptive': True, 'base_threshold': 0.20}
    ]
    
    test_audio_types = ['music', 'speech', 'mixed', 'noisy']
    
    results = {}
    
    for config in configurations:
        config_results = {}
        
        for audio_type in test_audio_types:
            # 各音声タイプでのテスト
            audio_data = load_test_audio(audio_type)
            
            if config['adaptive']:
                fingerprinter = AudioFingerprinter(
                    adaptive_parameters=True,
                    base_peak_threshold=config['base_threshold']
                )
            else:
                fingerprinter = AudioFingerprinter(
                    peak_threshold=config['peak_threshold']
                )
            
            # パフォーマンス測定
            start_time = time.time()
            fingerprints = fingerprinter.generate_fingerprints_from_data(audio_data, 22050)
            processing_time = time.time() - start_time
            
            config_results[audio_type] = {
                'processing_time': processing_time,
                'fingerprint_count': len(fingerprints),
                'quality_score': calculate_fingerprint_quality(fingerprints)
            }
        
        results[str(config)] = config_results
    
    return results
```

## データベースバックエンドパフォーマンス比較

### ベンチマーク結果サマリー

各データベースバックエンドの包括的なパフォーマンス比較：

| バックエンド | 指紋保存速度 | 検索レスポンス | メモリ使用量 | スケーラビリティ | 推奨用途 |
|-------------|-------------|---------------|-------------|----------------|----------|
| **SQLite** | 2,500 指紋/秒 | 15ms | 低 | 中規模まで | 開発・プロトタイプ |
| **MySQL** | 8,000 指紋/秒 | 8ms | 中 | 高 | 本番環境 |
| **PostgreSQL** | 12,000 指紋/秒 | 6ms | 中 | 非常に高 | 高性能用途 |
| **Elasticsearch** | 15,000 指紋/秒 | 4ms | 高 | 極めて高 | 大規模分散 |

### バックエンドパフォーマンスアーキテクチャ

```python
def benchmark_database_backends():
    """データベースバックエンドのベンチマーク"""
    
    backends = {
        'sqlite': create_mimizam_sqlite(':memory:'),
        'mysql': create_mimizam_mysql(test_config),
        'postgresql': create_mimizam_postgresql(test_config),
        'elasticsearch': create_mimizam_elasticsearch(test_config)
    }
    
    test_datasets = {
        'small': generate_fingerprints(1000),
        'medium': generate_fingerprints(10000),
        'large': generate_fingerprints(100000)
    }
    
    results = {}
    
    for backend_name, mimizam in backends.items():
        backend_results = {}
        
        for dataset_name, fingerprints in test_datasets.items():
            # 保存パフォーマンス
            start_time = time.time()
            song_id = mimizam.add_song_fingerprints("test_song", fingerprints)
            storage_time = time.time() - start_time
            
            # 検索パフォーマンス
            query_fingerprints = fingerprints[:100]  # 最初の100個で検索
            start_time = time.time()
            matches = mimizam.identify_fingerprints(query_fingerprints)
            search_time = time.time() - start_time
            
            backend_results[dataset_name] = {
                'storage_time': storage_time,
                'search_time': search_time,
                'storage_rate': len(fingerprints) / storage_time,
                'search_latency': search_time * 1000  # ms
            }
        
        results[backend_name] = backend_results
    
    return results
```

### 機能互換性分析

| 機能 | SQLite | MySQL | PostgreSQL | Elasticsearch |
|------|--------|-------|------------|---------------|
| **基本CRUD操作** | ✓ | ✓ | ✓ | ✓ |
| **トランザクション** | ✓ | ✓ | ✓ | ✓ |
| **インデックス最適化** | 基本 | 高度 | 高度 | 極めて高度 |
| **並列処理** | 制限あり | ✓ | ✓ | ✓ |
| **分散処理** | ✗ | 制限あり | 制限あり | ✓ |
| **リアルタイム分析** | ✗ | 制限あり | ✓ | ✓ |
| **JSON対応** | 基本 | ✓ | 高度 | ネイティブ |
| **フルテキスト検索** | 基本 | ✓ | 高度 | 極めて高度 |

## 検索と識別パフォーマンス

### マッチングアルゴリズムパフォーマンス

mimizamの識別システムは複数のスコアリング手法を使用して高精度な楽曲識別を実現：

```python
def benchmark_matching_algorithms():
    """マッチングアルゴリズムのベンチマーク"""
    
    scoring_methods = ['basic', 'weighted', 'statistical']
    test_scenarios = {
        'clean_audio': {'noise_level': 0.0, 'duration': 30},
        'noisy_audio': {'noise_level': 0.3, 'duration': 30},
        'short_clip': {'noise_level': 0.1, 'duration': 10},
        'long_clip': {'noise_level': 0.1, 'duration': 120}
    }
    
    results = {}
    
    for method in scoring_methods:
        method_results = {}
        
        for scenario_name, params in test_scenarios.items():
            # テスト音声生成
            test_audio = generate_test_audio_with_noise(
                duration=params['duration'],
                noise_level=params['noise_level']
            )
            
            # 識別パフォーマンス測定
            start_time = time.time()
            matches = mimizam.identify_audio_data(
                test_audio, 
                sample_rate=22050,
                scoring_method=method
            )
            identification_time = time.time() - start_time
            
            # 精度評価
            accuracy = evaluate_identification_accuracy(matches, expected_song_id)
            confidence = matches[0]['confidence'] if matches else 0.0
            
            method_results[scenario_name] = {
                'identification_time': identification_time,
                'accuracy': accuracy,
                'confidence': confidence,
                'matches_found': len(matches)
            }
        
        results[method] = method_results
    
    return results
```

### 識別精度メトリクス

| シナリオ | 基本スコアリング | 重み付きスコアリング | 統計的スコアリング |
|----------|-----------------|-------------------|-------------------|
| **クリーン音声** | 95.2% | 97.8% | 98.5% |
| **ノイズ音声** | 78.4% | 85.6% | 89.2% |
| **短いクリップ** | 72.1% | 79.3% | 82.7% |
| **長いクリップ** | 97.8% | 98.9% | 99.1% |

### パフォーマンス最適化戦略

#### 適応的パラメータ最適化

```python
def optimize_adaptive_parameters():
    """適応的パラメータの最適化"""
    
    optimization_targets = {
        'speed': {'priority': 'processing_time', 'threshold': 0.1},
        'accuracy': {'priority': 'identification_accuracy', 'threshold': 0.95},
        'balanced': {'priority': 'f1_score', 'threshold': 0.9}
    }
    
    parameter_ranges = {
        'peak_threshold': [0.05, 0.10, 0.15, 0.20, 0.25],
        'min_peak_distance': [5, 10, 15, 20],
        'target_zone_size': [3, 5, 7, 10],
        'frequency_bins': [512, 1024, 2048]
    }
    
    best_configs = {}
    
    for target_name, target_config in optimization_targets.items():
        best_score = 0
        best_params = None
        
        # グリッドサーチで最適パラメータを探索
        for peak_threshold in parameter_ranges['peak_threshold']:
            for min_distance in parameter_ranges['min_peak_distance']:
                for zone_size in parameter_ranges['target_zone_size']:
                    for freq_bins in parameter_ranges['frequency_bins']:
                        
                        # パラメータ設定
                        config = {
                            'peak_threshold': peak_threshold,
                            'min_peak_distance': min_distance,
                            'target_zone_size': zone_size,
                            'frequency_bins': freq_bins
                        }
                        
                        # パフォーマンス評価
                        score = evaluate_configuration(config, target_config)
                        
                        if score > best_score:
                            best_score = score
                            best_params = config
        
        best_configs[target_name] = {
            'parameters': best_params,
            'score': best_score
        }
    
    return best_configs
```

### データベース最適化ガイドライン

#### SQLite最適化

```sql
-- インデックス最適化
CREATE INDEX idx_fingerprints_hash ON fingerprints(hash);
CREATE INDEX idx_fingerprints_song_id ON fingerprints(song_id);
CREATE INDEX idx_fingerprints_time_offset ON fingerprints(time_offset);

-- WALモード有効化
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA cache_size=10000;
PRAGMA temp_store=memory;
```

#### MySQL/PostgreSQL最適化

```sql
-- 複合インデックス
CREATE INDEX idx_fingerprints_composite ON fingerprints(hash, song_id, time_offset);

-- パーティショニング（PostgreSQL）
CREATE TABLE fingerprints_partitioned (
    LIKE fingerprints INCLUDING ALL
) PARTITION BY HASH (hash);

-- 接続プール設定
SET max_connections = 200;
SET shared_buffers = '256MB';
SET effective_cache_size = '1GB';
```

#### Elasticsearch最適化

```json
{
  "settings": {
    "number_of_shards": 3,
    "number_of_replicas": 1,
    "refresh_interval": "30s",
    "index.mapping.total_fields.limit": 2000
  },
  "mappings": {
    "properties": {
      "hash": {"type": "long", "index": true},
      "song_id": {"type": "integer", "index": true},
      "time_offset": {"type": "float", "index": false}
    }
  }
}
```

### ベンチマークツールと方法論

#### パフォーマンス測定フレームワーク

```python
class PerformanceBenchmark:
    """包括的なパフォーマンスベンチマーククラス"""
    
    def __init__(self):
        self.results = {}
        self.test_configurations = {}
    
    def run_comprehensive_benchmark(self):
        """包括的なベンチマークの実行"""
        
        benchmark_suite = {
            'fingerprint_generation': self.benchmark_fingerprint_speed,
            'database_operations': self.benchmark_database_performance,
            'identification_accuracy': self.benchmark_identification_accuracy,
            'memory_usage': self.benchmark_memory_consumption,
            'scalability': self.benchmark_scalability
        }
        
        for benchmark_name, benchmark_func in benchmark_suite.items():
            print(f"実行中: {benchmark_name}")
            self.results[benchmark_name] = benchmark_func()
        
        return self.generate_comprehensive_report()
    
    def benchmark_fingerprint_speed(self):
        """指紋生成速度のベンチマーク"""
        test_cases = [
            {'duration': 10, 'sample_rate': 22050},
            {'duration': 30, 'sample_rate': 22050},
            {'duration': 60, 'sample_rate': 22050},
            {'duration': 180, 'sample_rate': 22050}
        ]
        
        results = []
        for case in test_cases:
            audio_data = generate_test_audio(case['duration'], case['sample_rate'])
            
            start_time = time.time()
            fingerprints = fingerprinter.generate_fingerprints_from_data(
                audio_data, case['sample_rate']
            )
            processing_time = time.time() - start_time
            
            results.append({
                'duration': case['duration'],
                'processing_time': processing_time,
                'throughput_ratio': case['duration'] / processing_time,
                'fingerprint_count': len(fingerprints)
            })
        
        return results
    
    def benchmark_database_performance(self):
        """データベースパフォーマンスのベンチマーク"""
        backends = ['sqlite', 'mysql', 'postgresql', 'elasticsearch']
        operations = ['insert', 'search', 'update', 'delete']
        
        results = {}
        for backend in backends:
            backend_results = {}
            mimizam = create_test_mimizam(backend)
            
            for operation in operations:
                operation_time = self.measure_database_operation(mimizam, operation)
                backend_results[operation] = operation_time
            
            results[backend] = backend_results
        
        return results
    
    def generate_comprehensive_report(self):
        """包括的なレポート生成"""
        report = {
            'summary': self.generate_summary_statistics(),
            'recommendations': self.generate_optimization_recommendations(),
            'detailed_results': self.results,
            'benchmark_metadata': {
                'timestamp': time.time(),
                'system_info': self.collect_system_info(),
                'test_configurations': self.test_configurations
            }
        }
        
        return report

# ベンチマーク実行例
benchmark = PerformanceBenchmark()
comprehensive_results = benchmark.run_comprehensive_benchmark()

print("ベンチマーク結果サマリー:")
for category, results in comprehensive_results['summary'].items():
    print(f"{category}: {results}")
```

### パフォーマンス監視とプロファイリング

#### リアルタイムパフォーマンス監視

```python
def setup_performance_monitoring():
    """パフォーマンス監視の設定"""
    
    monitoring_config = {
        'metrics': [
            'fingerprint_generation_rate',
            'database_query_latency',
            'memory_usage',
            'cpu_utilization',
            'identification_accuracy'
        ],
        'collection_interval': 1.0,  # 秒
        'alert_thresholds': {
            'fingerprint_generation_rate': {'min': 500},  # 指紋/秒
            'database_query_latency': {'max': 100},       # ms
            'memory_usage': {'max': 1024},                # MB
            'identification_accuracy': {'min': 0.85}      # 85%
        }
    }
    
    return monitoring_config

def collect_runtime_metrics(mimizam, monitoring_config):
    """実行時メトリクスの収集"""
    
    metrics = {}
    
    # CPU使用率
    metrics['cpu_percent'] = psutil.cpu_percent(interval=1)
    
    # メモリ使用量
    process = psutil.Process()
    metrics['memory_mb'] = process.memory_info().rss / 1024 / 1024
    
    # 指紋生成レート（過去1分間の平均）
    metrics['fingerprint_rate'] = calculate_recent_fingerprint_rate()
    
    # データベースレスポンス時間
    metrics['db_latency'] = measure_database_latency(mimizam)
    
    # アラート判定
    alerts = check_performance_alerts(metrics, monitoring_config['alert_thresholds'])
    
    return metrics, alerts
```

## 関連ドキュメント

- [はじめに](./02_getting_started.md) - 基本的なセットアップと使用方法
- [コアアーキテクチャ](./03_core_architecture.md) - システムアーキテクチャの詳細
- [データベースバックエンド](./05_database_backends.md) - データベース設定と最適化
- [実例とチュートリアル](./06_examples_tutorials.md) - 実践的な使用例
- [テストと開発](./07_testing_development.md) - 開発環境とテスト手法
        plt.style.use('seaborn-v0_8')
        sns.set_palette("husl")
    
    def plot_processing_performance(self, audio_results):
        """音声処理性能をプロット"""
        
        fig, axes = plt.subplots(2, 2, figsize=(15, 10))
        fig.suptitle('音声処理性能分析', fontsize=16)
        
        # 1. ファイルサイズ vs 処理時間
        axes[0, 0].scatter(audio_results['file_sizes'], audio_results['generation_times'])
        axes[0, 0].set_xlabel('ファイルサイズ (MB)')
        axes[0, 0].set_ylabel('処理時間 (秒)')
        axes[0, 0].set_title('ファイルサイズ vs 処理時間')
        
        # 2. 音声時間 vs 処理時間
        axes[0, 1].scatter(audio_results['durations'], audio_results['generation_times'])
        axes[0, 1].set_xlabel('音声時間 (秒)')
        axes[0, 1].set_ylabel('処理時間 (秒)')
        axes[0, 1].set_title('音声時間 vs 処理時間')
        
        # 3. スループット分布
        axes[1, 0].hist(audio_results['throughput'], bins=10, alpha=0.7)
        axes[1, 0].set_xlabel('スループット (x リアルタイム)')
        axes[1, 0].set_ylabel('頻度')
        axes[1, 0].set_title('スループット分布')
        
        # 4. 指紋数 vs 処理時間
        axes[1, 1].scatter(audio_results['fingerprint_counts'], audio_results['generation_times'])
        axes[1, 1].set_xlabel('指紋数')
        axes[1, 1].set_ylabel('処理時間 (秒)')
        axes[1, 1].set_title('指紋数 vs 処理時間')
        
        plt.tight_layout()
        plt.savefig('audio_processing_performance.png', dpi=300, bbox_inches='tight')
        plt.show()
    
    def plot_database_scalability(self, db_results):
        """データベーススケーラビリティをプロット"""
        
        fig, axes = plt.subplots(1, 2, figsize=(12, 5))
        fig.suptitle('データベース性能分析', fontsize=16)
        
        # 1. クエリサイズ vs 検索時間
        axes[0].plot(db_results['query_sizes'], db_results['search_times'], 'o-')
        axes[0].set_xlabel('クエリサイズ')
        axes[0].set_ylabel('検索時間 (秒)')
        axes[0].set_title('スケーラビリティ')
        axes[0].grid(True, alpha=0.3)
        
        # 2. 検索効率（クエリサイズあたりの時間）
        efficiency = [time/size for time, size in zip(db_results['search_times'], db_results['query_sizes'])]
        axes[1].plot(db_results['query_sizes'], efficiency, 'o-', color='orange')
        axes[1].set_xlabel('クエリサイズ')
        axes[1].set_ylabel('効率 (秒/クエリ)')
        axes[1].set_title('検索効率')
        axes[1].grid(True, alpha=0.3)
        
        plt.tight_layout()
        plt.savefig('database_performance.png', dpi=300, bbox_inches='tight')
        plt.show()
    
    def plot_memory_timeline(self, memory_timeline):
        """メモリ使用量の時系列をプロット"""
        
        song_counts = [entry['song_count'] for entry in memory_timeline]
        memory_usage = [entry['memory_mb'] for entry in memory_timeline]
        
        plt.figure(figsize=(10, 6))
        plt.plot(song_counts, memory_usage, 'o-', linewidth=2, markersize=6)
        plt.xlabel('楽曲数')
        plt.ylabel('メモリ使用量 (MB)')
        plt.title('メモリ使用量の推移')
        plt.grid(True, alpha=0.3)
        
        # 線形トレンドを追加
        coeffs = np.polyfit(song_counts, memory_usage, 1)
        trend_line = np.poly1d(coeffs)
        plt.plot(song_counts, trend_line(song_counts), '--', alpha=0.7, 
                label=f'トレンド: {coeffs[0]:.2f} MB/楽曲')
        plt.legend()
        
        plt.tight_layout()
        plt.savefig('memory_timeline.png', dpi=300, bbox_inches='tight')
        plt.show()
    
    def plot_accuracy_analysis(self, accuracy_results, type_analysis):
        """精度分析をプロット"""
        
        fig, axes = plt.subplots(2, 2, figsize=(15, 10))
        fig.suptitle('識別精度分析', fontsize=16)
        
        # 1. 信頼度分布
        confidences = accuracy_results['confidence_scores']
        axes[0, 0].hist(confidences, bins=20, alpha=0.7, edgecolor='black')
        axes[0, 0].set_xlabel('信頼度')
        axes[0, 0].set_ylabel('頻度')
        axes[0, 0].set_title('信頼度分布')
        
        # 2. テストタイプ別精度
        test_types = list(type_analysis.keys())
        accuracies = [type_analysis[t]['accuracy'] for t in test_types]
        
        axes[0, 1].bar(test_types, accuracies, alpha=0.7)
        axes[0, 1].set_ylabel('正確度')
        axes[0, 1].set_title('テストタイプ別正確度')
        axes[0, 1].tick_params(axis='x', rotation=45)
        
        # 3. 混同行列風の結果サマリー
        correct = accuracy_results['correct_identifications']
        fp = accuracy_results['false_positives']
        fn = accuracy_results['false_negatives']
        
        categories = ['正解', '偽陽性', '偽陰性']
        values = [correct, fp, fn]
        colors = ['green', 'orange', 'red']
        
        axes[1, 0].pie(values, labels=categories, colors=colors, autopct='%1.1f%%')
        axes[1, 0].set_title('識別結果分布')
        
        # 4. テストタイプ別信頼度
        avg_confidences = [type_analysis[t]['avg_confidence'] for t in test_types]
        
        axes[1, 1].bar(test_types, avg_confidences, alpha=0.7, color='skyblue')
        axes[1, 1].set_ylabel('平均信頼度')
        axes[1, 1].set_title('テストタイプ別平均信頼度')
        axes[1, 1].tick_params(axis='x', rotation=45)
        
        plt.tight_layout()
        plt.savefig('accuracy_analysis.png', dpi=300, bbox_inches='tight')
        plt.show()

# 使用例
visualizer = PerformanceVisualizer()

# 各種グラフを生成
visualizer.plot_processing_performance(audio_results)
visualizer.plot_database_scalability(db_results)
visualizer.plot_memory_timeline(memory_timeline)
visualizer.plot_accuracy_analysis(accuracy_results, type_analysis)
```

## 総合パフォーマンスレポート

### 5. 統合レポート生成

```python
class PerformanceReporter:
    """パフォーマンスレポート生成クラス"""
    
    def __init__(self):
        self.report_data = {}
    
    def generate_comprehensive_report(self, audio_results, db_results, 
                                    memory_timeline, accuracy_results):
        """包括的なパフォーマンスレポートを生成"""
        
        report = {
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'system_info': self._get_system_info(),
            'audio_processing': self._analyze_audio_processing(audio_results),
            'database_performance': self._analyze_database_performance(db_results),
            'memory_usage': self._analyze_memory_usage(memory_timeline),
            'accuracy_metrics': self._analyze_accuracy(accuracy_results),
            'recommendations': self._generate_recommendations(
                audio_results, db_results, memory_timeline, accuracy_results
            )
        }
        
        return report
    
    def _get_system_info(self):
        """システム情報を取得"""
        import platform
        
        return {
            'platform': platform.platform(),
            'python_version': platform.python_version(),
            'cpu_count': psutil.cpu_count(),
            'memory_total_gb': psutil.virtual_memory().total / 1024**3,
            'disk_free_gb': psutil.disk_usage('/').free / 1024**3
        }
    
    def _analyze_audio_processing(self, audio_results):
        """音声処理分析"""
        if not audio_results['generation_times']:
            return {}
        
        return {
            'avg_processing_time': np.mean(audio_results['generation_times']),
            'max_processing_time': np.max(audio_results['generation_times']),
            'min_processing_time': np.min(audio_results['generation_times']),
            'avg_throughput': np.mean(audio_results['throughput']),
            'avg_fingerprints_per_file': np.mean(audio_results['fingerprint_counts']),
            'processing_efficiency': np.mean([
                count / time for count, time in 
                zip(audio_results['fingerprint_counts'], audio_results['generation_times'])
                if time > 0
            ])
        }
    
    def _analyze_database_performance(self, db_results):
        """データベース性能分析"""
        if not db_results['search_times']:
            return {}
        
        # スケーラビリティ分析
        coeffs = np.polyfit(db_results['query_sizes'], db_results['search_times'], 1)
        scalability_slope = coeffs[0]
        
        return {
            'avg_search_time': np.mean(db_results['search_times']),
            'max_search_time': np.max(db_results['search_times']),
            'min_search_time': np.min(db_results['search_times']),
            'scalability_slope': scalability_slope,
            'scalability_rating': self._rate_scalability(scalability_slope)
        }
    
    def _analyze_memory_usage(self, memory_timeline):
        """メモリ使用量分析"""
        if len(memory_timeline) < 2:
            return {}
        
        song_counts = [entry['song_count'] for entry in memory_timeline]
        memory_usage = [entry['memory_mb'] for entry in memory_timeline]
        
        # メモリ効率を計算
        coeffs = np.polyfit(song_counts, memory_usage, 1)
        memory_per_song = coeffs[0]
        
        return {
            'initial_memory': memory_usage[0],
            'final_memory': memory_usage[-1],
            'memory_per_song': memory_per_song,
            'memory_efficiency_rating': self._rate_memory_efficiency(memory_per_song)
        }
    
    def _analyze_accuracy(self, accuracy_results):
        """精度分析"""
        total = accuracy_results['total_tests']
        if total == 0:
            return {}
        
        correct = accuracy_results['correct_identifications']
        
        return {
            'accuracy': correct / total,
            'total_tests': total,
            'correct_identifications': correct,
            'false_positives': accuracy_results['false_positives'],
            'false_negatives': accuracy_results['false_negatives'],
            'avg_confidence': np.mean(accuracy_results['confidence_scores']) 
                            if accuracy_results['confidence_scores'] else 0
        }
    
    def _rate_scalability(self, slope):
        """スケーラビリティを評価"""
        if slope < 0.001:
            return "優秀"
        elif slope < 0.01:
            return "良好"
        elif slope < 0.1:
            return "普通"
        else:
            return "要改善"
    
    def _rate_memory_efficiency(self, memory_per_song):
        """メモリ効率を評価"""
        if memory_per_song < 1.0:
            return "優秀"
        elif memory_per_song < 5.0:
            return "良好"
        elif memory_per_song < 10.0:
            return "普通"
        else:
            return "要改善"
    
    def _generate_recommendations(self, audio_results, db_results, 
                                memory_timeline, accuracy_results):
        """改善提案を生成"""
        recommendations = []
        
        # 音声処理の推奨事項
        if audio_results['generation_times']:
            avg_time = np.mean(audio_results['generation_times'])
            if avg_time > 2.0:
                recommendations.append({
                    'category': '音声処理',
                    'issue': '処理時間が長い',
                    'suggestion': 'Numba JIT最適化またはパラメータ調整を検討'
                })
        
        # データベースの推奨事項
        if db_results['search_times']:
            avg_search = np.mean(db_results['search_times'])
            if avg_search > 0.1:
                recommendations.append({
                    'category': 'データベース',
                    'issue': '検索時間が長い',
                    'suggestion': 'インデックス最適化またはクエリ改善を検討'
                })
        
        # メモリの推奨事項
        if len(memory_timeline) >= 2:
            song_counts = [entry['song_count'] for entry in memory_timeline]
            memory_usage = [entry['memory_mb'] for entry in memory_timeline]
            coeffs = np.polyfit(song_counts, memory_usage, 1)
            memory_per_song = coeffs[0]
            
            if memory_per_song > 5.0:
                recommendations.append({
                    'category': 'メモリ',
                    'issue': 'メモリ使用量が多い',
                    'suggestion': 'メモリ最適化またはバッチサイズ調整を検討'
                })
        
        # 精度の推奨事項
        if accuracy_results['total_tests'] > 0:
            accuracy = accuracy_results['correct_identifications'] / accuracy_results['total_tests']
            if accuracy < 0.8:
                recommendations.append({
                    'category': '精度',
                    'issue': '識別精度が低い',
                    'suggestion': 'パラメータ調整または前処理改善を検討'
                })
        
        return recommendations
    
    def save_report(self, report, filename='performance_report.json'):
        """レポートをファイルに保存"""
        import json
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        print(f"パフォーマンスレポートを保存しました: {filename}")
    
    def print_summary(self, report):
        """レポートサマリーを表示"""
        print("=" * 60)
        print("mimizam パフォーマンス分析レポート")
        print("=" * 60)
        print(f"分析日時: {report['timestamp']}")
        print(f"システム: {report['system_info']['platform']}")
        print(f"CPU: {report['system_info']['cpu_count']}コア")
        print(f"メモリ: {report['system_info']['memory_total_gb']:.1f}GB")
        
        if 'audio_processing' in report and report['audio_processing']:
            audio = report['audio_processing']
            print(f"\n音声処理性能:")
            print(f"  平均処理時間: {audio['avg_processing_time']:.3f}秒")
            print(f"  平均スループット: {audio['avg_throughput']:.2f}x リアルタイム")
            print(f"  処理効率: {audio['processing_efficiency']:.1f} 指紋/秒")
        
        if 'database_performance' in report and report['database_performance']:
            db = report['database_performance']
            print(f"\nデータベース性能:")
            print(f"  平均検索時間: {db['avg_search_time']:.3f}秒")
            print(f"  スケーラビリティ: {db['scalability_rating']}")
        
        if 'memory_usage' in report and report['memory_usage']:
            memory = report['memory_usage']
            print(f"\nメモリ使用量:")
            print(f"  楽曲あたりメモリ: {memory['memory_per_song']:.2f}MB")
            print(f"  メモリ効率: {memory['memory_efficiency_rating']}")
        
        if 'accuracy_metrics' in report and report['accuracy_metrics']:
            accuracy = report['accuracy_metrics']
            print(f"\n識別精度:")
            print(f"  正確度: {accuracy['accuracy']:.3f}")
            print(f"  平均信頼度: {accuracy['avg_confidence']:.3f}")
        
        if 'recommendations' in report and report['recommendations']:
            print(f"\n改善提案:")
            for rec in report['recommendations']:
                print(f"  [{rec['category']}] {rec['issue']}")
                print(f"    → {rec['suggestion']}")

# 使用例
reporter = PerformanceReporter()

# 包括的レポートを生成
comprehensive_report = reporter.generate_comprehensive_report(
    audio_results, db_results, memory_timeline, accuracy_results
)

# レポートを表示・保存
reporter.print_summary(comprehensive_report)
reporter.save_report(comprehensive_report, 'mimizam_performance_report.json')
```

## まとめ

パフォーマンス分析により、mimizamシステムの性能を定量的に評価し、最適化の方向性を決定できます。

### 主要な分析手法

- **音声処理性能**: 処理時間、スループット、指紋生成効率
- **データベース性能**: 検索時間、スケーラビリティ、クエリ効率
- **メモリ使用量**: 使用パターン、リーク検出、効率性
- **識別精度**: 正確度、信頼度、テストタイプ別分析

### 可視化とレポート

- **グラフ生成**: 性能トレンド、分布、相関関係の可視化
- **統合レポート**: 包括的な性能評価と改善提案
- **継続監視**: 定期的な性能測定とトラッキング

### 最適化指針

- **ボトルネック特定**: 性能制限要因の明確化
- **改善優先度**: 効果的な最適化ポイントの特定
- **目標設定**: 具体的な性能目標の設定

## 関連ドキュメント

- [パフォーマンス最適化](./06_3_performance_optimization.md) - 高速化技術
- [テストと開発](./07_testing_development.md) - 品質保証手法
- [コアアーキテクチャ](./03_core_architecture.md) - システムの内部構造
- [データベースバックエンド](./05_database_backends.md) - データベース最適化
