# 動画処理

このドキュメントでは、mimizamを使用して動画ファイルから音声を抽出し、音声指紋を生成する方法について説明します。動画コンテンツの音声識別や分析に活用できます。

他の実例については、以下を参照してください：
- [基本的な使用例](./06_1_basic_usage_examples.md) - すぐに使えるサンプルコード
- [パフォーマンス最適化](./06_3_performance_optimization.md) - 高速化技術

## 概要

動画処理機能により、MP4、AVI、MOV等の動画ファイルから音声トラックを抽出し、mimizamの音声指紋システムで処理できます。これにより、動画コンテンツの音楽識別、著作権検出、コンテンツ分析が可能になります。

## 基本的な動画処理

### 動画から音声抽出

```python
from mimizam import create_mimizam_sqlite
import moviepy.editor as mp
import os
import tempfile

class VideoProcessor:
    """動画処理クラス"""
    
    def __init__(self, db_path):
        self.mimizam = create_mimizam_sqlite(db_path)
    
    def extract_audio_from_video(self, video_path, output_path=None):
        """動画ファイルから音声を抽出"""
        
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"動画ファイルが見つかりません: {video_path}")
        
        try:
            # 動画ファイルを読み込み
            video = mp.VideoFileClip(video_path)
            
            # 音声トラックを取得
            audio = video.audio
            
            if audio is None:
                raise ValueError("動画ファイルに音声トラックが含まれていません")
            
            # 出力パスが指定されていない場合は一時ファイルを作成
            if output_path is None:
                temp_file = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
                output_path = temp_file.name
                temp_file.close()
            
            # 音声をWAVファイルとして保存
            audio.write_audiofile(
                output_path,
                codec='pcm_s16le',  # 16-bit PCM
                ffmpeg_params=['-ac', '1', '-ar', '22050']  # モノラル、22050Hz
            )
            
            # リソースを解放
            audio.close()
            video.close()
            
            print(f"音声抽出完了: {output_path}")
            return output_path
            
        except Exception as e:
            raise RuntimeError(f"音声抽出エラー: {e}")
    
    def process_video_file(self, video_path, video_title=None):
        """動画ファイルを処理してデータベースに登録"""
        
        print(f"動画処理開始: {os.path.basename(video_path)}")
        
        try:
            # 音声を抽出
            audio_path = self.extract_audio_from_video(video_path)
            
            # タイトルが指定されていない場合はファイル名を使用
            if video_title is None:
                video_title = os.path.splitext(os.path.basename(video_path))[0]
            
            # 音声指紋を生成してデータベースに登録
            song_id = self.mimizam.add_song(
                audio_path,
                song_name=video_title,
                file_path=video_path  # 元の動画ファイルパスを保存
            )
            
            # 一時音声ファイルを削除
            if os.path.exists(audio_path):
                os.unlink(audio_path)
            
            print(f"動画処理完了: ID {song_id}")
            return song_id
            
        except Exception as e:
            print(f"動画処理エラー: {e}")
            return None

# 使用例
processor = VideoProcessor("video_music.db")

# 動画ファイルを処理
video_file = "path/to/your/video.mp4"
song_id = processor.process_video_file(video_file, "My Video Title")
```

### 動画の音声識別

```python
def identify_video_audio(processor, video_path):
    """動画の音声を識別"""
    
    print(f"動画音声識別: {os.path.basename(video_path)}")
    
    try:
        # 動画から音声を抽出
        audio_path = processor.extract_audio_from_video(video_path)
        
        # 音声識別を実行
        matches = processor.mimizam.identify(audio_path)
        
        # 一時音声ファイルを削除
        if os.path.exists(audio_path):
            os.unlink(audio_path)
        
        # 結果を表示
        if matches:
            print(f"識別結果:")
            for i, match in enumerate(matches[:3], 1):
                print(f"  {i}. {match['song_name']}")
                print(f"     信頼度: {match['confidence']:.3f}")
                print(f"     スコア: {match['score']:.3f}")
        else:
            print("マッチする音声が見つかりませんでした")
        
        return matches
        
    except Exception as e:
        print(f"動画音声識別エラー: {e}")
        return None

# 使用例
query_video = "path/to/query/video.mp4"
matches = identify_video_audio(processor, query_video)
```

## 関連ドキュメント

- [基本的な使用例](./06_1_basic_usage_examples.md) - すぐに使えるサンプルコード
- [パフォーマンス最適化](./06_3_performance_optimization.md) - 高速化技術
- [コアアーキテクチャ](./03_core_architecture.md) - システムの内部構造
- [高レベルAPI](./04_1_high_level_api.md) - 統合インターフェース
