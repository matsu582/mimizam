# 動画処理

mimizamシステムは動画ファイルからの音声抽出と指紋生成をサポートしています。このページでは、動画ファイルの処理方法と動画音声の識別について説明します。

基本的な音声処理については、[基本的な使用例](./14_basic_usage_examples.md)を参照してください。高度な処理技術については、[パフォーマンス最適化](./16_performance_optimization.md)を参照してください。

## 動画処理の概要

### 対応動画形式

mimizamは以下の動画形式をサポートしています：

| 形式 | 拡張子 | 音声コーデック | 備考 |
|------|--------|---------------|------|
| MP4 | .mp4 | AAC, MP3 | 最も一般的な形式 |
| AVI | .avi | PCM, MP3 | 古い形式だが広く対応 |
| MOV | .mov | AAC, PCM | Apple形式 |
| MKV | .mkv | 各種 | オープンソース形式 |
| WebM | .webm | Vorbis, Opus | Web用形式 |

### 必要な依存関係

動画処理には追加の依存関係が必要です：

```bash
# FFmpeg（システムレベル）
# Ubuntu/Debian
sudo apt install ffmpeg

# macOS
brew install ffmpeg

# Windows
# https://ffmpeg.org/download.html からダウンロード

# Python依存関係
pip install moviepy
pip install ffmpeg-python
```

## 基本的な動画処理

### 動画からの音声抽出

```python
from mimizam import create_mimizam_sqlite
import moviepy.editor as mp
import tempfile
import os

def extract_audio_from_video(video_path, audio_path=None):
    """動画ファイルから音声を抽出"""
    if audio_path is None:
        # 一時ファイルを作成
        temp_fd, audio_path = tempfile.mkstemp(suffix='.wav')
        os.close(temp_fd)
    
    try:
        # 動画を読み込み
        video = mp.VideoFileClip(video_path)
        
        # 音声を抽出
        audio = video.audio
        
        # WAV形式で保存
        audio.write_audiofile(
            audio_path,
            codec='pcm_s16le',  # 16-bit PCM
            ffmpeg_params=['-ac', '1']  # モノラル変換
        )
        
        # リソース解放
        audio.close()
        video.close()
        
        return audio_path
        
    except Exception as e:
        if os.path.exists(audio_path):
            os.remove(audio_path)
        raise e

def video_fingerprinting_example():
    """動画ファイルの指紋生成例"""
    video_file = "sample_video.mp4"
    
    with create_mimizam_sqlite("video_music.db") as mimizam:
        try:
            # 動画から音声を抽出
            print(f"音声抽出中: {video_file}")
            audio_path = extract_audio_from_video(video_file)
            
            # 楽曲として追加
            song_id = mimizam.add_song(
                audio_path,
                "Video Background Music",
                "Video Artist"
            )
            
            print(f"動画音声追加完了: ID {song_id}")
            
            # 一時ファイル削除
            os.remove(audio_path)
            
        except Exception as e:
            print(f"動画処理エラー: {e}")

if __name__ == "__main__":
    video_fingerprinting_example()
```

### 動画音声の識別

```python
def identify_video_audio():
    """動画音声の識別"""
    query_video = "query_video.mp4"
    
    with create_mimizam_sqlite("video_music.db") as mimizam:
        try:
            # クエリ動画から音声を抽出
            print(f"クエリ音声抽出中: {query_video}")
            query_audio = extract_audio_from_video(query_video)
            
            # 音声識別
            result = mimizam.identify_audio(query_audio)
            
            if result:
                song, confidence = result
                print(f"識別成功: {song.title}")
                print(f"信頼度: {confidence:.2%}")
            else:
                print("動画音声を識別できませんでした")
            
            # 一時ファイル削除
            os.remove(query_audio)
            
        except Exception as e:
            print(f"動画識別エラー: {e}")

if __name__ == "__main__":
    identify_video_audio()
```

## 高度な動画処理

### 動画セグメント処理

