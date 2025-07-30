# テストと開発

このページでは、mimizamプロジェクトのテストスイートと開発環境について説明します。単体テスト、統合テスト、パフォーマンステストの実行方法と、開発環境のセットアップについて詳しく解説します。

基本的な使用方法については、[基本的な使用例](./14_basic_usage_examples.md)を参照してください。パフォーマンス分析については、[パフォーマンス分析](./18_performance_analysis.md)を参照してください。

## テストスイート概要

### テスト構成

mimizamプロジェクトは以下のテストカテゴリで構成されています：

| テストタイプ | ディレクトリ | 目的 |
|-------------|-------------|------|
| **単体テスト** | `tests/unit/` | 個別コンポーネントの機能検証 |
| **統合テスト** | `tests/integration/` | コンポーネント間の連携検証 |
| **パフォーマンステスト** | `tests/performance/` | 性能要件の検証 |
| **エンドツーエンドテスト** | `tests/e2e/` | 全体フローの検証 |

### テスト実行

```bash
# 全テスト実行
python -m pytest

# 特定カテゴリのテスト実行
python -m pytest tests/unit/
python -m pytest tests/integration/
python -m pytest tests/performance/

# カバレッジ付きテスト実行
python -m pytest --cov=src --cov-report=html

# 詳細出力
python -m pytest -v --tb=short
```

## 単体テスト

### AudioFingerprinterテスト

```python
import pytest
import numpy as np
from src.audio_fingerprinter import AudioFingerprinter

class TestAudioFingerprinter:
    """AudioFingerprinterの単体テスト"""
    
    def setup_method(self):
        """テストセットアップ"""
        self.fingerprinter = AudioFingerprinter(
            n_fft=1024,
            hop_length=512,
            min_amplitude=-60
        )
    
    def test_fingerprint_generation(self):
        """指紋生成テスト"""
        # テスト音声ファイル
        test_audio_file = "tests/data/test_audio.wav"
        
        fingerprints = self.fingerprinter.generate_fingerprints(test_audio_file)
        
        # 基本検証
        assert isinstance(fingerprints, list)
        assert len(fingerprints) > 0
        
        # 指紋形式検証
        for hash_value, time_offset in fingerprints:
            assert isinstance(hash_value, str)
            assert len(hash_value) == 64  # SHA-256ハッシュ長
            assert isinstance(time_offset, float)
            assert time_offset >= 0
    
    def test_empty_audio_handling(self):
        """空音声の処理テスト"""
        # 無音ファイル
        silent_audio_file = "tests/data/silent.wav"
        
        fingerprints = self.fingerprinter.generate_fingerprints(silent_audio_file)
        
        # 無音では指紋が生成されないことを確認
        assert len(fingerprints) == 0
    
    def test_invalid_file_handling(self):
        """無効ファイルの処理テスト"""
        with pytest.raises(FileNotFoundError):
            self.fingerprinter.generate_fingerprints("nonexistent.wav")
    
    def test_parameter_validation(self):
        """パラメータ検証テスト"""
        # 無効なパラメータでの初期化
        with pytest.raises(ValueError):
            AudioFingerprinter(n_fft=0)
        
        with pytest.raises(ValueError):
            AudioFingerprinter(hop_length=-1)
    
    @pytest.mark.parametrize("n_fft,hop_length", [
        (512, 256),
        (1024, 512),
        (2048, 1024),
    ])
    def test_different_parameters(self, n_fft, hop_length):
        """異なるパラメータでのテスト"""
        fingerprinter = AudioFingerprinter(n_fft=n_fft, hop_length=hop_length)
        
        test_audio_file = "tests/data/test_audio.wav"
        fingerprints = fingerprinter.generate_fingerprints(test_audio_file)
        
        assert isinstance(fingerprints, list)
```

### FingerprintDatabaseテスト

