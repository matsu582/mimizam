# 高レベルAPI

> 関連するソースファイル

このドキュメントでは、mimizamの高レベルAPIについて詳しく説明します。Mimizamクラス、ファクトリ関数、便利メソッドなど、日常的な使用で最も重要なAPIコンポーネントを扱います。

低レベルコンポーネントについては、[低レベルコンポーネント](./04_2_low_level_components.md)を参照してください。

## 概要

高レベルAPIは、mimizamの機能を簡単に使用できるように設計された統合インターフェースです。複雑な内部実装を隠蔽し、直感的で使いやすいメソッドを提供します。

### 高レベルAPIの設計原則

| 原則 | 説明 | 実装効果 |
|------|------|---------|
| **簡潔性** | 最小限のコードで最大の機能を提供 | 開発効率向上 |
| **一貫性** | 統一されたインターフェース設計 | 学習コスト削減 |
| **拡張性** | カスタマイズ可能なパラメータ設定 | 柔軟な用途対応 |
| **堅牢性** | 包括的なエラーハンドリング | 安定したアプリケーション |

## Mimizamクラス

### クラス設計

Mimizamクラスは、音声指紋生成、データベース管理、楽曲識別の全機能を統合した高レベルインターフェースを提供します。

#### 設計原則
- **統合性**: 複数のコンポーネントを単一インターフェースで管理
- **抽象化**: 内部実装の複雑さを隠蔽
- **一貫性**: 統一されたメソッド命名と引数構造
- **拡張性**: 将来の機能追加に対応する柔軟な設計

### 楽曲管理メソッド

#### add_song()

楽曲をデータベースに追加する主要メソッドです。音声ファイルから指紋を生成し、メタデータと共にデータベースに保存します。

##### 機能概要
- **音声処理**: 対応フォーマットの自動検出と読み込み
- **指紋生成**: 高精度な音声指紋の自動生成
- **メタデータ管理**: 楽曲情報の構造化保存
- **エラー処理**: ファイル不存在やフォーマットエラーの適切な処理

##### サポートメタデータ
- **基本情報**: アーティスト名、アルバム名、再生時間
- **分類情報**: ジャンル、リリース年、トラック番号
- **技術情報**: ファイルパス、音声品質、エンコード情報
- **カスタム情報**: ユーザー定義の追加属性
        
        return song_id
        
    except Exception as e:
        if isinstance(e, (AudioProcessingError, DatabaseError, FileNotFoundError)):
            raise
        else:
            raise AudioProcessingError(f"楽曲追加エラー: {e}")
```

#### get_song_info()

```python
def get_song_info(self, song_id):
    """
    楽曲情報を取得
    
    Args:
        song_id (int): 楽曲ID
    
    Returns:
        dict: 楽曲情報
            - id (int): 楽曲ID
            - name (str): 楽曲名
            - artist (str): アーティスト名
            - album (str): アルバム名
            - duration (float): 再生時間
            - file_path (str): ファイルパス
            - created_at (datetime): 作成日時
    
    Raises:
        DatabaseError: データベース操作エラー
        ValueError: 無効な楽曲ID
    
    Example:
        >>> song_info = mimizam.get_song_info(1)
        >>> print(f"楽曲名: {song_info['name']}")
        >>> print(f"アーティスト: {song_info['artist']}")
    """
    try:
        song_info = self.database.get_song_info(song_id)
        if not song_info:
            raise ValueError(f"楽曲ID {song_id} が見つかりません")
        return song_info
    except Exception as e:
        if isinstance(e, (DatabaseError, ValueError)):
            raise
        else:
            raise DatabaseError(f"楽曲情報取得エラー: {e}")
