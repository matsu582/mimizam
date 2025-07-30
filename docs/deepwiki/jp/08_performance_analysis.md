# パフォーマンス分析

> 関連するソースファイル

このドキュメントでは、mimizamシステムのパフォーマンス分析手法、測定ツール、最適化指標について説明します。システムの性能を定量的に評価し、ボトルネックを特定するための実用的な手法を提供します。

## 概要

パフォーマンス分析は、mimizamシステムの効率性と拡張性を評価するための重要なプロセスです。適切な分析により、システムの弱点を特定し、最適化の方向性を決定できます。

## 主要な性能指標

### 1. 音声処理性能

```python
import time
import numpy as np
from mimizam import create_mimizam_sqlite
import matplotlib.pyplot as plt

class AudioProcessingAnalyzer:
    """音声処理性能分析クラス"""
    
    def __init__(self, mimizam):
        self.mimizam = mimizam
        self.metrics = []
    
    def analyze_fingerprint_generation(self, audio_files):
        """指紋生成性能を分析"""
        
        results = {
            'file_sizes': [],
            'durations': [],
            'generation_times': [],
            'fingerprint_counts': [],
            'throughput': []
        }
        
        for audio_file in audio_files:
            try:
                # ファイル情報を取得
                import librosa
                import os
                
                file_size = os.path.getsize(audio_file) / 1024 / 1024  # MB
                duration = librosa.get_duration(filename=audio_file)
                
                # 指紋生成時間を測定
                start_time = time.time()
                fingerprints = self.mimizam.fingerprinter.generate_fingerprints(audio_file)
                generation_time = time.time() - start_time
                
                # スループットを計算（秒あたりの処理時間）
                throughput = duration / generation_time if generation_time > 0 else 0
                
                # 結果を記録
                results['file_sizes'].append(file_size)
                results['durations'].append(duration)
                results['generation_times'].append(generation_time)
                results['fingerprint_counts'].append(len(fingerprints))
                results['throughput'].append(throughput)
                
                print(f"ファイル: {os.path.basename(audio_file)}")
                print(f"  サイズ: {file_size:.2f}MB, 時間: {duration:.1f}秒")
                print(f"  処理時間: {generation_time:.3f}秒, 指紋数: {len(fingerprints)}")
                print(f"  スループット: {throughput:.2f}x リアルタイム")
                
            except Exception as e:
                print(f"エラー {audio_file}: {e}")
        
        return results
    
    def analyze_database_performance(self, query_sizes=[10, 50, 100, 500, 1000]):
        """データベース性能を分析"""
        
        results = {
            'query_sizes': [],
            'search_times': [],
            'result_counts': []
        }
        
        for query_size in query_sizes:
            # ランダムハッシュを生成
            query_hashes = [
                {'hash': np.random.randint(0, 2**32), 'time_offset': float(i)}
                for i in range(query_size)
            ]
            
            # 検索時間を測定
            start_time = time.time()
            matches = self.mimizam.database.search_fingerprints(query_hashes)
            search_time = time.time() - start_time
            
            # 結果数を計算
            total_results = sum(len(song_matches) for song_matches in matches.values())
            
            results['query_sizes'].append(query_size)
            results['search_times'].append(search_time)
            results['result_counts'].append(total_results)
            
            print(f"クエリサイズ: {query_size}, 検索時間: {search_time:.3f}秒, 結果数: {total_results}")
        
        return results
    
    def generate_performance_report(self, audio_results, db_results):
        """パフォーマンスレポートを生成"""
        
        report = {
            'audio_processing': {
                'avg_generation_time': np.mean(audio_results['generation_times']),
                'avg_throughput': np.mean(audio_results['throughput']),
                'avg_fingerprints_per_second': np.mean([
                    count / time for count, time in 
                    zip(audio_results['fingerprint_counts'], audio_results['generation_times'])
                    if time > 0
                ])
            },
            'database_performance': {
                'avg_search_time': np.mean(db_results['search_times']),
                'search_scalability': self._calculate_scalability(
                    db_results['query_sizes'], 
                    db_results['search_times']
                )
            }
        }
        
        return report
    
    def _calculate_scalability(self, sizes, times):
        """スケーラビリティを計算"""
        if len(sizes) < 2:
            return 0
        
        # 線形回帰で傾きを計算
        coeffs = np.polyfit(sizes, times, 1)
        return coeffs[0]  # 傾き（サイズあたりの時間増加）

# 使用例
mimizam = create_mimizam_sqlite("performance_test.db")
analyzer = AudioProcessingAnalyzer(mimizam)

# 音声処理性能を分析
audio_files = ["test1.wav", "test2.wav", "test3.wav"]
audio_results = analyzer.analyze_fingerprint_generation(audio_files)

# データベース性能を分析
db_results = analyzer.analyze_database_performance()

# レポートを生成
report = analyzer.generate_performance_report(audio_results, db_results)
print(f"\nパフォーマンスレポート:")
print(f"平均指紋生成時間: {report['audio_processing']['avg_generation_time']:.3f}秒")
print(f"平均スループット: {report['audio_processing']['avg_throughput']:.2f}x")
print(f"平均検索時間: {report['database_performance']['avg_search_time']:.3f}秒")
```