```python
def process_video_segments():
    """動画を時間セグメントに分割して処理"""
    video_file = "long_video.mp4"
    segment_duration = 30  # 30秒セグメント
    
    with create_mimizam_sqlite("segmented_video.db") as mimizam:
        try:
            # 動画を読み込み
            video = mp.VideoFileClip(video_file)
            total_duration = video.duration
            
            print(f"動画長: {total_duration:.1f}秒")
            print(f"セグメント数: {int(total_duration / segment_duration) + 1}")
            
            segment_results = []
            
            # セグメントごとに処理
            for start_time in range(0, int(total_duration), segment_duration):
                end_time = min(start_time + segment_duration, total_duration)
                
                print(f"処理中: {start_time}秒 - {end_time}秒")
                
                # セグメントを抽出
                segment = video.subclip(start_time, end_time)
                segment_audio = segment.audio
                
                # 一時音声ファイル作成
                temp_fd, temp_audio = tempfile.mkstemp(suffix='.wav')
                os.close(temp_fd)
                
                try:
                    # 音声を保存
                    segment_audio.write_audiofile(
                        temp_audio,
                        codec='pcm_s16le',
                        ffmpeg_params=['-ac', '1'],
                        verbose=False,
                        logger=None
                    )
                    
                    # 楽曲として追加
                    song_id = mimizam.add_song(
                        temp_audio,
                        f"Video Segment {start_time}-{end_time}s",
                        "Segmented Video"
                    )
                    
                    segment_results.append({
                        'start_time': start_time,
                        'end_time': end_time,
                        'song_id': song_id
                    })
                    
                finally:
                    # リソース解放
                    segment_audio.close()
                    segment.close()
                    if os.path.exists(temp_audio):
                        os.remove(temp_audio)
            
            video.close()
            
            print(f"\nセグメント処理完了: {len(segment_results)} セグメント")
            
            return segment_results
            
        except Exception as e:
            print(f"セグメント処理エラー: {e}")
            return []

if __name__ == "__main__":
    process_video_segments()
```

### バッチ動画処理

```python
import glob
from concurrent.futures import ThreadPoolExecutor, as_completed

def batch_video_processing():
    """複数動画ファイルのバッチ処理"""
    
    def process_single_video(video_path):
        """単一動画ファイルの処理"""
        try:
            # 動画から音声を抽出
            audio_path = extract_audio_from_video(video_path)
            
            # ファイル名から情報を抽出
            filename = os.path.splitext(os.path.basename(video_path))[0]
            
            with create_mimizam_sqlite("batch_videos.db") as mimizam:
                song_id = mimizam.add_song(
                    audio_path,
                    filename,
                    "Video Collection"
                )
            
            # 一時ファイル削除
            os.remove(audio_path)
            
            return {
                'video_path': video_path,
                'song_id': song_id,
                'status': 'success'
            }
            
        except Exception as e:
            return {
                'video_path': video_path,
                'error': str(e),
                'status': 'error'
            }
    
    # 動画ファイルを検索
    video_files = glob.glob("video_collection/*.mp4")
    video_files.extend(glob.glob("video_collection/*.avi"))
    video_files.extend(glob.glob("video_collection/*.mov"))
    
    print(f"処理対象動画数: {len(video_files)}")
    
    results = []
    
    # 並列処理
    with ThreadPoolExecutor(max_workers=2) as executor:  # 動画処理は重いので2並列
        future_to_video = {
            executor.submit(process_single_video, video_path): video_path
            for video_path in video_files
        }
        
        for future in as_completed(future_to_video):
            video_path = future_to_video[future]
            try:
                result = future.result()
                results.append(result)
                
                if result['status'] == 'success':
                    print(f"✓ 完了: {os.path.basename(video_path)}")
                else:
                    print(f"✗ エラー: {os.path.basename(video_path)} - {result['error']}")
                    
            except Exception as e:
                print(f"✗ 処理エラー: {os.path.basename(video_path)} - {e}")
    
    # 結果統計
    successful = [r for r in results if r['status'] == 'success']
    failed = [r for r in results if r['status'] == 'error']
    
    print(f"\n処理結果:")
    print(f"成功: {len(successful)} 動画")
    print(f"失敗: {len(failed)} 動画")

if __name__ == "__main__":
    batch_video_processing()
```

