# 動画処理

mimizamは動画ファイルから音声を抽出して音声指紋を生成し、動画コンテンツの識別を行うことができます。FFmpegとの連携により、様々な動画形式に対応し、効率的な動画音声処理を実現します。

## 🎬 動画処理の概要

### 対応機能

```
動画処理システム
├── 音声抽出
│   ├── FFmpeg連携
│   ├── 複数形式対応
│   └── 品質設定
├── バッチ処理
│   ├── ディレクトリ一括処理
│   ├── 並列処理
│   └── 進捗監視
├── 動画検索
│   ├── 部分マッチング
│   ├── 時間範囲指定
│   └── 類似度評価
└── メタデータ管理
    ├── 動画情報抽出
    ├── タイムスタンプ記録
    └── 検索結果表示
```

## 🔧 VideoFingerprinter クラス

### 基本的な使用方法

```python
from mimizam.examples.video_fingerprinter import VideoFingerprinter
from mimizam import create_mimizam_sqlite
import os

# 動画指紋生成器の初期化
video_fingerprinter = VideoFingerprinter(
    temp_dir="./temp_audio",           # 一時音声ファイル保存先
    keep_temp_files=False,             # 一時ファイルを保持するか
    audio_format="wav",                # 抽出音声形式
    sample_rate=22050,                 # サンプルレート
    audio_quality="high"               # 音声品質
)

# データベース接続
mimizam = create_mimizam_sqlite("video_database.db")

# 動画ファイルの処理
video_path = "sample_video.mp4"
song_id = video_fingerprinter.process_video(
    video_path=video_path,
    title="Sample Video",
    artist="Content Creator",
    mimizam=mimizam
)

print(f"動画処理完了: {song_id}")
```

### 対応動画形式

```python
# 対応する動画形式
SUPPORTED_VIDEO_FORMATS = {
    'mp4': 'MPEG-4 Video',
    'avi': 'Audio Video Interleave',
    'mov': 'QuickTime Movie',
    'mkv': 'Matroska Video',
    'wmv': 'Windows Media Video',
    'flv': 'Flash Video',
    'webm': 'WebM Video',
    'm4v': 'iTunes Video',
    '3gp': '3GPP Video',
    'ogv': 'Ogg Video'
}

# 対応する音声形式（抽出後）
SUPPORTED_AUDIO_FORMATS = {
    'wav': 'Waveform Audio',
    'mp3': 'MPEG Audio Layer III',
    'flac': 'Free Lossless Audio Codec',
    'aac': 'Advanced Audio Coding',
    'ogg': 'Ogg Vorbis'
}
```

### FFmpeg連携設定