### 2. メモリ使用量分析

```python
import psutil
import os
import gc
from contextlib import contextmanager

class MemoryAnalyzer:
    """メモリ使用量分析クラス"""
    
    def __init__(self):
        self.process = psutil.Process(os.getpid())
        self.baseline_memory = None
    
    @contextmanager
    def memory_profiler(self, operation_name):
        """メモリプロファイリングコンテキスト"""
        
        # 開始前のメモリ状態
        gc.collect()  # ガベージコレクション
        start_memory = self.process.memory_info()
        
        print(f"{operation_name} 開始時メモリ: {start_memory.rss / 1024 / 1024:.1f}MB")
        
        try:
            yield self
        finally:
            # 終了後のメモリ状態
            gc.collect()
            end_memory = self.process.memory_info()
            
            memory_diff = (end_memory.rss - start_memory.rss) / 1024 / 1024
            
            print(f"{operation_name} 終了時メモリ: {end_memory.rss / 1024 / 1024:.1f}MB")
            print(f"メモリ増加量: {memory_diff:+.1f}MB")
    
    def analyze_memory_usage_pattern(self, mimizam, audio_files):
        """メモリ使用パターンを分析"""
        
        memory_timeline = []
        
        for i, audio_file in enumerate(audio_files):
            with self.memory_profiler(f"楽曲 {i+1} 処理"):
                try:
                    # 楽曲を追加
                    song_id = mimizam.add_song(audio_file, song_name=f"Test Song {i+1}")
                    
                    # メモリ状態を記録
                    current_memory = self.process.memory_info().rss / 1024 / 1024
                    memory_timeline.append({
                        'song_count': i + 1,
                        'memory_mb': current_memory,
                        'song_id': song_id
                    })
                    
                except Exception as e:
                    print(f"エラー: {e}")
        
        return memory_timeline
    
    def detect_memory_leaks(self, memory_timeline):
        """メモリリークを検出"""
        
        if len(memory_timeline) < 3:
            return {"leak_detected": False, "message": "データ不足"}
        
        # メモリ使用量の傾向を分析
        song_counts = [entry['song_count'] for entry in memory_timeline]
        memory_usage = [entry['memory_mb'] for entry in memory_timeline]
        
        # 線形回帰で傾きを計算
        coeffs = np.polyfit(song_counts, memory_usage, 1)
        slope = coeffs[0]  # MB per song
        
        # メモリリークの判定（楽曲あたり5MB以上の増加）
        leak_threshold = 5.0
        leak_detected = slope > leak_threshold
        
        return {
            "leak_detected": leak_detected,
            "memory_per_song": slope,
            "threshold": leak_threshold,
            "message": f"楽曲あたり{slope:.2f}MBのメモリ増加" + 
                      (" - リーク疑い" if leak_detected else " - 正常範囲")
        }

# 使用例
memory_analyzer = MemoryAnalyzer()

# メモリ使用パターンを分析
audio_files = ["test1.wav", "test2.wav", "test3.wav", "test4.wav", "test5.wav"]
memory_timeline = memory_analyzer.analyze_memory_usage_pattern(mimizam, audio_files)

# メモリリークを検出
leak_analysis = memory_analyzer.detect_memory_leaks(memory_timeline)
print(f"\nメモリリーク分析: {leak_analysis['message']}")
```

### 3. 識別精度分析