```

#### get_song_count()

データベース内の楽曲数を取得する統計メソッドです。

##### 機能
- **楽曲数取得**: データベース内の総楽曲数の即座取得
- **統計情報**: システム利用状況の把握
- **管理支援**: データベース容量とパフォーマンス管理

#### delete_song()

指定された楽曲をデータベースから完全に削除するメソッドです。

##### 削除処理
- **楽曲削除**: 楽曲レコードとメタデータの完全削除
- **指紋削除**: 関連する全音声指紋データの削除
- **整合性保証**: データベース整合性の自動維持
- **エラー処理**: 無効ID や削除失敗の適切な処理

### 音声識別メソッド

#### identify()

音声ファイルから楽曲を識別するメインメソッドです。高精度な音声指紋マッチングにより楽曲を特定します。

##### 識別プロセス
- **音声読み込み**: 対応フォーマットの自動検出と読み込み
- **指紋生成**: クエリ音声からの特徴抽出
- **データベース検索**: 効率的な指紋マッチング
- **結果ランキング**: 信頼度に基づく結果順位付け

##### 返却情報
- **楽曲情報**: ID、楽曲名、アーティスト、アルバム
- **マッチング情報**: スコア、信頼度、マッチ数
- **時間情報**: 時間オフセット、マッチ位置
- **品質指標**: 識別精度と信頼性評価
            raise
        else:
            raise AudioProcessingError(f"音声識別エラー: {e}")
```

#### identify_audio_data()

```python
def identify_audio_data(self, audio_data, sample_rate, threshold=None):
    """
    音声データから楽曲を識別
    
    Args:
        audio_data (numpy.ndarray): 音声データ
        sample_rate (int): サンプリングレート
        threshold (float, optional): マッチング閾値
    
    Returns:
        list: マッチした楽曲のリスト
    
    Raises:
        AudioProcessingError: 音声処理エラー
        ValueError: 無効な音声データ
    
    Example:
        >>> import librosa
        >>> audio_data, sr = librosa.load("query.wav")
        >>> matches = mimizam.identify_audio_data(audio_data, sr)
    """
    try:
        if audio_data is None or len(audio_data) == 0:
            raise ValueError("無効な音声データです")
        
        # 指紋を生成
        query_fingerprints = self.fingerprinter.generate_fingerprints_from_data(
            audio_data, sample_rate
        )
        
        # 識別を実行
        return self._identify_fingerprints(query_fingerprints, threshold)
        
    except Exception as e:
        if isinstance(e, (AudioProcessingError, ValueError)):
            raise
        else:
            raise AudioProcessingError(f"音声データ識別エラー: {e}")
```

### 可視化メソッド

#### generate_spectrogram()

```python
def generate_spectrogram(self, audio_path):
    """
    スペクトログラムを生成
    
    Args:
        audio_path (str): 音声ファイルのパス
    
    Returns:
        numpy.ndarray: スペクトログラム（時間×周波数）
#### generate_spectrogram()

音声ファイルからスペクトログラムを生成する低レベルメソッドです。

##### 機能概要
- **時間周波数変換**: 音声信号の時間-周波数表現への変換
- **スペクトログラム生成**: 高解像度な音響特徴の可視化
- **前処理**: 音声品質の正規化と最適化
- **エラー処理**: ファイル形式や品質問題の適切な処理

#### detect_peaks()

スペクトログラムから音響ピークを検出する特徴抽出メソッドです。

##### ピーク検出
- **局所最大値検出**: 時間-周波数空間での顕著な特徴点抽出
- **閾値処理**: ノイズ除去と重要ピークの選別
- **座標取得**: 時間と周波数の正確な座標情報
- **品質管理**: 検出精度の最適化と調整

## ファクトリ関数

### create_mimizam_sqlite()

SQLiteバックエンドを使用したMimizamインスタンスを作成するファクトリ関数です。

#### 機能概要
- **簡単セットアップ**: 最小限の設定でSQLiteベースシステムを構築
- **自動初期化**: データベーススキーマの自動作成と設定
- **パラメータ調整**: 音声処理パラメータのカスタマイズ対応
- **エラー処理**: データベース接続とファイル問題の適切な処理

#### 設定可能パラメータ
- **音声処理**: サンプリングレート、FFTサイズ、ホップ長
- **ピーク検出**: 検出閾値、最小距離、ターゲットゾーンサイズ
- **マッチング**: 最大時間差、スコアリング手法
- **データベース**: ファイルパス、接続設定、最適化オプション
    # 指紋生成器を作成
    fingerprinter = AudioFingerprinter(**params)
    
    # データベースを作成
    database = FingerprintDatabase(backend)
    
    # Mimizamインスタンスを作成
    return Mimizam(fingerprinter, database)
```

