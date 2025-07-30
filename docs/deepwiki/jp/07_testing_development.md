# テストと開発

> 関連するソースファイル

このドキュメントでは、mimizamシステムのテスト手法、開発環境の構築、デバッグ技術について説明します。品質保証と継続的な開発のためのベストプラクティスを提供します。

## 概要

テストと開発セクションでは、mimizamの開発プロセス、テスト戦略、品質保証手法について包括的に説明します。単体テストから統合テスト、パフォーマンステストまで、実用的なテスト手法を提供します。

## 開発環境の構築

### 1. 開発環境セットアップ

```python
# requirements-dev.txt
pytest>=7.0.0
pytest-cov>=4.0.0
pytest-mock>=3.10.0
pytest-benchmark>=4.0.0
black>=22.0.0
flake8>=5.0.0
mypy>=1.0.0
pre-commit>=2.20.0
jupyter>=1.0.0
matplotlib>=3.5.0
seaborn>=0.11.0
```

```bash
# 開発環境のセットアップ
pip install -r requirements-dev.txt

# pre-commitフックの設定
pre-commit install

# テスト実行
pytest tests/ -v --cov=src/
```

### 2. プロジェクト構造

```
mimizam/
├── src/
│   ├── __init__.py
│   ├── audio_fingerprinter.py
│   ├── fingerprint_database.py
│   ├── backends/
│   └── exceptions.py
├── tests/
│   ├── __init__.py
│   ├── test_audio_fingerprinter.py
│   ├── test_fingerprint_database.py
│   ├── test_backends/
│   ├── fixtures/
│   └── conftest.py
├── examples/
├── docs/
└── scripts/
```

## 単体テスト

### 3. AudioFingerprinterのテスト

```python
# tests/test_audio_fingerprinter.py
import pytest
import numpy as np
import tempfile
import os
from unittest.mock import patch, MagicMock

from src.audio_fingerprinter import AudioFingerprinter
from src.exceptions import AudioProcessingError

class TestAudioFingerprinter:
    """AudioFingerprinterの単体テスト"""
    
    @pytest.fixture
    def fingerprinter(self):
        """テスト用fingerprinterインスタンス"""
        return AudioFingerprinter(
            sample_rate=22050,
            n_fft=2048,
            hop_length=512,
            peak_threshold=0.15
        )
    
    @pytest.fixture
    def sample_audio_data(self):
        """サンプル音声データ"""
        # 1秒間のサイン波を生成
        duration = 1.0
        sample_rate = 22050
        frequency = 440  # A4音
        
        t = np.linspace(0, duration, int(sample_rate * duration))
        audio_data = np.sin(2 * np.pi * frequency * t).astype(np.float32)
        
        return audio_data, sample_rate
    
    @pytest.fixture
    def temp_audio_file(self, sample_audio_data):
        """一時音声ファイル"""
        audio_data, sample_rate = sample_audio_data
        
        # 一時ファイルを作成
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
            temp_path = f.name
        
        # librosで音声ファイルを保存
        import soundfile as sf
        sf.write(temp_path, audio_data, sample_rate)
        
        yield temp_path
        
        # クリーンアップ
        if os.path.exists(temp_path):
            os.unlink(temp_path)
    
    def test_initialization(self):
        """初期化テスト"""
        fingerprinter = AudioFingerprinter(
            sample_rate=44100,
            n_fft=4096,
            peak_threshold=0.2
        )
        
        assert fingerprinter.sample_rate == 44100
        assert fingerprinter.n_fft == 4096
        assert fingerprinter.peak_threshold == 0.2
    
    def test_generate_spectrogram(self, fingerprinter, temp_audio_file):
        """スペクトログラム生成テスト"""
        spectrogram = fingerprinter.generate_spectrogram(temp_audio_file)
        
        # 形状をチェック
        assert spectrogram.ndim == 2
        assert spectrogram.shape[0] > 0  # 周波数ビン
        assert spectrogram.shape[1] > 0  # 時間フレーム
        
        # データ型をチェック
        assert spectrogram.dtype == np.float64
    
    def test_detect_peaks(self, fingerprinter, temp_audio_file):
        """ピーク検出テスト"""
        peaks = fingerprinter.detect_peaks(temp_audio_file)
        
        # ピークが検出されることを確認
        assert isinstance(peaks, list)
        assert len(peaks) > 0
        
        # ピーク形式をチェック
        for peak in peaks[:5]:  # 最初の5個をチェック
            assert isinstance(peak, tuple)
            assert len(peak) == 2
            assert isinstance(peak[0], (int, np.integer))  # time
            assert isinstance(peak[1], (int, np.integer))  # frequency
    
    def test_generate_fingerprints(self, fingerprinter, temp_audio_file):
        """指紋生成テスト"""
        fingerprints = fingerprinter.generate_fingerprints(temp_audio_file)
        
        # 指紋が生成されることを確認
        assert isinstance(fingerprints, list)
        assert len(fingerprints) > 0
        
        # 指紋形式をチェック
        for fp in fingerprints[:5]:
            assert isinstance(fp, dict)
            assert 'hash' in fp
            assert 'time_offset' in fp
            assert isinstance(fp['hash'], (int, np.integer))
            assert isinstance(fp['time_offset'], (float, np.floating))
    
    def test_generate_fingerprints_from_data(self, fingerprinter, sample_audio_data):
        """音声データからの指紋生成テスト"""
        audio_data, sample_rate = sample_audio_data
        
        fingerprints = fingerprinter.generate_fingerprints_from_data(
            audio_data, sample_rate
        )
        
        assert isinstance(fingerprints, list)
        assert len(fingerprints) > 0
    
    def test_file_not_found_error(self, fingerprinter):
        """ファイル未存在エラーテスト"""
        with pytest.raises(AudioProcessingError):
            fingerprinter.generate_fingerprints("nonexistent_file.wav")
    
    @patch('librosa.load')
    def test_audio_loading_error(self, mock_load, fingerprinter):
        """音声読み込みエラーテスト"""
        mock_load.side_effect = Exception("Loading failed")
        
        with pytest.raises(AudioProcessingError):
            fingerprinter.generate_fingerprints("test.wav")
    
    def test_empty_audio_data(self, fingerprinter):
        """空の音声データテスト"""
        empty_audio = np.array([])
        
        with pytest.raises(AudioProcessingError):
            fingerprinter.generate_fingerprints_from_data(empty_audio, 22050)
    
    def test_parameter_validation(self):
        """パラメータ検証テスト"""
        # 無効なサンプリングレート
        with pytest.raises(ValueError):
            AudioFingerprinter(sample_rate=0)
        
        # 無効なFFTサイズ
        with pytest.raises(ValueError):
            AudioFingerprinter(n_fft=0)
        
        # 無効な閾値
        with pytest.raises(ValueError):
            AudioFingerprinter(peak_threshold=-1)
```

