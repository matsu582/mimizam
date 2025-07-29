# パフォーマンステスト

mimizamシステムの性能を定量的に評価するための包括的なパフォーマンステスト手法を解説します。処理速度、メモリ使用量、スケーラビリティ、負荷耐性など、様々な観点からシステムの性能を測定・評価する方法を提供します。

## 🚀 パフォーマンステストの概要

### テスト分類

```
パフォーマンステスト
├── 処理速度テスト
│   ├── 指紋生成速度
│   ├── 検索応答時間
│   └── バッチ処理性能
├── メモリ使用量テスト
│   ├── メモリリーク検出
│   ├── ピークメモリ測定
│   └── ガベージコレクション効率
├── スケーラビリティテスト
│   ├── データ量増加対応
│   ├── 同時接続数対応
│   └── 分散処理性能
└── 負荷テスト
    ├── 高負荷耐性
    ├── ストレステスト
    └── 長時間稼働テスト
```

## ⚡ 処理速度テスト

### 指紋生成性能テスト

```python
import time
import numpy as np
import matplotlib.pyplot as plt
from typing import Dict, List, Tuple
import psutil
import gc

def test_fingerprint_generation_speed(audio_durations: list = None,
                                    configurations: dict = None) -> dict:
        """指紋生成速度テスト"""
        
        if audio_durations is None:
            audio_durations = [1, 5, 10, 30, 60, 120]  # 秒
        
        if configurations is None:
            configurations = {
                'default': {
                    'n_fft': 2048,
                    'hop_length': 512,
                    'enable_numba_optimization': False
                },
                'optimized': {
                    'n_fft': 2048,
                    'hop_length': 512,
                    'enable_numba_optimization': True
                },
                'high_quality': {
                    'n_fft': 4096,
                    'hop_length': 256,
                    'enable_numba_optimization': True
                }
            }
        
        results = {}
        
        for config_name, config in configurations.items():
            print(f"設定 '{config_name}' のテスト実行中...")
            
            config_results = {
                'durations': [],
                'processing_times': [],
                'throughput_ratios': [],
                'fingerprint_counts': [],
                'memory_usage': []
            }
            
            from mimizam import AudioFingerprinter
            fingerprinter = AudioFingerprinter(**config)
            
            for duration in audio_durations:
                # テスト音声生成
                audio = self._generate_test_audio(duration)
                
                # メモリ使用量測定開始
                process = psutil.Process()
                initial_memory = process.memory_info().rss / 1024 / 1024  # MB
                
                # 処理時間測定
                start_time = time.time()
                fingerprints = fingerprinter.fingerprint_audio(audio)
                processing_time = time.time() - start_time
                
                # メモリ使用量測定終了
                final_memory = process.memory_info().rss / 1024 / 1024  # MB
                memory_increase = final_memory - initial_memory
                
                # 結果記録
                throughput_ratio = duration / processing_time
                
                config_results['durations'].append(duration)
                config_results['processing_times'].append(processing_time)
                config_results['throughput_ratios'].append(throughput_ratio)
                config_results['fingerprint_counts'].append(len(fingerprints))
                config_results['memory_usage'].append(memory_increase)
                
                print(f"  {duration}秒音声: {processing_time:.3f}秒 "
                      f"({throughput_ratio:.2f}x実時間, "
                      f"{len(fingerprints)}指紋, "
                      f"{memory_increase:.1f}MB)")
                
                # メモリクリーンアップ
                del audio, fingerprints
                gc.collect()
            
            results[config_name] = config_results
        
        return results
    
def generate_test_audio(duration: int) -> np.ndarray:
        """テスト音声生成"""
        
        sample_rate = 22050
        samples = sample_rate * duration
        
        # 複合波形生成（より現実的な音声に近い）
        t = np.linspace(0, duration, samples)
        
        # 基本周波数 + 倍音 + ノイズ
        audio = (
            np.sin(2 * np.pi * 440 * t) +           # A4
            0.5 * np.sin(2 * np.pi * 880 * t) +     # A5
            0.25 * np.sin(2 * np.pi * 1320 * t) +   # E6
            0.1 * np.random.randn(samples)          # ノイズ
        )
        
        # 振幅正規化
        audio = audio / np.max(np.abs(audio)) * 0.8
        
        return audio

# 使用例
# 指紋生成速度テスト
fingerprint_results = test_fingerprint_generation_speed()

print("パフォーマンステスト完了")
```