### create_mimizam_mysql()

```python
def create_mimizam_mysql(host, user, password, database, port=3306, **params):
    """
    MySQLバックエンドでMimizamインスタンスを作成
    
    Args:
        host (str): MySQLサーバーのホスト
        user (str): ユーザー名
        password (str): パスワード
        database (str): データベース名
        port (int, optional): ポート番号（デフォルト: 3306）
        **params: AudioFingerprinterのパラメータ
    
    Returns:
        Mimizam: 設定済みのMimizamインスタンス
    
    Example:
        >>> mimizam = create_mimizam_mysql(
        ...     host="localhost",
        ...     user="mimizam_user",
        ...     password="secure_password",
        ...     database="music_db"
        ... )
        >>> 
        >>> # SSL接続
        >>> mimizam = create_mimizam_mysql(
        ...     host="mysql.example.com",
        ...     user="mimizam_user",
        ...     password="secure_password",
        ...     database="music_db",
        ...     ssl_disabled=False,
        ...     ssl_ca="/path/to/ca.pem"
        ... )
    """
    from mimizam.backends.mysql_backend import MySQLBackend
    from mimizam.audio_fingerprinter import AudioFingerprinter
    from mimizam.fingerprint_database import FingerprintDatabase
    
    # バックエンドを作成
    backend = MySQLBackend(host, user, password, database, port)
    
    # 指紋生成器を作成
    fingerprinter = AudioFingerprinter(**params)
    
    # データベースを作成
    database = FingerprintDatabase(backend)
    
    # Mimizamインスタンスを作成
    return Mimizam(fingerprinter, database)
```

### create_mimizam_postgresql()

PostgreSQLバックエンドを使用したMimizamインスタンスを作成するエンタープライズ向けファクトリ関数です。

#### 機能概要
- **高性能データベース**: PostgreSQLの高度な機能を活用
- **スケーラビリティ**: 大規模データセットに対応
- **セキュリティ**: SSL接続と認証機能の完全サポート
- **トランザクション**: ACID準拠の信頼性の高いデータ処理

#### 接続設定
- **基本接続**: ホスト、ユーザー、パスワード、データベース名
- **セキュリティ**: SSL/TLS暗号化接続オプション
- **パフォーマンス**: 接続プールとキャッシュ設定
- **監視**: 接続状態とパフォーマンス監視機能

### create_mimizam_elasticsearch()

Elasticsearchバックエンドを使用したMimizamインスタンスを作成する分散検索向けファクトリ関数です。

#### 機能概要
- **分散検索**: 高速な全文検索と音声指紋検索
- **スケーラビリティ**: 水平スケーリングによる大容量対応
- **リアルタイム**: 近リアルタイムでの検索とインデックス更新
- **分析機能**: 高度な検索分析と統計機能

#### クラスター設定
- **ノード管理**: 単一ノードから複数ノードクラスターまで対応
- **インデックス設定**: カスタムインデックス名とマッピング設定
- **セキュリティ**: 認証、SSL/TLS、ロールベースアクセス制御
- **監視**: クラスター状態とパフォーマンス監視

## 便利メソッド

### バッチ処理

大量の音声ファイルを効率的に処理するためのバッチ処理機能を提供します。

