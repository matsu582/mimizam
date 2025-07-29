# テスト

mimizamプロジェクトの包括的なテスト戦略とテスト実装について詳しく解説します。単体テスト、統合テスト、パフォーマンステスト、コンテナテストなど、品質保証のための多層的なテストアプローチを提供します。

## 🧪 テスト戦略の概要

### テスト階層

```
テスト階層
├── 単体テスト (Unit Tests)
│   ├── 音声指紋生成テスト
│   ├── データベース操作テスト
│   └── ユーティリティ関数テスト
├── 統合テスト (Integration Tests)
│   ├── バックエンド統合テスト
│   ├── API統合テスト
│   └── エンドツーエンドテスト
├── パフォーマンステスト
│   ├── 処理速度テスト
│   ├── メモリ使用量テスト
│   └── スケーラビリティテスト
└── コンテナテスト
    ├── MySQLコンテナテスト
    ├── PostgreSQLコンテナテスト
    └── Elasticsearchコンテナテスト
```

## 🔬 単体テスト

### AudioFingerprinter テスト

```python
import unittest
import numpy as np
from mimizam import AudioFingerprinter, Peak, Fingerprint

class TestAudioFingerprinter(unittest.TestCase):
    """AudioFingerprinter単体テスト"""
    
    def setUp(self):
        """テスト前準備"""
        self.fingerprinter = AudioFingerprinter()
        self.test_audio = np.random.randn(22050)  # 1秒のテスト音声
        
    def test_fingerprint_generation(self):
        """指紋生成テスト"""
        fingerprints = self.fingerprinter.fingerprint_audio(self.test_audio)
        
        # 指紋が生成されることを確認
        self.assertIsInstance(fingerprints, list)
        self.assertGreater(len(fingerprints), 0)
        
        # 各指紋の形式確認
        for fp in fingerprints:
            self.assertIsInstance(fp, Fingerprint)
            self.assertIsInstance(fp.hash, int)
            self.assertIsInstance(fp.time_offset, float)
    
    def test_empty_audio_handling(self):
        """空音声データの処理テスト"""
        empty_audio = np.array([])
        
        with self.assertRaises(ValueError):
            self.fingerprinter.fingerprint_audio(empty_audio)
    
    def test_short_audio_handling(self):
        """短い音声データの処理テスト"""
        short_audio = np.random.randn(1000)  # 0.045秒
        
        fingerprints = self.fingerprinter.fingerprint_audio(short_audio)
        # 短い音声でも処理できることを確認
        self.assertIsInstance(fingerprints, list)
    
    def test_numba_optimization(self):
        """Numba最適化テスト"""
        # 最適化なし
        fp_normal = AudioFingerprinter(enable_numba_optimization=False)
        fingerprints_normal = fp_normal.fingerprint_audio(self.test_audio)
        
        # 最適化あり
        fp_optimized = AudioFingerprinter(enable_numba_optimization=True)
        fingerprints_optimized = fp_optimized.fingerprint_audio(self.test_audio)
        
        # 結果の一貫性確認
        self.assertEqual(len(fingerprints_normal), len(fingerprints_optimized))
    
    def test_parameter_validation(self):
        """パラメータ検証テスト"""
        # 無効なパラメータでの初期化
        with self.assertRaises(ValueError):
            AudioFingerprinter(n_fft=0)
        
        with self.assertRaises(ValueError):
            AudioFingerprinter(hop_length=0)
        
        with self.assertRaises(ValueError):
            AudioFingerprinter(min_amplitude=0)  # 正の値は無効

class TestFingerprintDatabase(unittest.TestCase):
    """FingerprintDatabase単体テスト"""
    
    def setUp(self):
        """テスト前準備"""
        from mimizam import DatabaseConfig
        from mimizam.database_backends import create_backend
        
        # テスト用インメモリデータベース
        config = DatabaseConfig(backend='sqlite', file_path=':memory:')
        self.backend = create_backend(config)
        self.backend.connect()
        self.backend.create_tables()
        
        from mimizam import FingerprintDatabase
        self.db = FingerprintDatabase(config)
    
    def tearDown(self):
        """テスト後クリーンアップ"""
        if hasattr(self, 'backend'):
            self.backend.disconnect()
    
    def test_song_addition(self):
        """楽曲追加テスト"""
        from mimizam import Song
        
        song = Song(
            id="test_001",
            title="Test Song",
            artist="Test Artist",
            file_path="test.wav"
        )
        
        # 楽曲追加
        result = self.db.add_song_with_fingerprints(song, [])
        self.assertTrue(result)
        
        # 楽曲一覧確認
        songs = self.db.list_songs()
        self.assertEqual(len(songs), 1)
        self.assertEqual(songs[0].title, "Test Song")
    
    def test_fingerprint_search(self):
        """指紋検索テスト"""
        from mimizam import Song, Fingerprint
        
        # テストデータ準備
        song = Song(
            id="test_002",
            title="Search Test Song",
            artist="Search Artist",
            file_path="search_test.wav"
        )
        
        fingerprints = [
            Fingerprint(hash=12345, time_offset=1.0),
            Fingerprint(hash=67890, time_offset=2.0)
        ]
        
        # データ追加
        self.db.add_song_with_fingerprints(song, fingerprints)
        
        # 検索実行
        query_fingerprints = [
            Fingerprint(hash=12345, time_offset=1.0)
        ]
        
        results = self.db.search_fingerprints(query_fingerprints)
        
        # 結果確認
        self.assertGreater(len(results), 0)
        self.assertEqual(results[0]['song']['title'], "Search Test Song")

# テスト実行例
if __name__ == '__main__':
    # 基本テストスイート
    basic_suite = unittest.TestSuite()
    basic_suite.addTest(unittest.makeSuite(TestAudioFingerprinter))
    basic_suite.addTest(unittest.makeSuite(TestFingerprintDatabase))
    
    # テスト実行
    runner = unittest.TextTestRunner(verbosity=2)
    
    print("=== 基本テスト実行 ===")
    basic_result = runner.run(basic_suite)
    
    # 結果サマリー
    total_tests = basic_result.testsRun
    total_failures = len(basic_result.failures)
    total_errors = len(basic_result.errors)
    
    print(f"\n=== テスト結果サマリー ===")
    print(f"実行テスト数: {total_tests}")
    print(f"成功: {total_tests - total_failures - total_errors}")
    print(f"失敗: {total_failures}")
    print(f"エラー: {total_errors}")
```

