# データベース層

> 関連するソースファイル

このドキュメントでは、mimizamの統一データベース抽象化層について説明します。この層は、SQLite、MySQL、PostgreSQL、Elasticsearchなど複数のデータベースバックエンドに対する共通インターフェースを提供し、アプリケーションレベルでの透明な切り替えを可能にします。

他のコンポーネントについては、[音声指紋エンジン](./03_1_audio_fingerprinting_engine.md)および[マッチング・識別システム](./03_3_matching_identification.md)を参照してください。

## 概要

データベース層は、異なるデータベースシステム間での透明な切り替えを可能にする抽象化レイヤーです。この設計により、アプリケーションコードを変更することなく、開発環境ではSQLite、本番環境ではMySQLやPostgreSQLを使用できます。

### データベース抽象化の利点

| 利点 | 説明 | 実装効果 |
|------|------|---------|
| **透明性** | アプリケーションコードの変更なしでバックエンド切り替え | 開発効率向上 |
| **拡張性** | 新しいデータベースバックエンドの容易な追加 | システム柔軟性 |
| **一貫性** | 統一されたインターフェースによる操作の標準化 | コード品質向上 |
| **移植性** | 異なる環境間でのスムーズな移行 | デプロイメント簡素化 |

## アーキテクチャ統合

mimizamのデータベース層は、複数のデータベースシステムに対する統一されたインターフェースを提供する3層アーキテクチャを採用しています。

### アーキテクチャ概要

```
┌─────────────────────────────────────────────────────────────┐
│                    統合API層                               │
├─────────────────────────────────────────────────────────────┤
│           FingerprintDatabase（統合インターフェース）        │
│  • 楽曲管理 • 指紋保存 • 検索機能 • 統計情報              │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                  データベース抽象化層                       │
├─────────────────────────────────────────────────────────────┤
│              DatabaseBackend（抽象基底クラス）              │
│  • 接続管理 • スキーマ管理 • CRUD操作 • エラーハンドリング │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                 具体的なバックエンド実装                    │
├─────────────────────────────────────────────────────────────┤
│  SQLiteBackend │ MySQLBackend │ PostgreSQLBackend │ ESBackend │
│  • ファイルDB   • 本番環境     • 高機能DB        • 分散検索  │
└─────────────────────────────────────────────────────────────┘
```

### データフロー

| 段階 | 処理内容 | 責任範囲 |
|------|---------|---------|
| **アプリケーション層** | 高レベルAPI呼び出し | ビジネスロジック |
| **統合API層** | リクエスト処理と結果統合 | データ変換、エラーハンドリング |
| **抽象化層** | バックエンド固有の実装呼び出し | インターフェース標準化 |
| **バックエンド層** | データベース固有の操作実行 | 実際のデータ操作 |

## 主要コンポーネント

### DatabaseBackend抽象基底クラス

全てのデータベースバックエンドが実装する共通インターフェースを定義します。この抽象基底クラスは、異なるデータベースシステム間での一貫した操作を保証します。

#### 主要な抽象メソッド
- **接続管理**: データベースへの接続と切断の処理
- **スキーマ管理**: 必要なテーブル構造の作成と維持
- **楽曲操作**: 楽曲情報の挿入、取得、削除機能
- **指紋操作**: 音声指紋の保存と検索機能
- **統計情報**: データベース内の楽曲数などの統計取得

この設計により、各バックエンド実装は統一されたインターフェースを通じて、それぞれの特性を活かした最適化を行うことができます。

### FingerprintDatabaseクラス

データベースバックエンドを統合する高レベルインターフェースとして機能します。このクラスは、アプリケーション層とデータベース層の間の橋渡し役を担います。

#### 主要な機能領域

**楽曲管理機能**
- 楽曲メタデータと音声指紋の統合保存
- 楽曲情報の取得と更新
- 楽曲の削除とクリーンアップ

**検索・マッチング機能**
- 指紋ベースの高速検索
- マッチング結果の統合処理
- 検索結果の品質評価

**統計・監視機能**
- データベース使用状況の監視
- パフォーマンス統計の収集
- システム健全性の評価

**エラーハンドリング**
- 包括的な例外処理機構
- 詳細なエラーログ記録
- 自動復旧機能の提供

## データモデル設計

### 楽曲情報の管理

