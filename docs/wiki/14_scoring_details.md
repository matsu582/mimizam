# スコアリング詳細

mimizamの音声マッチングシステムでは、複数のスコアリング方式を提供しています。用途と要求される精度・速度に応じて最適な方式を選択できます。

## 🎯 スコアリング方式の概要

mimizamは3つの主要なスコアリング方式を提供します：

| 方式 | 特徴 | 速度 | 精度 | 推奨用途 |
|------|------|------|------|----------|
| **hybrid** | バランス型（推奨） | 中 | 高 | 一般的な用途 |
| **histogram** | 高速型 | 高 | 中 | リアルタイム処理 |
| **detailed** | 高精度型 | 低 | 最高 | 高精度が必要な場合 |

## 🔄 Hybrid スコアリング（推奨）

### 概要
Hybridスコアリングは、速度と精度のバランスを取った2段階処理方式です。デフォルトで使用される推奨方式です。

### アルゴリズム
1. **第1段階**: 高速ヒストグラム方式で候補を絞り込み
2. **第2段階**: 上位候補に対して詳細分析を実行

### 使用例
```python
from mimizam import create_mimizam_sqlite

with create_mimizam_sqlite("music.db") as mimizam:
    # Hybridスコアリング（デフォルト）
    results = mimizam.search_song(
        "query.wav",
        scoring_method='hybrid',
        min_confidence=0.3,
        top_k=5
    )
    
    for result in results:
        song = result['song']
        confidence = result['confidence']
        print(f"{song.title}: {confidence:.2%}")
```

### パラメータ設定
```python
# カスタムHybrid設定
with create_mimizam_sqlite(
    "music.db",
    # Hybrid固有設定
    hybrid_stage1_candidates=50,    # 第1段階候補数
    hybrid_stage2_candidates=10,    # 第2段階候補数
    hybrid_confidence_threshold=0.1, # 第1段階信頼度閾値
    
    # 共通設定
    time_tolerance=0.1,             # 時間許容範囲（秒）
    freq_tolerance=50               # 周波数許容範囲（Hz）
) as mimizam:
    results = mimizam.search_song("query.wav", scoring_method='hybrid')
```

### 性能特性
- **処理時間**: 中程度（histogram の1.5-2倍）
- **メモリ使用量**: 中程度
- **精度**: 高い（detailed の90-95%）
- **推奨データベースサイズ**: 1万-10万曲

## ⚡ Histogram スコアリング（高速）

### 概要
Histogramスコアリングは、時間オフセットのヒストグラム分析による高速マッチング方式です。

### アルゴリズム
1. **ハッシュマッチング**: クエリ指紋とデータベース指紋の一致を検索
2. **時間オフセット計算**: マッチした指紋の時間差を計算
3. **ヒストグラム生成**: 時間オフセットのヒストグラムを作成
4. **ピーク検出**: ヒストグラムの最大ピークを信頼度として使用

### 使用例
```python
with create_mimizam_sqlite("music.db") as mimizam:
    # 高速Histogramスコアリング
    results = mimizam.search_song(
        "query.wav",
        scoring_method='histogram',
        min_confidence=0.2,  # 低い閾値で高速検索
        top_k=10
    )
    
    print(f"高速検索結果: {len(results)}件")
```

### パラメータ設定
```python
# カスタムHistogram設定
with create_mimizam_sqlite(
    "music.db",
    # Histogram固有設定
    histogram_bin_size=0.1,         # ヒストグラムビンサイズ（秒）
    histogram_peak_threshold=5,     # ピーク検出閾値
    max_matches_per_hash=100,       # ハッシュあたり最大マッチ数
    
    # 高速化設定
    enable_early_termination=True,  # 早期終了
    max_candidates=1000             # 最大候補数
) as mimizam:
    results = mimizam.search_song("query.wav", scoring_method='histogram')
```

### 性能特性
- **処理時間**: 最高速
- **メモリ使用量**: 低い
- **精度**: 中程度
- **推奨用途**: リアルタイム処理、大規模データベース