```python
import pytest
import tempfile
import os
from src.fingerprint_database import FingerprintDatabase
from src.backends.sqlite_backend import SQLiteBackend

class TestFingerprintDatabase:
    """FingerprintDatabaseの単体テスト"""
    
    def setup_method(self):
        """テストセットアップ"""
        # 一時データベースファイル
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_db.close()
        
        backend = SQLiteBackend(self.temp_db.name)
        self.database = FingerprintDatabase(backend)
    
    def teardown_method(self):
        """テストクリーンアップ"""
        self.database.close()
        os.unlink(self.temp_db.name)
    
    def test_song_addition(self):
        """楽曲追加テスト"""
        song_id = self.database.add_song(
            "tests/data/test_audio.wav",
            "Test Song",
            "Test Artist"
        )
        
        assert isinstance(song_id, int)
        assert song_id > 0
        
        # 楽曲取得テスト
        song = self.database.get_song_by_id(song_id)
        assert song is not None
        assert song.title == "Test Song"
        assert song.artist == "Test Artist"
    
    def test_duplicate_song_handling(self):
        """重複楽曲の処理テスト"""
        # 同じ楽曲を2回追加
        song_id1 = self.database.add_song(
            "tests/data/test_audio.wav",
            "Test Song",
            "Test Artist"
        )
        
        song_id2 = self.database.add_song(
            "tests/data/test_audio.wav",
            "Test Song",
            "Test Artist"
        )
        
        # 異なるIDが割り当てられることを確認
        assert song_id1 != song_id2
    
    def test_song_search(self):
        """楽曲検索テスト"""
        # テストデータ追加
        self.database.add_song("tests/data/song1.wav", "Song One", "Artist A")
        self.database.add_song("tests/data/song2.wav", "Song Two", "Artist B")
        self.database.add_song("tests/data/song3.wav", "Another Song", "Artist A")
        
        # タイトル検索
        results = self.database.search_songs_by_title("Song")
        assert len(results) == 3
        
        # アーティスト検索
        results = self.database.search_songs_by_artist("Artist A")
        assert len(results) == 2
    
    def test_song_deletion(self):
        """楽曲削除テスト"""
        song_id = self.database.add_song(
            "tests/data/test_audio.wav",
            "Test Song",
            "Test Artist"
        )
        
        # 削除実行
        success = self.database.delete_song(song_id)
        assert success
        
        # 削除確認
        song = self.database.get_song_by_id(song_id)
        assert song is None
    
    def test_database_statistics(self):
        """データベース統計テスト"""
        # 初期状態
        stats = self.database.get_database_stats()
        assert stats['song_count'] == 0
        assert stats['fingerprint_count'] == 0
        
        # 楽曲追加後
        self.database.add_song("tests/data/test_audio.wav", "Test Song", "Test Artist")
        
        stats = self.database.get_database_stats()
        assert stats['song_count'] == 1
        assert stats['fingerprint_count'] > 0
```

## 統合テスト

### エンドツーエンド識別テスト

```python
import pytest
from mimizam import create_mimizam_sqlite
import tempfile
import os

class TestEndToEndIdentification:
    """エンドツーエンド識別テスト"""
    
    def setup_method(self):
        """テストセットアップ"""
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_db.close()
        
        self.mimizam = create_mimizam_sqlite(self.temp_db.name)
    
    def teardown_method(self):
        """テストクリーンアップ"""
        self.mimizam.close()
        os.unlink(self.temp_db.name)
    
    def test_basic_identification_workflow(self):
        """基本的な識別ワークフローテスト"""
        # 楽曲追加
        song_id = self.mimizam.add_song(
            "tests/data/reference_song.wav",
            "Reference Song",
            "Test Artist"
        )
        
        assert song_id > 0
        
        # 同じ楽曲の一部を識別
        result = self.mimizam.identify_audio("tests/data/query_clip.wav")
        
        assert result is not None
        song, confidence = result
        assert song.id == song_id
        assert confidence > 0.5  # 50%以上の信頼度
    
    def test_multiple_songs_identification(self):
        """複数楽曲での識別テスト"""
        # 複数楽曲を追加
        songs = [
            ("tests/data/song1.wav", "Song 1", "Artist 1"),
            ("tests/data/song2.wav", "Song 2", "Artist 2"),
            ("tests/data/song3.wav", "Song 3", "Artist 3"),
        ]
        
        song_ids = []
        for file_path, title, artist in songs:
            song_id = self.mimizam.add_song(file_path, title, artist)
            song_ids.append(song_id)
        
        # 各楽曲のクエリで識別テスト
        query_files = [
            "tests/data/query1.wav",
            "tests/data/query2.wav",
            "tests/data/query3.wav",
        ]
        
        for i, query_file in enumerate(query_files):
            result = self.mimizam.identify_audio(query_file)
            
            assert result is not None
            song, confidence = result
            assert song.id == song_ids[i]
    
    def test_no_match_scenario(self):
        """マッチしないシナリオのテスト"""
        # 楽曲追加
        self.mimizam.add_song("tests/data/song1.wav", "Song 1", "Artist 1")
        
        # 全く異なる音声で識別
        result = self.mimizam.identify_audio("tests/data/different_audio.wav")
        
        # マッチしないことを確認
        assert result is None
    
    def test_low_quality_audio_identification(self):
        """低品質音声の識別テスト"""
        # 高品質楽曲を追加
        song_id = self.mimizam.add_song(
            "tests/data/high_quality.wav",
            "High Quality Song",
            "Test Artist"
        )
        
        # 低品質クエリで識別
        result = self.mimizam.identify_audio("tests/data/low_quality_query.wav")
        
        if result:
            song, confidence = result
            assert song.id == song_id
            # 低品質でも最低限の信頼度を期待
            assert confidence > 0.2
```

