# マッチング・識別システム

このページでは、mimizamシステムの検索とマッチング機能について説明します。これらのコンポーネントは、クエリ音声を既存の指紋データベースと照合し、信頼度スコアを計算して楽曲を識別します。

音声指紋生成の詳細については、[音声指紋エンジン](./04_audio_fingerprinting_engine.md)を参照してください。データベース操作については、[データベース層](./05_database_layer.md)を参照してください。高レベルAPIの使用方法については、[高レベルAPI](./07_high_level_api.md)を参照してください。

## マッチングアーキテクチャ概要

mimizamのマッチングシステムは、効率的な検索と正確な信頼度計算を提供する複数のコンポーネントで構成されています：

```
クエリ音声 → 指紋生成 → ハッシュ検索 → 候補フィルタリング → スコアリング → 結果ランキング
     ↓           ↓         ↓           ↓            ↓           ↓
AudioFingerprinter → FingerprintMatcher → 時間整列 → 信頼度計算 → 最終結果
```

## FingerprintMatcher クラス

`FingerprintMatcher`クラスは、指紋マッチングと楽曲識別の中核機能を提供します。

### 主要メソッド

#### 楽曲識別

```python
def identify_audio(self, audio_file_path: str, min_confidence: float = 0.3) -> Optional[Tuple[Song, float]]:
    """音声ファイルから楽曲を識別"""
    
def search_song(self, audio_file_path: str, min_confidence: float = 0.2, top_k: int = 10) -> List[Dict[str, Any]]:
    """複数の候補楽曲を検索"""
```

#### 内部マッチング処理

```python
def _find_matching_fingerprints(self, query_fingerprints: List[Tuple[str, float]]) -> Dict[int, List[Tuple[float, float]]]:
    """クエリ指紋に一致するデータベース指紋を検索"""
    
def _calculate_time_alignment(self, matches: Dict[int, List[Tuple[float, float]]]) -> Dict[int, float]:
    """時間整列を計算"""
    
def _calculate_confidence_score(self, song_id: int, matches: List[Tuple[float, float]], time_alignment: float) -> float:
    """信頼度スコアを計算"""
```

## マッチング処理フロー

### 1. クエリ指紋生成

```python
def identify_audio(self, audio_file_path: str, min_confidence: float = 0.3) -> Optional[Tuple[Song, float]]:
    # 1. クエリ音声から指紋を生成
    query_fingerprints = self.fingerprinter.generate_fingerprints(audio_file_path)
    
    if not query_fingerprints:
        return None
```

### 2. データベース検索

```python
    # 2. データベースから一致する指紋を検索
    matching_fingerprints = self._find_matching_fingerprints(query_fingerprints)
    
    if not matching_fingerprints:
        return None
```

### 3. 時間整列計算

```python
    # 3. 各楽曲の時間整列を計算
    time_alignments = self._calculate_time_alignment(matching_fingerprints)
```

### 4. 信頼度スコアリング

```python
    # 4. 信頼度スコアを計算
    scored_candidates = []
    for song_id, matches in matching_fingerprints.items():
        time_alignment = time_alignments[song_id]
        confidence = self._calculate_confidence_score(song_id, matches, time_alignment)
        
        if confidence >= min_confidence:
            song = self.database.get_song_by_id(song_id)
            scored_candidates.append((song, confidence, time_alignment))
```

### 5. 結果選択

```python
    # 5. 最高スコアの楽曲を選択
    if scored_candidates:
        best_match = max(scored_candidates, key=lambda x: x[1])
        return (best_match[0], best_match[1])
    
    return None
```

## 信頼度スコアリング

### スコアリング方式

mimizamは複数のスコアリング方式をサポートしています：

| 方式 | 説明 | 用途 |
|------|------|------|
| **基本スコア** | 一致指紋数 / クエリ指紋数 | 高速な基本識別 |
| **時間整列スコア** | 時間的一貫性を考慮した重み付け | 高精度識別 |
| **適応スコア** | 音声特性に基づく動的調整 | ノイズ耐性向上 |

### 基本スコアリング

```python
def _calculate_basic_score(self, matches: List[Tuple[float, float]], query_count: int) -> float:
    """基本的な信頼度スコア計算"""
    if query_count == 0:
        return 0.0
    
    match_count = len(matches)
    return min(match_count / query_count, 1.0)
```

### 時間整列スコアリング

```python
def _calculate_time_aligned_score(self, matches: List[Tuple[float, float]], time_alignment: float) -> float:
    """時間整列を考慮した信頼度スコア計算"""
    if not matches:
        return 0.0
    
    # 時間整列からの偏差を計算
    aligned_matches = 0
    time_tolerance = 0.1  # 100ms許容範囲
    
    for query_time, db_time in matches:
        expected_db_time = query_time + time_alignment
        if abs(db_time - expected_db_time) <= time_tolerance:
            aligned_matches += 1
    
    return aligned_matches / len(matches)
```

### 適応スコアリング

