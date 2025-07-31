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

マッチング処理の中核を担うコンポーネントとして、音声識別の全プロセスを統合管理します。

#### 主要な処理段階
1. **データベース検索**: 指紋ハッシュによる高速な候補抽出
2. **時間オフセット分析**: 時間的一貫性による品質評価
3. **スコアリング**: 複数手法による信頼度計算
4. **結果フィルタリング**: 閾値とランキングによる最適化

#### 設定可能パラメータ
- **スコアリング手法**: 重み付き、統計的、適応的手法の選択
- **マッチング閾値**: 識別精度と処理速度のバランス調整
- **最大マッチ数**: 結果セットサイズの制御

### 時間オフセット分析

時間オフセット分析は、マッチング品質を評価する重要な処理段階です。この分析により、偶然の一致と真のマッチを区別できます。

#### 分析手法
- **統計的評価**: 時間オフセットの分布パターン分析
- **一貫性チェック**: 時間的な連続性の検証
- **外れ値除去**: ノイズや偶然の一致の排除
- **信頼度計算**: マッチ品質の定量的評価
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
## スコアリング手法

mimizamシステムは、マッチング品質を評価するための複数のスコアリング手法を提供します。各手法は異なる特徴と適用シナリオを持ちます。

### ハイブリッド手法

最も汎用的なスコアリング手法として、複数の評価指標を統合します。

#### 評価要素
- **マッチ数**: 基本的な一致指紋の数量
- **時間一貫性**: 時間オフセットの統計的一貫性
- **分布品質**: マッチの時間的分散パターン
- **信頼度重み**: 各マッチの信頼性による重み付け

### ヒストグラム手法

時間オフセットのヒストグラム分析に基づく手法です。

#### 特徴
- **ピーク検出**: 時間オフセット分布の主要ピーク特定
- **ノイズ除去**: 散発的な偶然一致の排除
- **密度評価**: マッチ密度による品質評価
- **閾値適応**: 動的な閾値調整機能

### 詳細手法

高精度な統計分析による詳細評価手法です。

#### 分析要素
- **統計的検定**: 時間一貫性の統計的有意性検証
- **外れ値処理**: 統計的手法による異常値除去
- **信頼区間**: マッチ品質の信頼区間計算
- **適応的重み**: 音声特性に基づく動的重み調整

## 結果ランキングとフィルタリング

識別結果の最終処理段階として、スコアベースのランキングと品質フィルタリングを実行します。

### ランキング戦略
- **スコア順位付け**: 計算されたスコアによる降順ソート
- **信頼度考慮**: スコアと信頼度の複合評価
- **一貫性重視**: 時間的一貫性の高いマッチの優先
- **適応的調整**: クエリ特性に基づく動的調整

### フィルタリング機能
- **閾値フィルタリング**: 最小スコア要件による品質保証
- **重複除去**: 同一楽曲の重複マッチ統合
- **結果数制限**: 効率的な結果セット管理
- **メタデータ統合**: 楽曲情報の自動付加

## 高度なマッチング技術

### 時間窓マッチング

長時間の音声クエリに対する効率的な処理手法として、時間窓ベースのマッチングを提供します。

#### 処理戦略
- **窓分割**: 音声クエリを固定時間間隔で分割
- **並列処理**: 各時間窓での独立したマッチング実行
- **結果統合**: 窓間での結果の統計的統合
- **品質評価**: 窓間一貫性による信頼度評価

#### 利点
- **メモリ効率**: 大容量音声の段階的処理
- **処理速度**: 並列化による高速化
- **精度向上**: 局所的マッチングによる精度向上
- **スケーラビリティ**: 任意長音声への対応

### 適応的閾値調整

システムの識別精度を動的に最適化する適応的閾値調整機能を提供します。

#### 調整戦略
- **履歴分析**: 過去のマッチング結果に基づく学習
- **動的調整**: クエリ特性に応じた閾値の自動調整
- **品質監視**: マッチング品質の継続的な評価
- **最適化**: 精度と再現率のバランス最適化

#### 適応機能
- **過少マッチ対応**: 閾値の段階的引き下げ
- **過多マッチ対応**: 閾値の段階的引き上げ
- **安定性保証**: 閾値変動の適切な制限
- **学習機能**: 成功パターンの自動学習

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