楽曲テーブルは、音声ファイルのメタデータを効率的に管理するよう設計されています。主要な属性には、楽曲識別子、タイトル、アーティスト情報、アルバム情報、再生時間、ファイルパスが含まれます。

### 指紋データの構造

指紋テーブルは、音声指紋の高速検索を可能にする最適化された構造を持ちます。各指紋レコードは、ハッシュ値、時間オフセット、周波数情報を含み、効率的なインデックス戦略により高速な検索を実現します。

#### インデックス戦略
- **ハッシュインデックス**: 指紋検索の高速化
- **楽曲IDインデックス**: 楽曲別指紋の効率的な取得
- **複合インデックス**: 複雑なクエリの最適化

## 具体的なバックエンド実装

### SQLiteBackend

軽量なファイルベースデータベースバックエンドです。

```python
import sqlite3
import os

class SQLiteBackend(DatabaseBackend):
    """SQLiteデータベースバックエンド"""
    
    def __init__(self, db_path):
        self.db_path = db_path
        self.connection = None
    
    def connect(self):
        """SQLiteデータベースに接続"""
        try:
            self.connection = sqlite3.connect(self.db_path)
            self.connection.row_factory = sqlite3.Row
            return True
        except sqlite3.Error as e:
            raise DatabaseError(f"SQLite接続エラー: {e}")
    
    def disconnect(self):
        """接続を切断"""
        if self.connection:
            self.connection.close()
            self.connection = None
    
    def create_tables(self):
        """テーブルを作成"""
        cursor = self.connection.cursor()
        
        # songsテーブル
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS songs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                artist TEXT,
                album TEXT,
                duration REAL,
                file_path TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # fingerprintsテーブル
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS fingerprints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                song_id INTEGER NOT NULL,
                hash INTEGER NOT NULL,
                time_offset REAL NOT NULL,
                anchor_freq INTEGER,
                target_freq INTEGER,
                time_delta INTEGER,
                FOREIGN KEY (song_id) REFERENCES songs(id) ON DELETE CASCADE
            )
        ''')
        
        # インデックス作成
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_fingerprints_hash ON fingerprints(hash)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_fingerprints_song_id ON fingerprints(song_id)')
        
        self.connection.commit()
    
    def insert_song(self, song_name, **metadata):
        """楽曲を挿入"""
        cursor = self.connection.cursor()
        
        cursor.execute('''
            INSERT INTO songs (name, artist, album, duration, file_path)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            song_name,
            metadata.get('artist'),
            metadata.get('album'),
            metadata.get('duration'),
            metadata.get('file_path')
        ))
        
        self.connection.commit()
        return cursor.lastrowid
    
    def insert_fingerprints(self, song_id, fingerprints):
        """指紋を挿入"""
        cursor = self.connection.cursor()
        
        fingerprint_data = [
            (song_id, fp['hash'], fp['time_offset'], 
             fp.get('anchor_freq'), fp.get('target_freq'), fp.get('time_delta'))
            for fp in fingerprints
        ]
        
        cursor.executemany('''
            INSERT INTO fingerprints (song_id, hash, time_offset, anchor_freq, target_freq, time_delta)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', fingerprint_data)
        
        self.connection.commit()
    
    def search_fingerprints(self, fingerprints):
        """指紋を検索"""
        cursor = self.connection.cursor()
        
        # ハッシュ値のリストを作成
        hash_values = [fp['hash'] for fp in fingerprints]
        placeholders = ','.join(['?'] * len(hash_values))
        
        cursor.execute(f'''
            SELECT song_id, hash, time_offset
            FROM fingerprints
            WHERE hash IN ({placeholders})
        ''', hash_values)
        
        results = cursor.fetchall()
        
        # 結果をグループ化
        matches = {}
        for row in results:
            song_id = row['song_id']
            if song_id not in matches:
                matches[song_id] = []
            
            matches[song_id].append({
                'hash': row['hash'],
                'db_time': row['time_offset']
            })
        
        return matches
```

### MySQLBackend

本番環境向けの高性能データベースバックエンドとして最適化されています。

#### 主要特徴
- **高性能**: InnoDBエンジンによる高速なトランザクション処理
- **スケーラビリティ**: 大規模データセットへの対応
- **信頼性**: ACID特性による堅牢なデータ整合性
- **同時実行性**: 複数クライアントからの同時アクセス対応

