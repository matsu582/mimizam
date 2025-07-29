"""
mimizam統一例外クラス

全てのmimizamモジュールで使用する統一された例外階層を提供
"""

import logging
from typing import Optional, Any, NoReturn


class MimizamError(Exception):
    """mimizamシステムの基底例外クラス"""
    
    def __init__(self, message: str, original_error: Optional[Exception] = None, 
                 context: Optional[dict] = None):
        super().__init__(message)
        self.message = message
        self.original_error = original_error
        self.context = context or {}
    
    def __str__(self) -> str:
        if self.original_error:
            return f"{self.message} (原因: {self.original_error})"
        return self.message


class DatabaseError(MimizamError):
    """データベース関連エラー"""
    pass


class ConnectionError(DatabaseError):
    """データベース接続エラー"""
    pass


class QueryError(DatabaseError):
    """データベースクエリエラー"""
    pass


class AudioProcessingError(MimizamError):
    """音声処理関連エラー"""
    pass


class FingerprintGenerationError(AudioProcessingError):
    """フィンガープリント生成エラー"""
    pass


class ConfigurationError(MimizamError):
    """設定関連エラー"""
    pass


class ValidationError(MimizamError):
    """データ検証エラー"""
    pass
