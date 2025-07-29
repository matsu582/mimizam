"""
音声指紋用のデータベースバックエンド

複数のデータベースシステム（SQLite、MySQL、PostgreSQL、Elasticsearch）をサポートするための統一インターフェースを提供。
"""

import logging

# 共通データ構造とインターフェースのインポート
from .database_base import DatabaseBackend, DatabaseConfig, Song
from .exceptions import ConfigurationError

# 各データベースバックエンドの実装をインポート
try:
    from .backends.sqlite_backend import SQLiteBackend
except ImportError:
    SQLiteBackend = None

try:
    from .backends.mysql_backend import MySQLBackend
except ImportError:
    MySQLBackend = None

try:
    from .backends.postgresql_backend import PostgreSQLBackend
except ImportError:
    PostgreSQLBackend = None

try:
    from .backends.elasticsearch_backend import ElasticsearchBackend
except ImportError:
    ElasticsearchBackend = None


def create_database_backend(config: DatabaseConfig) -> DatabaseBackend:
    """設定に基づいてデータベースバックエンドを作成"""
    logger = logging.getLogger(__name__)
    
    backend_map = {
        'sqlite': SQLiteBackend,
        'mysql': MySQLBackend,
        'postgres': PostgreSQLBackend,
        'postgresql': PostgreSQLBackend,
        'elasticsearch': ElasticsearchBackend,
        'es': ElasticsearchBackend
    }
    
    backend_type = config.backend.lower()
    backend_class = backend_map.get(backend_type)
    
    # バックエンドタイプの妥当性チェック
    if backend_type not in backend_map:
        supported_backends = [k for k, v in backend_map.items() if v is not None]
        error_msg = f"Unsupported backend: {config.backend}. Supported backends: {supported_backends}"
        logger.error(error_msg)
        raise ConfigurationError(error_msg)
    
    # バックエンドクラスの利用可能性チェック
    if backend_class is None:
        error_msg = f"{config.backend} backend implementation is not available. Please check that required libraries are installed."
        logger.error(error_msg)
        raise ConfigurationError(error_msg)
    
    logger.info(f"Creating {config.backend} backend...")
    return backend_class(config)


# 後方互換性のための再エクスポート
__all__ = [
    'DatabaseBackend',
    'DatabaseConfig', 
    'Song',
    'SQLiteBackend',
    'MySQLBackend',
    'PostgreSQLBackend',
    'ElasticsearchBackend',
    'create_database_backend'
]