## 動画音声の品質最適化

### 音声品質向上

```python
def enhance_video_audio_quality(video_path, enhanced_audio_path):
    """動画音声の品質向上"""
    try:
        # 動画を読み込み
        video = mp.VideoFileClip(video_path)
        audio = video.audio
        
        # 音声品質向上の設定
        enhanced_audio = audio.fx(
            # ノーマライゼーション
            mp.afx.audio_normalize
        )
        
        # 高品質で保存
        enhanced_audio.write_audiofile(
            enhanced_audio_path,
            codec='pcm_s24le',  # 24-bit PCM
            ffmpeg_params=[
                '-ac', '1',  # モノラル
                '-ar', '44100',  # 44.1kHz
                '-af', 'highpass=f=80,lowpass=f=8000'  # フィルタ適用
            ]
        )
        
        # リソース解放
        enhanced_audio.close()
        audio.close()
        video.close()
        
        return enhanced_audio_path
        
    except Exception as e:
        print(f"音声品質向上エラー: {e}")
        raise

def quality_enhanced_processing():
    """品質向上された動画音声処理"""
    video_file = "low_quality_video.mp4"
    
    with create_mimizam_sqlite("enhanced_video.db") as mimizam:
        try:
            # 音声品質を向上
            temp_fd, enhanced_audio = tempfile.mkstemp(suffix='.wav')
            os.close(temp_fd)
            
            enhance_video_audio_quality(video_file, enhanced_audio)
            
            # 品質向上された音声で指紋生成
            song_id = mimizam.add_song(
                enhanced_audio,
                "Enhanced Video Audio",
                "Quality Enhanced"
            )
            
            print(f"品質向上音声追加完了: ID {song_id}")
            
            # 一時ファイル削除
            os.remove(enhanced_audio)
            
        except Exception as e:
            print(f"品質向上処理エラー: {e}")

if __name__ == "__main__":
    quality_enhanced_processing()
```

## ライブストリーム処理

### リアルタイム動画音声識別

```python
import threading
import queue
import time

def realtime_video_identification():
    """リアルタイム動画音声識別"""
    
    class VideoStreamProcessor:
        def __init__(self, mimizam_instance):
            self.mimizam = mimizam_instance
            self.audio_queue = queue.Queue()
            self.running = False
        
        def start_processing(self):
            """処理開始"""
            self.running = True
            
            # 音声処理スレッド
            processing_thread = threading.Thread(target=self._process_audio_queue)
            processing_thread.start()
            
            return processing_thread
        
        def stop_processing(self):
            """処理停止"""
            self.running = False
        
        def add_audio_segment(self, audio_path):
            """音声セグメントを処理キューに追加"""
            self.audio_queue.put(audio_path)
        
        def _process_audio_queue(self):
            """音声キューの処理"""
            while self.running:
                try:
                    # タイムアウト付きでキューから取得
                    audio_path = self.audio_queue.get(timeout=1.0)
                    
                    # 音声識別
                    result = self.mimizam.identify_audio(audio_path)
                    
                    if result:
                        song, confidence = result
                        print(f"[{time.strftime('%H:%M:%S')}] 識別: {song.title} ({confidence:.1%})")
                    else:
                        print(f"[{time.strftime('%H:%M:%S')}] 識別失敗")
                    
                    # 一時ファイル削除
                    if os.path.exists(audio_path):
                        os.remove(audio_path)
                    
                    self.audio_queue.task_done()
                    
                except queue.Empty:
                    continue
                except Exception as e:
                    print(f"処理エラー: {e}")
    
    # ストリーム処理の例
    with create_mimizam_sqlite("stream_music.db") as mimizam:
        processor = VideoStreamProcessor(mimizam)
        
        # 処理開始
        processing_thread = processor.start_processing()
        
        try:
            # 模擬ストリームデータ
            stream_segments = [
                "stream_segment_1.wav",
                "stream_segment_2.wav",
                "stream_segment_3.wav"
            ]
            
            for segment in stream_segments:
                # セグメントを処理キューに追加
                processor.add_audio_segment(segment)
                
                # 次のセグメントまで待機
                time.sleep(5)
            
            # 処理完了まで待機
            processor.audio_queue.join()
            
        finally:
            # 処理停止
            processor.stop_processing()
            processing_thread.join()

if __name__ == "__main__":
    realtime_video_identification()
```