### 4. FingerprintDatabaseのテスト

```python
# tests/test_fingerprint_database.py
import pytest
import tempfile
import os
from unittest.mock import Mock, patch

from src.fingerprint_database import FingerprintDatabase
from src.backends.sqlite_backend import SQLiteBackend
from src.exceptions import DatabaseError

class TestFingerprintDatabase:
    """FingerprintDatabaseの単体テスト"""
    
    @pytest.fixture
    def temp_db_path(self):
        """一時データベースファイル"""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            temp_path = f.name
        
        yield temp_path
        
        if os.path.exists(temp_path):
            os.unlink(temp_path)
    
    @pytest.fixture
    def database(self, temp_db_path):
        """テスト用データベース"""
        backend = SQLiteBackend(temp_db_path)
        return FingerprintDatabase(backend)
    
    @pytest.fixture
    def sample_fingerprints(self):
        """サンプル指紋データ"""
        return [
            {'hash': 12345, 'time_offset': 1.0},
            {'hash': 67890, 'time_offset': 2.0},
            {'hash': 11111, 'time_offset': 3.0}
        ]
    
    def test_store_song(self, database, sample_fingerprints):
        """楽曲保存テスト"""
        song_id = database.store_song(
            "Test Song",
            sample_fingerprints,
            artist="Test Artist",
            album="Test Album"
        )
        
        assert isinstance(song_id, int)
        assert song_id > 0
    
    def test_get_song_info(self, database, sample_fingerprints):
        """楽曲情報取得テスト"""
        # 楽曲を保存
        song_id = database.store_song("Test Song", sample_fingerprints)
        
        # 楽曲情報を取得
        song_info = database.get_song_info(song_id)
        
        assert song_info is not None
        assert song_info['id'] == song_id
        assert song_info['name'] == "Test Song"
    
    def test_get_song_count(self, database, sample_fingerprints):
        """楽曲数取得テスト"""
        initial_count = database.get_song_count()
        
        # 楽曲を追加
        database.store_song("Song 1", sample_fingerprints)
        database.store_song("Song 2", sample_fingerprints)
        
        final_count = database.get_song_count()
        assert final_count == initial_count + 2
    
    def test_search_fingerprints(self, database, sample_fingerprints):
        """指紋検索テスト"""
        # 楽曲を保存
        song_id = database.store_song("Test Song", sample_fingerprints)
        
        # 検索用指紋（一部マッチ）
        query_fingerprints = [
            {'hash': 12345, 'time_offset': 1.0},
            {'hash': 99999, 'time_offset': 4.0}  # マッチしない
        ]
        
        matches = database.search_fingerprints(query_fingerprints)
        
        assert isinstance(matches, dict)
        assert song_id in matches
        assert len(matches[song_id]) > 0
    
    def test_delete_song(self, database, sample_fingerprints):
        """楽曲削除テスト"""
        # 楽曲を保存
        song_id = database.store_song("Test Song", sample_fingerprints)
        
        # 削除前の確認
        assert database.get_song_info(song_id) is not None
        
        # 削除実行
        success = database.delete_song(song_id)
        assert success is True
        
        # 削除後の確認
        assert database.get_song_info(song_id) is None
    
    def test_empty_fingerprints(self, database):
        """空の指紋リストテスト"""
        song_id = database.store_song("Empty Song", [])
        
        assert isinstance(song_id, int)
        
        # 検索しても結果が返らないことを確認
        matches = database.search_fingerprints([{'hash': 12345, 'time_offset': 1.0}])
        assert song_id not in matches
    
    def test_backend_error_handling(self, temp_db_path):
        """バックエンドエラーハンドリングテスト"""
        # 無効なバックエンドをモック
        mock_backend = Mock()
        mock_backend.connect.side_effect = Exception("Connection failed")
        
        with pytest.raises(DatabaseError):
            FingerprintDatabase(mock_backend)
    
    def test_duplicate_song_names(self, database, sample_fingerprints):
        """重複楽曲名テスト"""
        # 同じ名前の楽曲を複数保存
        song_id1 = database.store_song("Duplicate Name", sample_fingerprints)
        song_id2 = database.store_song("Duplicate Name", sample_fingerprints)
        
        assert song_id1 != song_id2
        
        # 両方とも取得できることを確認
        song_info1 = database.get_song_info(song_id1)
        song_info2 = database.get_song_info(song_id2)
        
        assert song_info1['name'] == song_info2['name']
        assert song_info1['id'] != song_info2['id']
```

