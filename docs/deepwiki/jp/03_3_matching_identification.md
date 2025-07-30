# マッチング・識別システム

> 関連するソースファイル

このドキュメントでは、クエリ音声の指紋をデータベース内の既知の楽曲と照合し、最適なマッチを特定するマッチング・識別システムについて説明します。システムは、ハッシュマッチング、時間オフセット分析、複数のスコアリング手法、結果ランキングを組み合わせて高精度な識別を実現します。

他のコンポーネントについては、[音声指紋エンジン](./03_1_audio_fingerprinting_engine.md)および[データベース層](./03_2_database_layer.md)を参照してください。

## 概要

マッチング・識別システムは、クエリ音声から生成された指紋をデータベース内の指紋と照合し、最も可能性の高い楽曲を特定します。システムは、ハッシュマッチング、時間オフセット分析、複数のスコアリング手法、結果ランキングを組み合わせて高精度な識別を実現します。

### マッチングアーキテクチャ

| コンポーネント | 機能 | 技術的特徴 |
|---------------|------|-----------|
| **ハッシュマッチング** | 指紋ハッシュの高速検索 | インデックス最適化、並列処理 |
| **時間オフセット分析** | 時間的一貫性の評価 | 統計的分析、外れ値除去 |
| **スコアリングシステム** | 複数手法による信頼度計算 | 重み付き、統計的、適応的手法 |
| **結果ランキング** | 最適マッチの特定と順位付け | 閾値調整、品質フィルタリング |

## 識別プロセス

### 処理フロー

```
クエリ音声指紋
    │
    ▼
データベース検索（並列処理）
    │
    ▼
ハッシュマッチング（インデックス最適化）
    │
    ▼
時間オフセット分析（統計的評価）
    │
    ▼
スコアリング（複数手法統合）
    │
    ▼
結果ランキング（適応的閾値）
    │
    ▼
識別結果（信頼度付き）
```

### 処理段階の詳細

| 段階 | 処理内容 | パフォーマンス指標 |
|------|---------|------------------|
| **データベース検索** | ハッシュ値による高速検索 | ~1ms/1000指紋 |
| **時間オフセット分析** | 時間的一貫性の統計的評価 | ~5ms/楽曲候補 |
| **スコアリング** | 複数手法による信頼度計算 | ~2ms/楽曲候補 |
| **結果ランキング** | 最終順位付けとフィルタリング | ~1ms/結果セット |

## 主要コンポーネント

### MatchingEngineクラス

マッチング処理の中核を担うクラスです。

```python
class MatchingEngine:
    """音声マッチング・識別エンジン"""
    
    def __init__(self, database, scoring_method='weighted'):
        self.database = database
        self.scoring_method = scoring_method
        self.match_threshold = 0.1
        self.max_matches = 10
    
    def identify_audio(self, query_fingerprints):
        """音声を識別"""
        # 1. データベース検索
        raw_matches = self.database.search_fingerprints(query_fingerprints)
        
        # 2. 時間オフセット分析
        analyzed_matches = self._analyze_time_offsets(raw_matches, query_fingerprints)
        
        # 3. スコアリング
        scored_matches = self._score_matches(analyzed_matches)
        
        # 4. 結果フィルタリングとランキング
        final_results = self._rank_and_filter_results(scored_matches)
        
        return final_results
```

### 時間オフセット分析

```python
def _analyze_time_offsets(self, raw_matches, query_fingerprints):
    """時間オフセットを分析してマッチの質を評価"""
    analyzed_matches = {}
    
    # クエリ指紋をハッシュでインデックス化
    query_hash_map = {fp['hash']: fp['time_offset'] for fp in query_fingerprints}
    
    for song_id, db_matches in raw_matches.items():
        time_pairs = []
        
        for db_match in db_matches:
            hash_value = db_match['hash']
            if hash_value in query_hash_map:
                query_time = query_hash_map[hash_value]
                db_time = db_match['db_time']
                time_pairs.append({
                    'query_time': query_time,
                    'db_time': db_time,
                    'time_diff': db_time - query_time
                })
        
        if time_pairs:
            analyzed_matches[song_id] = {
                'time_pairs': time_pairs,
                'match_count': len(time_pairs)
            }
    
    return analyzed_matches
```

## スコアリング手法

### 基本スコアリング

```python
def _basic_scoring(self, matches):
    """基本的なマッチ数ベースのスコアリング"""
    scored_results = []
    
    for song_id, match_data in matches.items():
        score = match_data['match_count']
        
        scored_results.append({
            'song_id': song_id,
            'score': score,
            'match_count': match_data['match_count'],
            'method': 'basic'
        })
    
    return scored_results
```

### 重み付きスコアリング

