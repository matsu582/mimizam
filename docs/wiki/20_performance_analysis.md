# パフォーマンス分析

mimizamシステムの詳細なパフォーマンス分析手法を解説します。ボトルネックの特定、処理時間の測定、メモリ使用量の監視、スケーラビリティの評価など、システムの性能を科学的に分析するための包括的なアプローチを提供します。

## 📊 パフォーマンス分析の概要

### 分析対象領域

```
パフォーマンス分析
├── 音声処理性能
│   ├── 指紋生成時間
│   ├── スペクトログラム計算
│   └── ピーク検出効率
├── データベース性能
│   ├── 検索応答時間
│   ├── 挿入処理速度
│   └── インデックス効率
├── メモリ使用量
│   ├── メモリリーク検出
│   ├── ガベージコレクション
│   └── キャッシュ効率
└── スケーラビリティ
    ├── 同時接続数
    ├── データ量増加対応
    └── 負荷分散効果
```

## 🔍 PerformanceAnalyzer クラス

### 基本的な使用方法

```python
from mimizam.adaptive_parameters import PerformanceMonitor
import time
import psutil
import numpy as np
from typing import Dict, List, Any
import matplotlib.pyplot as plt

def analyze_fingerprint_generation(audio_files: List[str], 
                                   fingerprinter_configs: Dict[str, Dict]) -> Dict:
    """指紋生成性能の詳細分析"""
    from mimizam import PerformanceMonitor
    
    monitor = PerformanceMonitor()
    results = {
        'configurations': {},
        'summary': {},
        'recommendations': []
    }
    
    for config_name, config in fingerprinter_configs.items():
        print(f"設定 '{config_name}' の分析開始...")
        
        config_results = analyze_single_configuration(
            audio_files, config, config_name, monitor
        )
        
        results['configurations'][config_name] = config_results
    
    # 設定間比較
    results['summary'] = compare_configurations(results['configurations'])
    results['recommendations'] = generate_recommendations(results['summary'])
    
    return results

def analyze_single_configuration(audio_files: List[str], config: dict, 
                               config_name: str, monitor) -> dict:
    """単一設定の分析"""
    from mimizam import AudioFingerprinter
    import time
    
    fingerprinter = AudioFingerprinter(**config)
    results = {
        'config_name': config_name,
        'processing_times': [],
        'fingerprint_counts': [],
        'memory_usage': []
    }
    
    for audio_file in audio_files:
        start_time = time.time()
        fingerprints = fingerprinter.fingerprint_file(audio_file)
        processing_time = time.time() - start_time
        
        results['processing_times'].append(processing_time)
        results['fingerprint_counts'].append(len(fingerprints))
        
        # メモリ使用量取得
        metrics = monitor.get_metrics()
        if 'memory_usage' in metrics:
            results['memory_usage'].append(metrics['memory_usage'])
    
    return results

def compare_configurations(configurations: dict) -> dict:
    """設定間比較"""
    import numpy as np
    
    summary = {}
    for config_name, config_results in configurations.items():
        summary[config_name] = {
            'avg_processing_time': np.mean(config_results['processing_times']),
            'avg_fingerprint_count': np.mean(config_results['fingerprint_counts']),
            'total_files_processed': len(config_results['processing_times'])
        }
    
    return summary

def generate_recommendations(summary: dict) -> list:
    """推奨事項生成"""
    recommendations = []
    
    # 最速設定を特定
    fastest_config = min(summary.keys(), 
                        key=lambda k: summary[k]['avg_processing_time'])
    recommendations.append(f"最速設定: {fastest_config}")
    
    # 最多指紋生成設定を特定
    most_fingerprints_config = max(summary.keys(),
                                  key=lambda k: summary[k]['avg_fingerprint_count'])
    recommendations.append(f"最多指紋生成設定: {most_fingerprints_config}")
    
    return recommendations
        
        return results
    
    def _analyze_single_configuration(self, audio_files: List[str], 
                                    config: Dict, config_name: str) -> Dict:
        """単一設定での性能分析"""
        
        from mimizam import AudioFingerprinter
        import librosa
        
        # 指紋生成器の作成
        fingerprinter = AudioFingerprinter(**config)
        
        metrics = {
            'processing_times': [],
            'fingerprint_counts': [],
            'memory_usage': [],
            'cpu_usage': [],
            'audio_durations': [],
            'throughput': [],
            'errors': []
        }
        
        for audio_file in audio_files:
            try:
                # システムメトリクス取得開始
                process = psutil.Process()
                start_memory = process.memory_info().rss
                start_cpu_time = process.cpu_times().user
                
                # 音声読み込み
                audio, sr = librosa.load(audio_file, sr=22050)
                audio_duration = len(audio) / sr
                
                # 指紋生成（時間測定）
                start_time = time.time()
                fingerprints = fingerprinter.fingerprint_audio(audio)
                processing_time = time.time() - start_time
                
                # システムメトリクス取得終了
                end_memory = process.memory_info().rss
                end_cpu_time = process.cpu_times().user
                
                # メトリクス記録
                metrics['processing_times'].append(processing_time)
                metrics['fingerprint_counts'].append(len(fingerprints))
                metrics['memory_usage'].append((end_memory - start_memory) / 1024 / 1024)  # MB
                metrics['cpu_usage'].append(end_cpu_time - start_cpu_time)
                metrics['audio_durations'].append(audio_duration)
                metrics['throughput'].append(audio_duration / processing_time)  # 実時間比
                
            except Exception as e:
                metrics['errors'].append(str(e))
                print(f"処理エラー {audio_file}: {e}")
        
        # 統計計算
        if metrics['processing_times']:
            stats = self._calculate_statistics(metrics)
            return {
                'config': config,
                'metrics': metrics,
                'statistics': stats,
                'error_count': len(metrics['errors'])
            }
        else:
            return {
                'config': config,
                'metrics': metrics,
                'statistics': {},
                'error_count': len(metrics['errors'])
            }
    
    def _calculate_statistics(self, metrics: Dict) -> Dict:
        """統計値計算"""
        
        stats = {}
        
        for metric_name, values in metrics.items():
            if isinstance(values, list) and values and all(isinstance(v, (int, float)) for v in values):
                values_array = np.array(values)
                stats[metric_name] = {
                    'mean': float(np.mean(values_array)),
                    'median': float(np.median(values_array)),
                    'std': float(np.std(values_array)),
                    'min': float(np.min(values_array)),
                    'max': float(np.max(values_array)),
                    'percentile_95': float(np.percentile(values_array, 95)),
                    'percentile_99': float(np.percentile(values_array, 99))
                }
        
        return stats
    
    def _compare_configurations(self, configurations: Dict) -> Dict:
        """設定間比較"""
        
        comparison = {
            'best_throughput': None,
            'best_memory_efficiency': None,
            'best_accuracy': None,
            'fastest_processing': None,
            'comparison_matrix': {}
        }
        
        # 各指標での最優秀設定を特定
        best_scores = {}
        
        for config_name, config_data in configurations.items():
            if 'statistics' in config_data and config_data['statistics']:
                stats = config_data['statistics']
                
                # スループット（実時間比）
                if 'throughput' in stats:
                    throughput_mean = stats['throughput']['mean']
                    if comparison['best_throughput'] is None or throughput_mean > best_scores.get('throughput', 0):
                        comparison['best_throughput'] = config_name
                        best_scores['throughput'] = throughput_mean
                
                # メモリ効率（少ない方が良い）
                if 'memory_usage' in stats:
                    memory_mean = stats['memory_usage']['mean']
                    if comparison['best_memory_efficiency'] is None or memory_mean < best_scores.get('memory', float('inf')):
                        comparison['best_memory_efficiency'] = config_name
                        best_scores['memory'] = memory_mean
                
                # 処理速度（少ない方が良い）
                if 'processing_times' in stats:
                    processing_mean = stats['processing_times']['mean']
                    if comparison['fastest_processing'] is None or processing_mean < best_scores.get('processing', float('inf')):
                        comparison['fastest_processing'] = config_name
                        best_scores['processing'] = processing_mean
        
        return comparison
    
    def _generate_recommendations(self, summary: Dict) -> List[str]:
        """推奨事項生成"""
        
        recommendations = []
        
        if summary['best_throughput']:
            recommendations.append(
                f"最高スループット: {summary['best_throughput']} 設定を推奨"
            )
        
        if summary['best_memory_efficiency']:
            recommendations.append(
                f"メモリ効率: {summary['best_memory_efficiency']} 設定を推奨"
            )
        
        if summary['fastest_processing']:
            recommendations.append(
                f"処理速度: {summary['fastest_processing']} 設定を推奨"
            )
        
        return recommendations

# 使用例
analyzer = PerformanceAnalyzer()

# テスト用設定
configs = {
    'default': {
        'n_fft': 2048,
        'hop_length': 512,
        'min_amplitude': -60,
        'enable_numba_optimization': False
    },
    'optimized': {
        'n_fft': 2048,
        'hop_length': 512,
        'min_amplitude': -60,
        'enable_numba_optimization': True
    },
    'high_quality': {
        'n_fft': 4096,
        'hop_length': 256,
        'min_amplitude': -70,
        'enable_numba_optimization': True
    }
}

# テスト音声ファイル
test_files = ["test1.wav", "test2.wav", "test3.wav"]

# 分析実行
results = analyzer.analyze_fingerprint_generation(test_files, configs)

# 結果表示
print("=== パフォーマンス分析結果 ===")
for config_name, config_results in results['configurations'].items():
    if 'statistics' in config_results and config_results['statistics']:
        stats = config_results['statistics']
        print(f"\n設定: {config_name}")
        
        if 'processing_times' in stats:
            print(f"  処理時間: {stats['processing_times']['mean']:.3f}秒 (±{stats['processing_times']['std']:.3f})")
        
        if 'throughput' in stats:
            print(f"  スループット: {stats['throughput']['mean']:.2f}x 実時間")
        
        if 'memory_usage' in stats:
            print(f"  メモリ使用量: {stats['memory_usage']['mean']:.1f}MB")

print(f"\n推奨事項:")
for rec in results['recommendations']:
    print(f"  - {rec}")
```