### データベースバックエンドテスト

```python
import pytest
from mimizam import (
    create_mimizam_sqlite,
    create_mimizam_mysql,
    create_mimizam_postgresql
)

class TestDatabaseBackends:
    """データベースバックエンドテスト"""
    
    @pytest.mark.parametrize("backend_factory", [
        lambda: create_mimizam_sqlite(":memory:"),
        # MySQL/PostgreSQLは環境に応じて有効化
        # lambda: create_mimizam_mysql("localhost", "test_db", "user", "pass"),
        # lambda: create_mimizam_postgresql("localhost", "test_db", "user", "pass"),
    ])
    def test_backend_compatibility(self, backend_factory):
        """バックエンド互換性テスト"""
        try:
            mimizam = backend_factory()
        except Exception:
            pytest.skip("Backend not available")
        
        try:
            # 基本操作テスト
            song_id = mimizam.add_song(
                "tests/data/test_audio.wav",
                "Test Song",
                "Test Artist"
            )
            
            assert song_id > 0
            
            # 楽曲取得
            song = mimizam.get_song_by_id(song_id)
            assert song is not None
            assert song.title == "Test Song"
            
            # 識別テスト
            result = mimizam.identify_audio("tests/data/query_clip.wav")
            # 結果の形式確認（マッチするかは問わない）
            assert result is None or (len(result) == 2 and isinstance(result[1], float))
            
        finally:
            mimizam.close()
```

## パフォーマンステスト

### ベンチマークテスト

```python
import pytest
import time
from mimizam import create_mimizam_sqlite

class TestPerformance:
    """パフォーマンステスト"""
    
    def setup_method(self):
        """テストセットアップ"""
        self.mimizam = create_mimizam_sqlite(":memory:")
    
    def teardown_method(self):
        """テストクリーンアップ"""
        self.mimizam.close()
    
    def test_fingerprint_generation_speed(self):
        """指紋生成速度テスト"""
        test_file = "tests/data/test_audio_30sec.wav"
        
        start_time = time.time()
        song_id = self.mimizam.add_song(test_file, "Test Song", "Test Artist")
        end_time = time.time()
        
        processing_time = end_time - start_time
        
        # 30秒音声の処理が10秒以内に完了することを期待
        assert processing_time < 10.0
        assert song_id > 0
    
    def test_identification_speed(self):
        """識別速度テスト"""
        # 楽曲追加
        self.mimizam.add_song("tests/data/reference.wav", "Reference", "Artist")
        
        query_file = "tests/data/query_10sec.wav"
        
        start_time = time.time()
        result = self.mimizam.identify_audio(query_file)
        end_time = time.time()
        
        identification_time = end_time - start_time
        
        # 10秒クエリの識別が2秒以内に完了することを期待
        assert identification_time < 2.0
    
    def test_batch_processing_performance(self):
        """バッチ処理性能テスト"""
        test_files = [
            f"tests/data/batch_test_{i}.wav" 
            for i in range(10)
        ]
        
        start_time = time.time()
        
        for i, file_path in enumerate(test_files):
            self.mimizam.add_song(file_path, f"Song {i}", f"Artist {i}")
        
        end_time = time.time()
        
        total_time = end_time - start_time
        avg_time_per_song = total_time / len(test_files)
        
        # 1楽曲あたり平均5秒以内の処理を期待
        assert avg_time_per_song < 5.0
    
    @pytest.mark.slow
    def test_large_database_performance(self):
        """大規模データベース性能テスト"""
        # 100楽曲を追加
        for i in range(100):
            self.mimizam.add_song(
                f"tests/data/large_test_{i}.wav",
                f"Song {i}",
                f"Artist {i % 10}"  # 10アーティストに分散
            )
        
        # 識別性能テスト
        start_time = time.time()
        result = self.mimizam.identify_audio("tests/data/large_query.wav")
        end_time = time.time()
        
        identification_time = end_time - start_time
        
        # 100楽曲データベースでも5秒以内の識別を期待
        assert identification_time < 5.0
```

