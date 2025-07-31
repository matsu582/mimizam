# テストと開発

> 関連するソースファイル

このドキュメントでは、mimizam音声指紋システムに貢献する開発者向けのガイダンスを提供します。テストインフラ、開発環境セットアップ、テスト構成、パフォーマンス評価ワークフローについて説明します。基本的な使用方法とAPIリファレンスについては、[はじめに](./02_getting_started.md)と[APIリファレンス](./04_api_reference.md)を参照してください。

## 開発環境セットアップ

### Python要件

mimizamシステムは`pyproject.toml`で指定されているPython 3.9以上を必要とします。

### 依存関係構造

プロジェクトはコア依存関係とオプションのバックエンド固有パッケージを持つモジュラー依存関係構造を使用しています：

| 依存関係カテゴリ | パッケージ | 目的 |
|-----------------|-----------|------|
| **コア音声処理** | `numpy`, `librosa`, `scipy`, `soundfile`, `numba` | 音声解析と指紋生成 |
| **パフォーマンスライブラリ** | `psutil`, `resampy` | 最適化された数学演算 |
| **テストインフラ** | `testcontainers`, `coverage`, `pytest` | 分離されたテスト環境 |
| **データベースバックエンド** | `mysql-connector-python`, `psycopg-binary`, `elasticsearch` | オプションのデータベースサポート |

### 開発用インストール

```bash
# 開発依存関係を含む完全インストール
pip install -e ".[dev,mysql,postgresql,elasticsearch]"

# 基本開発セットアップ（SQLiteのみ）
pip install -e ".[dev]"

# 特定のバックエンドのみ
pip install -e ".[dev,mysql]"
```

## テストアーキテクチャ

### テストスイート構成

mimizamのテストスイートは、包括的なカバレッジと信頼性の高い実行を確保するために構造化されています：

```
tests/
├── unit/                    # 単体テスト
│   ├── test_audio_fingerprinter.py
│   ├── test_database_layer.py
│   └── test_backends/
├── integration/             # 統合テスト
│   ├── test_end_to_end.py
│   └── test_database_integration.py
├── performance/             # パフォーマンステスト
│   ├── test_fingerprint_speed.py
│   └── test_memory_usage.py
├── fixtures/                # テストデータ
│   ├── audio_samples/
│   └── database_schemas/
└── conftest.py             # 共有フィクスチャ
```

### コアコンポーネントテスト

#### 音声処理パイプラインテスト

音声指紋エンジンの各段階を検証：

```python
def test_spectrogram_generation():
    """スペクトログラム生成の正確性をテスト"""
    fingerprinter = AudioFingerprinter()
    spectrogram = fingerprinter.generate_spectrogram(test_audio_path)
    
    assert spectrogram.shape[0] == expected_frequency_bins
    assert spectrogram.shape[1] == expected_time_frames
    assert np.all(spectrogram >= 0)  # 非負値の確認

def test_peak_detection_accuracy():
    """ピーク検出アルゴリズムの精度をテスト"""
    peaks = fingerprinter.detect_peaks(synthetic_audio)
    
    # 既知の周波数ピークが検出されることを確認
    detected_frequencies = [peak[1] for peak in peaks]
    assert 440 in detected_frequencies  # A4音の検出
```

#### データベース層テスト

各データベースバックエンドの機能を検証：

```python
@pytest.mark.parametrize("backend_type", ["sqlite", "mysql", "postgresql"])
def test_fingerprint_storage_retrieval(backend_type):
    """指紋の保存と取得をテスト"""
    backend = create_test_backend(backend_type)
    database = FingerprintDatabase(backend)
    
    # 指紋保存
    song_id = database.store_song("test_song", test_fingerprints)
    
    # 取得と検証
    retrieved = database.get_song_fingerprints(song_id)
    assert len(retrieved) == len(test_fingerprints)
```

### マッチングシステムテスト

#### 識別精度テスト

```python
def test_identification_accuracy():
    """楽曲識別の精度をテスト"""
    # 既知の楽曲を追加
    song_id = mimizam.add_song(original_audio, "test_song")
    
    # ノイズを追加した音声で識別テスト
    noisy_audio = add_gaussian_noise(original_audio, snr_db=20)
    matches = mimizam.identify_audio_data(noisy_audio, sample_rate)
    
    assert len(matches) > 0
    assert matches[0]['song_id'] == song_id
    assert matches[0]['confidence'] > 0.8
```

#### 統合テスト

```python
def test_complete_workflow():
    """完全なワークフローの統合テスト"""
    # 1. 楽曲追加
    song_ids = []
    for audio_file in test_audio_files:
        song_id = mimizam.add_song(audio_file, f"song_{len(song_ids)}")
        song_ids.append(song_id)
    
    # 2. 各楽曲の識別テスト
    for i, audio_file in enumerate(test_audio_files):
        matches = mimizam.identify(audio_file)
        assert matches[0]['song_id'] == song_ids[i]
```

### パフォーマンステストインフラ

#### Testcontainers統合