## 📈 データベース性能分析

### 検索性能分析

```python
def analyze_search_performance(mimizam_instances: Dict, 
                             query_files: List[str],
                             confidence_levels: List[float] = None) -> Dict:
    """検索性能の詳細分析"""
    
    if confidence_levels is None:
        confidence_levels = [0.1, 0.3, 0.5, 0.7, 0.9]
    
    results = {
        'backends': {},
        'confidence_analysis': {},
        'scalability_analysis': {}
    }
    
    for backend_name, mimizam in mimizam_instances.items():
        print(f"バックエンド '{backend_name}' の分析開始...")
        
        backend_results = analyze_backend_performance(
            mimizam, query_files, confidence_levels, backend_name
        )
        
        results['backends'][backend_name] = backend_results
    
    # 信頼度レベル別分析
    results['confidence_analysis'] = analyze_confidence_impact(
        results['backends'], confidence_levels
    )
    
    # スケーラビリティ分析
    results['scalability_analysis'] = analyze_scalability(
        results['backends']
    )
    
    return results

def analyze_backend_performance(mimizam_instance, query_files: List[str],
                              confidence_levels: List[float], backend_name: str) -> dict:
    """バックエンド性能分析"""
    import time
    
    results = {
        'backend_name': backend_name,
        'query_results': [],
        'performance_metrics': {}
    }
    
    total_queries = 0
    total_time = 0
    
    for query_file in query_files:
        for confidence in confidence_levels:
            start_time = time.time()
            matches = mimizam_instance.recognize_file(query_file, confidence_threshold=confidence)
            query_time = time.time() - start_time
            
            results['query_results'].append({
                'file': query_file,
                'confidence': confidence,
                'matches': len(matches) if matches else 0,
                'query_time': query_time
            })
            
            total_queries += 1
            total_time += query_time
    
    results['performance_metrics'] = {
        'avg_query_time': total_time / total_queries if total_queries > 0 else 0,
        'total_queries': total_queries,
        'queries_per_second': total_queries / total_time if total_time > 0 else 0
    }
    
    return results

def analyze_confidence_impact(backends: dict, confidence_levels: List[float]) -> dict:
    """信頼度レベル別分析"""
    confidence_analysis = {}
    
    for confidence in confidence_levels:
        confidence_analysis[confidence] = {}
        
        for backend_name, backend_results in backends.items():
            confidence_queries = [
                q for q in backend_results['query_results'] 
                if q['confidence'] == confidence
            ]
            
            if confidence_queries:
                avg_matches = sum(q['matches'] for q in confidence_queries) / len(confidence_queries)
                avg_time = sum(q['query_time'] for q in confidence_queries) / len(confidence_queries)
                
                confidence_analysis[confidence][backend_name] = {
                    'avg_matches': avg_matches,
                    'avg_query_time': avg_time
                }
    
    return confidence_analysis

def analyze_scalability(backends: dict) -> dict:
    """スケーラビリティ分析"""
    scalability_analysis = {}
    
    for backend_name, backend_results in backends.items():
        metrics = backend_results['performance_metrics']
        
        scalability_analysis[backend_name] = {
            'queries_per_second': metrics.get('queries_per_second', 0),
            'avg_query_time': metrics.get('avg_query_time', 0),
            'scalability_score': metrics.get('queries_per_second', 0) * 100  # 簡易スコア
        }
    
    return scalability_analysis
        
        return results
    
    def _analyze_backend_performance(self, mimizam, query_files: List[str], 
                                   confidence_levels: List[float], 
                                   backend_name: str) -> Dict:
        """単一バックエンドの性能分析"""
        
        metrics = {
            'search_times': [],
            'result_counts': [],
            'confidence_levels': [],
            'database_stats': None,
            'concurrent_performance': {}
        }
        
        # データベース統計取得
        try:
            songs = mimizam.list_songs()
            metrics['database_stats'] = {
                'song_count': len(songs),
                'total_fingerprints': sum(len(mimizam.database.backend.get_song_fingerprints(song.id)) 
                                        for song in songs[:10])  # サンプル10曲
            }
        except:
            metrics['database_stats'] = {'song_count': 0, 'total_fingerprints': 0}
        
        # 各信頼度レベルでの検索テスト
        for confidence in confidence_levels:
            for query_file in query_files:
                try:
                    start_time = time.time()
                    results = mimizam.search_song(query_file, min_confidence=confidence)
                    search_time = time.time() - start_time
                    
                    metrics['search_times'].append(search_time)
                    metrics['result_counts'].append(len(results))
                    metrics['confidence_levels'].append(confidence)
                    
                except Exception as e:
                    print(f"検索エラー {query_file} (信頼度{confidence}): {e}")
        
        # 同時接続性能テスト
        metrics['concurrent_performance'] = self._test_concurrent_searches(
            mimizam, query_files[0] if query_files else None
        )
        
        return metrics
    
    def _test_concurrent_searches(self, mimizam, query_file: str, 
                                max_concurrent: int = 10) -> Dict:
        """同時検索性能テスト"""
        
        if not query_file:
            return {}
        
        import threading
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        concurrent_results = {}
        
        for num_threads in [1, 2, 4, 8, max_concurrent]:
            thread_times = []
            
            def single_search():
                start_time = time.time()
                try:
                    results = mimizam.search_song(query_file, min_confidence=0.3)
                    return time.time() - start_time
                except:
                    return None
            
            # 並列検索実行
            with ThreadPoolExecutor(max_workers=num_threads) as executor:
                futures = [executor.submit(single_search) for _ in range(num_threads)]
                
                for future in as_completed(futures):
                    result = future.result()
                    if result is not None:
                        thread_times.append(result)
            
            if thread_times:
                concurrent_results[num_threads] = {
                    'mean_time': np.mean(thread_times),
                    'max_time': np.max(thread_times),
                    'min_time': np.min(thread_times),
                    'throughput': num_threads / np.mean(thread_times)
                }
        
        return concurrent_results
    
    def _analyze_confidence_impact(self, backend_results: Dict, 
                                 confidence_levels: List[float]) -> Dict:
        """信頼度レベルの影響分析"""
        
        confidence_analysis = {}
        
        for confidence in confidence_levels:
            confidence_analysis[confidence] = {}
            
            for backend_name, backend_data in backend_results.items():
                # 該当信頼度レベルのデータを抽出
                indices = [i for i, c in enumerate(backend_data['confidence_levels']) 
                          if c == confidence]
                
                if indices:
                    search_times = [backend_data['search_times'][i] for i in indices]
                    result_counts = [backend_data['result_counts'][i] for i in indices]
                    
                    confidence_analysis[confidence][backend_name] = {
                        'avg_search_time': np.mean(search_times),
                        'avg_result_count': np.mean(result_counts),
                        'search_time_std': np.std(search_times)
                    }
        
        return confidence_analysis
    
    def generate_performance_report(self, analysis_results: Dict) -> str:
        """性能分析レポート生成"""
        
        report = []
        report.append("=" * 60)
        report.append("データベース性能分析レポート")
        report.append("=" * 60)
        report.append("")
        
        # バックエンド別性能サマリー
        report.append("【バックエンド別性能サマリー】")
        for backend_name, backend_data in analysis_results['backends'].items():
            report.append(f"\n{backend_name}:")
            
            if backend_data['search_times']:
                avg_time = np.mean(backend_data['search_times'])
                report.append(f"  平均検索時間: {avg_time:.3f}秒")
                
                avg_results = np.mean(backend_data['result_counts'])
                report.append(f"  平均結果数: {avg_results:.1f}件")
            
            # データベース統計
            if backend_data['database_stats']:
                stats = backend_data['database_stats']
                report.append(f"  楽曲数: {stats['song_count']:,}件")
                report.append(f"  指紋数（推定）: {stats['total_fingerprints']:,}件")
            
            # 同時接続性能
            if backend_data['concurrent_performance']:
                report.append("  同時接続性能:")
                for threads, perf in backend_data['concurrent_performance'].items():
                    report.append(f"    {threads}スレッド: {perf['mean_time']:.3f}秒 "
                                f"(スループット: {perf['throughput']:.1f} req/sec)")
        
        # 信頼度レベル別分析
        report.append("\n【信頼度レベル別分析】")
        for confidence, conf_data in analysis_results['confidence_analysis'].items():
            report.append(f"\n信頼度 {confidence}:")
            for backend_name, backend_perf in conf_data.items():
                report.append(f"  {backend_name}: {backend_perf['avg_search_time']:.3f}秒 "
                            f"({backend_perf['avg_result_count']:.1f}件)")
        
        report.append("")
        report.append("=" * 60)
        
        return "\n".join(report)

# 使用例
db_analyzer = DatabasePerformanceAnalyzer()

# 複数バックエンドでのテスト
from mimizam import create_mimizam_sqlite, create_mimizam_mysql

mimizam_instances = {
    'SQLite': create_mimizam_sqlite('test_sqlite.db'),
    'MySQL': create_mimizam_mysql(
        host='localhost',
        database='test_mysql',
        username='test',
        password='test'
    )
}

# 分析実行
query_files = ["query1.wav", "query2.wav"]
db_results = db_analyzer.analyze_search_performance(
    mimizam_instances, 
    query_files,
    confidence_levels=[0.1, 0.3, 0.5, 0.7]
)

# レポート生成
report = db_analyzer.generate_performance_report(db_results)
print(report)
```

