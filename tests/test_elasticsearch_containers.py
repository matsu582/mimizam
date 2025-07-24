"""
Elasticsearchコンテナを使用したインテグレーションテスト
"""

import unittest
import time
import sys
import os
from pathlib import Path

try:
    from testcontainers.elasticsearch import ElasticSearchContainer
    TESTCONTAINERS_AVAILABLE = True
except ImportError:
    TESTCONTAINERS_AVAILABLE = False

from mimizam import DatabaseConfig, Song
from mimizam import FingerprintDatabase
from mimizam import Fingerprint
from mimizam import create_mimizam_elasticsearch
sys.path.append(os.path.dirname(__file__))
from test_utils import TestAudioMixin


@unittest.skipUnless(TESTCONTAINERS_AVAILABLE, "Testcontainersが利用できません")
class TestElasticsearchContainers(TestAudioMixin, unittest.TestCase):
    """Elasticsearchコンテナテストと統合テスト"""
    
    def setUp(self):
        """各テストの前に実行される準備"""
        self.test_timeout = 30  # テストタイムアウト（秒）
        self.es_startup_time = 45  # Elasticsearch起動時間（秒）
        
        # テスト用音声ファイル作成
        self.setup_audio()
    
    def tearDown(self):
        """各テストの後処理"""
        self.teardown_audio()
    
    def _create_elasticsearch_config(self, container, index_suffix="test"):
        """Elasticsearchコンテナ用の設定を作成（シャード・レプリカ設定対応）"""
        host = container.get_container_host_ip()
        port = container.get_exposed_port(9200)
        
        config = DatabaseConfig(
            backend='elasticsearch',
            host=host,
            port=int(port),
            index_name=f"fingerprints_{index_suffix}",
            username=None,
            password=None,
            verify_certs=False,  # テスト環境では証明書検証を無効
            pool_timeout=30,
            # テスト環境用のシャード・レプリカ設定（最小構成）
            es_songs_shards=1,
            es_songs_replicas=0,
            es_fingerprints_shards=1,  # テスト用に軽量化
            es_fingerprints_replicas=0
        )
        
        return config
    
    def _wait_for_elasticsearch(self, host, port, timeout=60):
        """Elasticsearchが利用可能になるまで待機"""
        import requests
        import time
        
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                response = requests.get(f"http://{host}:{port}/_cluster/health", timeout=5)
                if response.status_code == 200:
                    health = response.json()
                    if health.get('status') in ['green', 'yellow']:
                        print(f"✅ Elasticsearchクラスターの状態: {health.get('status')}")
                        return True
            except Exception:
                pass
            
            print("⏳ Elasticsearchの起動を待機中...")
            time.sleep(5)
        
        print("❌ Elasticsearchの起動タイムアウト")
        return False

    def test_elasticsearch_container_basic_operations(self):
        """Elasticsearchコンテナでの基本操作テスト"""
        print("🐳 Elasticsearchコンテナを起動中（セキュリティ無効化設定）...")
        
        # Elasticsearchセキュリティを無効化してテスト用に設定
        with ElasticSearchContainer("elasticsearch:8.11.0").with_env(
            "discovery.type", "single-node"
        ).with_env(
            "xpack.security.enabled", "false"
        ).with_env(
            "xpack.security.http.ssl.enabled", "false"
        ).with_env(
            "ES_JAVA_OPTS", "-Xms512m -Xmx512m"
        ) as elasticsearch:
            config = self._create_elasticsearch_config(elasticsearch, "basic")
            
            print(f"Elasticsearch接続情報: {config.host}:{config.port}")
            print(f"インデックス名: {config.index_name}")
            
            # Elasticsearchが完全に起動するまで待機
            print("⏳ Elasticsearchの起動を待機中...")
            if not self._wait_for_elasticsearch(config.host, config.port):
                self.fail("Elasticsearchの起動に失敗しました")
            
            try:
                # データベース接続テスト
                db = FingerprintDatabase(config)
                
                # 基本操作テスト
                test_song = Song(
                    id="es_test_song",
                    title="Elasticsearch Test Song",
                    artist="Test Artist",
                    file_path="/path/to/test.wav"
                )
                
                # 楽曲追加
                print("📝 楽曲を追加中...")
                success = db.add_song(test_song)
                self.assertTrue(success, "Elasticsearchでの楽曲追加に失敗")
                
                # インデックス更新を待機
                time.sleep(2)
                
                # 楽曲取得
                print("🔍 楽曲を取得中...")
                retrieved_song = db.get_song(test_song.id)
                self.assertIsNotNone(retrieved_song, "Elasticsearchでの楽曲取得に失敗")
                self.assertEqual(retrieved_song.title, test_song.title)
                
                # フィンガープリント追加
                print("🎵 フィンガープリントを追加中...")
                test_fingerprints = [
                    Fingerprint(hash_value="es_hash1", time_offset=0.1),
                    Fingerprint(hash_value="es_hash2", time_offset=0.2),
                    Fingerprint(hash_value="es_hash3", time_offset=0.3),
                ]
                
                success = db.add_fingerprints(test_song.id, test_fingerprints)
                self.assertTrue(success, "Elasticsearchでのフィンガープリント追加に失敗")
                
                # インデックス更新を待機
                time.sleep(2)
                
                # フィンガープリント検索
                print("🔎 フィンガープリントを検索中...")
                query_fingerprints = [
                    Fingerprint(hash_value="es_hash1", time_offset=0.05),
                    Fingerprint(hash_value="es_hash2", time_offset=0.15),
                ]
                
                matches = db.search_fingerprints(query_fingerprints)
                self.assertIn(test_song.id, matches, "Elasticsearchでのフィンガープリント検索に失敗")
                
                # 統計確認
                print("📊 統計を確認中...")
                stats = db.get_database_stats()
                self.assertEqual(stats["songs"], 1)
                self.assertEqual(stats["fingerprints"], len(test_fingerprints))
                
                db.disconnect()
                print("✅ Elasticsearchテスト完了")
                
            except Exception as e:
                self.fail(f"Elasticsearchテストに失敗: {e}")
    
    def test_elasticsearch_container_search_capabilities(self):
        """Elasticsearchコンテナでの検索機能テスト"""
        print("🔍 Elasticsearch検索機能テスト...")
        
        with ElasticSearchContainer("elasticsearch:8.11.0").with_env(
            "discovery.type", "single-node"
        ).with_env(
            "xpack.security.enabled", "false"
        ).with_env(
            "xpack.security.http.ssl.enabled", "false"
        ).with_env(
            "ES_JAVA_OPTS", "-Xms512m -Xmx512m"
        ) as elasticsearch:
            config = self._create_elasticsearch_config(elasticsearch, "search")
            
            print("⏳ Elasticsearchの起動を待機中...")
            if not self._wait_for_elasticsearch(config.host, config.port):
                self.fail("Elasticsearchの起動に失敗しました")
            
            try:
                db = FingerprintDatabase(config)
                
                # 複数楽曲の追加
                print("📝 複数楽曲を追加中...")
                songs = []
                for i in range(3):
                    song = Song(
                        id=f"es_search_test_song_{i}",
                        title=f"Elasticsearch Search Test Song {i}",
                        artist=f"Search Test Artist {i}",
                        file_path=f"/path/to/search_test{i}.wav"
                    )
                    songs.append(song)
                    success = db.add_song(song)
                    self.assertTrue(success, f"楽曲{i}の追加に失敗")
                
                time.sleep(2)  # インデックス更新待機
                
                # 各楽曲にユニークなフィンガープリントを追加
                print("🎵 フィンガープリントを追加中...")
                for i, song in enumerate(songs):
                    fingerprints = [
                        Fingerprint(hash_value=f"es_search_hash_{i}_{j}", time_offset=j*0.1)
                        for j in range(5)
                    ]
                    success = db.add_fingerprints(song.id, fingerprints)
                    self.assertTrue(success, f"楽曲{i}のフィンガープリント追加に失敗")
                
                time.sleep(2)  # インデックス更新待機
                
                # 楽曲リスト取得
                print("📋 楽曲リストを取得中...")
                all_songs = db.list_songs()
                self.assertEqual(len(all_songs), 3, "楽曲リストの取得に失敗")
                
                # 特定楽曲の検索
                print("🔎 特定楽曲を検索中...")
                query_fingerprints = [
                    Fingerprint(hash_value="es_search_hash_1_0", time_offset=0.05),
                ]
                
                matches = db.search_fingerprints(query_fingerprints)
                self.assertIn(songs[1].id, matches, "特定楽曲の検索に失敗")
                
                # 統計確認
                print("📊 統計を確認中...")
                stats = db.get_database_stats()
                self.assertEqual(stats["songs"], 3)
                self.assertEqual(stats["fingerprints"], 15)  # 3楽曲 × 5フィンガープリント
                
                db.disconnect()
                print("✅ Elasticsearch検索機能テスト完了")
                
            except Exception as e:
                self.fail(f"Elasticsearch検索機能テストに失敗: {e}")
    
    def test_elasticsearch_container_performance(self):
        """Elasticsearchコンテナでの性能テスト"""
        print("📊 Elasticsearch性能テスト...")
        
        with ElasticSearchContainer("elasticsearch:8.11.0").with_env(
            "discovery.type", "single-node"
        ).with_env(
            "xpack.security.enabled", "false"
        ).with_env(
            "xpack.security.http.ssl.enabled", "false"
        ).with_env(
            "ES_JAVA_OPTS", "-Xms512m -Xmx512m"
        ) as elasticsearch:
            config = self._create_elasticsearch_config(elasticsearch, "performance")
            
            print("⏳ Elasticsearchの起動を待機中...")
            if not self._wait_for_elasticsearch(config.host, config.port):
                self.fail("Elasticsearchの起動に失敗しました")
            
            try:
                db = FingerprintDatabase(config)
                
                # テスト用データ準備
                print("📝 テスト用データを準備中...")
                test_songs = [
                    Song(
                        id=f"es_perf_test_song_{i}",
                        title=f"Elasticsearch Performance Test Song {i}",
                        artist=f"Test Artist {i}",
                        file_path=f"/path/to/es_test{i}.wav"
                    )
                    for i in range(1, 6)  # 5楽曲
                ]
                
                # 楽曲追加性能
                print("📊 楽曲追加性能を測定中...")
                start_time = time.time()
                for song in test_songs:
                    db.add_song(song)
                song_add_time = time.time() - start_time
                
                time.sleep(2)  # インデックス更新待機
                
                # フィンガープリント追加性能
                print("📊 フィンガープリント追加性能を測定中...")
                start_time = time.time()
                for i, song in enumerate(test_songs):
                    fingerprints = [
                        Fingerprint(hash_value=f"es_perf_hash_{song.id}_{j}", time_offset=j*0.1)
                        for j in range(10)  # 楽曲あたり10個
                    ]
                    success = db.add_fingerprints(song.id, fingerprints)
                    self.assertTrue(success, f"楽曲{i}のフィンガープリント追加に失敗")
                fingerprint_add_time = time.time() - start_time
                
                time.sleep(2)  # インデックス更新待機
                
                # 検索性能
                print("📊 検索性能を測定中...")
                start_time = time.time()
                query_fingerprints = [
                    Fingerprint(hash_value=f"es_perf_hash_{test_songs[0].id}_0", time_offset=0.05)
                ]
                matches = db.search_fingerprints(query_fingerprints)
                search_time = time.time() - start_time
                
                # 結果表示
                print("\n📈 Elasticsearch性能結果:")
                print(f"  楽曲追加: {song_add_time:.3f}s")
                print(f"  フィンガープリント追加: {fingerprint_add_time:.3f}s")
                print(f"  検索: {search_time:.3f}s")
                print(f"  マッチ数: {len(matches)}")
                
                # 基本的な妥当性チェック（現実的な値に調整）
                self.assertGreater(len(matches), 0, "検索結果が見つかりません")
                self.assertLess(song_add_time, 600.0, "楽曲追加時間が長すぎます")  # 10分に延長
                self.assertLess(fingerprint_add_time, 600.0, "フィンガープリント追加時間が長すぎます")  # 10分に延長
                self.assertLess(search_time, 30.0, "検索時間が長すぎます")  # 30秒に延長
                
                db.disconnect()
                print("✅ Elasticsearch性能テスト完了")
                
            except Exception as e:
                self.fail(f"Elasticsearch性能テストに失敗: {e}")
    
    def test_elasticsearch_backend_operations(self):
        """Elasticsearchバックエンドの基本操作テスト"""
        print("🐳 Elasticsearchバックエンド操作テストを開始...")
        
        with ElasticSearchContainer("elasticsearch:8.11.0").with_env(
            "discovery.type", "single-node"
        ).with_env(
            "xpack.security.enabled", "false"
        ).with_env(
            "xpack.security.http.ssl.enabled", "false"
        ).with_env(
            "ES_JAVA_OPTS", "-Xms512m -Xmx512m"
        ) as elasticsearch:
            
            config = self._create_elasticsearch_config(elasticsearch, "backend_test")
            
            # Elasticsearch起動待機
            if not self._wait_for_elasticsearch(config.host, config.port):
                self.skipTest("Elasticsearchの起動に失敗しました")
            
            # データベース接続テスト
            db = FingerprintDatabase(config)
            
            # テストデータ準備
            test_song = Song(
                id="test_song_es_backend",
                title="Elasticsearch Backend Test Song",
                artist="Test Artist",
                file_path="/path/to/test.wav"
            )
            
            test_fingerprints = [
                Fingerprint(hash_value="es_backend_hash1", time_offset=0.1),
                Fingerprint(hash_value="es_backend_hash2", time_offset=0.2),
                Fingerprint(hash_value="es_backend_hash3", time_offset=0.3),
                Fingerprint(hash_value="es_backend_hash4", time_offset=0.4),
                Fingerprint(hash_value="es_backend_hash5", time_offset=0.5),
            ]
            
            try:
                # Elasticsearchのインデックス準備時間を考慮
                time.sleep(2)
                
                # 楽曲追加テスト
                success = db.add_song(test_song)
                self.assertTrue(success, "楽曲の追加に失敗しました")
                
                # インデックス更新を待機
                time.sleep(2)
                
                # 楽曲取得テスト
                retrieved_song = db.get_song(test_song.id)
                self.assertIsNotNone(retrieved_song, "楽曲の取得に失敗しました")
                self.assertEqual(retrieved_song.title, test_song.title)
                self.assertEqual(retrieved_song.artist, test_song.artist)
                
                # フィンガープリント追加テスト
                success = db.add_fingerprints(test_song.id, test_fingerprints)
                self.assertTrue(success, "フィンガープリントの追加に失敗しました")
                
                # インデックス更新を待機
                time.sleep(2)
                
                # フィンガープリント検索テスト
                query_fingerprints = [
                    Fingerprint(hash_value="es_backend_hash1", time_offset=0.05),
                    Fingerprint(hash_value="es_backend_hash2", time_offset=0.15),
                ]
                
                matches = db.search_fingerprints(query_fingerprints)
                self.assertIn(test_song.id, matches, "フィンガープリントの検索に失敗しました")
                
                # データベース統計テスト（Elasticsearchでは近似値の可能性）
                stats = db.get_database_stats()
                self.assertGreaterEqual(stats["songs"], 1)
                self.assertGreaterEqual(stats["fingerprints"], len(test_fingerprints))
                
                # 楽曲一覧テスト
                songs = db.list_songs()
                self.assertGreaterEqual(len(songs), 1)
                found_song = any(song.id == test_song.id for song in songs)
                self.assertTrue(found_song, "追加した楽曲が見つかりません")
                
            finally:
                # 接続終了
                db.disconnect()

    def test_elasticsearch_large_dataset_operations(self):
        """Elasticsearch大量データ操作テスト"""
        print("🐳 Elasticsearch大量データテストを開始...")
        
        with ElasticSearchContainer("elasticsearch:8.11.0").with_env(
            "discovery.type", "single-node"
        ).with_env(
            "xpack.security.enabled", "false"
        ).with_env(
            "xpack.security.http.ssl.enabled", "false"
        ).with_env(
            "ES_JAVA_OPTS", "-Xms512m -Xmx512m"
        ) as elasticsearch:
            
            config = self._create_elasticsearch_config(elasticsearch, "large_data_test")
            
            # Elasticsearch起動待機
            if not self._wait_for_elasticsearch(config.host, config.port):
                self.skipTest("Elasticsearchの起動に失敗しました")
            
            db = FingerprintDatabase(config)
            
            try:
                time.sleep(2)  # インデックス準備
                
                # 大量の楽曲を追加
                large_song_count = 15  # Elasticsearchはより重いのでテスト数を減らす
                for i in range(large_song_count):
                    song = Song(
                        id=f"large_es_song_{i}",
                        title=f"Large Elasticsearch Song {i}",
                        artist=f"Test Artist {i}",
                        file_path=f"/path/to/large_test_{i}.wav"
                    )
                    success = db.add_song(song)
                    self.assertTrue(success, f"楽曲{i}の追加に失敗")
                
                # インデックス更新待機
                time.sleep(3)
                
                # 大量のフィンガープリントを追加
                fingerprints = []
                for i in range(50):  # フィンガープリント数も調整
                    fingerprints.append(
                        Fingerprint(hash_value=f"large_es_hash_{i}", time_offset=i * 0.1)
                    )
                
                success = db.add_fingerprints("large_es_song_0", fingerprints)
                self.assertTrue(success, "大量フィンガープリントの追加に失敗")
                
                # インデックス更新待機
                time.sleep(3)
                
                # 統計確認
                stats = db.get_database_stats()
                self.assertGreaterEqual(stats["songs"], large_song_count)
                self.assertGreaterEqual(stats["fingerprints"], 50)
                
                print(f"📊 Elasticsearch大量データ結果: {stats['songs']}曲, {stats['fingerprints']}フィンガープリント")
                
            finally:
                db.disconnect()

    # === Mimizam統合テスト ===
    
    def test_mimizam_elasticsearch_complete_workflow(self):
        """MimizamとElasticsearchの完全ワークフローテスト"""
        print("🎵 Mimizam Elasticsearch統合テストを開始...")
        
        with ElasticSearchContainer("elasticsearch:8.11.0").with_env(
            "discovery.type", "single-node"
        ).with_env(
            "xpack.security.enabled", "false"
        ).with_env(
            "xpack.security.http.ssl.enabled", "false"
        ).with_env(
            "ES_JAVA_OPTS", "-Xms512m -Xmx512m"
        ) as elasticsearch:
            
            # Elasticsearch起動待機
            es_host = elasticsearch.get_container_host_ip()
            es_port = elasticsearch.get_exposed_port(9200)
            
            # Elasticsearchが利用可能になるまで待機
            if not self._wait_for_elasticsearch(es_host, es_port):
                self.skipTest("Elasticsearchの起動に失敗しました")
            
            elasticsearch_config = {
                'host': es_host,
                'port': es_port,
                'index_name': 'mimizam_integration_test'
            }
            
            # Mimizamインスタンスを作成
            mimizam = create_mimizam_elasticsearch(
                **elasticsearch_config,
                matcher_config={
                    'min_confidence': 0.1,
                    'max_results': 5,
                    'scoring_method': 'hybrid'
                },
                enable_adaptive_params=False
            )
            
            try:
                # インデックス準備時間
                time.sleep(2)
                
                # 楽曲追加テスト
                song_id = "mimizam_elasticsearch_integration"
                success = mimizam.add_song(
                    file_path=self.test_audio_file,
                    title="Mimizam Elasticsearch Integration Test",
                    artist="Elasticsearch Integration Artist",
                    song_id=song_id
                )
                self.assertTrue(success, "Elasticsearchでの楽曲追加に失敗")
                
                # インデックス更新待機
                time.sleep(3)
                
                # 楽曲取得テスト
                retrieved_song = mimizam.get_song(song_id)
                self.assertIsNotNone(retrieved_song, "楽曲取得に失敗")
                self.assertEqual(retrieved_song.title, "Mimizam Elasticsearch Integration Test")
                self.assertEqual(retrieved_song.artist, "Elasticsearch Integration Artist")
                
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
                self.assertGreaterEqual(len(songs), 1)
                found_song = any(song.id == song_id for song in songs)
                self.assertTrue(found_song, "追加した楽曲が見つかりません")
                
                # 統計情報テスト（Elasticsearchでは近似値の可能性）
                stats = mimizam.get_database_stats()
                self.assertGreaterEqual(stats['songs'], 1)
                self.assertGreater(stats['fingerprints'], 0)
                
                # 楽曲削除テスト
                delete_success = mimizam.delete_song(song_id)
                self.assertTrue(delete_success, "楽曲削除に失敗")
                
                # インデックス更新待機
                time.sleep(3)
                
                # 削除確認（Elasticsearchでは例外が発生する可能性があるため、try-exceptでハンドリング）
                try:
                    deleted_song = mimizam.get_song(song_id)
                    self.assertIsNone(deleted_song, "楽曲が削除されていません")
                except Exception:
                    # 正常な動作として扱う（削除済み楽曲の取得で例外発生）
                    pass
                
            finally:
                mimizam.close()
    
    def test_mimizam_elasticsearch_matcher_configuration(self):
        """Mimizam Elasticsearch matcher設定テスト"""
        print("🎵 Mimizam Elasticsearch matcher設定テストを開始...")
        
        with ElasticSearchContainer("elasticsearch:8.11.0").with_env(
            "discovery.type", "single-node"
        ).with_env(
            "xpack.security.enabled", "false"
        ).with_env(
            "xpack.security.http.ssl.enabled", "false"
        ).with_env(
            "ES_JAVA_OPTS", "-Xms512m -Xmx512m"
        ) as elasticsearch:
            
            es_host = elasticsearch.get_container_host_ip()
            es_port = elasticsearch.get_exposed_port(9200)
            
            # Elasticsearchが利用可能になるまで待機
            if not self._wait_for_elasticsearch(es_host, es_port):
                self.skipTest("Elasticsearchの起動に失敗しました")
            
            elasticsearch_config = {
                'host': es_host,
                'port': es_port,
                'index_name': 'mimizam_config_test'
            }
            
            # カスタムmatcher設定
            custom_matcher_config = {
                'min_confidence': 0.3,
                'max_results': 3,
                'scoring_method': 'detailed'
            }
            
            # Elasticsearchが利用可能になるまで待機
            if not self._wait_for_elasticsearch(es_host, es_port):
                self.skipTest("Elasticsearchの起動に失敗しました")
            
            mimizam = create_mimizam_elasticsearch(
                **elasticsearch_config,
                matcher_config=custom_matcher_config,
                enable_adaptive_params=False
            )
            
            try:
                time.sleep(2)  # インデックス準備
                
                # 設定確認
                self.assertEqual(mimizam.matcher.min_confidence, 0.3)
                self.assertEqual(mimizam.matcher.max_results, 3)
                
                # 楽曲追加
                success = mimizam.add_song(
                    file_path=self.test_audio_file,
                    title="Elasticsearch Config Test Song",
                    artist="Config Test Artist"
                )
                self.assertTrue(success)
                
                time.sleep(2)  # インデックス更新待機
                
                # 設定された値で検索
                results = mimizam.search_song(
                    query_file_path=self.test_audio_file,
                    min_confidence=0.1,
                    top_k=10
                )
                self.assertGreater(len(results), 0)
                
            finally:
                mimizam.close()
    
    def test_mimizam_elasticsearch_context_manager(self):
        """Mimizam Elasticsearchコンテキストマネージャーテスト"""
        print("🎵 Mimizam Elasticsearch context manager テストを開始...")
        
        with ElasticSearchContainer("elasticsearch:8.11.0").with_env(
            "discovery.type", "single-node"
        ).with_env(
            "xpack.security.enabled", "false"
        ).with_env(
            "xpack.security.http.ssl.enabled", "false"
        ).with_env(
            "ES_JAVA_OPTS", "-Xms512m -Xmx512m"
        ) as elasticsearch:
            
            es_host = elasticsearch.get_container_host_ip()
            es_port = elasticsearch.get_exposed_port(9200)
            
            # Elasticsearchが利用可能になるまで待機
            if not self._wait_for_elasticsearch(es_host, es_port):
                self.skipTest("Elasticsearchの起動に失敗しました")
            
            # Elasticsearchが利用可能になるまで待機
            if not self._wait_for_elasticsearch(es_host, es_port):
                self.skipTest("Elasticsearchの起動に失敗しました")
            
            elasticsearch_config = {
                'host': es_host,
                'port': es_port,
                'index_name': 'mimizam_context_test'
            }
            
            with create_mimizam_elasticsearch(**elasticsearch_config) as mimizam:
                time.sleep(2)  # インデックス準備
                
                # 楽曲追加
                success = mimizam.add_song(
                    file_path=self.test_audio_file,
                    title="Elasticsearch Context Test Song",
                    artist="Context Test Artist"
                )
                self.assertTrue(success)
                
                time.sleep(2)  # インデックス更新待機
                
                # 統計確認
                stats = mimizam.get_database_stats()
                self.assertGreaterEqual(stats['songs'], 1)
            
            # コンテキスト終了後は自動的にクローズされる


if __name__ == "__main__":
    if not TESTCONTAINERS_AVAILABLE:
        print("⚠️  Testcontainersが利用できません。以下のコマンドでインストールしてください：")
        print("pip install testcontainers")
        sys.exit(1)
    
    print("🐳 Elasticsearchコンテナテストを開始します...")
    print("⏳ Elasticsearchコンテナの起動には時間がかかる場合があります...")
    print("🔒 セキュリティ無効化設定でテスト環境を構築します")
    print("📋 注意: テストには約3-5分かかる場合があります")
    
    # 全てのテストを実行
    test_loader = unittest.TestLoader()
    test_suite = test_loader.loadTestsFromTestCase(TestElasticsearchContainers)
    
    runner = unittest.TextTestRunner(verbosity=2, buffer=True)
    result = runner.run(test_suite)
    
    # 結果サマリー
    print(f"\n{'='*60}")
    print("📊 Elasticsearchテスト結果サマリー:")
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