```python
import subprocess
import json
from pathlib import Path
from mimizam import create_mimizam_sqlite

def extract_audio_from_video(video_path: str, output_path: str = None, 
                           ffmpeg_path: str = "ffmpeg") -> str:
    """動画から音声を抽出"""
    
    if output_path is None:
        video_name = Path(video_path).stem
        output_path = f"{video_name}.wav"
    
    # FFmpegコマンドを構築
    cmd = [
        ffmpeg_path,
        "-i", video_path,
        "-vn",  # 動画ストリームを無視
        "-acodec", "pcm_s16le",  # 16bit PCM
        "-ar", "22050",  # サンプリングレート
        "-ac", "1",  # モノラル
        "-y",  # 上書き許可
        output_path
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        print(f"音声抽出完了: {output_path}")
        return output_path
    except subprocess.CalledProcessError as e:
        raise Exception(f"FFmpeg error: {e.stderr}")

def process_video_with_mimizam(video_path: str, title: str, artist: str) -> str:
    """動画を処理してmimizamに追加"""
    
    # mimizamインスタンスを作成
    mimizam = create_mimizam_sqlite("video_database.db")
    
    try:
        # 音声を抽出
        audio_path = extract_audio_from_video(video_path)
        
        # mimizamに追加
        song_id = mimizam.add_song(audio_path, title, artist)
        
        # 一時ファイルを削除
        Path(audio_path).unlink()
        
        print(f"動画が追加されました: {song_id}")
        return song_id
        
    except Exception as e:
        print(f"動画処理エラー: {e}")
        return None
    finally:
        mimizam.close()

def get_video_info(video_path: str) -> dict:
    """動画情報を取得"""
    
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        video_path
        ]
        
        try:
            import subprocess
            import json
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True
            )
            
            info = json.loads(result.stdout)
            
            # 動画情報の抽出
            video_info = {
                'duration': float(info['format'].get('duration', 0)),
                'size': int(info['format'].get('size', 0)),
                'bitrate': int(info['format'].get('bit_rate', 0)),
                'format_name': info['format'].get('format_name', ''),
                'streams': []
            }
            
            # ストリーム情報
            for stream in info['streams']:
                stream_info = {
                    'codec_type': stream.get('codec_type'),
                    'codec_name': stream.get('codec_name'),
                    'duration': float(stream.get('duration', 0))
                }
                
                if stream['codec_type'] == 'video':
                    stream_info.update({
                        'width': stream.get('width'),
                        'height': stream.get('height'),
                        'fps': eval(stream.get('r_frame_rate', '0/1'))
                    })
                elif stream['codec_type'] == 'audio':
                    stream_info.update({
                        'sample_rate': int(stream.get('sample_rate', 0)),
                        'channels': int(stream.get('channels', 0))
                    })
                
                video_info['streams'].append(stream_info)
            
            return video_info
            
        except subprocess.CalledProcessError as e:
            print(f"動画情報取得エラー: {e}")
            return {}

# 使用例
processor = VideoProcessor()
video_info = processor.get_video_info("sample_video.mp4")
print(f"動画情報: {video_info}")

audio_path = processor.extract_audio("sample_video.mp4")
print(f"抽出された音声: {audio_path}")
```

## 🎵 動画音声指紋生成

### 動画音声指紋生成

