# 映像のハッシュ指紋（B3）の実験 script

映像指紋を、音声と同じ「離散ハッシュを完全一致で引き、ずれの投票で確かめる」作りにできるかを試した script。RANSAC と生 AKAZE 記述子は使わない。結果は `docs/video_fingerprint_hash_experiment.md` にまとめた。製品コード（`src/`）は変えていない。

## 前提

- `mimizam` の親ディレクトリを `sys.path` に入れて `mimizam.src` を import する。repo のディレクトリ名は `mimizam` のままにする。
- 作業ディレクトリは `VFEXP_DIR`（既定 `~/vfexp`）。動画・クエリ・キャッシュ・結果はここに置く。
  - `src/`: 1 組目の動画（`bbb.mp4` `ed.mp4` `sintel.mp4` `tos.mov` `sprite.mp4` `agent327.mp4`、負例 `llamigos.webm` `dillama.mp4`）
  - `src2/`: 2 組目の動画（`hero.mp4` `coffee.mp4` `spring.mp4` `cosmos.mp4`、負例 `llamadrama.ogv` `pioneer.mp4`）
- 動画は Blender の Open Movie（CC BY）と Pioneer One（CC BY-NC-SA）。repo には入れない。
- numba 版（`NB=1`）は venv の numba を使う。

## 実行順（1 組目）

```bash
cd experiments/video_fingerprint
P=../../.venv/bin/python
$P make_queries.py            # 30 秒×8 種の加工のクエリ（$VFEXP_DIR/q）
$P extract.py                 # DB 動画とクエリの AKAZE を $VFEXP_DIR/cache に保存
$P extract_stretch.py         # クエリを横に ×1.33・×1.78 に伸ばして抽出し直す
$P extract_crops.py           # クエリを幅・高さ 1/2 の窓 3×3 に切り出して抽出し直す

# 現状（V0）と C 案（mimizam の ANN→RANSAC 経路に指紋だけ差し替え）
$P eval_c.py V0; $P eval_c.py C2b

# B3（3 点ハッシュ＋重複なし投票）1000 点＋縦横比 2 通り＋窓 9 通り、numba 版
env TAG=B3fsc1000 NB=1 NBSS=1 FAST=1 MODE=sim WBITS=6 NPTS=1000 \
  STRETCH=133,178,c00,c10,c20,c01,c11,c21,c02,c12,c22 $P eval_b2.py
$P analyze_s.py B3fsc1000     # 正解率・誤検出 0 での再現率・加工別
```

2 組目は `make_queries2.py` を使い、各 script に `META=$VFEXP_DIR/q2/meta.json`、`extract.py` に `DBF=src2/hero.mp4,src2/coffee.mp4,src2/spring.mp4,src2/cosmos.mp4`、評価に `DBV=bbb,ed,sintel,tos,sprite,agent327,hero,coffee,spring,cosmos` を付ける。

## `eval_b2.py` の主な環境変数

| 変数 | 意味 |
|---|---|
| `MODE` | `sim`＝3 点の相似不変ハッシュ（B3）、`aff`＝4 点のアフィン不変ハッシュ（B2） |
| `NPTS` | 1 フレームで使う AKAZE の点数（応答の強い順） |
| `STRETCH` | 追加で引くクエリ。`133` `178` は横の伸縮、`c00`〜`c22` は切り出した窓 |
| `FAST` | 1 で 2×2 の特異値を閉じた式、値だけの unique を sort で出す（結果は同じ） |
| `NB` / `NBSS` | `NB=1 NBSS=1` で当たりの処理を numba（範囲探しは numpy）。`NB=2` は並列版 |
| `BACKEND` | `sqlite` / `pg` でハッシュを DB の索引から引く（`PGUSER` `PGPASSWORD`） |
| `LIMIT` | クエリを間引いて N 本だけ評価する |

## そのほかの script

- `eval_b.py`: 最初の B（3 点ハッシュ、重複なし投票なし）
- `invariance.py`: 点を検出し直さずに座標だけ変えて、ハッシュが残る割合を測る
- `repeat.py` `repeat2.py` `repeat_pip.py`: 加工の前後で AKAZE の点が同じ場所に出る割合を測る
- `analyze.py`: V0・C 案の集計、`cmp_nb.py`: 2 つの結果が同じかと速度の比較