```python
def _weighted_scoring(self, matches):
    """時間一貫性を考慮した重み付きスコアリング"""
    scored_results = []
    
    for song_id, match_data in matches.items():
        time_pairs = match_data['time_pairs']
        
        if len(time_pairs) < 2:
            score = len(time_pairs)
            consistency_weight = 1.0
        else:
            # 時間差の一貫性を評価
            time_diffs = [pair['time_diff'] for pair in time_pairs]
            
            # 最頻時間差を特定
            time_diff_mode = self._find_mode(time_diffs)
            
            # 一貫性スコアを計算
            consistent_matches = sum(1 for diff in time_diffs 
                                   if abs(diff - time_diff_mode) < 5.0)
            
            # 重み付きスコア
            consistency_weight = consistent_matches / len(time_pairs)
            score = len(time_pairs) * consistency_weight
        
        scored_results.append({
            'song_id': song_id,
            'score': score,
            'match_count': match_data['match_count'],
            'consistency': consistency_weight,
            'method': 'weighted'
        })
    
    return scored_results

def _find_mode(self, values, tolerance=2.0):
    """値のリストから最頻値を特定"""
    if not values:
        return 0
    
    # ヒストグラムを作成
    histogram = {}
    for value in values:
        # 許容範囲内の既存のキーを検索
        found_key = None
        for key in histogram:
            if abs(value - key) <= tolerance:
                found_key = key
                break
        
        if found_key is not None:
            histogram[found_key] += 1
        else:
            histogram[value] = 1
    
    # 最頻値を返す
    return max(histogram, key=histogram.get)
```

### 統計的スコアリング

```python
def _statistical_scoring(self, matches):
    """統計的手法による高度なスコアリング"""
    import numpy as np
    scored_results = []
    
    for song_id, match_data in matches.items():
        time_pairs = match_data['time_pairs']
        
        if len(time_pairs) < 3:
            score = len(time_pairs)
            confidence = 0.5
        else:
            time_diffs = [pair['time_diff'] for pair in time_pairs]
            
            # 統計的分析
            mean_diff = np.mean(time_diffs)
            std_diff = np.std(time_diffs)
            
            # 外れ値を除去
            filtered_diffs = [diff for diff in time_diffs 
                            if abs(diff - mean_diff) <= 2 * std_diff]
            
            # 信頼度計算
            confidence = len(filtered_diffs) / len(time_diffs)
            
            # スコア計算
            score = len(filtered_diffs) * confidence * (1 / (std_diff + 1))
        
        scored_results.append({
            'song_id': song_id,
            'score': score,
            'match_count': match_data['match_count'],
            'confidence': confidence,
            'method': 'statistical'
        })
    
    return scored_results
```

## 結果ランキングとフィルタリング

```python
def _rank_and_filter_results(self, scored_matches):
    """結果をランキングしてフィルタリング"""
    # スコアでソート
    sorted_matches = sorted(scored_matches, key=lambda x: x['score'], reverse=True)
    
    # 閾値でフィルタリング
    filtered_matches = [match for match in sorted_matches 
                       if match['score'] >= self.match_threshold]
    
    # 最大件数で制限
    final_matches = filtered_matches[:self.max_matches]
    
    # 楽曲情報を追加
    enriched_matches = []
    for match in final_matches:
        song_info = self.database.get_song_info(match['song_id'])
        
        enriched_match = {
            'song_id': match['song_id'],
            'song_name': song_info.get('name', 'Unknown'),
            'artist': song_info.get('artist'),
            'album': song_info.get('album'),
            'score': match['score'],
            'match_count': match['match_count'],
            'confidence': match.get('confidence', 1.0),
            'method': match['method']
        }
        
        enriched_matches.append(enriched_match)
    
    return enriched_matches
```

## 高度なマッチング技術

### 時間窓マッチング