```python
from mimizam import create_mimizam_sqlite
import subprocess
import os

def process_video_with_mimizam(video_path: str, title: str = None, artist: str = None):
    """動画ファイルから音声を抽出してmimizamに追加"""
    
    # メタデータの準備
    if title is None:
        title = os.path.splitext(os.path.basename(video_path))[0]
    if artist is None:
        artist = "Unknown Creator"
    
    # 一時音声ファイルのパス
    temp_audio_path = f"temp_{os.path.basename(video_path)}.wav"
    
    try:
        # FFmpegで音声抽出
        cmd = [
            'ffmpeg',
            '-i', video_path,
            '-vn',                    # 動画ストリーム無視
            '-acodec', 'pcm_s16le',   # 音声コーデック
            '-ar', '22050',           # サンプルレート
            '-ac', '1',               # モノラル
            '-y',                     # 上書き許可
            temp_audio_path
        ]
        
        subprocess.run(cmd, capture_output=True, check=True)
        
        # mimizamに楽曲として追加
        mimizam = create_mimizam_sqlite("video_music.db")
        song_id = mimizam.add_song(temp_audio_path, title, artist)
        
        print(f"動画処理完了: {title} (ID: {song_id})")
        
        mimizam.close()
        return song_id
        
    finally:
        # 一時ファイルのクリーンアップ
        if os.path.exists(temp_audio_path):
            os.remove(temp_audio_path)
            
        except Exception as e:
            self.stats['processing_errors'] += 1
            print(f"動画処理エラー {video_path}: {e}")
            raise
    
    def _update_song_metadata(self, song_id: str, video_info: dict, video_path: str):
        """楽曲メタデータに動画情報を追加"""
        
        # 動画固有のメタデータ
        video_metadata = {
            'source_type': 'video',
            'original_video_path': video_path,
            'video_duration': video_info.get('duration', 0),
            'video_format': video_info.get('format_name', ''),
            'video_size': video_info.get('size', 0),
            'video_bitrate': video_info.get('bitrate', 0)
        }
        
        # 動画ストリーム情報
        for stream in video_info.get('streams', []):
            if stream['codec_type'] == 'video':
                video_metadata.update({
                    'video_codec': stream.get('codec_name'),
                    'video_width': stream.get('width'),
                    'video_height': stream.get('height'),
                    'video_fps': stream.get('fps')
                })
            elif stream['codec_type'] == 'audio':
                video_metadata.update({
                    'audio_codec': stream.get('codec_name'),
                    'audio_sample_rate': stream.get('sample_rate'),
                    'audio_channels': stream.get('channels')
                })
        
        # メタデータ更新（実装は省略）
        print(f"メタデータ更新: {video_metadata}")
    
    def search_video(self, query_video_path: str, min_confidence: float = 0.3) -> list:
        """動画による検索"""
        
        try:
            # クエリ動画から音声抽出
            query_audio_path = self.processor.extract_audio(query_video_path)
            
            # 音声検索実行
            results = self.mimizam.search_song(
                query_path=query_audio_path,
                min_confidence=min_confidence
            )
            
            # 一時ファイルクリーンアップ
            if os.path.exists(query_audio_path):
                os.remove(query_audio_path)
            
            # 結果に動画情報を追加
            enhanced_results = []
            for result in results:
                enhanced_result = result.copy()
                enhanced_result['query_type'] = 'video'
                enhanced_result['query_path'] = query_video_path
                enhanced_results.append(enhanced_result)
            
            return enhanced_results
            
        except Exception as e:
            print(f"動画検索エラー: {e}")
            return []
    
    def get_processing_stats(self) -> dict:
        """処理統計を取得"""
        return self.stats.copy()

# 使用例
video_system = VideoFingerprintSystem(
    database_config={'file_path': 'video_music.db'}
)

# 動画処理
song_id = video_system.process_video_file(
    "music_video.mp4",
    title="My Favorite Song",
    artist="Great Artist"
)

# 動画検索
results = video_system.search_video("query_video.mp4")
for result in results:
    print(f"マッチ: {result['song']['title']} (信頼度: {result['confidence']:.3f})")

# 統計表示
stats = video_system.get_processing_stats()
print(f"処理統計: {stats}")
```

## 📁 バッチ動画処理

### ディレクトリ一括処理

