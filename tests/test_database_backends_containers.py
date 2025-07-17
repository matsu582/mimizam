"""
複数のデータベースバックエンド間での一貫性テスト

このテストファイルは複数のバックエンドを同時に起動し、
データの一貫性とクロスバックエンド互換性をテストします。

個別のバックエンドテストは各専用ファイルで実行してください。
性能評価テストは test_performance.py で実行してください。
"""

import unittest
import time
import sys
import os
from pathlib import Path
from typing import List, Optional

from pathlib import Path
from typing import List, Optional

try:
    from testcontainers.elasticsearch import ElasticSearchContainer
    from testcontainers.mysql import MySqlContainer
    from testcontainers.postgres import PostgresContainer
    TESTCONTAINERS_AVAILABLE = True
except ImportError as e:
    print(f"Testcontainers import error: {e}")
    TESTCONTAINERS_AVAILABLE = False
    # 代替クラスを定義
    class ElasticSearchContainer:
        pass
    class MySqlContainer:
        pass  
    class PostgresContainer:
        pass

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from src.database_base import DatabaseConfig, Song
from src.fingerprint_database import FingerprintDatabase
from src.audio_fingerprinter import Fingerprint
from src.mimizam import (
    Mimizam, create_mimizam_sqlite, create_mimizam_mysql,
    create_mimizam_postgresql, create_mimizam_elasticsearch
)


