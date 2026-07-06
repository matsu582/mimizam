# mimizam

**mimizam**は音声指紋（Audio Fingerprinting）と映像指紋（Video Fingerprinting）のためのPython実装です。音声はShazam風アルゴリズムでユニークな指紋を生成し、映像はAKAZE特徴量＋VLAD＋PCAでフレーム単位の指紋を生成します。いずれもデータベースと照合することで高精度な識別を実現します。

[![Python](https://img.shields.io/badge/python-3.9+-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Coverage](https://img.shields.io/badge/coverage-73%25-yellowgreen.svg)]()

## 主な機能

- **高精度音声指紋生成**: Shazamアルゴリズムベースの指紋生成
- **映像指紋生成**: AKAZE特徴量＋VLAD＋PCAによるフレーム単位指紋と、フレーム単位ANN投票による部分クリップ検索
- **音声＋映像の統合検索**: 音声・映像の一致を統合スコアで評価（位置乖離チェック付き）
- **適応パラメータ最適化**: 音声特性に応じた自動パラメータ調整
- **マルチデータベース対応**: SQLite、MySQL、MariaDB、PostgreSQL、Elasticsearch（映像指紋のANNはsqlite-vec / pgvector / Elasticsearch dense_vector / MariaDBネイティブVECTORを使用）
- **リアルタイム音声識別**: 短い音声クリップから楽曲を特定
- **可視化機能**: スペクトログラムとピーク検出の可視化

## クイックスタート

### インストール

```bash
# リポジトリをクローン
git clone https://github.com/animalmatsuzawa/mimizam.git
cd mimizam

# 依存関係をインストール
pip install -r requirements.txt

# パッケージをインストール（開発モード）
pip install -e .
```

映像指紋機能に必要な依存（`opencv-contrib-python` / `scikit-learn` / `scenedetect`）はコア依存に含まれています。既定バックエンドSQLiteのANNに必須の`sqlite-vec`もコア依存です。

> **OpenCVについて**: 映像指紋はAKAZEを使用するため`opencv-contrib-python`が必須です（`opencv-python`とは競合するため入れないでください）。AKAZEはOpenCV 4.xでは`cv2.AKAZE_create`、OpenCV 5.xでは`cv2.xfeatures2d.AKAZE_create`として提供され、mimizamは両対応です。

### 基本的な使用方法

```python
from mimizam import create_mimizam_sqlite

# SQLiteを使用した簡単なセットアップ
with create_mimizam_sqlite("my_music.db") as mimizam:
    # 楽曲をデータベースに追加
    song_id = mimizam.add_song("path/to/song.wav", "My Song", "Artist Name")
    print(f"楽曲が追加されました (ID: {song_id})")
    
    # 音声検索
    results = mimizam.search_song("path/to/query.wav", min_confidence=0.3)
    for result in results:
        song = result['song']
        confidence = result['confidence']
        print(f"発見: {song.title} by {song.artist} (信頼度: {confidence:.2%})")
    
    # 音声識別（最も可能性の高い楽曲）
    identified = mimizam.identify_audio("path/to/query.wav")
    if identified:
        song, confidence = identified
        print(f"識別結果: {song.title} (信頼度: {confidence:.2%})")
```

### 映像の基本的な使用方法

```python
from mimizam import create_mimizam_sqlite

with create_mimizam_sqlite("my_media.db") as mimizam:
    # 映像指紋の実行時設定（環境変数ではなくクラス機能として設定）
    mimizam.configure_video(scene_eval_fps=4.0, profile_frames=False)

    # 学習済みコードブック/PCAモデルを読み込み（推奨）
    mimizam.load_video_model("model/codebook_model.npz")

    # 映像を登録
    # （モデル未読込の場合は初回登録映像でモデルを自作するが、
    #   単一映像から学習したコードブックは品質が低い。上記の
    #   学習済みモデル読み込みを強く推奨。）
    video_id = mimizam.add_video("path/to/video.mp4", "My Video")

    # 映像で検索（フレーム単位ANN投票→精密照合、PiP矩形検出付き）
    results = mimizam.search_video("path/to/clip.mp4", top_k=5)
    for result in results:
        print(result)
```

学習済みコードブックモデル（`model/codebook_model.npz`）を使うCLIツールも同梱しています。

```bash
# 映像の登録（音声＋映像の統合指紋を登録）
python examples/movie_fingerprinter.py path/to/video.mp4 --database ./media.db

# 生AKAZE記述子をDBに保存しつつ登録する。
# モデル更新後に指紋を再生成（rebuild_video_fingerprints）したい場合は必須。
# DB容量が増える点に注意。
python examples/movie_fingerprinter.py path/to/video.mp4 --database ./media.db \
    --model ./model/codebook_model.npz --store-descriptors

# 映像で統合検索（音声＋映像）
python examples/movie_search.py -D -k 10 -m ./model/codebook_model.npz \
    path/to/clip.mp4 --database ./media.db
```

### デモの実行

```bash
# デモ用音声ファイルを生成
python scripts/create_demo_audio.py

# Mimizamデモを実行
python examples/mimizam_demo.py

```

## アーキテクチャ

### コア技術

1. **スペクトログラム生成**: 短時間フーリエ変換（STFT）による時間-周波数解析
2. **適応ピーク検出**: 音声特性に応じた動的閾値によるスペクトルピーク抽出
3. **ハッシュベース指紋**: アンカー・ターゲットピークペアからSHA-256ハッシュ生成
4. **インテリジェントマッチング**: 時間アライメントと信頼度スコアリング

### 映像指紋

1. **シーン/キーフレーム選定**: `scene_eval_fps`で間引いた評価フレームに対しPySceneDetect（`ContentDetector`）でカットを検出。加えて定期サンプリングも実施
2. **AKAZE特徴量抽出**: キーフレームごとに局所AKAZE（MLDB）記述子を抽出（`opencv-contrib-python`が必須）。AKAZEを採用したのは、回転・スケール・輝度変化（再エンコードやPiP縮小）に頑健で、非線形拡散スケール空間により圧縮ぼけ下でもエッジを保存でき、バイナリMLDB記述子が省メモリかつ高速照合（1,000フレームで約100万記述子規模でも実用的）で、SURFのような特許制約がなくOpenCV 4.x/5.x双方で利用可能、さらに古典的アルゴリズムのためGPU不要でCPUのみで動作する（ALIKED/DISK/LightGlue等の深層学習特徴量と異なりGPUやモデル重みが不要）ためです。詳細な理由は[仕様書](docs/video_fingerprint_spec.md)を参照。
3. **VLAD＋PCAエンコード**: 学習済みコードブック上でVLADにより記述子を集約してフレーム単位指紋を生成し、PCAで次元削減
4. **フレーム単位ANN投票**: クエリの各フレームがバックエンドのベクトルANNで近傍を取得し、映像別に得票/類似度を集計。その後、時間整合区間を精密照合で確認（PiP矩形検出付き）

## データベースバックエンド

mimizamは複数のデータベースに対応：

```python
from mimizam import (
    create_mimizam_sqlite,
    create_mimizam_mysql,
    create_mimizam_mariadb,
    create_mimizam_postgresql,
    create_mimizam_elasticsearch
)

# SQLite（簡単・高速・推奨。映像ANNはsqlite-vec）
mimizam = create_mimizam_sqlite("fingerprints.db")

# MySQL（拡張性。映像ANNは総当たり）
mimizam = create_mimizam_mysql(
    host="localhost", database="music_db",
    username="user", password="pass"
)

# MariaDB（11.7+のネイティブVECTOR索引で映像ANN）
mimizam = create_mimizam_mariadb(
    host="localhost", database="music_db",
    username="user", password="pass"
)

# PostgreSQL（高性能。映像ANNはpgvector）
mimizam = create_mimizam_postgresql(
    host="localhost", database="music_db",
    username="user", password="pass"
)

# Elasticsearch（分散検索。映像ANNはdense_vector kNN）
mimizam = create_mimizam_elasticsearch(
    host="localhost", index_name="music_index"
)
```

映像指紋のフレーム近傍検索（ANN）は、SQLite=`sqlite-vec`、PostgreSQL=`pgvector`、Elasticsearch=`dense_vector`、MariaDB=ネイティブ`VECTOR`索引を用います。MySQLはネイティブANN索引が無いため全フレーム総当たりで同一形式の結果を返します。

## プロジェクト構造

```
mimizam/
├── src/
│   ├── mimizam.py                    # 統合高レベルAPI
│   ├── audio_fingerprinter.py        # 音声指紋生成
│   ├── fingerprint_database.py       # データベース管理
│   ├── database_backends.py          # 統一バックエンド
│   ├── adaptive_parameters.py        # 適応パラメータ調整
│   └── backends/                     # 個別バックエンド実装
│   ├── video_fingerprinter.py        # 映像指紋生成（AKAZE+VLAD+PCA）
│   ├── video_database.py             # 映像指紋データベース
│   ├── pip_detector.py               # PiP（ワイプ）矩形検出
│   └── backends/                     # 個別バックエンド実装（sqlite/mysql/mariadb/postgresql/elasticsearch）
├── examples/
│   ├── mimizam_demo.py               # 音声APIデモ
│   ├── movie_fingerprinter.py        # 映像＋音声の統合指紋登録CLI
│   ├── movie_search.py               # 映像＋音声の統合検索CLI
│   ├── audio_from_video_fingerprinter.py        # 動画から音声を抽出して音声指紋を登録
│   ├── audio_from_video_search.py               # 動画から抽出した音声で検索
│   ├── visual_from_video_fingerprinter.py       # 動画から映像（視覚）指紋を登録
│   └── visual_from_video_search.py              # 映像（視覚）指紋で検索
├── model/                            # 学習済みコードブックモデル
├── test_media/                       # デモ用音声ファイル
├── tests/                           # テストスイート
├── docs/                            # ドキュメント
└── scripts/                         # ユーティリティ（モデル学習・DB移行等）
```

## 使用例

### 音声検索
```python
# 短い音声クリップから楽曲を識別
results = mimizam.search_song("humming.wav", top_k=3)
```

### カスタム音声読み込み

```python
import numpy as np

# 独自の音声データから指紋生成
audio_data = np.array([...])  # 音声サンプル
fingerprints = fingerprinter.fingerprint_audio(audio_data, sr=22050)
```

### 音声登録

```python
import glob
from pathlib import Path

# ファイルの登録処理
audio_files = glob.glob("music/*.wav")
with create_mimizam_sqlite("batch.db") as mimizam:
    for file_path in audio_files:
        title = Path(file_path).stem
        mimizam.add_song(file_path, title, "Unknown Artist")
```

### 可視化

```python
# スペクトログラムとピーク検出の可視化
audio = fingerprinter.load_audio("song.wav")
fingerprinter.visualize_analysis(audio, title="song.wav")
```

### カスタム設定

```python
# 高精度設定
fingerprinter = AudioFingerprinter(
    n_fft=4096,           # より高い周波数解像度
    hop_length=256,       # より細かい時間解像度
    min_amplitude=-50     # より敏感な検出
)
```

## 性能向上のヒント

1. **音声品質**: 高品質音声（44.1kHz以上）で最良結果
2. **サンプル長**: 10秒以上で識別精度向上
3. **適応パラメータ**: enable_adaptive_params=Trueで高速化
4. **データベース選択**: 小規模ならSQLite、大規模ならPostgreSQL

## テスト

```bash
# 全テスト実行
python run_tests.py

```

## ドキュメント

詳細なドキュメントは`docs/`ディレクトリに含まれています：

- [映像指紋の仕様](docs/video_fingerprint_spec.md)
- [データベースセットアップ](docs/DATABASE_SETUP.md)
- [指紋生成詳細](docs/fingerprint_generation_details.md)
- [指紋スコアリング詳細](docs/fingerprint_scoring_details.md)

## ライセンス

mimizamは[MITライセンス](LICENSE)の下で公開されています。

## 謝辞

- [Avery Li-Chun Wang](https://www.ee.columbia.edu/~dpwe/papers/Wang03-shazam.pdf)によるオリジナルShazamアルゴリズム
- 音声処理ライブラリ[librosa](https://librosa.org/)
- 各種オープンソース音声指紋実装からのインスピレーション
  - [dejavu GitHub](https://github.com/worldveil/dejavu)
  - [audfprint GitHub](https://github.com/dpwe/audfprint)

## 参考文献

- Wang, A. L. C. (2003). "An Industrial Strength Audio Search Algorithm"
- Ellis, D. P. W. (2009). "Robust Landmark-Based Audio Fingerprinting"
- Cano, P. et al. (2005). "A Review of Audio Fingerprinting"

---

**注意**: この実装は個人の趣味で作成されました。商用システムと同等の性能を保証するものではありません。