```python
def _windowed_matching(self, query_fingerprints, window_size=10.0):
    """時間窓を使用したマッチング"""
    windowed_results = []
    
    # クエリを時間窓に分割
    max_time = max(fp['time_offset'] for fp in query_fingerprints)
    num_windows = int(max_time / window_size) + 1
    
    for i in range(num_windows):
        start_time = i * window_size
        end_time = (i + 1) * window_size
        
        # 窓内の指紋を抽出
        window_fingerprints = [fp for fp in query_fingerprints 
                             if start_time <= fp['time_offset'] < end_time]
        
        if window_fingerprints:
            # 窓内でマッチング
            window_matches = self.identify_audio(window_fingerprints)
            
            # 結果に窓情報を追加
            for match in window_matches:
                match['window_start'] = start_time
                match['window_end'] = end_time
                windowed_results.append(match)
    
    # 窓間での結果統合
    consolidated_results = self._consolidate_windowed_results(windowed_results)
    
    return consolidated_results

def _consolidate_windowed_results(self, windowed_results):
    """窓間の結果を統合"""
    song_scores = {}
    
    for result in windowed_results:
        song_id = result['song_id']
        
        if song_id not in song_scores:
            song_scores[song_id] = {
                'total_score': 0,
                'window_count': 0,
                'song_info': {
                    'song_name': result['song_name'],
                    'artist': result['artist'],
                    'album': result['album']
                }
            }
        
        song_scores[song_id]['total_score'] += result['score']
        song_scores[song_id]['window_count'] += 1
    
    # 平均スコアで最終結果を作成
    final_results = []
    for song_id, data in song_scores.items():
        avg_score = data['total_score'] / data['window_count']
        
        final_results.append({
            'song_id': song_id,
            'song_name': data['song_info']['song_name'],
            'artist': data['song_info']['artist'],
            'album': data['song_info']['album'],
            'score': avg_score,
            'window_count': data['window_count'],
            'method': 'windowed'
        })
    
    return sorted(final_results, key=lambda x: x['score'], reverse=True)
```

### 適応的閾値調整

```python
class AdaptiveThreshold:
    """適応的閾値調整"""
    
    def __init__(self, initial_threshold=0.1):
        self.threshold = initial_threshold
        self.match_history = []
    
    def adjust_threshold(self, query_results, expected_matches=1):
        """結果に基づいて閾値を調整"""
        if not query_results:
            # マッチがない場合は閾値を下げる
            self.threshold *= 0.9
        elif len(query_results) > expected_matches * 2:
            # マッチが多すぎる場合は閾値を上げる
            self.threshold *= 1.1
        
        # 閾値の範囲を制限
        self.threshold = max(0.01, min(1.0, self.threshold))
        
        # 履歴を記録
        self.match_history.append({
            'threshold': self.threshold,
            'match_count': len(query_results),
            'top_score': query_results[0]['score'] if query_results else 0
        })
        
        return self.threshold
    
    def get_optimal_threshold(self):
        """履歴に基づく最適閾値を取得"""
        if len(self.match_history) < 5:
            return self.threshold
        
        # 最近の履歴を分析
        recent_history = self.match_history[-10:]
        
        # 成功率の高い閾値を特定
        successful_thresholds = [h['threshold'] for h in recent_history 
                               if 1 <= h['match_count'] <= 3]
        
        if successful_thresholds:
            return sum(successful_thresholds) / len(successful_thresholds)
        else:
            return self.threshold
```

## パフォーマンス最適化

### 並列マッチング

```python
import concurrent.futures
import threading

class ParallelMatchingEngine(MatchingEngine):
    """並列処理対応マッチングエンジン"""
    
    def __init__(self, database, scoring_method='weighted', num_workers=4):
        super().__init__(database, scoring_method)
        self.num_workers = num_workers
        self.thread_local = threading.local()
    
    def identify_audio_parallel(self, query_fingerprints):
        """並列処理による音声識別"""
        # 指紋をチャンクに分割
        chunk_size = len(query_fingerprints) // self.num_workers
        chunks = [query_fingerprints[i:i + chunk_size] 
                 for i in range(0, len(query_fingerprints), chunk_size)]
        
        # 並列処理でマッチング
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.num_workers) as executor:
            future_to_chunk = {executor.submit(self._process_chunk, chunk): chunk 
                             for chunk in chunks}
            
            all_matches = {}
            for future in concurrent.futures.as_completed(future_to_chunk):
                chunk_matches = future.result()
                
                # 結果をマージ
                for song_id, matches in chunk_matches.items():
                    if song_id not in all_matches:
                        all_matches[song_id] = []
                    all_matches[song_id].extend(matches)
        
        # 統合された結果を処理
        analyzed_matches = self._analyze_time_offsets(all_matches, query_fingerprints)
        scored_matches = self._score_matches(analyzed_matches)
        final_results = self._rank_and_filter_results(scored_matches)
        
        return final_results
    
    def _process_chunk(self, chunk):
        """チャンクを処理"""
        return self.database.search_fingerprints(chunk)
```

### キャッシュ機能

