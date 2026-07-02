# scripts

mimizam の開発・運用補助スクリプト集。

## スクリプト一覧

| スクリプト | 概要 |
|---|---|
| `create_demo_audio.py` | デモ用合成音声ファイルの生成 |
| `migrate_database.py` | データベーススキーマの移行（全バックエンド対応） |
| `generate_transformed_videos.py` | 映像指紋検証用の改変動画生成 |

---

## create_demo_audio.py

デモ・テスト用の合成音声ファイル（WAV）を `test_media/` に生成する。

```bash
python scripts/create_demo_audio.py
```

生成されるファイル:
- `test_media/demo_song1.wav`
- `test_media/demo_song2.wav`
- `test_media/demo_query.wav`

---

## migrate_database.py

データベーススキーマを新バージョンに移行する。SQLite / MySQL / PostgreSQL / Elasticsearch の全バックエンドに対応。

```bash
# SQLite（デフォルト）
python scripts/migrate_database.py

# MySQL
python scripts/migrate_database.py --backend mysql --host localhost --database mimizam

# PostgreSQL
python scripts/migrate_database.py --backend postgresql --host localhost --database mimizam

# Elasticsearch
python scripts/migrate_database.py --backend elasticsearch --host localhost
```

---

## generate_transformed_videos.py

映像指紋の幾何変換耐性を検証するためのテストデータ（改変動画）を生成する。

### 依存パッケージ

```bash
pip install opencv-python numpy
```

### 基本的な使い方

```bash
# 単一映像に全変換パターンを適用
python scripts/generate_transformed_videos.py input.mp4 -o output_dir/

# 複数映像を同時に処理
python scripts/generate_transformed_videos.py video1.mp4 video2.mp4 -o output_dir/
```

### 変換タイプの指定

`-t` オプションで適用する変換タイプを絞り込める。

```bash
# 回転のみ
python scripts/generate_transformed_videos.py input.mp4 -t rotate

# 拡大縮小のみ
python scripts/generate_transformed_videos.py input.mp4 -t scale

# アスペクト比変更のみ
python scripts/generate_transformed_videos.py input.mp4 -t aspect

# PiP（Picture-in-Picture）のみ
python scripts/generate_transformed_videos.py input.mp4 -t pip

# 全変換（デフォルト）
python scripts/generate_transformed_videos.py input.mp4 -t all
```

### オプション

| オプション | 説明 | デフォルト |
|---|---|---|
| `-o`, `--output-dir` | 出力ディレクトリ | `transformed_videos` |
| `-t`, `--type` | 変換タイプ (`all`/`rotate`/`scale`/`aspect`/`pip`) | `all` |
| `--bg-video` | PiP画像背景用の映像ファイルパス | 自動選択 |
| `--overwrite` | 既存ファイルを上書き | スキップ |

### 生成される変換パターン（15種類）

**回転（5種類）**

| パターン | 説明 |
|---|---|
| `rotate_15` | 15度回転（黒余白付き） |
| `rotate_30` | 30度回転（黒余白付き） |
| `rotate_45` | 45度回転（黒余白付き） |
| `rotate_90` | 90度回転 |
| `rotate_180` | 180度回転 |

**拡大縮小（4種類）**

| パターン | 説明 |
|---|---|
| `scale_1.5x` | 1.5倍拡大 |
| `scale_2.0x` | 2.0倍拡大 |
| `scale_0.75x` | 0.75倍縮小 |
| `scale_0.5x` | 0.5倍縮小 |

**アスペクト比（1種類）**

| パターン | 説明 |
|---|---|
| `aspect_4_3` | 16:9 → 4:3 に変換 |

**PiP - Picture-in-Picture（5種類）**

| パターン | 説明 |
|---|---|
| `pip_corner_25pct_noise` | 右下25%サイズ + 静的ノイズ背景 |
| `pip_center_50pct_black` | 中央50%サイズ + 黒背景 |
| `pip_center_33pct_black` | 中央33%サイズ + 黒背景 |
| `pip_center_50pct_image` | 中央50%サイズ + 画像背景 |
| `pip_center_33pct_image` | 中央33%サイズ + 画像背景 |

### 出力ディレクトリ構成

```
output_dir/
├── video1/
│   ├── video1_rotate_15.mp4
│   ├── video1_rotate_30.mp4
│   ├── video1_rotate_45.mp4
│   ├── video1_rotate_90.mp4
│   ├── video1_rotate_180.mp4
│   ├── video1_scale_0.5x.mp4
│   ├── video1_scale_0.75x.mp4
│   ├── video1_scale_1.5x.mp4
│   ├── video1_scale_2.0x.mp4
│   ├── video1_aspect_4_3.mp4
│   ├── video1_pip_corner_25pct_noise.mp4
│   ├── video1_pip_center_50pct_black.mp4
│   ├── video1_pip_center_33pct_black.mp4
│   ├── video1_pip_center_50pct_image.mp4
│   └── video1_pip_center_33pct_image.mp4
└── video2/
    └── ...
```

### PiP画像背景について

PiP画像背景（`pip_center_*_image`）では、別の映像の最初のフレームを背景として使用する。

- 複数映像を指定した場合、自動的に別の映像を背景に選択
- `--bg-video` で明示的に背景映像を指定可能
- 背景映像が指定されていない場合はグレー背景にフォールバック