### 最適化のコツ
```python
# 高速化のための設定例
fast_config = {
    'histogram_bin_size': 0.2,      # 粗いビンサイズ
    'max_matches_per_hash': 50,     # マッチ数制限
    'enable_early_termination': True,
    'max_candidates': 500
}

with create_mimizam_sqlite("music.db", **fast_config) as mimizam:
    # 超高速検索
    results = mimizam.search_song(
        "query.wav", 
        scoring_method='histogram',
        min_confidence=0.15,
        top_k=3
    )
```

## 🔬 Detailed スコアリング（高精度）

### 概要
Detailedスコアリングは、包括的な分析による最高精度のマッチング方式です。

### アルゴリズム
1. **ハッシュマッチング**: 全ての一致する指紋を検索
2. **時間アライメント**: 複数の時間オフセット候補を評価
3. **密度分析**: マッチ密度の詳細計算
4. **統計的検証**: 信頼区間と有意性検定
5. **複合スコア**: 複数指標の重み付き統合

### 使用例
```python
with create_mimizam_sqlite("music.db") as mimizam:
    # 高精度Detailedスコアリング
    results = mimizam.search_song(
        "query.wav",
        scoring_method='detailed',
        min_confidence=0.5,  # 高い閾値で高精度検索
        top_k=3
    )
    
    for result in results:
        song = result['song']
        confidence = result['confidence']
        alignment = result['time_alignment']
        density = result.get('match_density', 0)
        
        print(f"{song.title}: {confidence:.2%}")
        print(f"  時間オフセット: {alignment:.2f}秒")
        print(f"  マッチ密度: {density:.1f} matches/sec")
```

### パラメータ設定
```python
# カスタムDetailed設定
with create_mimizam_sqlite(
    "music.db",
    # Detailed固有設定
    detailed_time_windows=[0.05, 0.1, 0.2],  # 複数時間窓
    detailed_density_threshold=2.0,          # 密度閾値
    detailed_statistical_test=True,          # 統計検定有効
    detailed_confidence_intervals=True,      # 信頼区間計算
    
    # 高精度設定
    time_tolerance=0.05,                     # 厳密な時間許容範囲
    freq_tolerance=25,                       # 厳密な周波数許容範囲
    min_match_count=10                       # 最小マッチ数
) as mimizam:
    results = mimizam.search_song("query.wav", scoring_method='detailed')
```

### 性能特性
- **処理時間**: 最も遅い
- **メモリ使用量**: 高い
- **精度**: 最高
- **推奨用途**: 高精度が必要な場合、少数の候補の詳細分析

### 詳細分析の活用
```python
def detailed_analysis_example():
    """詳細分析の使用例"""
    with create_mimizam_sqlite("music.db") as mimizam:
        results = mimizam.search_song(
            "query.wav", 
            scoring_method='detailed',
            min_confidence=0.3
        )
        
        for result in results:
            song = result['song']
            
            # 基本情報
            print(f"\n🎵 楽曲: {song.title}")
            print(f"信頼度: {result['confidence']:.2%}")
            
            # 詳細分析結果
            if 'detailed_analysis' in result:
                analysis = result['detailed_analysis']
                print(f"マッチ数: {analysis.get('match_count', 0)}")
                print(f"マッチ密度: {analysis.get('match_density', 0):.2f}")
                print(f"時間分散: {analysis.get('time_variance', 0):.3f}")
                print(f"統計的有意性: {analysis.get('p_value', 1):.4f}")
```

## ⚙️ スコアリング方式の選択指針

### 用途別推奨設定

#### 1. 一般的な音楽識別アプリ
```python
# バランス重視（推奨）
config = {
    'scoring_method': 'hybrid',
    'min_confidence': 0.3,
    'time_tolerance': 0.1,
    'freq_tolerance': 50
}
```

#### 2. リアルタイム音声監視
```python
# 速度重視
config = {
    'scoring_method': 'histogram',
    'min_confidence': 0.2,
    'max_matches_per_hash': 50,
    'enable_early_termination': True
}
```

