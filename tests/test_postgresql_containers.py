"""
PostgreSQLコンテナを使用したインテグレーションテスト
"""

import unittest
import time
import sys
import os
from pathlib import Path

try:
    from testcontainers.postgres import PostgresContainer
    TESTCONTAINERS_AVAILABLE = True
except ImportError:
    TESTCONTAINERS_AVAILABLE = False

from mimizam import DatabaseConfig, Song
from mimizam import FingerprintDatabase
from mimizam import Fingerprint
from mimizam import create_mimizam_postgresql
sys.path.append(os.path.dirname(__file__))
from test_utils import TestAudioMixin


@unittest.skipUnless(TESTCONTAINERS_AVAILABLE, "Testcontainersが利用できません")
class TestPostgreSQLContainers(TestAudioMixin, unittest.TestCase):
    """PostgreSQLコンテナテストと統合テスト"""
    
    def setUp(self):
        """各テストの前に実行される準備"""
        # テスト用音声ファイル作成
        self.setup_audio()
    
    def tearDown(self):
        """各テストの後処理"""
        self.teardown_audio()
    
    def test_postgresql_container_basic_operations(self):
        """PostgreSQLコンテナでの基本操作テスト"""
        print("🐳 PostgreSQLコンテナを起動中（デフォルト設定）...")
        
        with PostgresContainer("postgres:15") as postgres:
            # デフォルト設定を使用
            host = postgres.get_container_host_ip()
            port = postgres.get_exposed_port(5432)
            
            print(f"PostgreSQL接続情報: {host}:{port}")
            print(f"Username: {postgres.username}")
            print(f"Password: {postgres.password}")
            print(f"Database: {postgres.dbname}")
            
            # 設定を作成（デフォルト値使用）
            config = DatabaseConfig(
                backend='postgresql',
                host=host,
                port=int(port),
                database=postgres.dbname,    # 'test'
                username=postgres.username,  # 'test'
                password=postgres.password   # 'test'
            )
            
            # PostgreSQLが完全に起動するまで待機
            time.sleep(3)
            
            try:
                # データベース接続テスト
                db = FingerprintDatabase(config)
                
                # 基本操作テスト
                test_song = Song(
                    id="pg_test_song",
                    title="PostgreSQL Test Song",
                    artist="Test Artist",
                    file_path="/path/to/test.wav"
                )
                
                # 楽曲追加
                success = db.add_song(test_song)
                self.assertTrue(success, "PostgreSQLでの楽曲追加に失敗")
                
                # 楽曲取得
                retrieved_song = db.get_song(test_song.id)
                self.assertIsNotNone(retrieved_song, "PostgreSQLでの楽曲取得に失敗")
                self.assertEqual(retrieved_song.title, test_song.title)
                
                # フィンガープリント追加
                test_fingerprints = [
                    Fingerprint(hash_value="pg_hash1", time_offset=0.1),
                    Fingerprint(hash_value="pg_hash2", time_offset=0.2),
                    Fingerprint(hash_value="pg_hash3", time_offset=0.3),
                ]
                
                success = db.add_fingerprints(test_song.id, test_fingerprints)
                self.assertTrue(success, "PostgreSQLでのフィンガープリント追加に失敗")
                
                # フィンガープリント検索
                query_fingerprints = [
                    Fingerprint(hash_value="pg_hash1", time_offset=0.05),
                    Fingerprint(hash_value="pg_hash2", time_offset=0.15),
                ]
                
                matches = db.search_fingerprints(query_fingerprints)
                self.assertIn(test_song.id, matches, "PostgreSQLでのフィンガープリント検索に失敗")
                
                # 統計確認
                stats = db.get_database_stats()
                self.assertEqual(stats["songs"], 1)
                self.assertEqual(stats["fingerprints"], len(test_fingerprints))
                
                db.disconnect()
                print("✅ PostgreSQLテスト完了")
                
            except Exception as e:
                self.fail(f"PostgreSQLテストに失敗: {e}")
    
    def test_postgresql_container_advanced_features(self):
        """PostgreSQLコンテナでの高度な機能テスト"""
        print("🔄 PostgreSQL高度な機能テスト...")
        
        with PostgresContainer("postgres:15") as postgres:
            config = DatabaseConfig(
                backend='postgresql',
                host=postgres.get_container_host_ip(),
                port=int(postgres.get_exposed_port(5432)),
                database=postgres.dbname,
                username=postgres.username,
                password=postgres.password
            )
            
            time.sleep(3)  # 起動待機
            
            try:
                db = FingerprintDatabase(config)
                
                # 複数楽曲の追加
                songs = []
                for i in range(3):
                    song = Song(
                        id=f"advanced_test_song_{i}",
                        title=f"Advanced Test Song {i}",
                        artist=f"Test Artist {i}",
                        file_path=f"/path/to/advanced_test{i}.wav"
                    )
                    songs.append(song)
                    success = db.add_song(song)
                    self.assertTrue(success, f"楽曲{i}の追加に失敗")
                
                # 各楽曲にフィンガープリントを追加
                for i, song in enumerate(songs):
                    fingerprints = [
                        Fingerprint(hash_value=f"pg_advanced_hash_{i}_{j}", time_offset=j*0.1)
                        for j in range(5)
                    ]
                    success = db.add_fingerprints(song.id, fingerprints)
                    self.assertTrue(success, f"楽曲{i}のフィンガープリント追加に失敗")
                
                # 楽曲リスト取得
                all_songs = db.list_songs()
                self.assertEqual(len(all_songs), 3, "楽曲リストの取得に失敗")
                
                # 複合検索テスト
                query_fingerprints = [
                    Fingerprint(hash_value="pg_advanced_hash_0_0", time_offset=0.05),
                    Fingerprint(hash_value="pg_advanced_hash_1_1", time_offset=0.15),
                ]
                
                matches = db.search_fingerprints(query_fingerprints)
                self.assertGreaterEqual(len(matches), 2, "複合検索の結果が不十分")
                
                # 統計確認
                stats = db.get_database_stats()
                self.assertEqual(stats["songs"], 3)
                self.assertEqual(stats["fingerprints"], 15)  # 3楽曲 × 5フィンガープリント
                
                db.disconnect()
                print("✅ PostgreSQL高度な機能テスト完了")
                
            except Exception as e:
                self.fail(f"PostgreSQL高度な機能テストに失敗: {e}")
    
    def test_postgresql_container_performance(self):
        """PostgreSQLコンテナでの性能テスト"""
        print("📊 PostgreSQL性能テスト...")
        
        with PostgresContainer("postgres:15") as postgres:
            config = DatabaseConfig(
                backend='postgresql',
                host=postgres.get_container_host_ip(),
                port=int(postgres.get_exposed_port(5432)),
                database=postgres.dbname,
                username=postgres.username,
                password=postgres.password
            )
            
            time.sleep(3)  # 起動待機
            
            try:
                db = FingerprintDatabase(config)
                
                # テスト用データ準備
                test_songs = [
                    Song(
                        id=f"pg_perf_test_song_{i}",
                        title=f"PostgreSQL Performance Test Song {i}",
                        artist=f"Test Artist {i}",
                        file_path=f"/path/to/pg_test{i}.wav"
                    )
                    for i in range(1, 6)  # 5楽曲
                ]
                
                # 楽曲追加性能
                start_time = time.time()
                for song in test_songs:
                    db.add_song(song)
                song_add_time = time.time() - start_time
                
                # フィンガープリント追加性能
                start_time = time.time()
                for song in test_songs:
                    fingerprints = [
                        Fingerprint(hash_value=f"pg_perf_hash_{song.id}_{j}", time_offset=j*0.1)
                        for j in range(10)  # 楽曲あたり10個
                    ]
                    db.add_fingerprints(song.id, fingerprints)
                fingerprint_add_time = time.time() - start_time
                
                # 検索性能
                start_time = time.time()
                query_fingerprints = [
                    Fingerprint(hash_value=f"pg_perf_hash_{test_songs[0].id}_0", time_offset=0.05)
                ]
                matches = db.search_fingerprints(query_fingerprints)
                search_time = time.time() - start_time
                
                # 結果表示
                print("📈 PostgreSQL性能結果:")
                print(f"  楽曲追加: {song_add_time:.3f}s")
                print(f"  フィンガープリント追加: {fingerprint_add_time:.3f}s")
                print(f"  検索: {search_time:.3f}s")
                print(f"  マッチ数: {len(matches)}")
                
                # 基本的な妥当性チェック
                self.assertGreater(len(matches), 0, "検索結果が見つかりません")
                self.assertLess(song_add_time, 10.0, "楽曲追加時間が長すぎます")
                self.assertLess(fingerprint_add_time, 30.0, "フィンガープリント追加時間が長すぎます")
                self.assertLess(search_time, 5.0, "検索時間が長すぎます")
                
                db.disconnect()
                
            except Exception as e:
                self.fail(f"PostgreSQL性能テストに失敗: {e}")
    
    def test_postgresql_backend_operations(self):
        """PostgreSQLバックエンドの基本操作テスト"""
        print("🐳 PostgreSQLバックエンド操作テストを開始...")
        
        with PostgresContainer("postgres:15") as postgres:
            # デフォルト設定を使用
            host = postgres.get_container_host_ip()
            port = postgres.get_exposed_port(5432)
            
            config = DatabaseConfig(
                backend='postgresql',
                host=host,
                port=int(port),
                database=postgres.dbname,
                username=postgres.username,
                password=postgres.password
            )
            
            # データベース接続テスト
            db = FingerprintDatabase(config)
            
            # テストデータ準備
            test_song = Song(
                id="test_song_pg_backend",
                title="PostgreSQL Backend Test Song",
                artist="Test Artist",
                file_path="/path/to/test.wav"
            )
            
            test_fingerprints = [
                Fingerprint(hash_value="pg_backend_hash1", time_offset=0.1),
                Fingerprint(hash_value="pg_backend_hash2", time_offset=0.2),
                Fingerprint(hash_value="pg_backend_hash3", time_offset=0.3),
                Fingerprint(hash_value="pg_backend_hash4", time_offset=0.4),
                Fingerprint(hash_value="pg_backend_hash5", time_offset=0.5),
            ]
            
            try:
                # 楽曲追加テスト
                success = db.add_song(test_song)
                self.assertTrue(success, "楽曲の追加に失敗しました")
                
                # 楽曲取得テスト
                retrieved_song = db.get_song(test_song.id)
                self.assertIsNotNone(retrieved_song, "楽曲の取得に失敗しました")
                self.assertEqual(retrieved_song.title, test_song.title)
                self.assertEqual(retrieved_song.artist, test_song.artist)
                
                # フィンガープリント追加テスト
                success = db.add_fingerprints(test_song.id, test_fingerprints)
                self.assertTrue(success, "フィンガープリントの追加に失敗しました")
                
                # フィンガープリント検索テスト
                query_fingerprints = [
                    Fingerprint(hash_value="pg_backend_hash1", time_offset=0.05),
                    Fingerprint(hash_value="pg_backend_hash2", time_offset=0.15),
                ]
                
                matches = db.search_fingerprints(query_fingerprints)
                self.assertIn(test_song.id, matches, "フィンガープリントの検索に失敗しました")
                
                # データベース統計テスト
                stats = db.get_database_stats()
                self.assertEqual(stats["songs"], 1)
                self.assertEqual(stats["fingerprints"], len(test_fingerprints))
                
                # 楽曲一覧テスト
                songs = db.list_songs()
                self.assertEqual(len(songs), 1)
                self.assertEqual(songs[0].id, test_song.id)
                
            finally:
                # 接続終了
                db.disconnect()

    def test_postgresql_large_dataset_operations(self):
        """PostgreSQL大量データ操作テスト"""
        print("🐳 PostgreSQL大量データテストを開始...")
        
        with PostgresContainer("postgres:15") as postgres:
            config = DatabaseConfig(
                backend='postgresql',
                host=postgres.get_container_host_ip(),
                port=int(postgres.get_exposed_port(5432)),
                database=postgres.dbname,
                username=postgres.username,
                password=postgres.password
            )
            
            db = FingerprintDatabase(config)
            
            try:
                # 大量の楽曲を追加
                large_song_count = 20  # テスト時間を考慮
                for i in range(large_song_count):
                    song = Song(
                        id=f"large_pg_song_{i}",
                        title=f"Large PostgreSQL Song {i}",
                        artist=f"Test Artist {i}",
                        file_path=f"/path/to/large_test_{i}.wav"
                    )
                    success = db.add_song(song)
                    self.assertTrue(success, f"楽曲{i}の追加に失敗")
                
                # 大量のフィンガープリントを追加
                fingerprints = []
                for i in range(100):
                    fingerprints.append(
                        Fingerprint(hash_value=f"large_pg_hash_{i}", time_offset=i * 0.1)
                    )
                
                success = db.add_fingerprints("large_pg_song_0", fingerprints)
                self.assertTrue(success, "大量フィンガープリントの追加に失敗")
                
                # 統計確認
                stats = db.get_database_stats()
                self.assertGreaterEqual(stats["songs"], large_song_count)
                self.assertGreaterEqual(stats["fingerprints"], 100)
                
                print(f"📊 PostgreSQL大量データ結果: {stats['songs']}曲, {stats['fingerprints']}フィンガープリント")
                
            finally:
                db.disconnect()

    # === Mimizam統合テスト ===
    
    def test_mimizam_postgresql_complete_workflow(self):
        """MimizamとPostgreSQLの完全ワークフローテスト"""
        print("🎵 Mimizam PostgreSQL統合テストを開始...")
        
        with PostgresContainer("postgres:15") as postgres:
            postgres_config = {
                'host': postgres.get_container_host_ip(),
                'port': postgres.get_exposed_port(5432),
                'database': postgres.dbname,
                'username': postgres.username,
                'password': postgres.password
            }
            
            # Mimizamインスタンスを作成
            mimizam = create_mimizam_postgresql(
                **postgres_config,
                matcher_config={
                    'min_confidence': 0.1,
                    'max_results': 5,
                    'scoring_method': 'hybrid'
                },
                enable_adaptive_params=False
            )
            
            try:
                # 楽曲追加テスト
                song_id = "mimizam_postgresql_integration"
                success = mimizam.add_song(
                    file_path=self.test_audio_file,
                    title="Mimizam PostgreSQL Integration Test",
                    artist="PostgreSQL Integration Artist",
                    song_id=song_id
                )
                self.assertTrue(success, "PostgreSQLでの楽曲追加に失敗")
                
                # 楽曲取得テスト
                retrieved_song = mimizam.get_song(song_id)
                self.assertIsNotNone(retrieved_song, "楽曲取得に失敗")
                self.assertEqual(retrieved_song.title, "Mimizam PostgreSQL Integration Test")
                self.assertEqual(retrieved_song.artist, "PostgreSQL Integration Artist")
                
                # 楽曲検索テスト
                results = mimizam.search_song(
                    query_file_path=self.test_audio_file,
                    min_confidence=0.05,
                    top_k=5
                )
                self.assertGreater(len(results), 0, "検索結果が見つかりません")
                self.assertEqual(results[0]['song'].id, song_id)
                self.assertGreater(results[0]['confidence'], 0.1)
                
                # 音声識別テスト
                identification = mimizam.identify_audio(
                    query_file_path=self.test_audio_file,
                    min_confidence=0.1
                )
                self.assertIsNotNone(identification, "音声識別に失敗")
                identified_song, confidence = identification
                self.assertEqual(identified_song.id, song_id)
                self.assertGreater(confidence, 0.1)
                
                # 楽曲一覧テスト
                songs = mimizam.list_songs()
                self.assertEqual(len(songs), 1)
                self.assertEqual(songs[0].id, song_id)
                
                # 統計情報テスト
                stats = mimizam.get_database_stats()
                self.assertEqual(stats['songs'], 1)
                self.assertGreater(stats['fingerprints'], 0)
                
                # 楽曲削除テスト
                delete_success = mimizam.delete_song(song_id)
                self.assertTrue(delete_success, "楽曲削除に失敗")
                
                # 削除確認
                self.assertIsNone(mimizam.get_song(song_id))
                final_stats = mimizam.get_database_stats()
                self.assertEqual(final_stats['songs'], 0)
                
            finally:
                mimizam.close()
    
    def test_mimizam_postgresql_matcher_configuration(self):
        """Mimizam PostgreSQL matcher設定テスト"""
        print("🎵 Mimizam PostgreSQL matcher設定テストを開始...")
        
        with PostgresContainer("postgres:15") as postgres:
            postgres_config = {
                'host': postgres.get_container_host_ip(),
                'port': postgres.get_exposed_port(5432),
                'database': postgres.dbname,
                'username': postgres.username,
                'password': postgres.password
            }
            
            # カスタムmatcher設定
            custom_matcher_config = {
                'min_confidence': 0.3,
                'max_results': 3,
                'scoring_method': 'detailed'
            }
            
            mimizam = create_mimizam_postgresql(
                **postgres_config,
                matcher_config=custom_matcher_config,
                enable_adaptive_params=False
            )
            
            try:
                # 設定確認
                self.assertEqual(mimizam.matcher.min_confidence, 0.3)
                self.assertEqual(mimizam.matcher.max_results, 3)
                
                # 楽曲追加
                success = mimizam.add_song(
                    file_path=self.test_audio_file,
                    title="PostgreSQL Config Test Song",
                    artist="Config Test Artist"
                )
                self.assertTrue(success)
                
                # 設定された値で検索
                results = mimizam.search_song(
                    query_file_path=self.test_audio_file,
                    min_confidence=0.1,
                    top_k=10
                )
                self.assertGreater(len(results), 0)
                
            finally:
                mimizam.close()
    
    def test_mimizam_postgresql_context_manager(self):
        """Mimizam PostgreSQLコンテキストマネージャーテスト"""
        print("🎵 Mimizam PostgreSQL context manager テストを開始...")
        
        with PostgresContainer("postgres:15") as postgres:
            postgres_config = {
                'host': postgres.get_container_host_ip(),
                'port': postgres.get_exposed_port(5432),
                'database': postgres.dbname,
                'username': postgres.username,
                'password': postgres.password
            }
            
            with create_mimizam_postgresql(**postgres_config) as mimizam:
                # 楽曲追加
                success = mimizam.add_song(
                    file_path=self.test_audio_file,
                    title="PostgreSQL Context Test Song",
                    artist="Context Test Artist"
                )
                self.assertTrue(success)
                
                # 統計確認
                stats = mimizam.get_database_stats()
                self.assertEqual(stats['songs'], 1)
            
            # コンテキスト終了後は自動的にクローズされる