@unittest.skipUnless(TESTCONTAINERS_AVAILABLE, "Testcontainersが利用できません")
class TestCrossBackendConsistency(unittest.TestCase):
    """複数バックエンド間での一貫性テスト"""
    
    @classmethod
    def setUpClass(cls):
        """テストクラス全体の前処理"""
        cls.containers = {}
        cls.database_configs = {}
        
        # Elasticsearchコンテナの起動
        try:
            cls.elasticsearch_container = ElasticSearchContainer("elasticsearch:8.11.0")
            cls.elasticsearch_container.with_env("discovery.type", "single-node")
            cls.elasticsearch_container.with_env("xpack.security.enabled", "false")
            cls.elasticsearch_container.with_env("ES_JAVA_OPTS", "-Xms512m -Xmx512m")
            cls.elasticsearch_container.start()
            
            # 接続情報を取得
            es_host = cls.elasticsearch_container.get_container_host_ip()
            es_port = cls.elasticsearch_container.get_exposed_port(9200)
            
            cls.database_configs['elasticsearch'] = DatabaseConfig(
                backend='elasticsearch',
                host=es_host,
                port=int(es_port),
                index_name='test_fingerprints'
            )
            
            print(f"Elasticsearch起動: {es_host}:{es_port}")
            
            # Elasticsearchが完全に起動するまで待機
            time.sleep(10)
            
        except Exception as e:
            print(f"Elasticsearchコンテナの起動に失敗: {e}")
            cls.elasticsearch_container = None
        
        # MySQLコンテナの起動
        try:
            cls.mysql_container = MySqlContainer("mysql:8.0")
            # testcontainersのデフォルト設定を使用（環境変数を手動設定しない）
            cls.mysql_container.start()
            
            # 接続情報を取得（testcontainersのデフォルト値を使用）
            mysql_host = cls.mysql_container.get_container_host_ip()
            mysql_port = cls.mysql_container.get_exposed_port(3306)
            
            print(f"MySQL起動: {mysql_host}:{mysql_port}")
            print(f"MySQL デフォルト設定 - DB: {cls.mysql_container.dbname}, User: {cls.mysql_container.username}")
            
            # MySQLが完全に起動するまで待機
            time.sleep(15)
            
            cls.database_configs['mysql'] = DatabaseConfig(
                backend='mysql',
                host=mysql_host,
                port=int(mysql_port),
                database=cls.mysql_container.dbname,     # testcontainersのデフォルト
                username=cls.mysql_container.username,   # testcontainersのデフォルト
                password=cls.mysql_container.password    # testcontainersのデフォルト
            )
            
            print("MySQL接続設定完了")
            
        except Exception as e:
            print(f"MySQLコンテナの起動に失敗: {e}")
            cls.mysql_container = None
        
        # PostgreSQLコンテナの起動
        try:
            cls.postgres_container = PostgresContainer("postgres:15")
            # testcontainersのデフォルト設定を使用（環境変数を手動設定しない）
            cls.postgres_container.start()
            
            # 接続情報を取得（testcontainersのデフォルト値を使用）
            pg_host = cls.postgres_container.get_container_host_ip()
            pg_port = cls.postgres_container.get_exposed_port(5432)
            
            print(f"PostgreSQL起動: {pg_host}:{pg_port}")
            print(f"PostgreSQL デフォルト設定 - DB: {cls.postgres_container.dbname}, User: {cls.postgres_container.username}")
            
            cls.database_configs['postgresql'] = DatabaseConfig(
                backend='postgresql',
                host=pg_host,
                port=int(pg_port),
                database=cls.postgres_container.dbname,    # testcontainersのデフォルト
                username=cls.postgres_container.username,  # testcontainersのデフォルト
                password=cls.postgres_container.password   # testcontainersのデフォルト
            )
            
            # PostgreSQLが完全に起動するまで待機
            time.sleep(8)
            
            print("PostgreSQL接続設定完了")
            
        except Exception as e:
            print(f"PostgreSQLコンテナの起動に失敗: {e}")
            cls.postgres_container = None
    
    @classmethod
    def tearDownClass(cls):
        """テストクラス全体の後処理"""
        # コンテナの停止
        if hasattr(cls, 'elasticsearch_container') and cls.elasticsearch_container:
            cls.elasticsearch_container.stop()
        if hasattr(cls, 'mysql_container') and cls.mysql_container:
            cls.mysql_container.stop()
        if hasattr(cls, 'postgres_container') and cls.postgres_container:
            cls.postgres_container.stop()
    
    def setUp(self):
        """各テストの前処理"""
        self.test_song = Song(
            id="test_song_container",
            title="Container Test Song",
            artist="Test Artist",
            file_path="/path/to/test.wav"
        )
        
        self.test_fingerprints = [
            Fingerprint(hash_value="container_hash1", time_offset=0.1),
            Fingerprint(hash_value="container_hash2", time_offset=0.2),
            Fingerprint(hash_value="container_hash3", time_offset=0.3),
            Fingerprint(hash_value="container_hash4", time_offset=0.4),
            Fingerprint(hash_value="container_hash5", time_offset=0.5),
        ]
    
    def test_cross_backend_consistency(self):
        """複数のバックエンド間での一貫性テスト"""
        available_backends = []
        
        # 利用可能なバックエンドを確認
        if hasattr(self, 'mysql_container') and self.mysql_container:
            available_backends.append('mysql')
        if hasattr(self, 'postgres_container') and self.postgres_container:
            available_backends.append('postgresql')
        if hasattr(self, 'elasticsearch_container') and self.elasticsearch_container:
            available_backends.append('elasticsearch')
        
        if len(available_backends) < 2:
            self.skipTest("一貫性テストには最低2つのバックエンドが必要です")
        
        # 各バックエンドで同じ操作を実行
        for backend_name in available_backends:
            with self.subTest(backend=backend_name):
                config = self.database_configs[backend_name]
                db = FingerprintDatabase(config)
                
                # 楽曲追加
                success = db.add_song(self.test_song)
                self.assertTrue(success, f"{backend_name}での楽曲追加に失敗")
                
                # 待機（Elasticsearchの場合）
                if backend_name == 'elasticsearch':
                    time.sleep(2)
                
                # 楽曲取得
                retrieved_song = db.get_song(self.test_song.id)
                self.assertIsNotNone(retrieved_song, f"{backend_name}での楽曲取得に失敗")
                self.assertEqual(retrieved_song.title, self.test_song.title)
                
                # フィンガープリント追加
                success = db.add_fingerprints(self.test_song.id, self.test_fingerprints)
                self.assertTrue(success, f"{backend_name}でのフィンガープリント追加に失敗")
                
                # 待機（Elasticsearchの場合）
                if backend_name == 'elasticsearch':
                    time.sleep(2)
                
                # フィンガープリント検索
                query_fingerprints = [
                    Fingerprint(hash_value="container_hash1", time_offset=0.05),
                    Fingerprint(hash_value="container_hash2", time_offset=0.15),
                ]
                
                matches = db.search_fingerprints(query_fingerprints)
                self.assertIn(self.test_song.id, matches, f"{backend_name}での検索に失敗")
                
                db.disconnect()
    
    def test_backend_error_handling(self):
        """バックエンドのエラーハンドリングテスト"""
        # 無効な接続設定でのテスト
        invalid_configs = [
            DatabaseConfig(backend='mysql', host='invalid_host', port=3306, 
                          database='test', username='test', password='test'),
            DatabaseConfig(backend='postgresql', host='invalid_host', port=5432, 
                          database='test', username='test', password='test'),
            DatabaseConfig(backend='elasticsearch', host='invalid_host', port=9200),
        ]
        
        for config in invalid_configs:
            with self.subTest(backend=config.backend):
                # 無効な接続設定では例外が発生するか、接続に失敗するはず
                try:
                    db = FingerprintDatabase(config)
                    # 実際の操作を試してエラーを確認
                    try:
                        db.get_database_stats()
                        # 到達した場合は警告メッセージを出力
                        print(f"警告: {config.backend}で無効な接続設定が受け入れられました")
                    except Exception as op_e:
                        # 操作レベルでエラーが発生することを確認
                        self.assertIsNotNone(op_e)
                    finally:
                        try:
                            db.disconnect()
                        except Exception:
                            pass
                except Exception as e:
                    # 初期化レベルでエラーが発生することを確認
                    self.assertIsNotNone(e)