```python
def _calculate_adaptive_score(self, matches: List[Tuple[float, float]], audio_characteristics: Dict[str, float]) -> float:
    """音声特性に基づく適応的スコア計算"""
    base_score = self._calculate_time_aligned_score(matches, 0.0)
    
    # ノイズレベルに基づく調整
    noise_level = audio_characteristics.get('noise_level', 0.0)
    noise_penalty = min(noise_level * 0.2, 0.3)
    
    # 音声品質に基づく調整
    audio_quality = audio_characteristics.get('audio_quality', 1.0)
    quality_bonus = (audio_quality - 0.5) * 0.1
    
    adjusted_score = base_score - noise_penalty + quality_bonus
    return max(0.0, min(1.0, adjusted_score))
```

## 時間整列アルゴリズム

### 時間オフセット計算

```python
def _calculate_time_alignment(self, matches: Dict[int, List[Tuple[float, float]]]) -> Dict[int, float]:
    """各楽曲の最適な時間オフセットを計算"""
    alignments = {}
    
    for song_id, match_list in matches.items():
        if len(match_list) < 3:  # 最小マッチ数
            alignments[song_id] = 0.0
            continue
        
        # 時間差のヒストグラムを作成
        time_diffs = [db_time - query_time for query_time, db_time in match_list]
        
        # 最頻値を時間オフセットとして使用
        alignment = self._find_most_frequent_offset(time_diffs)
        alignments[song_id] = alignment
    
    return alignments
```

### オフセット最適化

```python
def _find_most_frequent_offset(self, time_diffs: List[float]) -> float:
    """時間差リストから最適なオフセットを見つける"""
    if not time_diffs:
        return 0.0
    
    # ヒストグラムビンを作成（100ms間隔）
    bin_size = 0.1
    bins = {}
    
    for diff in time_diffs:
        bin_key = round(diff / bin_size) * bin_size
        bins[bin_key] = bins.get(bin_key, 0) + 1
    
    # 最大頻度のビンを返す
    if bins:
        return max(bins.keys(), key=lambda k: bins[k])
    
    return 0.0
```

## 検索最適化

### インデックス活用

```python
def _find_matching_fingerprints(self, query_fingerprints: List[Tuple[str, float]]) -> Dict[int, List[Tuple[float, float]]]:
    """効率的な指紋検索"""
    matches = {}
    
    # バッチクエリで効率化
    hash_list = [fp[0] for fp in query_fingerprints]
    hash_to_query_time = {fp[0]: fp[1] for fp in query_fingerprints}
    
    # データベースから一括検索
    db_results = self.database.find_fingerprints_by_hashes(hash_list)
    
    for hash_value, song_id, db_time in db_results:
        query_time = hash_to_query_time[hash_value]
        
        if song_id not in matches:
            matches[song_id] = []
        
        matches[song_id].append((query_time, db_time))
    
    return matches
```

### キャッシュ戦略

```python
class FingerprintMatcher:
    def __init__(self, database: FingerprintDatabase):
        self.database = database
        self.fingerprinter = database.fingerprinter
        self._result_cache = {}
        self._cache_size_limit = 1000
    
    def _get_cached_result(self, audio_hash: str) -> Optional[Tuple[Song, float]]:
        """キャッシュされた結果を取得"""
        return self._result_cache.get(audio_hash)
    
    def _cache_result(self, audio_hash: str, result: Tuple[Song, float]) -> None:
        """結果をキャッシュに保存"""
        if len(self._result_cache) >= self._cache_size_limit:
            # LRU削除
            oldest_key = next(iter(self._result_cache))
            del self._result_cache[oldest_key]
        
        self._result_cache[audio_hash] = result
```

## パフォーマンス監視

### マッチング統計

```python
def get_matching_statistics(self) -> Dict[str, Any]:
    """マッチング統計情報を取得"""
    return {
        'total_queries': self._total_queries,
        'successful_matches': self._successful_matches,
        'average_confidence': self._average_confidence,
        'average_query_time': self._average_query_time,
        'cache_hit_rate': self._cache_hits / max(self._total_queries, 1),
        'most_matched_songs': self._get_top_matched_songs()
    }
```

### パフォーマンス最適化

```python
def _optimize_matching_performance(self):
    """マッチング性能の最適化"""
    # データベースインデックスの最適化
    self.database.optimize_fingerprint_indices()
    
    # キャッシュサイズの動的調整
    if self._cache_hit_rate < 0.3:
        self._cache_size_limit = min(self._cache_size_limit * 2, 5000)
    
    # クエリ並列化の設定
    if self._average_query_time > 1.0:
        self._enable_parallel_matching = True
```

## 関連ドキュメント

- [コアアーキテクチャ](./03_core_architecture.md) - システム全体の構成
- [音声指紋エンジン](./04_audio_fingerprinting_engine.md) - 指紋生成の詳細
- [データベース層](./05_database_layer.md) - データベース操作
- [高レベルAPI](./07_high_level_api.md) - 簡単な使用方法
- [パフォーマンス最適化](./16_performance_optimization.md) - 高速化技術