## 🧪 統合テスト

### エンドツーエンドテスト

```python
class TestEndToEnd(unittest.TestCase):
    """エンドツーエンド統合テスト"""
    
    def setUp(self):
        """テスト環境準備"""
        from mimizam import create_mimizam_sqlite
        import tempfile
        
        # 一時データベースファイル
        self.temp_db = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        self.temp_db.close()
        
        self.mimizam = create_mimizam_sqlite(self.temp_db.name)
        
        # テスト音声データ生成
        self.test_audio_data = self._generate_test_audio()
        
    def tearDown(self):
        """テスト後クリーンアップ"""
        import os
        if os.path.exists(self.temp_db.name):
            os.unlink(self.temp_db.name)
    
    def _generate_test_audio(self) -> Dict[str, np.ndarray]:
        """テスト用音声データ生成"""
        import numpy as np
        
        # 異なる特性の音声データを生成
        test_data = {}
        
        # 1. 正弦波ベース
        t = np.linspace(0, 5, 22050 * 5)  # 5秒
        test_data['sine_wave'] = np.sin(2 * np.pi * 440 * t)  # A4音
        
        # 2. ノイズベース
        test_data['noise'] = np.random.randn(22050 * 3)  # 3秒
        
        # 3. 複合波形
        test_data['complex'] = (
            np.sin(2 * np.pi * 440 * t[:22050*2]) +
            0.5 * np.sin(2 * np.pi * 880 * t[:22050*2]) +
            0.1 * np.random.randn(22050 * 2)
        )
        
        return test_data
    
    def test_complete_workflow(self):
        """完全ワークフローテスト"""
        
        # 1. 楽曲追加フェーズ
        song_ids = []
        for name, audio in self.test_audio_data.items():
            # 一時ファイルに保存
            import tempfile
            import soundfile as sf
            
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
                sf.write(temp_file.name, audio, 22050)
                
                # 楽曲追加
                song_id = self.mimizam.add_song(
                    file_path=temp_file.name,
                    title=f"Test Song {name}",
                    artist="Test Artist"
                )
                
                song_ids.append(song_id)
                
                # 一時ファイル削除
                os.unlink(temp_file.name)
        
        # 楽曲が正しく追加されたことを確認
        songs = self.mimizam.list_songs()
        self.assertEqual(len(songs), len(self.test_audio_data))
        
        # 2. 検索フェーズ
        for name, audio in self.test_audio_data.items():
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
                sf.write(temp_file.name, audio, 22050)
                
                # 同じ音声で検索
                results = self.mimizam.search_song(temp_file.name, min_confidence=0.1)
                
                # 結果確認
                self.assertGreater(len(results), 0, f"検索結果なし: {name}")
                
                # 最高信頼度の結果が元の楽曲であることを確認
                best_match = results[0]
                self.assertIn(name, best_match['song']['title'])
                
                os.unlink(temp_file.name)

# 使用例
def setup_test_logging():
    """テストログ設定"""
    import logging
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('test_results.log'),
            logging.StreamHandler()
        ]
    )
    
    return logging.getLogger(__name__)

def run_mimizam_tests(include_containers=False, include_performance=False):
    """mimizamテスト実行"""
    import unittest
    import time
    
    logger = setup_test_logging()
    logger.info("=== mimizam テストスイート実行開始 ===")
    
    test_results = {}
    
    # 基本テスト
    test_results['unit'] = run_unit_tests()
    test_results['integration'] = run_integration_tests()
    
    # オプションテスト
    if include_containers:
        test_results['containers'] = run_container_tests()
    
    if include_performance:
        test_results['performance'] = run_performance_tests()
    
    # レポート生成
    report = generate_test_report(test_results)
    
    logger.info("=== テストスイート実行完了 ===")
    
    return report

def run_unit_tests():
    """単体テスト実行"""
    import unittest
    import os
    
    logger = setup_test_logging()
    logger.info("単体テスト実行中...")
    
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(TestAudioFingerprinter))
    suite.addTest(unittest.makeSuite(TestFingerprintDatabase))
    
    runner = unittest.TextTestRunner(stream=open(os.devnull, 'w'))
    result = runner.run(suite)
    
    return {
        'tests_run': result.testsRun,
        'failures': len(result.failures),
        'errors': len(result.errors),
        'success_rate': (result.testsRun - len(result.failures) - len(result.errors)) / result.testsRun * 100 if result.testsRun > 0 else 0
    }

def run_integration_tests():
    """統合テスト実行"""
    import unittest
    
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(TestMimizamIntegration))
    
    runner = unittest.TextTestRunner(stream=open(os.devnull, 'w'))
    result = runner.run(suite)
    
    return {
        'tests_run': result.testsRun,
        'failures': len(result.failures),
        'errors': len(result.errors),
        'success_rate': (result.testsRun - len(result.failures) - len(result.errors)) / result.testsRun * 100 if result.testsRun > 0 else 0
    }

def run_container_tests():
    """コンテナテスト実行"""
    # 簡易実装
    return {
        'tests_run': 0,
        'failures': 0,
        'errors': 0,
        'success_rate': 100
    }

def run_performance_tests():
    """パフォーマンステスト実行"""
    # 簡易実装
    return {
        'tests_run': 0,
        'failures': 0,
        'errors': 0,
        'success_rate': 100
    }

def generate_test_report(test_results: dict):
    """テストレポート生成"""
    import time
    
    report = []
    report.append("=" * 60)
    report.append("mimizam テスト実行レポート")
    report.append("=" * 60)
    report.append(f"実行日時: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    report.append("")
    
    total_tests = 0
    total_failures = 0
    total_errors = 0
    
    for test_type, results in test_results.items():
        report.append(f"【{test_type.upper()}テスト】")
        report.append(f"  実行数: {results['tests_run']}")
        report.append(f"  失敗数: {results['failures']}")
        report.append(f"  エラー数: {results['errors']}")
        report.append(f"  成功率: {results['success_rate']:.1f}%")
        report.append("")
        
        total_tests += results['tests_run']
        total_failures += results['failures']
        total_errors += results['errors']
    
    # 全体サマリー
    overall_success_rate = (total_tests - total_failures - total_errors) / total_tests * 100 if total_tests > 0 else 0
    
    report.append("【全体サマリー】")
    report.append(f"  総テスト数: {total_tests}")
    report.append(f"  成功: {total_tests - total_failures - total_errors}")
    report.append(f"  失敗: {total_failures}")
    report.append(f"  エラー: {total_errors}")
    report.append(f"  全体成功率: {overall_success_rate:.1f}%")
    
    report.append("")
    report.append("=" * 60)
    
    return "\n".join(report)

# 使用例
if __name__ == '__main__':
    # 基本テストのみ実行
    report = run_mimizam_tests()
    print(report)
```

## 🔗 関連ドキュメント

- [パフォーマンステスト](./23_performance_testing.md) - 性能テスト詳細
- [品質保証](./24_quality_assurance.md) - 品質管理プロセス
- [デバッグとトラブルシューティング](./21_debugging.md) - 問題解決
- [プロジェクト構造](./06_project_structure.md) - テスト構成

## 💡 テストのベストプラクティス

### 1. テスト設計
- 適切なテスト分類と階層化
- 独立性と再現性の確保
- エッジケースの網羅

### 2. テスト実行
- 自動化された継続的テスト
- 並列実行による効率化
- 環境分離によるクリーンテスト

### 3. テスト保守
- テストコードの品質維持
- 定期的なテスト見直し
- ドキュメントとの同期

mimizamプロジェクトの品質を保証するため、これらのテスト手法を継続的に活用してください。
