# よくある質問（FAQ）

mimizamプロジェクトの使用、開発、トラブルシューティングに関してよく寄せられる質問とその回答をまとめました。初心者から上級者まで、様々なレベルの質問に対応しています。

基本的な使用方法については、[基本的な使用例](./14_basic_usage_examples.md)を参照してください。技術的な詳細については、[コアアーキテクチャ](./03_core_architecture.md)を参照してください。

## 🚀 基本的な使用方法

### Q1. mimizamとは何ですか？

mimizamは、音声指紋技術を使用した音楽識別システムです。Shazamアルゴリズムをベースに、音声ファイルから特徴的な指紋を生成し、短い音声クリップから楽曲を識別できます。

主な機能：
- 音声指紋の生成と保存
- 短い音声クリップからの楽曲識別
- 複数のデータベースバックエンド対応
- 高精度な音声マッチング

### Q2. mimizamをインストールするにはどうすればよいですか？

現在、mimizamはGitHubリポジトリからのインストールのみサポートしています：

```bash
# リポジトリをクローン
git clone https://github.com/animalmatsuzawa/mimizam.git
cd mimizam

# 依存関係をインストール
pip install -r requirements.txt

# 開発モードでインストール
pip install -e .
```

詳細なインストール手順については、[インストールガイド](./02_installation.md)を参照してください。

### Q3. 最初に何をすればよいですか？

基本的な使用例から始めることをお勧めします：

```python
from mimizam import create_mimizam_sqlite

# SQLiteデータベースを作成
with create_mimizam_sqlite("my_music.db") as mimizam:
    # 楽曲を追加
    song_id = mimizam.add_song("song.wav", "Song Title", "Artist Name")
    
    # 音声を識別
    result = mimizam.identify_audio("query.wav")
    
    if result:
        song, confidence = result
        print(f"識別結果: {song.title} by {song.artist} ({confidence:.2%})")
```

### Q4. どのような音声形式がサポートされていますか？

mimizamは以下の音声形式をサポートしています：

| 形式 | 拡張子 | 備考 |
|------|--------|------|
| WAV | .wav | 推奨形式 |
| MP3 | .mp3 | 一般的な圧縮形式 |
| FLAC | .flac | 無損失圧縮 |
| M4A | .m4a | Apple形式 |
| OGG | .ogg | オープンソース形式 |

内部的にはlibrosaを使用しているため、librosaがサポートする形式であれば処理可能です。

### Q5. 識別精度を向上させるにはどうすればよいですか？

識別精度を向上させる方法：

1. **高品質な音声を使用**
   - サンプリングレート: 44.1kHz以上
   - ビット深度: 16bit以上
   - ノイズの少ない音声

2. **適切なパラメータ設定**
   ```python
   mimizam = create_mimizam_sqlite(
       "precision.db",
       n_fft=4096,           # 大きなFFTサイズ
       hop_length=256,       # 小さなホップ長
       min_amplitude=-70,    # 厳しい振幅閾値
       enable_adaptive_params=True
   )
   ```

3. **十分な長さのクエリ音声**
   - 最低5秒以上の音声を推奨
   - 10-15秒あれば高い精度が期待できる

## 🗄️ データベースとストレージ

### Q6. どのデータベースを選択すればよいですか？

用途に応じてデータベースを選択してください：

| 用途 | 推奨データベース | 理由 |
|------|-----------------|------|
| 開発・テスト | SQLite | セットアップが簡単 |
| 小〜中規模本番 | MySQL | 安定性と性能のバランス |
| 大規模・高性能 | PostgreSQL | 高度な機能と性能 |
| 分散・検索重視 | Elasticsearch | スケーラビリティ |

詳細は[データベースバックエンド](./09_database_backends.md)を参照してください。

### Q7. データベースのサイズはどの程度になりますか？

楽曲1曲あたりの指紋数とデータベースサイズの目安：

| 楽曲長 | 指紋数 | SQLiteサイズ | 備考 |
|--------|--------|-------------|------|
| 3分 | 約1,000個 | 約100KB | 一般的な楽曲 |
| 5分 | 約1,500個 | 約150KB | 長めの楽曲 |
| 10分 | 約3,000個 | 約300KB | 長い楽曲 |

1,000曲のライブラリで約100-150MBのデータベースサイズになります。