## トラブルシューティング

### 一般的な問題と解決方法

```python
def diagnose_video_processing_issues():
    """動画処理問題の診断"""
    
    def check_ffmpeg_installation():
        """FFmpegインストール確認"""
        try:
            import subprocess
            result = subprocess.run(['ffmpeg', '-version'], 
                                  capture_output=True, text=True)
            if result.returncode == 0:
                print("✓ FFmpeg正常インストール済み")
                return True
            else:
                print("✗ FFmpegエラー")
                return False
        except FileNotFoundError:
            print("✗ FFmpeg未インストール")
            return False
    
    def check_video_file(video_path):
        """動画ファイル確認"""
        try:
            video = mp.VideoFileClip(video_path)
            
            print(f"動画情報: {video_path}")
            print(f"  長さ: {video.duration:.1f}秒")
            print(f"  FPS: {video.fps}")
            print(f"  解像度: {video.size}")
            
            if video.audio is not None:
                print(f"  音声: あり")
                print(f"  音声長: {video.audio.duration:.1f}秒")
            else:
                print(f"  音声: なし")
                return False
            
            video.close()
            return True
            
        except Exception as e:
            print(f"動画ファイルエラー: {e}")
            return False
    
    def test_audio_extraction(video_path):
        """音声抽出テスト"""
        try:
            temp_fd, temp_audio = tempfile.mkstemp(suffix='.wav')
            os.close(temp_fd)
            
            audio_path = extract_audio_from_video(video_path, temp_audio)
            
            # 音声ファイル確認
            if os.path.exists(audio_path):
                file_size = os.path.getsize(audio_path)
                print(f"✓ 音声抽出成功: {file_size} bytes")
                os.remove(audio_path)
                return True
            else:
                print("✗ 音声ファイル作成失敗")
                return False
                
        except Exception as e:
            print(f"音声抽出エラー: {e}")
            return False
    
    # 診断実行
    print("動画処理診断開始...")
    
    # FFmpeg確認
    ffmpeg_ok = check_ffmpeg_installation()
    
    # テスト動画ファイル確認
    test_video = "test_video.mp4"
    if os.path.exists(test_video):
        video_ok = check_video_file(test_video)
        
        if video_ok and ffmpeg_ok:
            extraction_ok = test_audio_extraction(test_video)
        else:
            extraction_ok = False
    else:
        print(f"テスト動画ファイル未発見: {test_video}")
        video_ok = False
        extraction_ok = False
    
    # 診断結果
    print(f"\n診断結果:")
    print(f"FFmpeg: {'OK' if ffmpeg_ok else 'NG'}")
    print(f"動画ファイル: {'OK' if video_ok else 'NG'}")
    print(f"音声抽出: {'OK' if extraction_ok else 'NG'}")
    
    if all([ffmpeg_ok, video_ok, extraction_ok]):
        print("✓ 動画処理環境正常")
    else:
        print("✗ 動画処理環境に問題あり")

if __name__ == "__main__":
    diagnose_video_processing_issues()
```

## 関連ドキュメント

- [基本的な使用例](./14_basic_usage_examples.md) - 基本的な音声処理
- [パフォーマンス最適化](./16_performance_optimization.md) - 高速化技術
- [高レベルAPI](./07_high_level_api.md) - Mimizamクラスの使用方法
- [よくある質問（FAQ）](./19_faq.md) - トラブルシューティング