```python
from functools import lru_cache
import hashlib

class CachedMatchingEngine(MatchingEngine):
    """キャッシュ機能付きマッチングエンジン"""
    
    def __init__(self, database, scoring_method='weighted', cache_size=1000):
        super().__init__(database, scoring_method)
        self.cache_size = cache_size
        self._setup_cache()
    
    def _setup_cache(self):
        """キャッシュを設定"""
        self._cached_search = lru_cache(maxsize=self.cache_size)(
            self._search_fingerprints_impl
        )
    
    def _search_fingerprints_impl(self, fingerprint_hash):
        """指紋検索の実装（キャッシュ対象）"""
        return self.database.search_fingerprints_by_hash(fingerprint_hash)
    
    def _create_fingerprint_hash(self, fingerprints):
        """指紋のハッシュを作成"""
        hash_string = '|'.join(str(fp['hash']) for fp in sorted(fingerprints, key=lambda x: x['hash']))
        return hashlib.md5(hash_string.encode()).hexdigest()
    
    def identify_audio(self, query_fingerprints):
        """キャッシュを使用した音声識別"""
        # 指紋のハッシュを作成
        fp_hash = self._create_fingerprint_hash(query_fingerprints)
        
        # キャッシュから検索
        try:
            cached_result = self._cached_search(fp_hash)
            if cached_result:
                return cached_result
        except:
            pass
        
        # キャッシュにない場合は通常の処理
        result = super().identify_audio(query_fingerprints)
        
        return result
```

## 品質評価とメトリクス

```python
class MatchingQualityAnalyzer:
    """マッチング品質分析"""
    
    def __init__(self):
        self.metrics_history = []
    
    def analyze_match_quality(self, query_fingerprints, results):
        """マッチ品質を分析"""
        if not results:
            return {
                'quality_score': 0.0,
                'confidence': 0.0,
                'coverage': 0.0,
                'consistency': 0.0
            }
        
        best_match = results[0]
        
        # カバレッジ（マッチした指紋の割合）
        coverage = best_match['match_count'] / len(query_fingerprints)
        
        # 信頼度（スコアの正規化）
        max_possible_score = len(query_fingerprints)
        confidence = min(1.0, best_match['score'] / max_possible_score)
        
        # 一貫性（上位結果間のスコア差）
        if len(results) > 1:
            score_ratio = results[1]['score'] / (results[0]['score'] + 1e-6)
            consistency = 1.0 - score_ratio
        else:
            consistency = 1.0
        
        # 総合品質スコア
        quality_score = (coverage * 0.4 + confidence * 0.4 + consistency * 0.2)
        
        metrics = {
            'quality_score': quality_score,
            'confidence': confidence,
            'coverage': coverage,
            'consistency': consistency,
            'match_count': best_match['match_count'],
            'top_score': best_match['score']
        }
        
        self.metrics_history.append(metrics)
        
        return metrics
    
    def get_performance_summary(self):
        """パフォーマンス要約を取得"""
        if not self.metrics_history:
            return {}
        
        import numpy as np
        
        quality_scores = [m['quality_score'] for m in self.metrics_history]
        confidences = [m['confidence'] for m in self.metrics_history]
        coverages = [m['coverage'] for m in self.metrics_history]
        
        return {
            'avg_quality': np.mean(quality_scores),
            'avg_confidence': np.mean(confidences),
            'avg_coverage': np.mean(coverages),
            'total_queries': len(self.metrics_history),
            'success_rate': sum(1 for q in quality_scores if q > 0.5) / len(quality_scores)
        }
```

## 使用例

### 基本的な音声識別

```python
from mimizam.matching_engine import MatchingEngine
from mimizam.database import FingerprintDatabase

# マッチングエンジンを初期化
database = FingerprintDatabase(backend)
matching_engine = MatchingEngine(database, scoring_method='weighted')

# 音声を識別
query_fingerprints = fingerprinter.generate_fingerprints("query.wav")
results = matching_engine.identify_audio(query_fingerprints)

# 結果を表示
for i, match in enumerate(results[:3]):
    print(f"{i+1}. {match['song_name']} - {match['artist']}")
    print(f"   スコア: {match['score']:.3f}")
    print(f"   信頼度: {match['confidence']:.3f}")
```

### 高度なマッチング

```python
# 適応的閾値を使用
adaptive_threshold = AdaptiveThreshold(initial_threshold=0.1)
matching_engine.match_threshold = adaptive_threshold.get_optimal_threshold()

# 並列処理でマッチング
parallel_engine = ParallelMatchingEngine(database, num_workers=4)
results = parallel_engine.identify_audio_parallel(query_fingerprints)

# 品質分析
quality_analyzer = MatchingQualityAnalyzer()
quality_metrics = quality_analyzer.analyze_match_quality(query_fingerprints, results)

print(f"マッチング品質: {quality_metrics['quality_score']:.3f}")
print(f"カバレッジ: {quality_metrics['coverage']:.3f}")
```

マッチング・識別システムは、mimizamの音声認識精度を決定する重要なコンポーネントです。複数のスコアリング手法と最適化技術により、高精度で高速な楽曲識別を実現します。