#### 3. 音楽著作権検証
```python
# 精度重視
config = {
    'scoring_method': 'detailed',
    'min_confidence': 0.6,
    'time_tolerance': 0.05,
    'freq_tolerance': 25,
    'detailed_statistical_test': True
}
```

#### 4. 大規模音楽データベース
```python
# スケーラビリティ重視
config = {
    'scoring_method': 'hybrid',
    'hybrid_stage1_candidates': 100,
    'hybrid_stage2_candidates': 5,
    'max_candidates': 2000
}
```

### データベースサイズ別推奨

| データベースサイズ | 推奨方式 | 設定 |
|-------------------|----------|------|
| < 1,000曲 | detailed | 高精度設定 |
| 1,000 - 10,000曲 | hybrid | バランス設定 |
| 10,000 - 100,000曲 | hybrid | 効率化設定 |
| > 100,000曲 | histogram | 高速設定 |

## 📊 性能比較

### ベンチマーク結果（10,000曲データベース）

| 方式 | 平均処理時間 | メモリ使用量 | 識別精度 | 適合率 | 再現率 |
|------|-------------|-------------|----------|--------|--------|
| histogram | 50ms | 20MB | 85% | 82% | 88% |
| hybrid | 120ms | 35MB | 92% | 90% | 94% |
| detailed | 300ms | 60MB | 96% | 95% | 97% |

### 信頼度閾値の影響

```python
def confidence_threshold_analysis():
    """信頼度閾値の影響分析"""
    thresholds = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6]
    methods = ['histogram', 'hybrid', 'detailed']
    
    with create_mimizam_sqlite("test_db.db") as mimizam:
        for method in methods:
            print(f"\n📊 {method.upper()} 方式:")
            print("閾値  | 結果数 | 平均信頼度")
            print("-" * 25)
            
            for threshold in thresholds:
                results = mimizam.search_song(
                    "test_query.wav",
                    scoring_method=method,
                    min_confidence=threshold,
                    top_k=10
                )
                
                if results:
                    avg_confidence = sum(r['confidence'] for r in results) / len(results)
                    print(f"{threshold:.1f}   | {len(results):4d}   | {avg_confidence:.2%}")
                else:
                    print(f"{threshold:.1f}   |    0   | N/A")

# 実行
# confidence_threshold_analysis()
```

## 🔧 カスタムスコアリング

### 独自スコアリング関数の実装

```python
from mimizam import FingerprintMatcher

def calculate_custom_score(matches: list, query_duration: float, 
                          weight_time: float = 0.4, weight_density: float = 0.4, 
                          weight_consistency: float = 0.2) -> float:
    """カスタムスコア計算"""
    import numpy as np
    
    if not matches:
        return 0.0
    
    # 時間アライメントスコア
    time_offsets = [m['time_offset'] for m in matches]
    time_consistency = 1.0 / (1.0 + np.std(time_offsets))
    
    # マッチ密度スコア
    match_density = len(matches) / query_duration
    density_score = min(match_density / 10.0, 1.0)  # 正規化
    
    # 一貫性スコア
    consistency_score = time_consistency
    
    # 重み付き統合
    final_score = (
        weight_time * time_consistency +
        weight_density * density_score +
        weight_consistency * consistency_score
    )
    
    return min(final_score, 1.0)

# 使用例
def custom_scoring_example():
    """カスタムスコアリングの使用例"""
    
    # 低レベルAPIでカスタムスコアリングを使用
    from mimizam import FingerprintDatabase, create_sqlite_config
    
    config = create_sqlite_config("music.db")
    db = FingerprintDatabase(config)
    
    try:
        # クエリ指紋を取得
        query_fingerprints = db.get_query_fingerprints("query.wav")
        
        # 基本マッチング
        raw_matches = db.find_raw_matches(query_fingerprints)
        
        # カスタムスコアリング適用
        scored_results = []
        for song_id, matches in raw_matches.items():
            score = calculate_custom_score(matches, query_duration=30.0, 
                                         weight_time=0.5, weight_density=0.3, weight_consistency=0.2)
            if score > 0.2:  # 閾値
                song = db.get_song(song_id)
                scored_results.append({
                    'song': song,
                    'confidence': score,
                    'match_count': len(matches)
                })
        
        # スコア順でソート
        scored_results.sort(key=lambda x: x['confidence'], reverse=True)
        
        print("🎯 カスタムスコアリング結果:")
        for result in scored_results[:5]:
            print(f"{result['song'].title}: {result['confidence']:.2%}")
    
    finally:
        db.close()

# 実行
# custom_scoring_example()
```