実際のデータベース環境での分離されたテスト：

```python
import pytest
from testcontainers.mysql import MySqlContainer
from testcontainers.postgres import PostgresContainer

@pytest.fixture(scope="session")
def mysql_container():
    """MySQL testcontainerの設定"""
    with MySqlContainer("mysql:8.0") as mysql:
        yield mysql

@pytest.fixture(scope="session") 
def postgres_container():
    """PostgreSQL testcontainerの設定"""
    with PostgresContainer("postgres:13") as postgres:
        yield postgres

def test_mysql_performance(mysql_container):
    """MySQL環境でのパフォーマンステスト"""
    connection_url = mysql_container.get_connection_url()
    backend = MySQLBackend.from_url(connection_url)
    
    # 大量データでのパフォーマンステスト
    start_time = time.time()
    for i in range(1000):
        backend.store_fingerprints(f"song_{i}", generate_test_fingerprints())
    
    duration = time.time() - start_time
    assert duration < 30.0  # 30秒以内での完了を期待
```

#### 音声データ生成

```python
def generate_test_audio(duration=10.0, sample_rate=22050):
    """テスト用音声データの生成"""
    t = np.linspace(0, duration, int(sample_rate * duration))
    
    # 複数の周波数成分を持つ複雑な信号
    frequencies = [440, 880, 1320, 1760]  # A4, A5, E6, A6
    audio = np.zeros_like(t)
    
    for freq in frequencies:
        audio += np.sin(2 * np.pi * freq * t) * np.random.uniform(0.5, 1.0)
    
    # ノイズ追加
    noise = np.random.normal(0, 0.1, audio.shape)
    audio = audio + noise
    
    return audio.astype(np.float32)
```

### パフォーマンス指標収集

#### テスト実行ワークフロー

```python
def test_fingerprint_generation_speed():
    """指紋生成速度のベンチマーク"""
    audio_data = generate_test_audio(duration=30.0)
    fingerprinter = AudioFingerprinter()
    
    start_time = time.time()
    fingerprints = fingerprinter.generate_fingerprints_from_data(
        audio_data, 22050
    )
    generation_time = time.time() - start_time
    
    # パフォーマンス指標
    fingerprints_per_second = len(fingerprints) / generation_time
    audio_duration_ratio = 30.0 / generation_time
    
    assert fingerprints_per_second > 100  # 最低100指紋/秒
    assert audio_duration_ratio > 1.0     # リアルタイムより高速
```

### 単体テスト実行

```bash
# 基本的な単体テスト
pytest tests/unit/ -v

# カバレッジ付きテスト
pytest tests/unit/ --cov=src/ --cov-report=html

# 特定のバックエンドテスト
pytest tests/unit/test_backends/test_mysql.py -v

# パフォーマンステスト
pytest tests/performance/ --benchmark-only
```

### Mimizam高レベルAPIテスト

#### エンドツーエンドワークフローテスト

```python
def test_complete_identification_workflow():
    """完全な識別ワークフローのテスト"""
    mimizam = create_mimizam_sqlite(":memory:")
    
    # 1. 楽曲ライブラリの構築
    song_ids = []
    for audio_file in test_audio_collection:
        song_id = mimizam.add_song(audio_file, song_name=audio_file.stem)
        song_ids.append(song_id)
    
    # 2. 識別精度の検証
    for i, audio_file in enumerate(test_audio_collection):
        matches = mimizam.identify(audio_file)
        
        assert len(matches) > 0
        assert matches[0]['song_id'] == song_ids[i]
        assert matches[0]['confidence'] > 0.7

def test_cross_backend_compatibility():
    """複数バックエンド間の互換性テスト"""
    backends = ['sqlite', 'mysql', 'postgresql']
    
    for backend_type in backends:
        mimizam = create_test_mimizam(backend_type)
        
        # 同じ楽曲で同じ結果が得られることを確認
        song_id = mimizam.add_song(reference_audio, "test_song")
        matches = mimizam.identify(reference_audio)
        
        assert matches[0]['song_id'] == song_id
        assert matches[0]['confidence'] > 0.9
```

### テスト実行ワークフロー

#### 単体テスト実行

```bash
# 基本的な単体テスト
pytest tests/unit/ -v

# 特定のコンポーネントテスト
pytest tests/unit/test_audio_fingerprinter.py::test_peak_detection -v

# カバレッジレポート生成
pytest tests/unit/ --cov=src/ --cov-report=html --cov-report=term
```

#### 統合テスト実行

```bash
# データベース統合テスト（testcontainers使用）
pytest tests/integration/ -v --tb=short

# 特定のバックエンドテスト
pytest tests/integration/ -k "mysql" -v

# パフォーマンステスト
pytest tests/performance/ --benchmark-only --benchmark-sort=mean
```

### パフォーマンステスト

#### テストデータ要件

パフォーマンステストには以下のテストデータセットを使用：