if __name__ == "__main__":
    if not TESTCONTAINERS_AVAILABLE:
        print("⚠️  Testcontainersが利用できません。以下のコマンドでインストールしてください：")
        print("pip install testcontainers")
        sys.exit(1)
    
    print("🐳 PostgreSQLコンテナテストを開始します...")
    print("⏳ PostgreSQLコンテナの起動には時間がかかる場合があります...")
    print("📋 注意: テストには約2-3分かかる場合があります")
    
    # 全てのテストを実行
    test_loader = unittest.TestLoader()
    test_suite = test_loader.loadTestsFromTestCase(TestPostgreSQLContainers)
    
    runner = unittest.TextTestRunner(verbosity=2, buffer=True)
    result = runner.run(test_suite)
    
    # 結果サマリー
    print(f"\n{'='*60}")
    print("📊 PostgreSQLテスト結果サマリー:")
    print(f"  総テスト数: {result.testsRun}")
    print(f"  成功: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"  失敗: {len(result.failures)}")
    print(f"  エラー: {len(result.errors)}")
    
    if result.failures:
        print("\n❌ 失敗したテスト:")
        for test, traceback in result.failures:
            print(f"  - {test}: {traceback.split(chr(10))[-2] if chr(10) in traceback else 'テスト失敗'}")
    
    if result.errors:
        print("\n⚠️ エラーが発生したテスト:")
        for test, traceback in result.errors:
            print(f"  - {test}: {traceback.split(chr(10))[-2] if chr(10) in traceback else 'テストエラー'}")
    
    print(f"{'='*60}")
    
    # 適切なコードで終了
    sys.exit(0 if result.wasSuccessful() else 1)