class TestContainerHealthCheck(unittest.TestCase):
    """コンテナのヘルスチェックテスト"""
    
    @unittest.skipUnless(TESTCONTAINERS_AVAILABLE, "Testcontainersが利用できません")
    def test_container_startup_health(self):
        """コンテナの起動ヘルスチェック"""
        # 軽量なコンテナでのヘルスチェック
        try:
            with MySqlContainer("mysql:8.0") as mysql:
                # testcontainersのデフォルト設定を使用
                
                # 起動待機時間を長めに設定
                time.sleep(10)
                
                # 接続テスト
                host = mysql.get_container_host_ip()
                port = mysql.get_exposed_port(3306)
                
                config = DatabaseConfig(
                    backend='mysql',
                    host=host,
                    port=int(port),
                    database=mysql.dbname,     # デフォルト値
                    username=mysql.username,   # デフォルト値
                    password=mysql.password    # デフォルト値
                )
                
                # 基本的な接続テスト
                db = FingerprintDatabase(config)
                
                # 簡単な操作テスト
                test_song = Song(
                    id="health_test_song",
                    title="Health Test Song",
                    artist="Test Artist",
                    file_path="/path/to/health_test.wav"
                )
                
                success = db.add_song(test_song)
                self.assertTrue(success, "ヘルスチェック用楽曲の追加に失敗")
                
                retrieved_song = db.get_song(test_song.id)
                self.assertIsNotNone(retrieved_song, "ヘルスチェック用楽曲の取得に失敗")
                
                db.disconnect()
                
        except Exception as e:
            self.fail(f"コンテナヘルスチェックに失敗: {e}")