#### バッチ処理機能
- **一括追加**: 複数音声ファイルの自動処理
- **進捗監視**: リアルタイムでの処理状況表示
- **エラー処理**: 個別ファイルエラーの適切な処理と継続
- **結果レポート**: 詳細な処理結果と統計情報

#### 処理最適化
- **並列処理**: マルチスレッドによる高速化
- **メモリ管理**: 大量ファイル処理時のメモリ効率化
- **エラー回復**: 一時的なエラーからの自動回復
- **進捗保存**: 中断時の処理状態保存と再開機能

### 統計情報

システムの利用状況とパフォーマンスを監視するための包括的な統計情報機能を提供します。

#### 統計項目
- **楽曲統計**: 総楽曲数、アーティスト数、アルバム数
- **指紋統計**: 総指紋数、楽曲あたり平均指紋数、指紋密度
- **データベース統計**: データベースサイズ、インデックスサイズ、使用容量
- **パフォーマンス統計**: 検索速度、追加速度、システム負荷

#### 監視機能
- **リアルタイム監視**: システム状態の継続的な監視
- **トレンド分析**: 時系列での利用傾向分析
- **アラート機能**: 異常値検出と通知機能
- **レポート生成**: 定期的な統計レポートの自動生成

## 実装パターン

### 基本的な実装パターン

標準的なmimizam使用パターンでは、以下のワークフローを推奨します：

#### 初期化フェーズ
- **インスタンス作成**: 適切なバックエンドの選択と設定
- **データベース設定**: スキーマ初期化と最適化設定
- **パラメータ調整**: 用途に応じた音声処理パラメータの設定

#### 楽曲管理フェーズ
- **楽曲追加**: メタデータ付きでの楽曲登録
- **品質確認**: 追加された楽曲の指紋品質検証
- **統計確認**: データベース状態の定期的な確認

#### 識別フェーズ
- **音声識別**: クエリ音声からの楽曲特定
- **結果評価**: 識別結果の信頼度と精度評価
- **結果活用**: 識別結果の適切な処理と活用

### 高度な実装パターン

エンタープライズ環境や大規模システムでの実装パターン：

#### スケーラブル設計
- **データベース選択**: PostgreSQLやElasticsearchによる高性能化
- **バッチ処理**: 大量楽曲の効率的な一括処理
- **並列処理**: マルチスレッドによる処理速度向上

#### 監視と最適化
- **統計監視**: システム利用状況の継続的な監視
- **パフォーマンス分析**: 処理速度と精度の定期的な評価
- **最適化調整**: 運用データに基づくパラメータ調整

### 可視化と分析

システムの動作を理解し最適化するための分析手法：

#### 音響分析
- **スペクトログラム可視化**: 音声特徴の視覚的確認
- **ピーク分析**: 検出された特徴点の分布確認
- **品質評価**: 指紋生成品質の定量的評価

#### システム分析
- **処理時間分析**: 各処理段階の時間測定
- **精度分析**: 識別精度の統計的評価
- **リソース分析**: CPU、メモリ使用量の監視

## まとめ

高レベルAPIにより、mimizamの強力な機能を簡単に利用できます。ファクトリ関数を使用することで、異なるデータベースバックエンド間での切り替えも容易に行えます。

### API設計の特徴
- **統合性**: 全機能への統一されたアクセスポイント
- **簡潔性**: 最小限のコードで最大の機能を提供
- **柔軟性**: 様々な用途と要求に対応する設定オプション
- **拡張性**: 将来の機能追加に対応する設計

### 技術的優位性
- **使いやすさ**: 直感的なメソッド名と一貫したインターフェース
- **信頼性**: 包括的なエラーハンドリングと例外処理
- **パフォーマンス**: 最適化されたデフォルト設定と調整可能性
- **互換性**: 複数のデータベースバックエンドへの統一アクセス

このAPIにより、開発者は音声指紋技術の複雑さを意識することなく、高精度な音声識別システムを構築できます。