```python
import glob
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

def process_video_directory_batch(video_dir: str, recursive: bool = True, file_patterns=None):
    """動画ディレクトリのバッチ処理"""
    
    if file_patterns is None:
        file_patterns = ['*.mp4', '*.avi', '*.mov', '*.mkv', '*.wmv']
    
    # 動画ファイル一覧取得
    video_files = []
    for pattern in file_patterns:
        if recursive:
            search_pattern = os.path.join(video_dir, '**', pattern)
            video_files.extend(glob.glob(search_pattern, recursive=True))
        else:
            search_pattern = os.path.join(video_dir, pattern)
            video_files.extend(glob.glob(search_pattern))
    
    print(f"処理対象動画ファイル数: {len(video_files)}")
    
    # mimizamインスタンス作成
    mimizam = create_mimizam_sqlite("batch_video_music.db")
    
    batch_stats = {
        'total_files': len(video_files),
        'processed_files': 0,
        'skipped_files': 0,
        'error_files': 0,
        'processing_time': 0
    }
    
    start_time = time.time()
    
    for i, video_path in enumerate(video_files):
        try:
            # ファイル名からメタデータを推測
            file_name = Path(video_path).stem
            title, artist = extract_metadata_from_filename(file_name)
            
            # 動画処理実行
            song_id = process_video_with_mimizam(video_path, title, artist)
            batch_stats['processed_files'] += 1
            
            print(f"✓ 処理完了 ({i+1}/{len(video_files)}): {title}")
            
        except Exception as e:
            batch_stats['error_files'] += 1
            print(f"✗ 処理エラー ({i+1}/{len(video_files)}): {video_path} - {e}")
        
        # 進捗表示
        if (i + 1) % 10 == 0:
            completed = batch_stats['processed_files'] + batch_stats['error_files']
            print(f"進捗: {completed}/{batch_stats['total_files']} "
                  f"({completed/batch_stats['total_files']*100:.1f}%)")
    
    batch_stats['processing_time'] = time.time() - start_time
    
    # 結果サマリー
    print(f"\n=== バッチ処理完了 ===")
    print(f"総ファイル数: {batch_stats['total_files']}")
    print(f"処理成功: {batch_stats['processed_files']}")
    print(f"エラー: {batch_stats['error_files']}")
    print(f"処理時間: {batch_stats['processing_time']:.2f}秒")
    
    mimizam.close()
    return batch_stats

def extract_metadata_from_filename(filename: str) -> tuple:
    """ファイル名からメタデータを抽出"""
    
    # 一般的な区切り文字で分割を試行
    separators = [' - ', '_-_', ' by ', '_by_', ' feat ', '_feat_']
    
    for sep in separators:
        if sep in filename:
            parts = filename.split(sep, 1)
            if len(parts) == 2:
                return parts[1].strip(), parts[0].strip()  # title, artist
    
    # 区切り文字が見つからない場合
    return filename, "Unknown Artist"

# 使用例
results = process_video_directory_batch(
    video_dir="/path/to/video/library",
    recursive=True,
    file_patterns=['*.mp4', '*.avi', '*.mov']
)
```

## 🔍 動画検索システム

### 高度な動画検索