## 📊 可視化とレポート

### パフォーマンスグラフ生成

```python
def create_performance_dashboard(analysis_results: dict, 
                               output_dir: str = "./performance_charts") -> list:
    """パフォーマンスダッシュボード作成"""
    import matplotlib.pyplot as plt
    import os
    
    os.makedirs(output_dir, exist_ok=True)
    chart_files = []
    
    # 1. 処理時間比較チャート
    processing_chart = create_processing_time_chart(
        analysis_results, 
        os.path.join(output_dir, "processing_times.png")
    )
    chart_files.append(processing_chart)
    
    # 2. メモリ使用量チャート
    memory_chart = create_memory_usage_chart(
        analysis_results,
        os.path.join(output_dir, "memory_usage.png")
    )
    chart_files.append(memory_chart)
    
    return chart_files

def create_processing_time_chart(results: dict, output_path: str) -> str:
    """処理時間比較チャート"""
    import matplotlib.pyplot as plt
    
    plt.figure(figsize=(12, 6))
    
    config_names = []
    mean_times = []
    
    for config_name, config_data in results.get('configurations', {}).items():
        if 'processing_times' in config_data:
            config_names.append(config_name)
            mean_times.append(sum(config_data['processing_times']) / len(config_data['processing_times']))
    
    if config_names:
        bars = plt.bar(config_names, mean_times)
        plt.title('設定別処理時間比較', fontsize=14, fontweight='bold')
        plt.xlabel('設定名')
        plt.ylabel('処理時間 (秒)')
        plt.xticks(rotation=45)
        
        # 値をバーの上に表示
        for bar, mean_time in zip(bars, mean_times):
            plt.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.01,
                    f'{mean_time:.3f}s', ha='center', va='bottom')
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()
    
    return output_path

def create_memory_usage_chart(results: dict, output_path: str) -> str:
    """メモリ使用量チャート"""
    import matplotlib.pyplot as plt
    
    plt.figure(figsize=(12, 6))
    
    config_names = []
    memory_usage = []
    
    for config_name, config_data in results.get('configurations', {}).items():
        if 'memory_usage' in config_data:
            config_names.append(config_name)
            memory_usage.append(sum(config_data['memory_usage']) / len(config_data['memory_usage']))
    
    if config_names:
        bars = plt.bar(config_names, memory_usage, color='lightcoral')
        plt.title('設定別メモリ使用量比較', fontsize=14, fontweight='bold')
        plt.xlabel('設定名')
        plt.ylabel('メモリ使用量 (MB)')
        plt.xticks(rotation=45)
        
        # 値をバーの上に表示
        for bar, memory in zip(bars, memory_usage):
            plt.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
                    f'{memory:.1f}MB', ha='center', va='bottom')
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()
    
    return output_path

# 使用例
chart_files = create_performance_dashboard(results)

print("生成されたチャート:")
for chart_file in chart_files:
    print(f"  - {chart_file}")
```

## 🔗 関連ドキュメント

- [パフォーマンス最適化](./12_performance_optimization.md) - 最適化手法
- [適応パラメータ調整](./15_adaptive_parameters.md) - パラメータ調整
- [パフォーマンステスト](./23_performance_testing.md) - テスト手法
- [デバッグとトラブルシューティング](./21_debugging.md) - 問題解決
- [品質保証](./24_quality_assurance.md) - 品質管理

## 💡 分析のベストプラクティス

### 1. 測定の信頼性
- 複数回の測定による平均化
- 外部要因の排除
- 一貫した測定環境

### 2. 包括的な分析
- 複数の指標による評価
- 異なる条件での測定
- 長期的な傾向の監視

### 3. 実用的な改善
- ボトルネックの特定
- 実装可能な最適化案
- 効果の定量的評価

パフォーマンス分析により、mimizamシステムの性能を科学的に評価し、継続的な改善を実現できます。