```python
class AccuracyAnalyzer:
    """識別精度分析クラス"""
    
    def __init__(self, mimizam):
        self.mimizam = mimizam
    
    def analyze_identification_accuracy(self, test_dataset):
        """識別精度を分析"""
        
        results = {
            'total_tests': 0,
            'correct_identifications': 0,
            'false_positives': 0,
            'false_negatives': 0,
            'confidence_scores': [],
            'detailed_results': []
        }
        
        for test_case in test_dataset:
            audio_file = test_case['audio_file']
            expected_song_id = test_case['expected_song_id']
            test_type = test_case.get('type', 'full')  # full, partial, noisy
            
            try:
                # 音声識別を実行
                matches = self.mimizam.identify(audio_file)
                
                results['total_tests'] += 1
                
                if matches:
                    best_match = matches[0]
                    predicted_song_id = best_match['song_id']
                    confidence = best_match['confidence']
                    
                    results['confidence_scores'].append(confidence)
                    
                    # 正解判定
                    if predicted_song_id == expected_song_id:
                        results['correct_identifications'] += 1
                        result_type = 'correct'
                    else:
                        results['false_positives'] += 1
                        result_type = 'false_positive'
                else:
                    # マッチなし
                    if expected_song_id is None:
                        results['correct_identifications'] += 1
                        result_type = 'correct_no_match'
                        confidence = 0.0
                    else:
                        results['false_negatives'] += 1
                        result_type = 'false_negative'
                        confidence = 0.0
                
                # 詳細結果を記録
                results['detailed_results'].append({
                    'audio_file': audio_file,
                    'test_type': test_type,
                    'expected_song_id': expected_song_id,
                    'predicted_song_id': matches[0]['song_id'] if matches else None,
                    'confidence': confidence,
                    'result_type': result_type
                })
                
                print(f"テスト: {os.path.basename(audio_file)} ({test_type})")
                print(f"  期待: {expected_song_id}, 予測: {matches[0]['song_id'] if matches else None}")
                print(f"  信頼度: {confidence:.3f}, 結果: {result_type}")
                
            except Exception as e:
                print(f"テストエラー {audio_file}: {e}")
        
        return results
    
    def calculate_metrics(self, results):
        """精度メトリクスを計算"""
        
        total = results['total_tests']
        correct = results['correct_identifications']
        fp = results['false_positives']
        fn = results['false_negatives']
        
        if total == 0:
            return {}
        
        # 基本メトリクス
        accuracy = correct / total
        precision = correct / (correct + fp) if (correct + fp) > 0 else 0
        recall = correct / (correct + fn) if (correct + fn) > 0 else 0
        f1_score = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
        
        # 信頼度統計
        confidence_scores = results['confidence_scores']
        avg_confidence = np.mean(confidence_scores) if confidence_scores else 0
        confidence_std = np.std(confidence_scores) if confidence_scores else 0
        
        return {
            'accuracy': accuracy,
            'precision': precision,
            'recall': recall,
            'f1_score': f1_score,
            'avg_confidence': avg_confidence,
            'confidence_std': confidence_std,
            'total_tests': total,
            'correct': correct,
            'false_positives': fp,
            'false_negatives': fn
        }
    
    def analyze_by_test_type(self, results):
        """テストタイプ別の分析"""
        
        type_analysis = {}
        
        for result in results['detailed_results']:
            test_type = result['test_type']
            
            if test_type not in type_analysis:
                type_analysis[test_type] = {
                    'total': 0,
                    'correct': 0,
                    'confidences': []
                }
            
            type_analysis[test_type]['total'] += 1
            
            if result['result_type'] == 'correct':
                type_analysis[test_type]['correct'] += 1
            
            type_analysis[test_type]['confidences'].append(result['confidence'])
        
        # 各タイプの精度を計算
        for test_type, data in type_analysis.items():
            data['accuracy'] = data['correct'] / data['total'] if data['total'] > 0 else 0
            data['avg_confidence'] = np.mean(data['confidences']) if data['confidences'] else 0
        
        return type_analysis

# 使用例
accuracy_analyzer = AccuracyAnalyzer(mimizam)

# テストデータセットを準備
test_dataset = [
    {'audio_file': 'test_full_1.wav', 'expected_song_id': 1, 'type': 'full'},
    {'audio_file': 'test_partial_1.wav', 'expected_song_id': 1, 'type': 'partial'},
    {'audio_file': 'test_noisy_1.wav', 'expected_song_id': 1, 'type': 'noisy'},
    {'audio_file': 'test_unknown.wav', 'expected_song_id': None, 'type': 'unknown'}
]

# 識別精度を分析
accuracy_results = accuracy_analyzer.analyze_identification_accuracy(test_dataset)

# メトリクスを計算
metrics = accuracy_analyzer.calculate_metrics(accuracy_results)
print(f"\n精度メトリクス:")
print(f"  正確度: {metrics['accuracy']:.3f}")
print(f"  適合率: {metrics['precision']:.3f}")
print(f"  再現率: {metrics['recall']:.3f}")
print(f"  F1スコア: {metrics['f1_score']:.3f}")
print(f"  平均信頼度: {metrics['avg_confidence']:.3f}")

# テストタイプ別分析
type_analysis = accuracy_analyzer.analyze_by_test_type(accuracy_results)
for test_type, data in type_analysis.items():
    print(f"\n{test_type}テスト:")
    print(f"  正確度: {data['accuracy']:.3f}")
    print(f"  平均信頼度: {data['avg_confidence']:.3f}")
```

## 可視化とレポート

### 4. パフォーマンス可視化

```python
import matplotlib.pyplot as plt
import seaborn as sns

class PerformanceVisualizer:
    """パフォーマンス可視化クラス"""
    
    def __init__(self):
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
