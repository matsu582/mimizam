# mimizam音声指紋マッチングのスコア計算について

mimizamの音声指紋マッチングは、尺度不変ハッシュを前提とした**単一検索マッチング**（速度・ピッチ変化に頑健）に統一されている。本書では現在の照合・スコア計算の方法とパラメータを記す。

> 旧仕様（`histogram` / `hybrid` / `detailed` の3方式と、time/freq スケールのブルートフォース探索による信頼度計算）は完全に廃止された。スコアリング方式の選択API（`scoring_method` / `set_scoring_method`）も存在しない。

---

## 1. 前提: 尺度不変ハッシュ

ハッシュはアンカー＋2ターゲットのピーク三つ組から生成される32bitビットパック値で、
時間比 `(t1-tA)/(t2-tA)` と周波数比 `log2(f1/fA)`, `log2(f2/fA)` を符号化する。
これにより、ハッシュ自体が**速度変化（時間伸縮）・ピッチ変化（周波数スケール）に本質的に不変**である。

その結果、照合側で time_scale / freq_scale を総当りしてハッシュを作り直す必要がなく、
**DB検索は1回のみ**で候補集合が完結する（詳細は `docs/fingerprint_generation_details.md`）。

### 1.1 共通パラメータ

```python
min_confidence = 0.1     # 最小信頼度閾値
max_results = 10         # 最大結果数
time_tolerance = 0.05    # 整列許容度（秒）。傾きで速度変化を吸収した後の
                         # オフセット残差の許容幅
```

---

## 2. 照合フロー（単一検索マッチング）

`FingerprintMatcher.find_matches()` の処理は次の通り。

```
クエリ指紋群
  ↓ database.search_fingerprints(query)  … DB検索は1回のみ
楽曲ごとの (query_time, db_time) 衝突ペア
  ↓ 支配直線 db ≈ slope·query + offset をハフ投票で頑健推定
  ↓ 整列インライア（残差 ±time_tolerance 以内）を抽出
  ↓ significance ベースの信頼度算出
min_confidence 以上を実効スコア順に整列
```

速度変化した一致では `query_time - db_time` は一定にならないため、
傾き（= time_scale）で正規化した残差 `db_time - slope·query_time` を一定量として扱う。

---

## 3. 支配直線の推定（頑健直線回帰）

尺度不変ハッシュは粗量子化のため偶発衝突が多く、外れ値が過半になりうる。
そこで中央値ではなく**最頻値ベース（ハフ投票）**で傾き・切片を推定する。

### 3.1 傾き候補の投票（`_estimate_slope_candidates`）

ペア間傾き `(dj-di)/(qj-qi)` を log2 空間でヒストグラム投票し、得票上位ビンの
傾き中央値を候補として複数返す。

```python
slope_range = (0.25, 4.0)     # 傾き（=time_scale）の妥当域
line_fit_sample_size = 150    # ペア傾き算出のサンプル点上限（O(K^2)抑制）
slope_log2_bin = 0.03         # 傾きヒストグラムのビン幅（log2空間）
slope_min_dq = 1.0            # 傾き算出に使う query 時間差の下限（秒）
slope_top_candidates = 5      # インライア評価に回す傾き候補ビン数
```

- 単一の最頻ビンだけだと、粗量子化で偶発的に別倍率のビンが競り勝つと取り違える。
  上位複数を後段のインライア評価に渡し、真の倍率を選び直せるようにする。
- query 側の時間差が十分大きいペアのみを使い、時間量子化の影響を抑える。

### 3.2 傾きの確定とインライア抽出（`_fit_scale_offset` / `_inliers_for_slope`）

各傾き候補について、オフセット `db_time - slope·query_time` の最頻ビン（幅 `time_tolerance`）
近傍のインライアを数え、**インライアが最大になる傾き**を採用する。
オフセットは最頻ビン内インライアの中央値とする。

---

## 4. 信頼度計算（significance ベース）

信頼度は `_confidence_from_inliers(aligned, total, db_span)` で算出する。
`aligned` は整列インライア数、`total` は全衝突ペア数、`db_span` は全衝突が散らばるDB時間幅。

### 4.1 significance（偶然整列に対する超過倍率）

全 `total` 件の衝突が DB時間幅 `db_span` 全域へ一様に散ると仮定すると、
許容幅 `±time_tolerance` の1オフセット帯に偶然入る期待数は

```
expected = total × (2·time_tolerance / db_span)
significance = aligned / expected
```

真の一致は一つのオフセットに集中するため `aligned ≫ expected`、無関係曲は
衝突が全域へ散って `aligned` が `expected` 並みに留まる。
`significance` は DB規模・衝突総数に依存せず両者を分離できる
（割合 `aligned/total` は大規模DBで正解でも極小になり不適）。

> `db_span` が不明・極小のときは `expected=1`（偶然1件相当）とみなし、
> `significance` を整列絶対数に退化させる（小規模・単体テスト向けの安全側フォールバック）。

### 4.2 信頼度の合成

```python
confidence_full_matches = 40        # 数項が飽和する整列数
confidence_full_significance = 100  # significance項が飽和する値
confidence_purity_floor = 0.5       # 純度項が効き始める整列割合

count_term = min(1, aligned / confidence_full_matches)                       # 整列の絶対数
sig_term   = min(1, log1p(significance) / log1p(confidence_full_significance))# 偶然超過倍率
base_conf  = count_term * sig_term                                           # 片方が低いと抑制

# クリーンな一致は整列割合が1.0近くまで上がる（無関係曲では起こらない）
purity_conf = max(0, (ratio - confidence_purity_floor) / (1 - confidence_purity_floor))

confidence = min(max(base_conf, purity_conf), 1.0)
```

- `base_conf` は「絶対数」と「偶然超過倍率」の積で、どちらか一方が低いだけで抑制される。
- 高純度時（ノイズが少なく整列割合が高い）は絶対数が少なくても高信頼度とみなす純度項を併用し、大きい方を採る。
- `aligned < 2` のペアは信頼度0（偶発衝突の棄却）。

### 4.3 パラメータ根拠

- **time_tolerance = 0.05秒**: 傾きで速度変化を吸収した後のオフセット残差の許容幅。
  ピーク時間分解能（約23ms）に見合う狭さにし、無関係曲の偶発整列を抑える。
- **confidence_full_matches = 40**: 整列インライアがこの件数で数項が飽和する。
- **confidence_full_significance = 100**: 多数のオフセット帯を暗黙に比較するため、
  偶然でも数倍程度は生じうる。確実な一致は数十〜百倍に達するので高めに設定する。
- **confidence_purity_floor = 0.5**: 無関係曲の整列割合（概ね0.1〜0.2）では純度項が0となり、
  クリーンな一致でのみ効く。

---

## 5. 結果の整列（`_sort_and_limit_results`）

`min_confidence` を満たす候補を、以下の優先度で降順整列し `max_results` 件に絞る。

1. 信頼度 `confidence`
2. マッチ数 `match_count`
3. 時間的整列率 `alignment_ratio`
4. 時間スケールの正確性（`time_scale` が 1.0 に近いほど良い）

各結果には `time_scale`（= 復元した傾き）と `time_offset`（= 切片）が付与される。
ピッチ不変はハッシュ側で吸収済みのため `freq_scale` は常に 1.0。

---

## 6. 参考文献

- Avery Li-Chun Wang, "An Industrial-Strength Audio Search Algorithm", 2003
- 音声指紋システムの既存実装を参考
  - https://github.com/worldveil/dejavu
  - https://github.com/dpwe/audfprint
- 各係数は実験データと経験則に基づく