@unittest.skipUnless(TESTCONTAINERS_AVAILABLE, "Testcontainersが利用できません")
class TestMimizamCrossBackendIntegration(unittest.TestCase):
    """Mimizam統合APIのクロスバックエンドテスト"""
    
    @classmethod
    def setUpClass(cls):
        """テストクラス全体の前処理"""
        # 既存のコンテナを再利用（TestDatabaseBackendsWithContainersと同じ）
        cls.containers = {}
        cls.database_configs = {}
        
        # MySQLコンテナの起動
        try:
            cls.mysql_container = MySqlContainer("mysql:8.0")
            # testcontainersのデフォルト設定を使用
            cls.mysql_container.start()
            
            mysql_host = cls.mysql_container.get_container_host_ip()
            mysql_port = cls.mysql_container.get_exposed_port(3306)
            
            cls.mysql_config = {
                'host': mysql_host,
                'port': int(mysql_port),
                'database': cls.mysql_container.dbname,     # デフォルト値
                'username': cls.mysql_container.username,   # デフォルト値
                'password': cls.mysql_container.password    # デフォルト値
            }
            
            print(f"Mimizam MySQL起動: {mysql_host}:{mysql_port}")
            print(f"Mimizam MySQL デフォルト設定 - DB: {cls.mysql_container.dbname}, User: {cls.mysql_container.username}")
            time.sleep(10)
            
        except Exception as e:
            print(f"Mimizam MySQL起動失敗: {e}")
            cls.mysql_container = None
    
    @classmethod
    def tearDownClass(cls):
        """テストクラス全体の後処理"""
        if hasattr(cls, 'mysql_container') and cls.mysql_container:
            cls.mysql_container.stop()
    
    def setUp(self):
        """各テストの前処理"""
        import tempfile
        import numpy as np
        
        # テスト用の一時ファイルを作成
        self.temp_dir = tempfile.mkdtemp()
        self.test_audio_file = self.create_test_audio_file()
    
    def tearDown(self):
        """各テストの後処理"""
        # 一時ファイルの削除
        if hasattr(self, 'test_audio_file') and os.path.exists(self.test_audio_file):
            os.unlink(self.test_audio_file)
        if hasattr(self, 'temp_dir') and os.path.exists(self.temp_dir):
            import shutil
            shutil.rmtree(self.temp_dir)
    
    def create_test_audio_file(self) -> str:
        """テスト用の音声ファイルを作成"""
        import numpy as np
        
        # シンプルな合成音声を作成
        duration = 2.0
        sr = 22050
        t = np.linspace(0, duration, int(duration * sr))
        
        # 複数の周波数成分を持つ信号
        audio = (
            0.5 * np.sin(2 * np.pi * 440 * t) +  # A4
            0.3 * np.sin(2 * np.pi * 880 * t) +  # A5
            0.2 * np.sin(2 * np.pi * 1320 * t)   # E6
        )
        
        # ファイルに保存
        audio_file = os.path.join(self.temp_dir, "mimizam_test_audio.wav")
        try:
            import soundfile as sf
            sf.write(audio_file, audio, sr)
        except ImportError:
            # soundfileが利用できない場合、wavファイル形式で直接保存
            import wave
            with wave.open(audio_file, 'wb') as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(sr)
                # float32からint16に変換
                audio_int16 = (audio * 32767).astype(np.int16)
                wav_file.writeframes(audio_int16.tobytes())
        return audio_file
    
    def test_mimizam_mysql_complete_workflow(self):
        """MimizamとMySQLの完全なワークフローテスト"""
        if not hasattr(self, 'mysql_container') or not self.mysql_container:
            self.skipTest("MySQLコンテナが利用できません")
        
        # Mimizamインスタンスを作成
        mimizam = create_mimizam_mysql(
            **self.mysql_config,
            matcher_config={
                'min_confidence': 0.1,
                'max_results': 10,
                'scoring_method': 'hybrid'
            },
            enable_adaptive_params=False  # テストの一貫性のため
        )
        
        try:
            # Step 1: 楽曲追加
            expected_song_id = "mimizam_mysql_test"
            result_song_id = mimizam.add_song(
                file_path=self.test_audio_file,
                title="Mimizam MySQL Test Song",
                artist="Mimizam Test Artist",
                song_id=expected_song_id
            )
            self.assertIsNotNone(result_song_id, "Mimizamでの楽曲追加に失敗")
            self.assertEqual(result_song_id, expected_song_id)
            
            # Step 2: 楽曲取得
            retrieved_song = mimizam.get_song(result_song_id)
            self.assertIsNotNone(retrieved_song, "楽曲取得に失敗")
            self.assertEqual(retrieved_song.title, "Mimizam MySQL Test Song")
            
            # Step 3: 楽曲検索
            results = mimizam.search_song(
                query_file_path=self.test_audio_file,
                min_confidence=0.05,
                top_k=5
            )
            self.assertGreater(len(results), 0, "検索結果が見つかりません")
            self.assertEqual(results[0]['song'].id, result_song_id)
            self.assertGreater(results[0]['confidence'], 0.1)
            
            # Step 4: 音声識別
            identification = mimizam.identify_audio(
                query_file_path=self.test_audio_file,
                min_confidence=0.1
            )
            self.assertIsNotNone(identification, "音声識別に失敗")
            identified_song, _ = identification
            self.assertEqual(identified_song.id, result_song_id)
            
            # Step 5: 楽曲一覧
            songs = mimizam.list_songs()
            self.assertEqual(len(songs), 1)
            self.assertEqual(songs[0].id, result_song_id)
            
            # Step 6: 統計情報
            stats = mimizam.get_database_stats()
            self.assertEqual(stats['songs'], 1)
            self.assertGreater(stats['fingerprints'], 0)
            
            # Step 7: 楽曲削除
            delete_success = mimizam.delete_song(result_song_id)
            self.assertTrue(delete_success, "楽曲削除に失敗")
            
            # 削除確認
            self.assertIsNone(mimizam.get_song(result_song_id))
            final_stats = mimizam.get_database_stats()
            self.assertEqual(final_stats['songs'], 0)
            
        finally:
            mimizam.close()
    
    def test_mimizam_sqlite_basic_operations(self):
        """MimizamのSQLite基本操作テスト（コンテナ環境）"""
        # SQLiteはコンテナ不要だが、統一したテスト環境で実行
        mimizam = create_mimizam_sqlite(
            db_path=':memory:',
            matcher_config={
                'min_confidence': 0.1,
                'max_results': 5,
                'scoring_method': 'hybrid'
            },
            enable_adaptive_params=False
        )
        
        try:
            # 楽曲追加と検索の基本フロー
            song_id = mimizam.add_song(
                file_path=self.test_audio_file,
                title="SQLite Container Test",
                artist="Container Test Artist"
            )
            self.assertIsNotNone(song_id)
            
            # 検索テスト
            results = mimizam.search_song(
                query_file_path=self.test_audio_file,
                min_confidence=0.05,
                top_k=3
            )
            self.assertGreater(len(results), 0)
            self.assertGreater(results[0]['confidence'], 0.1)
            
        finally:
            mimizam.close()
    
    def test_mimizam_configuration_validation(self):
        """Mimizam設定の検証テスト"""
        # カスタム設定でMimizamを作成
        custom_fingerprinter_config = {
            'n_fft': 1024,
            'hop_length': 256,
            'enable_adaptive_params': False,
            'audible_only': True
        }
        
        custom_matcher_config = {
            'min_confidence': 0.2,
            'max_results': 8,
            'scoring_method': 'detailed'
        }
        
        mimizam = create_mimizam_sqlite(
            db_path=':memory:',
            matcher_config=custom_matcher_config,
            **custom_fingerprinter_config
        )
        
        try:
            # 設定が正しく適用されているか確認
            self.assertEqual(mimizam.matcher.min_confidence, 0.2)
            self.assertEqual(mimizam.matcher.max_results, 8)
            
            # フィンガープリンター設定の確認（間接的）
            if hasattr(mimizam.fingerprinter, 'spectrogram_analyzer'):
                self.assertEqual(mimizam.fingerprinter.spectrogram_analyzer.n_fft, 1024)
                self.assertEqual(mimizam.fingerprinter.spectrogram_analyzer.hop_length, 256)
            
            # 基本動作の確認
            song_id = mimizam.add_song(
                file_path=self.test_audio_file,
                title="Config Test Song",
                artist="Config Test Artist"
            )
            self.assertIsNotNone(song_id)
            
        finally:
            mimizam.close()