## 統合テスト

### 5. エンドツーエンドテスト

```python
# tests/test_integration.py
import pytest
import tempfile
import os
import numpy as np
import soundfile as sf

from src.mimizam import Mimizam
from src.audio_fingerprinter import AudioFingerprinter
from src.fingerprint_database import FingerprintDatabase
from src.backends.sqlite_backend import SQLiteBackend

class TestIntegration:
    """統合テスト"""
    
    @pytest.fixture
    def temp_db_path(self):
        """一時データベースファイル"""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            temp_path = f.name
        
        yield temp_path
        
        if os.path.exists(temp_path):
            os.unlink(temp_path)
    
    @pytest.fixture
    def mimizam_instance(self, temp_db_path):
        """Mimizamインスタンス"""
        fingerprinter = AudioFingerprinter()
        backend = SQLiteBackend(temp_db_path)
        database = FingerprintDatabase(backend)
        
        return Mimizam(fingerprinter, database)
    
    @pytest.fixture
    def test_audio_files(self):
        """テスト用音声ファイル"""
        files = []
        
        for i, freq in enumerate([440, 880, 1320]):  # A4, A5, E6
            # 音声データを生成
            duration = 2.0
            sample_rate = 22050
            t = np.linspace(0, duration, int(sample_rate * duration))
            audio_data = np.sin(2 * np.pi * freq * t).astype(np.float32)
            
            # 一時ファイルに保存
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
                temp_path = f.name
            
            sf.write(temp_path, audio_data, sample_rate)
            files.append(temp_path)
        
        yield files
        
        # クリーンアップ
        for file_path in files:
            if os.path.exists(file_path):
                os.unlink(file_path)
    
    def test_complete_workflow(self, mimizam_instance, test_audio_files):
        """完全なワークフローテスト"""
        # 1. 楽曲を追加
        song_ids = []
        for i, audio_file in enumerate(test_audio_files):
            song_id = mimizam_instance.add_song(
                audio_file,
                song_name=f"Test Song {i+1}",
                artist=f"Test Artist {i+1}"
            )
            song_ids.append(song_id)
        
        # 2. 楽曲数を確認
        assert mimizam_instance.get_song_count() == len(test_audio_files)
        
        # 3. 各楽曲を識別
        for i, audio_file in enumerate(test_audio_files):
            matches = mimizam_instance.identify(audio_file)
            
            assert len(matches) > 0
            best_match = matches[0]
            assert best_match['song_id'] == song_ids[i]
            assert best_match['confidence'] > 0.5
    
    def test_audio_data_identification(self, mimizam_instance, test_audio_files):
        """音声データ識別テスト"""
        # 楽曲を追加
        song_id = mimizam_instance.add_song(
            test_audio_files[0],
            song_name="Test Song"
        )
        
        # 音声データを読み込み
        import librosa
        audio_data, sr = librosa.load(test_audio_files[0], sr=22050)
        
        # 音声データから識別
        matches = mimizam_instance.identify_audio_data(audio_data, sr)
        
        assert len(matches) > 0
        assert matches[0]['song_id'] == song_id
    
    def test_partial_audio_identification(self, mimizam_instance, test_audio_files):
        """部分音声識別テスト"""
        # 楽曲を追加
        song_id = mimizam_instance.add_song(
            test_audio_files[0],
            song_name="Full Song"
        )
        
        # 音声の一部を切り出し
        import librosa
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