### Q8. データベースをバックアップするにはどうすればよいですか？

データベースタイプ別のバックアップ方法：

**SQLite:**
```bash
# ファイルコピー
cp music.db music_backup.db

# SQLダンプ
sqlite3 music.db .dump > backup.sql
```

**MySQL:**
```bash
mysqldump -u user -p database_name > backup.sql
```

**PostgreSQL:**
```bash
pg_dump -U user database_name > backup.sql
```

## ⚡ パフォーマンスと最適化

### Q9. 処理速度を向上させるにはどうすればよいですか？

パフォーマンス向上の方法：

1. **パラメータ調整**
   ```python
   # 高速処理用設定
   mimizam = create_mimizam_sqlite(
       "fast.db",
       n_fft=1024,        # 小さなFFTサイズ
       hop_length=512,    # 大きなホップ長
       min_amplitude=-50  # 緩い閾値
   )
   ```

2. **バッチ処理の活用**
   ```python
   # トランザクション内で複数楽曲を処理
   with mimizam.database.backend.transaction():
       for file_path, title, artist in song_list:
           mimizam.add_song(file_path, title, artist)
   ```

3. **適切なデータベース選択**
   - 大量データ: PostgreSQL
   - 高速検索: Elasticsearch

### Q10. メモリ使用量を削減するにはどうすればよいですか？

メモリ使用量削減の方法：

1. **ストリーミング処理**（大きなファイル用）
2. **バッチサイズの調整**
3. **不要なデータの定期削除**
4. **適切なガベージコレクション**

詳細は[パフォーマンス最適化](./16_performance_optimization.md)を参照してください。

### Q11. Numba最適化は使用できますか？

現在、Numba JIT最適化は無効化されています。これは以下の理由によります：

- 期待された性能向上が得られなかった
- ピークオーバーフロー問題が発生した
- 標準のPython実装で十分な性能が得られている

将来的に改善される可能性がありますが、現在は標準実装を使用してください。

## 🔧 トラブルシューティング

### Q12. 音声ファイルが読み込めません

音声ファイル読み込みエラーの対処法：

1. **ファイル形式の確認**
   ```python
   import librosa
   try:
       audio, sr = librosa.load("audio_file.wav")
       print(f"読み込み成功: {len(audio)} サンプル, {sr}Hz")
   except Exception as e:
       print(f"読み込みエラー: {e}")
   ```

2. **ファイルパスの確認**
   - 絶対パスを使用
   - ファイルの存在確認
   - 権限の確認

3. **依存関係の確認**
   ```bash
   pip install librosa soundfile
   ```

### Q13. 識別結果が返されません

識別が失敗する原因と対処法：

1. **音声品質の問題**
   - ノイズが多い
   - 音量が小さすぎる
   - 圧縮による劣化

2. **データベースの問題**
   - 参照楽曲が登録されていない
   - 指紋生成に失敗している

3. **パラメータの調整**
   ```python
   # より緩い条件で識別
   result = mimizam.identify_audio("query.wav", min_confidence=0.1)
   ```

### Q14. データベース接続エラーが発生します

データベース接続エラーの対処法：

1. **SQLite**
   - ファイルパスの確認
   - 書き込み権限の確認
   - ディスク容量の確認

2. **MySQL/PostgreSQL**
   - サーバーの起動確認
   - 認証情報の確認
   - ネットワーク接続の確認

3. **Elasticsearch**
   - サービスの起動確認
   - ポート番号の確認
   - インデックス設定の確認

### Q15. メモリ不足エラーが発生します

メモリ不足の対処法：

1. **大きなファイルの分割処理**
2. **バッチサイズの削減**
3. **不要なオブジェクトの削除**
4. **システムメモリの増設**

## 🛠️ 開発とカスタマイゼーション

### Q16. カスタムデータベースバックエンドを作成できますか？

はい、`DatabaseBackend`クラスを継承してカスタムバックエンドを作成できます：

```python
from src.database_base import DatabaseBackend

class CustomBackend(DatabaseBackend):
    def connect(self):
        # カスタム接続処理
        pass
    
    def execute_query(self, query, params=()):
        # カスタムクエリ実行
        pass
```

詳細は[低レベルコンポーネント](./08_low_level_components.md)を参照してください。