```python
# テストデータ生成
def create_performance_test_dataset():
    """パフォーマンステスト用データセット作成"""
    dataset = {
        'short_clips': generate_audio_clips(duration=5.0, count=100),
        'medium_clips': generate_audio_clips(duration=30.0, count=50), 
        'long_clips': generate_audio_clips(duration=180.0, count=10),
        'noisy_clips': add_noise_variants(base_clips, noise_levels=[0.1, 0.3, 0.5])
    }
    return dataset

@pytest.mark.performance
def test_batch_processing_speed():
    """バッチ処理速度のテスト"""
    dataset = create_performance_test_dataset()
    mimizam = create_mimizam_sqlite(":memory:")
    
    start_time = time.time()
    for audio_clip in dataset['medium_clips']:
        mimizam.add_song(audio_clip, song_name=f"song_{len(song_ids)}")
    
    processing_time = time.time() - start_time
    songs_per_second = len(dataset['medium_clips']) / processing_time
    
    assert songs_per_second > 1.0  # 最低1楽曲/秒の処理速度
```

### 継続的統合考慮事項

#### データベースバックエンドテストマトリックス

CI環境では以下のマトリックスでテストを実行：

| Python版 | SQLite | MySQL | PostgreSQL | Elasticsearch |
|----------|--------|-------|------------|---------------|
| 3.9      | ✓      | ✓     | ✓          | ✓             |
| 3.10     | ✓      | ✓     | ✓          | ✓             |
| 3.11     | ✓      | ✓     | ✓          | ✓             |
| 3.12     | ✓      | ✓     | ✓          | ✓             |

#### テスト分類とタグ付け

```python
# テストマーカーの使用例
@pytest.mark.unit
def test_fingerprint_generation():
    """単体テスト"""
    pass

@pytest.mark.integration  
def test_database_integration():
    """統合テスト"""
    pass

@pytest.mark.performance
def test_processing_speed():
    """パフォーマンステスト"""
    pass

@pytest.mark.slow
def test_large_dataset_processing():
    """時間のかかるテスト"""
    pass
```
        full_audio, sr = librosa.load(test_audio_files[0], sr=22050)
        
        # 中間部分を抽出（0.5秒〜1.5秒）
        start_sample = int(0.5 * sr)
        end_sample = int(1.5 * sr)
        partial_audio = full_audio[start_sample:end_sample]
        
        # 部分音声で識別
        matches = mimizam_instance.identify_audio_data(partial_audio, sr)
        
        assert len(matches) > 0
        assert matches[0]['song_id'] == song_id
    
    def test_no_match_scenario(self, mimizam_instance, test_audio_files):
        """マッチしないシナリオテスト"""
        # 1つの楽曲のみ追加
        mimizam_instance.add_song(
            test_audio_files[0],
            song_name="Only Song"
        )
        
        # 異なる楽曲で識別を試行
        matches = mimizam_instance.identify(test_audio_files[1])
        
        # マッチしないか、信頼度が低いことを確認
        if matches:
            assert matches[0]['confidence'] < 0.3
        else:
            assert len(matches) == 0
    
    def test_song_deletion_workflow(self, mimizam_instance, test_audio_files):
        """楽曲削除ワークフローテスト"""
        # 楽曲を追加
        song_id = mimizam_instance.add_song(
            test_audio_files[0],
            song_name="To Be Deleted"
        )
        
        # 削除前の確認
        assert mimizam_instance.get_song_count() == 1
        matches = mimizam_instance.identify(test_audio_files[0])
        assert len(matches) > 0
        
        # 楽曲を削除
        success = mimizam_instance.delete_song(song_id)
        assert success is True
        
        # 削除後の確認
        assert mimizam_instance.get_song_count() == 0
        matches = mimizam_instance.identify(test_audio_files[0])
        assert len(matches) == 0 or matches[0]['confidence'] < 0.1

# 使用例
pytest.main(["-v", "tests/test_integration.py"])
```

## まとめ

テストと開発環境の整備により、mimizamシステムの品質と信頼性を確保できます。

### 主要なテスト手法

- **単体テスト**: 個別コンポーネントの動作確認
- **統合テスト**: システム全体の動作確認
- **パフォーマンステスト**: 性能要件の検証
- **品質保証**: コードカバレッジと継続的インテグレーション

### 開発支援ツール

- **デバッグユーティリティ**: 実行時間とメモリ使用量の監視
- **テストデータ生成**: 一貫したテスト環境の提供
- **自動化**: CI/CDによる品質管理の自動化

### ベストプラクティス

- **テスト駆動開発**: テストを先に書いてから実装
- **継続的テスト**: 変更のたびにテストを実行
- **品質メトリクス**: カバレッジとパフォーマンスの監視
- **ドキュメント**: テストケースの明確な文書化

## 関連ドキュメント

- [コアアーキテクチャ](./03_core_architecture.md) - システムの内部構造
- [APIリファレンス](./04_api_reference.md) - 完全なAPI仕様
- [パフォーマンス最適化](./06_3_performance_optimization.md) - 高速化とチューニング
- [基本的な使用例](./06_1_basic_usage_examples.md) - すぐに使えるサンプルコード
