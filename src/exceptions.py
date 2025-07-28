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


def log_and_raise(logger: logging.Logger, exception_class: type, 
                  message: str, original_error: Optional[Exception] = None,
                  context: Optional[dict] = None, level: str = "error") -> NoReturn:
    """
    統一されたエラーログ出力と例外発生
    
    Args:
        logger: ログ出力用のロガー
        exception_class: 発生させる例外クラス
        message: エラーメッセージ
        original_error: 元の例外（ある場合）
        context: 追加のコンテキスト情報
        level: ログレベル（error, warning, info）
    """
    full_context = context or {}
    if original_error:
        full_context['original_error'] = str(original_error)
        full_context['original_type'] = type(original_error).__name__
    
    log_message = f"{message}"
    if full_context:
        log_message += f" | Context: {full_context}"
    
    getattr(logger, level)(log_message)
    raise exception_class(message, original_error, context)