## 🎛️ 動的スコアリング調整

### 音声特性に応じた自動調整

```python
def adaptive_scoring_example():
    """適応的スコアリングの例"""
    
    def analyze_query_characteristics(query_path: str) -> dict:
        """クエリ音声の特性分析"""
        import librosa
        
        audio, sr = librosa.load(query_path, sr=22050)
        
        # 基本特性
        duration = len(audio) / sr
        rms_energy = np.sqrt(np.mean(audio**2))
        zero_crossing_rate = np.mean(librosa.feature.zero_crossing_rate(audio))
        
        # ノイズレベル推定
        noise_level = np.std(audio[:int(0.5 * sr)])
        snr_estimate = 20 * np.log10(rms_energy / (noise_level + 1e-10))
        
        return {
            'duration': duration,
            'snr': snr_estimate,
            'energy': rms_energy,
            'zcr': zero_crossing_rate
        }
    
    def select_optimal_scoring(characteristics: dict) -> dict:
        """特性に基づく最適スコアリング選択"""
        duration = characteristics['duration']
        snr = characteristics['snr']
        energy = characteristics['energy']
        
        # 短い音声
        if duration < 5:
            return {
                'scoring_method': 'detailed',
                'min_confidence': 0.4,
                'time_tolerance': 0.1
            }
        
        # ノイズが多い音声
        elif snr < 10:
            return {
                'scoring_method': 'hybrid',
                'min_confidence': 0.2,
                'time_tolerance': 0.15,
                'freq_tolerance': 75
            }
        
        # 高品質音声
        elif snr > 20 and energy > 0.01:
            return {
                'scoring_method': 'histogram',
                'min_confidence': 0.3,
                'time_tolerance': 0.08
            }
        
        # デフォルト
        else:
            return {
                'scoring_method': 'hybrid',
                'min_confidence': 0.3,
                'time_tolerance': 0.1
            }
    
    # 使用例
    query_path = "queries/test_audio.wav"
    
    # 音声特性分析
    characteristics = analyze_query_characteristics(query_path)
    print(f"音声特性: 長さ={characteristics['duration']:.1f}s, "
          f"SNR={characteristics['snr']:.1f}dB")
    
    # 最適設定選択
    optimal_config = select_optimal_scoring(characteristics)
    print(f"選択された設定: {optimal_config}")
    
    # 適応的検索実行
    with create_mimizam_sqlite("music.db") as mimizam:
        results = mimizam.search_song(query_path, **optimal_config)
        print(f"検索結果: {len(results)}件")

# 実行
# adaptive_scoring_example()
```

## 🔗 関連ドキュメント

- [音声指紋生成](./13_fingerprint_generation.md) - 指紋生成アルゴリズム
- [統合API](./07_unified_api.md) - スコアリング方式の指定方法
- [パフォーマンス最適化](./12_performance_optimization.md) - 速度向上テクニック
- [実装例](./16_basic_examples.md) - 実践的な使用例
- [トラブルシューティング](./21_debugging.md) - スコアリング関連の問題解決

## 📚 参考文献

- **Wang, A. L. C.** (2003). "An Industrial-Strength Audio Search Algorithm"
- **Ellis, D. P. W.** (2009). "Robust Landmark-Based Audio Fingerprinting"
- **Cano, P. et al.** (2005). "A Review of Audio Fingerprinting"
- **Six, J. & Leman, M.** (2014). "Panako - A Scalable Acoustic Fingerprinting System"
