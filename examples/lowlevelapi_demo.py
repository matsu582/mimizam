#!/usr/bin/env python3
"""
Shazam風音声フィンガープリンティングシステムの使用例
"""

import os
import sys
from pathlib import Path
import numpy as np
import logging


from mimizam import AudioFingerprinter, FingerprintDatabase, FingerprintMatcher, Song, DatabaseConfig

def setup_logging():
    """ログ設定のセットアップ"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )


def add_song_to_database(fingerprinter: AudioFingerprinter, 
                        database: FingerprintDatabase,
                        audio_file: str,
                        song_id: str,
                        title: str,
                        artist: str) -> bool:
    """
    楽曲をフィンガープリントデータベースに追加する
    
    Args:
        fingerprinter: AudioFingerprinterインスタンス
        database: FingerprintDatabaseインスタンス
        audio_file: 音声ファイルのパス
        song_id: 一意の楽曲識別子
        title: 楽曲タイトル
        artist: アーティスト名
        
    Returns:
        成功時はTrue、失敗時はFalse
    """
    try:
        print(f"Processing: {title} by {artist}")
        
        # フィンガープリントを生成
        fingerprints = fingerprinter.fingerprint_file(audio_file)
        print(f"Generated {len(fingerprints)} fingerprints")
        
        # 楽曲オブジェクトを作成
        song = Song(id=song_id, title=title, artist=artist, file_path=audio_file)
        
        # データベースに追加
        if database.add_song(song):
            if database.add_fingerprints(song_id, fingerprints):
                print(f"Successfully added {title} to database")
                return True
        
        print(f"Failed to add {title} to database")
        return False
        
    except Exception as e:
        print(f"Error processing {title}: {e}")
        return False


def identify_audio_sample(fingerprinter: AudioFingerprinter,
                         matcher: FingerprintMatcher,
                         audio_file: str) -> None:
    """
    フィンガープリントデータベースを使用して音声サンプルを特定する
    
    Args:
        fingerprinter: AudioFingerprinterインスタンス
        matcher: FingerprintMatcherインスタンス
        audio_file: 特定する音声ファイルのパス
    """
    try:
        print(f"\nIdentifying audio sample: {audio_file}")
        
        # クエリ用のフィンガープリントを生成
        fingerprints = fingerprinter.fingerprint_file(audio_file)
        print(f"Generated {len(fingerprints)} query fingerprints")
        
        # 検索
        result = matcher.identify_audio(fingerprints)
        
        if result:
            song, confidence = result
            print("✅ MATCH FOUND!")
            print(f"   Song: {song.title}")
            print(f"   Artist: {song.artist}")
            print(f"   Confidence: {confidence:.2%}")
        else:
            print("❌ No match found")
            
    except Exception as e:
        print(f"Error identifying audio: {e}")


def generate_test_audio():
    """デモ用のテスト音声ファイルを生成"""
    print("Generating test audio files...")
    
    # データディレクトリが存在しない場合は作成
    data_dir = Path("../data")
    data_dir.mkdir(exist_ok=True)
    
    # テスト音声信号を生成
    duration = 5  # 秒
    sample_rate = 22050
    t = np.linspace(0, duration, duration * sample_rate)
    
    # テスト楽曲1: シンプルなサイン波
    freq1 = 440  # A4
    audio1 = np.sin(2 * np.pi * freq1 * t)
    
    # テスト楽曲2: 和音（複数の周波数）
    freq2_1, freq2_2, freq2_3 = 261.63, 329.63, 392.00  # Cメジャーコード
    audio2 = (np.sin(2 * np.pi * freq2_1 * t) + 
              np.sin(2 * np.pi * freq2_2 * t) + 
              np.sin(2 * np.pi * freq2_3 * t)) / 3
    
    # テスト楽曲3: より複雑な信号
    audio3 = (np.sin(2 * np.pi * 523.25 * t) +  # C5
              0.5 * np.sin(2 * np.pi * 659.25 * t) +  # E5
              0.3 * np.sin(2 * np.pi * 783.99 * t))  # G5
    
    # numpy配列として保存（実際のシナリオでは実際の音声ファイルを使用）
    np.save(data_dir / "test_song_1.npy", audio1)
    np.save(data_dir / "test_song_2.npy", audio2)
    np.save(data_dir / "test_song_3.npy", audio3)
    
    # test_song_1からサンプルを作成（録音をシミュレート）
    start_idx = sample_rate * 1  # 1秒から開始
    end_idx = start_idx + sample_rate * 2  # 2秒間の長さ
    sample1 = audio1[start_idx:end_idx]
    np.save(data_dir / "sample_from_song_1.npy", sample1)
    
    print("Test audio files generated in ../data/")
    
    # テストアーティストの定数を定義
    TEST_ARTIST = "Test Artist"
    
    return [
        (str(data_dir / "test_song_1.npy"), "song_1", "Test Song 1", TEST_ARTIST),
        (str(data_dir / "test_song_2.npy"), "song_2", "Test Song 2", TEST_ARTIST),
        (str(data_dir / "test_song_3.npy"), "song_3", "Test Song 3", TEST_ARTIST),
    ], str(data_dir / "sample_from_song_1.npy")


def load_numpy_audio(file_path: str) -> np.ndarray:
    """numpyファイルから音声をロード"""
    return np.load(file_path)


def main():
    """メイン例関数"""
    setup_logging()
    
    print("Shazam-style Audio Fingerprinting Demo")
    print("=" * 40)
    
    # コンポーネントを初期化
    fingerprinter = AudioFingerprinter()
    
    # データベース設定を作成
    db_config = DatabaseConfig(
        backend='sqlite',
        file_path='demo_fingerprints.db'
    )
    database = FingerprintDatabase(db_config)
    matcher = FingerprintMatcher(database)
    
    # テスト音声ファイルを生成
    test_songs, test_sample = generate_test_audio()
    
    # numpyファイルを処理するためにfingerprinteをを修正
    original_load_audio = fingerprinter.load_audio
    def load_audio_wrapper(file_path):
        if file_path.endswith('.npy'):
            return load_numpy_audio(file_path)
        else:
            return original_load_audio(file_path)
    
    fingerprinter.load_audio = load_audio_wrapper
    
    print("\n📊 Database Stats:")
    stats = database.get_database_stats()
    print(f"   Songs: {stats['songs']}")
    print(f"   Fingerprints: {stats['fingerprints']}")
    
    # テスト楽曲をデータベースに追加
    print("\n🎵 Adding songs to database...")
    for audio_file, song_id, title, artist in test_songs:
        add_song_to_database(fingerprinter, database, audio_file, song_id, title, artist)
    
    # 更新された統計を表示
    print("\n📊 Updated Database Stats:")
    stats = database.get_database_stats()
    print(f"   Songs: {stats['songs']}")
    print(f"   Fingerprints: {stats['fingerprints']}")
    
    # 識別をテスト
    print("\n🔍 Testing audio identification...")
    identify_audio_sample(fingerprinter, matcher, test_sample)
    
    # データベース内の全楽曲をリスト表示
    print("\n📚 Songs in database:")
    songs = database.list_songs()
    for song in songs:
        print(f"   - {song.title} by {song.artist} (ID: {song.id})")
    
    print("\n✅ Demo completed!")



if __name__ == "__main__":
    main()