```python
def search_video_with_time_range(query_video_path: str, start_time: float = 0, 
                                 duration: float = None, min_confidence: float = 0.3):
    """時間範囲指定での動画検索"""
    
    # 一時音声ファイルのパス
    temp_audio_path = f"temp_segment_{int(start_time)}_{int(duration or 30)}.wav"
    
    try:
        # 指定範囲の音声抽出
        cmd = [
            'ffmpeg',
            '-i', query_video_path,
            '-ss', str(start_time),      # 開始時間
            '-t', str(duration or 30),   # 継続時間
            '-vn',                       # 動画ストリーム無視
            '-acodec', 'pcm_s16le',      # 音声コーデック
            '-ar', '22050',              # サンプルレート
            '-ac', '1',                  # モノラル
            '-y',                        # 上書き許可
            temp_audio_path
        ]
        
        subprocess.run(cmd, capture_output=True, check=True)
        
        # 音声検索実行
        mimizam = create_mimizam_sqlite("video_search.db")
        results = mimizam.search_song(temp_audio_path, min_confidence)
        
        # 結果に時間情報を追加
        enhanced_results = []
        for result in results:
            enhanced_result = result.copy()
            enhanced_result['query_time_range'] = {
                'start': start_time,
                'duration': duration or 30,
                'end': start_time + (duration or 30)
            }
            enhanced_results.append(enhanced_result)
        
        mimizam.close()
        return enhanced_results
        
    except Exception as e:
        print(f"時間範囲検索エラー: {e}")
        return []
    finally:
        # 一時ファイルクリーンアップ
        if os.path.exists(temp_audio_path):
            os.remove(temp_audio_path)

def multi_segment_video_search(query_video_path: str, segment_duration: float = 30,
                              overlap: float = 10, min_confidence: float = 0.3):
    """複数セグメントでの動画検索"""
    
    # 動画の長さを取得（簡易版）
    try:
        import subprocess
        result = subprocess.run([
            'ffprobe', '-v', 'quiet', '-show_entries', 'format=duration',
            '-of', 'csv=p=0', query_video_path
        ], capture_output=True, text=True)
        total_duration = float(result.stdout.strip())
    except:
        print("動画の長さを取得できませんでした。デフォルト値を使用します。")
        total_duration = 300  # 5分と仮定
    
    # セグメント分割
    segments = []
    current_time = 0
    
    while current_time < total_duration:
        segment_end = min(current_time + segment_duration, total_duration)
        segments.append({
            'start': current_time,
            'duration': segment_end - current_time
        })
        current_time += segment_duration - overlap
    
    print(f"セグメント数: {len(segments)}")
    
    # 各セグメントで検索実行
    all_results = []
    for i, segment in enumerate(segments):
        print(f"セグメント {i+1}/{len(segments)} 検索中...")
        
        segment_results = search_video_with_time_range(
            query_video_path,
            segment['start'],
            segment['duration'],
            min_confidence
        )
        
        # セグメント情報を追加
        for result in segment_results:
            result['segment_index'] = i
            result['segment_info'] = segment
        
        all_results.extend(segment_results)
    
    # 結果の統合と重複除去
    consolidated_results = consolidate_search_results(all_results)
    
    return consolidated_results

def consolidate_search_results(results: list) -> list:
    """検索結果の統合"""
    
    # 楽曲IDでグループ化
    grouped_results = {}
    for result in results:
        song_id = result['song']['id']
        if song_id not in grouped_results:
            grouped_results[song_id] = []
        grouped_results[song_id].append(result)
    
    # 各楽曲の最高信頼度結果を選択
    consolidated = []
    for song_id, song_results in grouped_results.items():
        best_result = max(song_results, key=lambda x: x['confidence'])
        
        # セグメント情報をまとめる
        segments = [r.get('segment_info', {}) for r in song_results if 'segment_info' in r]
        best_result['matched_segments'] = segments
        best_result['segment_count'] = len(segments)
        
        consolidated.append(best_result)
    
    # 信頼度でソート
    consolidated.sort(key=lambda x: x['confidence'], reverse=True)
    
    return consolidated

# 使用例

# 時間範囲指定検索
results = search_video_with_time_range(
    "query_video.mp4",
    start_time=30,    # 30秒から
    duration=60,      # 60秒間
    min_confidence=0.4
)

print(f"時間範囲検索結果: {len(results)}件")
for result in results:
    song = result['song']
    time_range = result['query_time_range']
    print(f"マッチ: {song['title']} by {song['artist']}")
    print(f"信頼度: {result['confidence']:.3f}")
    print(f"検索範囲: {time_range['start']}-{time_range['end']}秒")

# 複数セグメント検索
multi_results = multi_segment_video_search(
    "long_video.mp4",
    segment_duration=45,  # 45秒セグメント
    overlap=15,           # 15秒オーバーラップ
    min_confidence=0.3
)

print(f"\n複数セグメント検索結果: {len(multi_results)}件")
for result in multi_results:
    song = result['song']
    print(f"マッチ: {song['title']} by {song['artist']}")
    print(f"信頼度: {result['confidence']:.3f}")
    print(f"マッチセグメント数: {result['segment_count']}")
```

## 🔗 関連ドキュメント

- [基本的な使用方法](./03_basic_usage.md) - 基本操作
- [高度な使用例](./17_advanced_examples.md) - 応用技術
- [バッチ処理](./17_advanced_examples.md#バッチ処理とパイプライン) - 大量処理
- [パフォーマンス最適化](./12_performance_optimization.md) - 性能向上
- [データベース設定](./10_database_setup.md) - データベース構成

## 💡 動画処理のベストプラクティス

### 1. FFmpeg設定
- 適切な音声品質設定
- 効率的なコーデック選択
- エラーハンドリングの実装

### 2. 一時ファイル管理
- 適切なクリーンアップ
- ディスク容量の監視
- 並列処理時の競合回避

### 3. メタデータ活用
- 動画情報の保存
- 検索結果の充実
- トレーサビリティの確保

動画処理機能により、mimizamシステムは音声だけでなく動画コンテンツの識別も可能になり、より幅広い用途に対応できます。