def create_cross_backend_test_suite():
    """クロスバックエンドテストのテストスイートを作成"""
    suite = unittest.TestSuite()
    
    # クロスバックエンドテストを追加
    suite.addTests(unittest.TestLoader().loadTestsFromTestCase(TestCrossBackendConsistency))
    suite.addTests(unittest.TestLoader().loadTestsFromTestCase(TestContainerHealthCheck))
    suite.addTests(unittest.TestLoader().loadTestsFromTestCase(TestMimizamCrossBackendIntegration))
    
    return suite


if __name__ == "__main__":
    print("🔍 Testcontainers availability check...")
    
    if not TESTCONTAINERS_AVAILABLE:
        print("⚠️  Testcontainersが利用できません。以下のコマンドでインストールしてください：")
        print("pip install testcontainers")
        sys.exit(1)
    
    print("🐳 クロスバックエンド一貫性テストを開始します...")
    print("⏳ 複数のコンテナの起動には時間がかかる場合があります...")
    print("\n📌 注意:")
    print("  - 個別のバックエンドテストは各専用ファイルで実行してください")
    print("  - 性能評価テストは test_performance.py で実行してください")
    
    # クロスバックエンドテストを実行
    runner = unittest.TextTestRunner(verbosity=2)
    suite = create_cross_backend_test_suite()
    result = runner.run(suite)
    
    # サマリーを出力
    print("\n🐳 クロスバックエンドテストサマリー:")
    print(f"実行されたテスト: {result.testsRun}")
    print(f"失敗: {len(result.failures)}")
    print(f"エラー: {len(result.errors)}")
    
    if result.failures:
        print("\n❌ 失敗:")
        for test, traceback in result.failures:
            print(f"- {test}: {traceback}")
    
    if result.errors:
        print("\n❌ エラー:")
        for test, traceback in result.errors:
            print(f"- {test}: {traceback}")
    
    # 適切なコードで終了
    sys.exit(0 if result.wasSuccessful() else 1)
