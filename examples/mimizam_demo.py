#!/usr/bin/env python3
"""
Mimizamシステムの使用例デモ

基本的な音楽追加、検索、識別の操作を示します。
"""

import os
import sys
import logging
from pathlib import Path

from mimizam import Mimizam, create_mimizam_sqlite
from mimizam import DatabaseConfig


def setup_logging():
    """ログ設定を初期化"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )


def demo_basic_usage():
    """基本的な使用方法のデモ"""
    print("🎵 Mimizam基本使用デモ")
    print("============================================================")
    
    # SQLiteを使用してMimizamインスタンスを作成
    with create_mimizam_sqlite("demo_music.db") as mimizam:
        print("✅ Mimizamシステムが初期化されました")
        
        # デモ音声ファイルのパス（test_media/ディレクトリに配置）
        demo_files = [
            ("test_media/demo_song1.wav", "Demo Song 1", "Demo Artist"),
            ("test_media/demo_song2.wav", "Demo Song 2", "Another Artist"),
        ]
        
        # 音楽をシステムに追加
        print("\n📝 音楽をデータベースに追加中...")
        for file_path, title, artist in demo_files:
            if os.path.exists(file_path):
                song_id = mimizam.add_song(file_path, title, artist)
                if song_id:
                    print(f"✅ 追加完了: {title} by {artist} (ID: {song_id})")
                else:
                    print(f"❌ 追加失敗: {title} by {artist}")
            else:
                print(f"⚠️  ファイルが見つかりません: {file_path}")
        
        # データベース統計の表示
        stats = mimizam.get_database_stats()
        print(f"\n📊 データベース統計:")
        print(f"   楽曲数: {stats.get('songs', 0)}")
        print(f"   フィンガープリント数: {stats.get('fingerprints', 0)}")
        
        # 楽曲リストの表示
        print(f"\n📋 登録された楽曲一覧:")
        songs = mimizam.list_songs()
        for song in songs:
            print(f"   {song.id}: {song.title} by {song.artist}")
        
        # 音声検索のデモ
        print(f"\n🔍 音声検索デモ:")
        query_file = "test_media/demo_query.wav"
        if os.path.exists(query_file):
            results = mimizam.search_song(query_file, min_confidence=0.1, top_k=3)
            if results:
                print(f"   {len(results)}件の検索結果:")
                for i, result in enumerate(results, 1):
                    song = result['song']
                    confidence = result['confidence']
                    print(f"   {i}. {song.title} by {song.artist} (信頼度: {confidence:.2%})")
            else:
                print("   マッチする楽曲が見つかりませんでした")
        else:
            print(f"   クエリファイルが見つかりません: {query_file}")
        
        # 音声識別のデモ
        print(f"\n🎯 音声識別デモ:")
        if os.path.exists(query_file):
            identified = mimizam.identify_audio(query_file, min_confidence=0.3)
            if identified:
                song, confidence = identified
                print(f"   識別結果: {song.title} by {song.artist} (信頼度: {confidence:.2%})")
            else:
                print("   楽曲を識別できませんでした")
        else:
            print(f"   クエリファイルが見つかりません: {query_file}")


def demo_advanced_usage():
    """高度な使用方法のデモ"""
    print("\n🔧 Mimizam高度な使用デモ")
    print("============================================================")
    
    # カスタム設定でMimizamを作成
    custom_config = DatabaseConfig(
        backend='sqlite',
        file_path='advanced_music.db'
    )
    
    fingerprinter_config = {
        'n_fft': 4096,  # より高い解像度
        'hop_length': 256,  # より細かい時間解像度
        'min_amplitude': -50  # より敏感な検出
    }
    
    with Mimizam(custom_config, fingerprinter_config) as mimizam:
        print("✅ カスタム設定でMimizamシステムが初期化されました")
        
        # 複数のバックエンドでの設定例を表示
        print("\n🗄️ サポートされているデータベースバックエンド:")
        
        print("   • SQLite (ローカルファイル)")
        print("     config = DatabaseConfig(backend='sqlite', file_path='music.db')")
        
        print("   • MySQL (リモートサーバー)")
        print("     config = DatabaseConfig(")
        print("         backend='mysql', host='localhost', port=3306,")
        print("         database='music_db', username='user', password='pass')")
        
        print("   • PostgreSQL (リモートサーバー)")
        print("     config = DatabaseConfig(")
        print("         backend='postgresql', host='localhost', port=5432,")
        print("         database='music_db', username='user', password='pass')")
        
        print("   • Elasticsearch (分散検索)")
        print("     config = DatabaseConfig(")
        print("         backend='elasticsearch', host='localhost', port=9200,")
        print("         index_name='music_index')")
        
        # AudioFingerprinterの設定例
        print("\n🎛️ AudioFingerprinterの設定例:")
        print("   fingerprinter_config = {")
        print("       'n_fft': 2048,           # FFTウィンドウサイズ")
        print("       'hop_length': 512,       # フレーム間隔")
        print("       'sr': 22050,             # サンプルレート")
        print("       'min_amplitude': -60    # 検出閾値")
        print("   }")


def demo_batch_processing():
    """バッチ処理のデモ"""
    print("\n📦 Mimizamバッチ処理デモ")
    print("============================================================")
    
    # 音楽ディレクトリ内の全ファイルを処理する例
    music_dir = Path("test_media")
    
    if music_dir.exists():
        with create_mimizam_sqlite("batch_music.db") as mimizam:
            print(f"✅ バッチ処理用Mimizamシステムが初期化されました")
            
            # 音声ファイルを検索
            audio_extensions = ['.wav', '.mp3', '.m4a', '.flac']
            audio_files = []
            
            for ext in audio_extensions:
                audio_files.extend(music_dir.glob(f"*{ext}"))
            
            print(f"📂 {len(audio_files)}個の音声ファイルを発見しました")
            
            # 各ファイルを処理
            for i, file_path in enumerate(audio_files, 1):
                title = file_path.stem  # ファイル名をタイトルとして使用
                artist = "Unknown Artist"  # デフォルトアーティスト
                
                print(f"   処理中 ({i}/{len(audio_files)}): {file_path.name}")
                
                try:
                    song_id = mimizam.add_song(str(file_path), title, artist)
                    if song_id:
                        print(f"     ✅ 追加完了: {title} (ID: {song_id})")
                    else:
                        print(f"     ❌ 追加失敗: {title}")
                except Exception as e:
                    print(f"     ⚠️  エラー: {e}")
            
            # 最終統計
            stats = mimizam.get_database_stats()
            print(f"\n📊 バッチ処理結果:")
            print(f"   処理ファイル数: {len(audio_files)}")
            print(f"   登録楽曲数: {stats.get('songs', 0)}")
            print(f"   総フィンガープリント数: {stats.get('fingerprints', 0)}")
    else:
        print(f"⚠️  音楽ディレクトリが見つかりません: {music_dir}")
        print("   test_media/ディレクトリに音声ファイルを配置してください")


def main():
    """メインデモ関数"""
    setup_logging()
    
    print("🎵 Mimizam デモンストレーション")
    print("============================================================")
    print("Shazam風音響フィンガープリンティングシステム")
    print("============================================================")
    
    try:
        # 基本使用方法
        demo_basic_usage()
        
        # 高度な使用方法
        demo_advanced_usage()
        
        # バッチ処理
        demo_batch_processing()
        
        print("\n🎉 デモ完了！")
        
    except Exception as e:
        print(f"❌ デモ実行中にエラーが発生しました: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
