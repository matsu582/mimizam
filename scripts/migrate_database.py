#!/usr/bin/env python3
"""
データベーススキーマ移行ユーティリティ
全データベースバックエンド対応版
"""

import os
import sys
import json
from typing import List, Dict, Any, Optional
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from database_base import DatabaseConfig

try:
    import sqlite3
except ImportError:
    sqlite3 = None

try:
    import mysql.connector
    from mysql.connector import Error as MySQLError
except ImportError:
    mysql = None
    MySQLError = Exception

try:
    import psycopg2
    from psycopg2 import Error as PostgresError
except ImportError:
    psycopg2 = None
    PostgresError = Exception

try:
    from elasticsearch import Elasticsearch
    from elasticsearch.exceptions import ElasticsearchException
except ImportError:
    Elasticsearch = None
    ElasticsearchException = Exception


class DatabaseMigrator:
    """全バックエンド対応データベース移行ツール"""
    
    def __init__(self):
        self.supported_backends = {
            'sqlite': self._migrate_sqlite,
            'mysql': self._migrate_mysql,
            'postgresql': self._migrate_postgresql,
            'elasticsearch': self._migrate_elasticsearch
        }
    
    def check_sqlite_schema(self, db_path: str) -> Dict[str, Any]:
        """SQLiteデータベーススキーマを確認"""
        if not os.path.exists(db_path):
            return {"exists": False, "error": f"Database file not found: {db_path}"}
        
        if sqlite3 is None:
            return {"exists": True, "error": "sqlite3 module not available"}
        
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            cursor.execute("PRAGMA table_info(songs)")
            columns = cursor.fetchall()
            
            column_names = [col[1] for col in columns]
            has_meta_column = "meta" in column_names
            
            cursor.execute("SELECT COUNT(*) FROM songs")
            song_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM fingerprints")
            fingerprint_count = cursor.fetchone()[0]
            
            conn.close()
            
            return {
                "exists": True,
                "backend": "sqlite",
                "has_meta_column": has_meta_column,
                "columns": column_names,
                "song_count": song_count,
                "fingerprint_count": fingerprint_count,
                "schema_version": "new" if has_meta_column else "old"
            }
            
        except Exception as e:
            return {"exists": True, "error": f"Database access error: {e}"}
    
    def check_mysql_schema(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """MySQLデータベーススキーマを確認"""
        if mysql is None:
            return {"exists": True, "error": "mysql-connector-python module not available"}
        
        try:
            connection = mysql.connector.connect(**config)
            cursor = connection.cursor()
            
            cursor.execute("SHOW COLUMNS FROM songs")
            columns = cursor.fetchall()
            
            column_names = [col[0] for col in columns]
            has_meta_column = "meta" in column_names
            
            cursor.execute("SELECT COUNT(*) FROM songs")
            song_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM fingerprints")
            fingerprint_count = cursor.fetchone()[0]
            
            connection.close()
            
            return {
                "exists": True,
                "backend": "mysql",
                "has_meta_column": has_meta_column,
                "columns": column_names,
                "song_count": song_count,
                "fingerprint_count": fingerprint_count,
                "schema_version": "new" if has_meta_column else "old"
            }
            
        except MySQLError as e:
            return {"exists": True, "error": f"MySQL access error: {e}"}
    
    def check_postgresql_schema(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """PostgreSQLデータベーススキーマを確認"""
        if psycopg2 is None:
            return {"exists": True, "error": "psycopg2 module not available"}
        
        try:
            connection = psycopg2.connect(**config)
            cursor = connection.cursor()
            
            cursor.execute("""
                SELECT column_name FROM information_schema.columns 
                WHERE table_name = 'songs' AND table_schema = 'public'
            """)
            columns = cursor.fetchall()
            
            column_names = [col[0] for col in columns]
            has_meta_column = "meta" in column_names
            
            cursor.execute("SELECT COUNT(*) FROM songs")
            song_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM fingerprints")
            fingerprint_count = cursor.fetchone()[0]
            
            connection.close()
            
            return {
                "exists": True,
                "backend": "postgresql",
                "has_meta_column": has_meta_column,
                "columns": column_names,
                "song_count": song_count,
                "fingerprint_count": fingerprint_count,
                "schema_version": "new" if has_meta_column else "old"
            }
            
        except PostgresError as e:
            return {"exists": True, "error": f"PostgreSQL access error: {e}"}
    
    def check_elasticsearch_schema(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Elasticsearchインデックススキーマを確認"""
        if Elasticsearch is None:
            return {"exists": True, "error": "elasticsearch module not available"}
        
        try:
            es = Elasticsearch([config])
            
            if not es.indices.exists(index="songs"):
                return {"exists": False, "error": "songs index not found"}
            
            mapping = es.indices.get_mapping(index="songs")
            properties = mapping["songs"]["mappings"]["properties"]
            
            has_meta_column = "meta" in properties
            column_names = list(properties.keys())
            
            song_count = es.count(index="songs")["count"]
            fingerprint_count = es.count(index="fingerprints")["count"]
            
            return {
                "exists": True,
                "backend": "elasticsearch",
                "has_meta_column": has_meta_column,
                "columns": column_names,
                "song_count": song_count,
                "fingerprint_count": fingerprint_count,
                "schema_version": "new" if has_meta_column else "old"
            }
            
        except ElasticsearchException as e:
            return {"exists": True, "error": f"Elasticsearch access error: {e}"}
    
    def _migrate_sqlite(self, db_path: str, backup: bool = True) -> Dict[str, Any]:
        """SQLiteデータベーススキーマを移行してmetaカラムを追加"""
        
        if backup:
            backup_path = f"{db_path}.backup"
            if os.path.exists(backup_path):
                os.remove(backup_path)
            
            import shutil
            shutil.copy2(db_path, backup_path)
            print(f"バックアップ作成: {backup_path}")
        
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            cursor.execute("ALTER TABLE songs ADD COLUMN meta TEXT")
            
            conn.commit()
            conn.close()
            
            return {"success": True, "message": "Schema migration completed successfully"}
            
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                return {"success": True, "message": "Meta column already exists"}
            else:
                return {"success": False, "error": f"Migration failed: {e}"}
        except Exception as e:
            return {"success": False, "error": f"Unexpected error: {e}"}
    
    def _migrate_mysql(self, config: Dict[str, Any], backup: bool = True) -> Dict[str, Any]:
        """MySQLデータベーススキーマを移行してmetaカラムを追加"""
        try:
            connection = mysql.connector.connect(**config)
            cursor = connection.cursor()
            
            cursor.execute("ALTER TABLE songs ADD COLUMN meta TEXT")
            connection.commit()
            connection.close()
            
            return {"success": True, "message": "MySQL schema migration completed successfully"}
            
        except MySQLError as e:
            if "duplicate column name" in str(e).lower():
                return {"success": True, "message": "Meta column already exists"}
            else:
                return {"success": False, "error": f"MySQL migration failed: {e}"}
        except Exception as e:
            return {"success": False, "error": f"Unexpected error: {e}"}
    
    def _migrate_postgresql(self, config: Dict[str, Any], backup: bool = True) -> Dict[str, Any]:
        """PostgreSQLデータベーススキーマを移行してmetaカラムを追加"""
        try:
            connection = psycopg2.connect(**config)
            cursor = connection.cursor()
            
            cursor.execute("ALTER TABLE songs ADD COLUMN meta TEXT")
            connection.commit()
            connection.close()
            
            return {"success": True, "message": "PostgreSQL schema migration completed successfully"}
            
        except PostgresError as e:
            if "already exists" in str(e).lower():
                return {"success": True, "message": "Meta column already exists"}
            else:
                return {"success": False, "error": f"PostgreSQL migration failed: {e}"}
        except Exception as e:
            return {"success": False, "error": f"Unexpected error: {e}"}
    
    def _migrate_elasticsearch(self, config: Dict[str, Any], backup: bool = True) -> Dict[str, Any]:
        """Elasticsearchインデックススキーマを移行してmetaフィールドを追加"""
        try:
            es = Elasticsearch([config])
            
            mapping_update = {
                "properties": {
                    "meta": {
                        "type": "text"
                    }
                }
            }
            
            es.indices.put_mapping(index="songs", body=mapping_update)
            
            return {"success": True, "message": "Elasticsearch schema migration completed successfully"}
            
        except ElasticsearchException as e:
            return {"success": False, "error": f"Elasticsearch migration failed: {e}"}
        except Exception as e:
            return {"success": False, "error": f"Unexpected error: {e}"}


def analyze_databases() -> None:
    """既存のデータベースファイルを分析"""
    print("=== データベーススキーマ分析レポート ===")
    print("'meta'カラムデータベーススキーマエラーの調査\n")
    
    migrator = DatabaseMigrator()
    
    db_files = []
    for file in os.listdir("."):
        if file.endswith(".db"):
            db_files.append(file)
    
    if not db_files:
        print("SQLiteデータベースファイルが見つかりません。")
        return
    
    print(f"発見されたSQLiteデータベースファイル: {len(db_files)}個")
    
    migration_needed = []
    
    for db_file in db_files:
        print(f"\n--- {db_file} ---")
        schema_info = migrator.check_sqlite_schema(db_file)
        
        if "error" in schema_info:
            print(f"❌ エラー: {schema_info['error']}")
            continue
        
        print(f"スキーマバージョン: {schema_info['schema_version']}")
        print(f"metaカラム存在: {'✅ あり' if schema_info['has_meta_column'] else '❌ なし'}")
        print(f"楽曲数: {schema_info['song_count']}")
        print(f"フィンガープリント数: {schema_info['fingerprint_count']}")
        print(f"カラム一覧: {', '.join(schema_info['columns'])}")
        
        if not schema_info['has_meta_column']:
            migration_needed.append(db_file)
    
    if migration_needed:
        print(f"\n=== 移行が必要なデータベース: {len(migration_needed)}個 ===")
        for db_file in migration_needed:
            print(f"- {db_file}")
        
        print("\n=== 問題の詳細 ===")
        print("1. 既存のデータベースファイルには'meta'カラムが存在しない")
        print("2. 新しいスキーマ定義では'meta TEXT'カラムが含まれている")
        print("3. examples/mimizam_demo.pyでSongオブジェクトにmetaフィールドを使用している")
        print("4. データベースとコードのスキーマ不整合によりエラーが発生")
        
        print("\n=== 解決方法 ===")
        print("A. 自動移行: python scripts/migrate_database.py --migrate を実行")
        print("B. 手動移行: ALTER TABLE songs ADD COLUMN meta TEXT; を実行")
        print("C. データベース再作成: 既存のデータベースファイルを削除して新規作成")
        
    else:
        print("\n✅ 全てのデータベースが最新のスキーマを使用しています。")


def migrate_all_databases() -> None:
    """全ての古いデータベースを移行"""
    print("=== データベーススキーマ移行実行 ===\n")
    
    migrator = DatabaseMigrator()
    
    db_files = [f for f in os.listdir(".") if f.endswith(".db")]
    
    if not db_files:
        print("SQLiteデータベースファイルが見つかりません。")
        return
    
    migrated_count = 0
    
    for db_file in db_files:
        schema_info = migrator.check_sqlite_schema(db_file)
        
        if "error" in schema_info:
            print(f"❌ {db_file}: スキップ - {schema_info['error']}")
            continue
        
        if schema_info['has_meta_column']:
            print(f"✅ {db_file}: 既に最新スキーマ")
            continue
        
        print(f"🔄 {db_file}: 移行中...")
        result = migrator._migrate_sqlite(db_file)
        
        if result['success']:
            print(f"✅ {db_file}: 移行完了 - {result['message']}")
            migrated_count += 1
        else:
            print(f"❌ {db_file}: 移行失敗 - {result['error']}")
    
    print(f"\n移行完了: {migrated_count}個のデータベース")


def main():
    if len(sys.argv) > 1:
        if sys.argv[1] == "--migrate":
            migrate_all_databases()
        elif sys.argv[1] == "--analyze":
            analyze_databases()
        elif sys.argv[1] == "--help":
            print("データベーススキーマ移行ユーティリティ")
            print("全データベースバックエンド対応版")
            print("\n使用方法:")
            print("  python scripts/migrate_database.py --analyze   # データベース分析")
            print("  python scripts/migrate_database.py --migrate   # スキーマ移行実行")
            print("  python scripts/migrate_database.py --help      # ヘルプ表示")
            print("\n対応バックエンド:")
            print("  - SQLite (ファイルベース)")
            print("  - MySQL (設定ファイル経由)")
            print("  - PostgreSQL (設定ファイル経由)")
            print("  - Elasticsearch (設定ファイル経由)")
        else:
            print("使用方法:")
            print("  python scripts/migrate_database.py --analyze   # データベース分析")
            print("  python scripts/migrate_database.py --migrate   # スキーマ移行実行")
            print("  python scripts/migrate_database.py --help      # ヘルプ表示")
    else:
        analyze_databases()


if __name__ == "__main__":
    main()