### Q17. 音声処理パラメータをカスタマイズできますか？

はい、`AudioFingerprinter`の初期化時にパラメータを指定できます：

```python
fingerprinter = AudioFingerprinter(
    n_fft=2048,                    # FFTサイズ
    hop_length=512,                # ホップ長
    min_amplitude=-60,             # 最小振幅閾値
    peak_neighborhood_size=20,     # ピーク検出近傍サイズ
    target_zone_size=5,            # ターゲットゾーンサイズ
    time_range=200                 # 時間範囲
)
```

### Q18. テストを実行するにはどうすればよいですか？

テストスイートの実行方法：

```bash
# 全テスト実行
python -m pytest

# カバレッジ付きテスト
python -m pytest --cov=src --cov-report=html

# 特定テストのみ実行
python -m pytest tests/unit/test_audio_fingerprinter.py
```

詳細は[テストと開発](./17_testing_development.md)を参照してください。

## 🌐 統合と応用

### Q19. Web APIとして使用できますか？

mimizamをWeb APIとして使用する例：

```python
from flask import Flask, request, jsonify
from mimizam import create_mimizam_sqlite

app = Flask(__name__)
mimizam = create_mimizam_sqlite("web_api.db")

@app.route('/identify', methods=['POST'])
def identify_audio():
    audio_file = request.files['audio']
    
    # 一時ファイルに保存
    temp_path = f"/tmp/{audio_file.filename}"
    audio_file.save(temp_path)
    
    # 識別実行
    result = mimizam.identify_audio(temp_path)
    
    if result:
        song, confidence = result
        return jsonify({
            'success': True,
            'song': {
                'title': song.title,
                'artist': song.artist,
                'confidence': confidence
            }
        })
    else:
        return jsonify({'success': False})

if __name__ == '__main__':
    app.run(debug=True)
```

### Q20. 動画ファイルから音声を抽出して処理できますか？

はい、動画処理機能をサポートしています：

```python
import moviepy.editor as mp

def extract_and_identify(video_path):
    # 動画から音声を抽出
    video = mp.VideoFileClip(video_path)
    audio_path = "extracted_audio.wav"
    video.audio.write_audiofile(audio_path)
    
    # 音声識別
    with create_mimizam_sqlite("video_music.db") as mimizam:
        result = mimizam.identify_audio(audio_path)
        return result
```

詳細は[動画処理](./15_video_processing.md)を参照してください。

## 📊 ライセンスとコントリビューション

### Q21. mimizamのライセンスは何ですか？

mimizamのライセンス情報については、リポジトリのLICENSEファイルを確認してください。

### Q22. プロジェクトに貢献するにはどうすればよいですか？

コントリビューションの方法：

1. **Issue報告**
   - バグ報告
   - 機能要求
   - ドキュメント改善提案

2. **プルリクエスト**
   - バグ修正
   - 新機能追加
   - ドキュメント改善

3. **テストとフィードバック**
   - 異なる環境でのテスト
   - パフォーマンステスト
   - 使用感のフィードバック

## 🔗 関連リソース

### Q23. さらに詳しい情報はどこで入手できますか？

詳細な技術情報については、以下のドキュメントを参照してください：

- [コアアーキテクチャ](./03_core_architecture.md) - システム全体の構成
- [音声指紋エンジン](./04_audio_fingerprinting_engine.md) - 音声処理の詳細
- [データベース層](./05_database_layer.md) - データベース抽象化
- [高レベルAPI](./07_high_level_api.md) - 簡単な使用方法
- [パフォーマンス最適化](./16_performance_optimization.md) - 高速化技術

### Q24. コミュニティやサポートはありますか？

現在、主なサポートチャネルは以下の通りです：

- **GitHub Issues**: バグ報告や機能要求
- **GitHub Discussions**: 一般的な質問や議論
- **ドキュメント**: 包括的な技術文書

## 関連ドキュメント

- [基本的な使用例](./14_basic_usage_examples.md) - 実践的なサンプルコード
- [インストールガイド](./02_installation.md) - セットアップ手順
- [コアアーキテクチャ](./03_core_architecture.md) - システム全体の理解
- [パフォーマンス最適化](./16_performance_optimization.md) - 高速化技術
- [テストと開発](./17_testing_development.md) - 開発環境とテスト