#### 最適化戦略
- **インデックス最適化**: 検索パフォーマンスの向上
- **接続プール**: 効率的なリソース管理
- **クエリ最適化**: 実行計画の最適化
- **文字セット対応**: 国際化対応のUTF-8サポート

### PostgreSQLBackend

高機能なオープンソースデータベースバックエンドとして、エンタープライズレベルの機能を提供します。

#### 主要特徴
- **高度な機能**: 複雑なクエリと分析機能
- **拡張性**: カスタム関数とデータ型のサポート
- **並行制御**: MVCC（Multi-Version Concurrency Control）
- **標準準拠**: SQL標準への高い準拠性

#### 技術的優位性
- **JSON対応**: 半構造化データの効率的な処理
- **全文検索**: 高度なテキスト検索機能
- **パーティショニング**: 大規模データの効率的な管理
- **レプリケーション**: 高可用性とスケーラビリティ

### ElasticsearchBackend

分散検索エンジンバックエンドとして、大規模な音声指紋データベースに対応します。

#### 主要特徴
- **分散アーキテクチャ**: 水平スケーリングによる高性能
- **リアルタイム検索**: 近リアルタイムでの検索結果提供
- **柔軟なスキーマ**: 動的マッピングによる柔軟なデータ構造
- **高可用性**: クラスター構成による障害耐性

#### 検索最適化
- **インデックス戦略**: 効率的なデータ分散とレプリケーション
- **クエリ最適化**: 複雑な検索条件の高速処理
- **アグリゲーション**: 統計情報の高速集計
- **キャッシュ機能**: 頻繁なクエリの高速化

## システム統合

### ファクトリパターン

各データベースバックエンドの作成と初期化を統一的に管理するファクトリパターンを採用しています。この設計により、アプリケーション層は具体的なバックエンド実装の詳細を意識することなく、設定ベースでのバックエンド選択が可能になります。

#### 設定駆動型アーキテクチャ
- **統一設定**: 全バックエンドに対する一貫した設定インターフェース
- **動的選択**: 実行時でのバックエンド切り替え機能
- **環境適応**: 開発・テスト・本番環境での自動適応
- **拡張性**: 新しいバックエンドの容易な追加

## 堅牢性とエラー処理

### 階層化エラー管理

システムは、データベース操作における様々なエラー状況に対応する階層化されたエラー処理機構を提供します。

#### エラー分類
- **接続エラー**: ネットワークやサーバー接続の問題
- **スキーマエラー**: データベース構造の不整合
- **クエリエラー**: SQL実行時の問題
- **データ整合性エラー**: 制約違反や不正なデータ

### 自動復旧機能
- **再接続機構**: 一時的な接続断に対する自動復旧
- **トランザクション管理**: 失敗時の自動ロールバック
- **リトライ戦略**: 指数バックオフによる再試行
- **フェイルオーバー**: 冗長化されたシステムでの自動切り替え

## パフォーマンス最適化戦略

### 接続管理の最適化

効率的なデータベース接続管理により、システム全体のパフォーマンスを向上させます。

#### 接続プール機能
- **リソース効率**: 接続の再利用による効率化
- **同時実行性**: 複数クライアントの並行処理対応
- **負荷分散**: 接続負荷の適切な分散
- **監視機能**: 接続状態の実時間監視

### バッチ処理最適化

大量データの効率的な処理のため、バッチ処理機能を提供します。

#### 処理戦略
- **チャンク分割**: 大量データの適切なサイズ分割
- **並列処理**: 複数バッチの同時実行
- **メモリ管理**: 効率的なメモリ使用量制御
- **進捗監視**: バッチ処理の進捗状況追跡

## まとめ

データベース層は、mimizamシステムの柔軟性と拡張性を支える重要なコンポーネントです。統一されたインターフェースにより、異なるデータベースシステム間での透明な切り替えが可能になります。

### 主要な利点
- **抽象化**: データベース固有の詳細からアプリケーション層を分離
- **移植性**: 異なる環境間での容易な移行
- **スケーラビリティ**: 成長に応じたバックエンドの段階的アップグレード
- **保守性**: 統一されたインターフェースによる保守作業の簡素化

この設計により、mimizamは小規模な開発環境から大規模な本番システムまで、様々な要求に対応できる柔軟なデータベースアーキテクチャを提供します。