## 📊 メモリ使用量テスト

### メモリリーク検出

```python
def test_memory_leak(test_function,
                    iterations: int = 100,
                    snapshot_interval: int = 10) -> dict:
        """メモリリークテスト"""
        
        import gc
        import tracemalloc
        
        # メモリトレース開始
        tracemalloc.start()
        
        results = {
            'iterations': [],
            'memory_usage_mb': [],
            'memory_growth_mb': [],
            'leak_detected': False,
            'leak_rate_mb_per_iteration': 0
        }
        
        process = psutil.Process()
        initial_memory = process.memory_info().rss / 1024 / 1024
        
        print(f"メモリリークテスト開始 (初期メモリ: {initial_memory:.1f} MB)")
        
        for i in range(iterations):
            # テスト関数実行
            test_function()
            
            # 定期的にメモリ使用量を記録
            if i % snapshot_interval == 0:
                # ガベージコレクション実行
                gc.collect()
                
                current_memory = process.memory_info().rss / 1024 / 1024
                memory_growth = current_memory - initial_memory
                
                results['iterations'].append(i)
                results['memory_usage_mb'].append(current_memory)
                results['memory_growth_mb'].append(memory_growth)
                
                print(f"  反復 {i}: {current_memory:.1f} MB (+{memory_growth:.1f} MB)")
        
        # 最終メモリ使用量
        final_memory = process.memory_info().rss / 1024 / 1024
        total_growth = final_memory - initial_memory
        
        # リーク検出判定
        if len(results['memory_growth_mb']) > 2:
            # 線形回帰でメモリ増加率を計算
            iterations_array = np.array(results['iterations'])
            memory_array = np.array(results['memory_growth_mb'])
            
            # 最小二乗法で傾きを計算
            slope = np.polyfit(iterations_array, memory_array, 1)[0]
            leak_rate = slope * snapshot_interval  # 反復あたりのリーク率
            
            results['leak_rate_mb_per_iteration'] = leak_rate
            
            # リーク判定（反復あたり0.1MB以上の増加）
            if leak_rate > 0.1:
                results['leak_detected'] = True
                print(f"⚠️  メモリリーク検出: {leak_rate:.3f} MB/iteration")
            else:
                print(f"✅ メモリリークなし (増加率: {leak_rate:.3f} MB/iteration)")
        
        # メモリトレース終了
        tracemalloc.stop()
        
        results['total_growth_mb'] = total_growth
        results['final_memory_mb'] = final_memory
        
        return results

# 使用例
def fingerprint_test():
    """指紋生成テスト関数"""
    from mimizam import AudioFingerprinter
    fingerprinter = AudioFingerprinter()
    
    # ランダム音声生成
    audio = np.random.randn(22050 * 5)  # 5秒
    
    # 指紋生成
    fingerprints = fingerprinter.fingerprint_audio(audio)
    
    # 明示的な削除
    del fingerprints, audio, fingerprinter

# メモリリークテスト実行
leak_results = test_memory_leak(fingerprint_test, iterations=200, snapshot_interval=20)

print("=== メモリリークテスト結果 ===")
print(f"リーク検出: {'あり' if leak_results['leak_detected'] else 'なし'}")
print(f"総メモリ増加: {leak_results['total_growth_mb']:.1f} MB")
```

## 🔗 関連ドキュメント

- [パフォーマンス最適化](./12_performance_optimization.md) - 最適化手法
- [パフォーマンス分析](./20_performance_analysis.md) - 詳細分析
- [テスト](./22_testing.md) - テスト手法
- [デバッグとトラブルシューティング](./21_debugging.md) - 問題解決
- [品質保証](./24_quality_assurance.md) - 品質管理

## 💡 パフォーマンステストのベストプラクティス

### 1. 測定の信頼性
- 複数回の測定による平均化
- 外部要因の排除
- 一貫した測定環境

### 2. 包括的なテスト
- 複数の指標による評価
- 異なる条件での測定
- 長期的な傾向の監視

### 3. 実用的な改善
- ボトルネックの特定
- 実装可能な最適化案
- 効果の定量的評価

mimizamシステムの性能を継続的に監視・改善するため、これらのパフォーマンステスト手法を活用してください。