### メモリ使用量テスト

```python
import psutil
import os

class TestMemoryUsage:
    """メモリ使用量テスト"""
    
    def get_memory_usage(self):
        """現在のメモリ使用量を取得"""
        process = psutil.Process(os.getpid())
        return process.memory_info().rss / 1024 / 1024  # MB
    
    def test_memory_leak_detection(self):
        """メモリリーク検出テスト"""
        initial_memory = self.get_memory_usage()
        
        # 繰り返し処理
        for i in range(10):
            mimizam = create_mimizam_sqlite(":memory:")
            
            # 楽曲追加
            mimizam.add_song("tests/data/test_audio.wav", f"Song {i}", "Artist")
            
            # 識別
            mimizam.identify_audio("tests/data/query.wav")
            
            # クリーンアップ
            mimizam.close()
        
        final_memory = self.get_memory_usage()
        memory_increase = final_memory - initial_memory
        
        # メモリ増加が50MB以下であることを確認
        assert memory_increase < 50
    
    def test_large_file_memory_usage(self):
        """大きなファイルのメモリ使用量テスト"""
        initial_memory = self.get_memory_usage()
        
        mimizam = create_mimizam_sqlite(":memory:")
        
        # 大きな音声ファイル処理
        mimizam.add_song("tests/data/large_audio_10min.wav", "Large Song", "Artist")
        
        peak_memory = self.get_memory_usage()
        memory_usage = peak_memory - initial_memory
        
        mimizam.close()
        
        # 10分音声でもメモリ使用量が500MB以下であることを確認
        assert memory_usage < 500
```

## 開発環境セットアップ

### 開発依存関係

```bash
# 開発用依存関係のインストール
pip install -r requirements-dev.txt

# 主要な開発ツール
pip install pytest pytest-cov pytest-benchmark
pip install black isort flake8 mypy
pip install pre-commit
```

### コード品質チェック

```bash
# コードフォーマット
black src/ tests/
isort src/ tests/

# リント
flake8 src/ tests/

# 型チェック
mypy src/

# 全品質チェック
make lint  # Makefileで定義
```

### 継続的インテグレーション

```yaml
# .github/workflows/test.yml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: [3.9, 3.10, 3.11]
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python ${{ matrix.python-version }}
      uses: actions/setup-python@v3
      with:
        python-version: ${{ matrix.python-version }}
    
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -r requirements.txt
        pip install -r requirements-dev.txt
    
    - name: Run tests
      run: |
        pytest --cov=src --cov-report=xml
    
    - name: Upload coverage
      uses: codecov/codecov-action@v3
```

## テストデータ管理

### テストデータ生成

```python
import numpy as np
import librosa
import soundfile as sf

def generate_test_audio(duration=10, sr=22050, frequency=440):
    """テスト用音声データを生成"""
    t = np.linspace(0, duration, int(sr * duration))
    
    # 基本波形
    audio = np.sin(2 * np.pi * frequency * t)
    
    # ノイズ追加
    noise = np.random.normal(0, 0.1, len(audio))
    audio = audio + noise
    
    # 正規化
    audio = audio / np.max(np.abs(audio))
    
    return audio, sr

def create_test_dataset():
    """テストデータセットを作成"""
    test_data_dir = "tests/data"
    os.makedirs(test_data_dir, exist_ok=True)
    
    # 基本テスト音声
    audio, sr = generate_test_audio(duration=30, frequency=440)
    sf.write(f"{test_data_dir}/test_audio.wav", audio, sr)
    
    # クエリ音声（一部抽出）
    query_audio = audio[sr*5:sr*15]  # 5-15秒部分
    sf.write(f"{test_data_dir}/query_clip.wav", query_audio, sr)
    
    # 無音ファイル
    silent_audio = np.zeros(sr * 5)
    sf.write(f"{test_data_dir}/silent.wav", silent_audio, sr)
    
    # 異なる周波数の音声
    for i, freq in enumerate([220, 330, 550, 660]):
        audio, sr = generate_test_audio(duration=20, frequency=freq)
        sf.write(f"{test_data_dir}/song{i+1}.wav", audio, sr)

if __name__ == "__main__":
    create_test_dataset()
```

## 関連ドキュメント

- [基本的な使用例](./14_basic_usage_examples.md) - 基本的な使用方法
- [パフォーマンス最適化](./16_performance_optimization.md) - 高速化技術
- [パフォーマンス分析](./18_performance_analysis.md) - 性能測定と分析
- [コアアーキテクチャ](./03_core_architecture.md) - システム全体の構成
