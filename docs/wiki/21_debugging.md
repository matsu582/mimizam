# デバッグとトラブルシューティング

mimizamシステムで発生する可能性のある問題の診断と解決方法を詳しく解説します。音声処理エラー、データベース接続問題、パフォーマンス低下、メモリリークなど、様々なトラブルに対する体系的なアプローチを提供します。

## 🔍 デバッグの概要

### 主要なトラブル分類

```
トラブルシューティング
├── 音声処理問題
│   ├── ファイル読み込みエラー
│   ├── 指紋生成失敗
│   └── 音声形式非対応
├── データベース問題
│   ├── 接続エラー
│   ├── クエリ失敗
│   └── スキーマ不整合
├── パフォーマンス問題
│   ├── 処理速度低下
│   ├── メモリリーク
│   └── CPU使用率高騰
└── システム問題
    ├── 依存関係エラー
    ├── 設定問題
    └── 環境固有問題
```

## 🛠️ DiagnosticTool クラス

### 基本的な診断機能

```python
import logging
import traceback
import psutil
import os
import sys
from typing import Dict, List, Any, Optional
import time

def setup_debug_logging(log_level=logging.INFO):
    """デバッグログ設定"""
    import logging
    import sys
    
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('mimizam_debug.log'),
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    return logging.getLogger(__name__)

def run_system_diagnostic() -> dict:
    """システム診断実行"""
    import time
    
    logger = setup_debug_logging()
    logger.info("=== mimizam システム診断開始 ===")
    
    results = {
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'system_info': check_system_environment(),
        'dependencies': check_dependencies(),
        'audio_processing': test_audio_processing(),
        'database_connectivity': test_database_connectivity(),
        'performance_baseline': measure_performance_baseline(),
        'recommendations': []
    }
    
    # 問題の特定と推奨事項生成
    results['recommendations'] = generate_recommendations(results)
    
    logger.info("=== システム診断完了 ===")
    return results

def check_system_environment() -> dict:
    """システム環境チェック"""
    import platform
    import sys
    
    return {
        'python_version': sys.version,
        'platform': platform.platform(),
        'architecture': platform.architecture()[0]
    }

def check_dependencies() -> dict:
    """依存関係チェック"""
    dependencies = {}
    
    try:
        import numpy
        dependencies['numpy'] = numpy.__version__
    except ImportError:
        dependencies['numpy'] = 'NOT_INSTALLED'
    
    try:
        import librosa
        dependencies['librosa'] = librosa.__version__
    except ImportError:
        dependencies['librosa'] = 'NOT_INSTALLED'
    
    try:
        import numba
        dependencies['numba'] = numba.__version__
    except ImportError:
        dependencies['numba'] = 'NOT_INSTALLED'
    
    return dependencies

def test_audio_processing() -> dict:
    """音声処理テスト"""
    try:
        from mimizam import AudioFingerprinter
        import numpy as np
        
        fingerprinter = AudioFingerprinter()
        test_audio = np.random.randn(22050)  # 1秒のテスト音声
        
        fingerprints = fingerprinter.fingerprint_audio(test_audio)
        
        return {
            'status': 'SUCCESS',
            'fingerprint_count': len(fingerprints),
            'error': None
        }
    except Exception as e:
        return {
            'status': 'FAILED',
            'fingerprint_count': 0,
            'error': str(e)
        }

def test_database_connectivity() -> dict:
    """データベース接続テスト"""
    try:
        from mimizam import create_mimizam_sqlite
        
        mimizam = create_mimizam_sqlite(':memory:')
        mimizam.close()
        
        return {
            'status': 'SUCCESS',
            'error': None
        }
    except Exception as e:
        return {
            'status': 'FAILED',
            'error': str(e)
        }

def measure_performance_baseline() -> dict:
    """パフォーマンスベースライン測定"""
    try:
        from mimizam import PerformanceMonitor
        import time
        
        monitor = PerformanceMonitor()
        
        start_time = time.time()
        # 簡単な処理時間測定
        time.sleep(0.1)
        elapsed = time.time() - start_time
        
        metrics = monitor.get_metrics()
        
        return {
            'status': 'SUCCESS',
            'elapsed_time': elapsed,
            'metrics': metrics
        }
    except Exception as e:
        return {
            'status': 'FAILED',
            'error': str(e)
        }

def generate_recommendations(results: dict) -> list:
    """推奨事項生成"""
    recommendations = []
    
    # 依存関係チェック
    deps = results.get('dependencies', {})
    for dep, version in deps.items():
        if version == 'NOT_INSTALLED':
            recommendations.append(f"{dep}がインストールされていません")
    
    # 音声処理チェック
    audio_test = results.get('audio_processing', {})
    if audio_test.get('status') == 'FAILED':
        recommendations.append(f"音声処理エラー: {audio_test.get('error')}")
    
    # データベース接続チェック
    db_test = results.get('database_connectivity', {})
    if db_test.get('status') == 'FAILED':
        recommendations.append(f"データベース接続エラー: {db_test.get('error')}")
    
    if not recommendations:
        recommendations.append("システムは正常に動作しています")
    
    return recommendations
        self.logger.info("=== システム診断完了 ===")
        
        return results
    
    def _check_system_environment(self) -> Dict[str, Any]:
        """システム環境チェック"""
        
        self.logger.info("システム環境をチェック中...")
        
        try:
            import platform
            
            env_info = {
                'python_version': platform.python_version(),
                'platform': platform.platform(),
                'architecture': platform.architecture(),
                'processor': platform.processor(),
                'cpu_count': os.cpu_count(),
                'memory_total_gb': psutil.virtual_memory().total / (1024**3),
                'disk_free_gb': psutil.disk_usage('/').free / (1024**3),
                'status': 'OK'
            }
            
            # 最小要件チェック
            warnings = []
            if env_info['memory_total_gb'] < 2:
                warnings.append("メモリ不足: 2GB以上を推奨")
            
            if env_info['disk_free_gb'] < 1:
                warnings.append("ディスク容量不足: 1GB以上の空き容量を推奨")
            
            if warnings:
                env_info['warnings'] = warnings
                env_info['status'] = 'WARNING'
            
            return env_info
            
        except Exception as e:
            self.logger.error(f"システム環境チェックエラー: {e}")
            return {
                'status': 'ERROR',
                'error': str(e),
                'traceback': traceback.format_exc()
            }
    
    def _check_dependencies(self) -> Dict[str, Any]:
        """依存関係チェック"""
        
        self.logger.info("依存関係をチェック中...")
        
        required_packages = {
            'numpy': '1.21.0',
            'librosa': '0.9.0',
            'numba': '0.56.0',
            'scipy': '1.7.0'
        }
        
        dependency_info = {
            'status': 'OK',
            'required': {},
            'missing': []
        }
        
        try:
            # 必須パッケージチェック
            for package, min_version in required_packages.items():
                try:
                    module = __import__(package)
                    version = getattr(module, '__version__', 'unknown')
                    dependency_info['required'][package] = {
                        'installed': True,
                        'version': version,
                        'required_version': min_version
                    }
                except ImportError:
                    dependency_info['missing'].append(package)
                    dependency_info['required'][package] = {
                        'installed': False,
                        'required_version': min_version
                    }
            
            # ステータス判定
            if dependency_info['missing']:
                dependency_info['status'] = 'ERROR'
            
            return dependency_info
            
        except Exception as e:
            self.logger.error(f"依存関係チェックエラー: {e}")
            return {
                'status': 'ERROR',
                'error': str(e),
                'traceback': traceback.format_exc()
            }
    
    def _test_audio_processing(self) -> Dict[str, Any]:
        """音声処理テスト"""
        
        self.logger.info("音声処理機能をテスト中...")
        
        test_result = {
            'status': 'OK',
            'tests': {},
            'errors': []
        }
        
        try:
            # 1. AudioFingerprintクラスのインポートテスト
            try:
                from mimizam import AudioFingerprinter
                test_result['tests']['import_audio_fingerprinter'] = True
            except ImportError as e:
                test_result['tests']['import_audio_fingerprinter'] = False
                test_result['errors'].append(f"AudioFingerprinter インポートエラー: {e}")
            
            # 2. テスト音声データ生成
            try:
                import numpy as np
                test_audio = np.random.randn(22050)  # 1秒のテスト音声
                test_result['tests']['generate_test_audio'] = True
            except Exception as e:
                test_result['tests']['generate_test_audio'] = False
                test_result['errors'].append(f"テスト音声生成エラー: {e}")
                return test_result
            
            # 3. 指紋生成テスト
            try:
                fingerprinter = AudioFingerprinter()
                fingerprints = fingerprinter.fingerprint_audio(test_audio)
                test_result['tests']['fingerprint_generation'] = len(fingerprints) > 0
                test_result['fingerprint_count'] = len(fingerprints)
            except Exception as e:
                test_result['tests']['fingerprint_generation'] = False
                test_result['errors'].append(f"指紋生成エラー: {e}")
            
            # ステータス判定
            failed_tests = [k for k, v in test_result['tests'].items() if not v]
            if failed_tests:
                test_result['status'] = 'ERROR' if len(failed_tests) > 2 else 'WARNING'
            
            return test_result
            
        except Exception as e:
            self.logger.error(f"音声処理テストエラー: {e}")
            return {
                'status': 'ERROR',
                'error': str(e),
                'traceback': traceback.format_exc()
            }
    
    def _test_database_connectivity(self) -> Dict[str, Any]:
        """データベース接続テスト"""
        
        self.logger.info("データベース接続をテスト中...")
        
        connectivity_result = {
            'status': 'OK',
            'backends': {},
            'errors': []
        }
        
        # SQLiteテスト
        try:
            from mimizam import create_mimizam_sqlite
            
            # メモリ内データベースでテスト
            mimizam = create_mimizam_sqlite(':memory:')
            songs = mimizam.list_songs()
            
            connectivity_result['backends']['sqlite'] = {
                'connection': True,
                'error': None
            }
            
        except Exception as e:
            connectivity_result['backends']['sqlite'] = {
                'connection': False,
                'error': str(e)
            }
            connectivity_result['errors'].append(f"SQLite接続エラー: {e}")
        
        # ステータス判定
        if 'sqlite' in connectivity_result['backends'] and not connectivity_result['backends']['sqlite']['connection']:
            connectivity_result['status'] = 'ERROR'
        
        return connectivity_result
    
    def _measure_performance_baseline(self) -> Dict[str, Any]:
        """パフォーマンスベースライン測定"""
        
        self.logger.info("パフォーマンスベースラインを測定中...")
        
        performance_result = {
            'status': 'OK',
            'metrics': {},
            'warnings': []
        }
        
        try:
            import numpy as np
            import time
            from mimizam import AudioFingerprinter
            
            # テスト音声（10秒）
            test_audio = np.random.randn(22050 * 10)
            
            # 指紋生成性能測定
            fingerprinter = AudioFingerprinter()
            
            start_time = time.time()
            fingerprints = fingerprinter.fingerprint_audio(test_audio)
            processing_time = time.time() - start_time
            
            performance_result['metrics'] = {
                'audio_duration': 10.0,
                'processing_time': processing_time,
                'throughput_ratio': 10.0 / processing_time,
                'fingerprints_generated': len(fingerprints)
            }
            
            # 性能警告
            if processing_time > 5.0:  # 10秒音声の処理に5秒以上
                performance_result['warnings'].append("処理速度が遅い可能性があります")
                performance_result['status'] = 'WARNING'
            
            if len(fingerprints) < 50:  # 指紋数が少ない
                performance_result['warnings'].append("生成される指紋数が少ない可能性があります")
                performance_result['status'] = 'WARNING'
            
            return performance_result
            
        except Exception as e:
            self.logger.error(f"パフォーマンス測定エラー: {e}")
            return {
                'status': 'ERROR',
                'error': str(e),
                'traceback': traceback.format_exc()
            }
    
    def _analyze_memory_usage(self) -> Dict[str, Any]:
        """メモリ使用量分析"""
        
        self.logger.info("メモリ使用量を分析中...")
        
        memory_result = {
            'status': 'OK',
            'initial_memory_mb': 0,
            'peak_memory_mb': 0,
            'memory_increase_mb': 0,
            'warnings': []
        }
        
        try:
            import gc
            import numpy as np
            from mimizam import AudioFingerprinter
            
            # 初期メモリ使用量
            process = psutil.Process()
            initial_memory = process.memory_info().rss / 1024 / 1024
            memory_result['initial_memory_mb'] = initial_memory
            
            # メモリ使用量測定テスト
            peak_memory = initial_memory
            
            for i in range(3):  # 3回のテスト
                # 大きな音声データで指紋生成
                test_audio = np.random.randn(22050 * 30)  # 30秒
                fingerprinter = AudioFingerprinter()
                fingerprints = fingerprinter.fingerprint_audio(test_audio)
                
                current_memory = process.memory_info().rss / 1024 / 1024
                peak_memory = max(peak_memory, current_memory)
                
                # メモリクリーンアップ
                del test_audio, fingerprints, fingerprinter
                gc.collect()
            
            memory_result['peak_memory_mb'] = peak_memory
            memory_result['memory_increase_mb'] = peak_memory - initial_memory
            
            # メモリ警告
            if memory_result['memory_increase_mb'] > 500:  # 500MB以上の増加
                memory_result['warnings'].append("メモリ使用量が大きい可能性があります")
                memory_result['status'] = 'WARNING'
            
            return memory_result
            
        except Exception as e:
            self.logger.error(f"メモリ分析エラー: {e}")
            return {
                'status': 'ERROR',
                'error': str(e),
                'traceback': traceback.format_exc()
            }
    
    def _generate_recommendations(self, results: Dict[str, Any]) -> List[str]:
        """推奨事項生成"""
        
        recommendations = []
        
        # システム環境の推奨事項
        if results['system_info']['status'] == 'WARNING':
            if 'warnings' in results['system_info']:
                for warning in results['system_info']['warnings']:
                    if 'メモリ不足' in warning:
                        recommendations.append("システムメモリを2GB以上に増設することを推奨します")
                    elif 'ディスク容量不足' in warning:
                        recommendations.append("ディスク容量を1GB以上確保することを推奨します")
        
        # 依存関係の推奨事項
        if results['dependencies']['status'] == 'ERROR':
            if results['dependencies']['missing']:
                missing_packages = ', '.join(results['dependencies']['missing'])
                recommendations.append(f"必須パッケージをインストールしてください: {missing_packages}")
        
        # パフォーマンスの推奨事項
        if results['performance_baseline']['status'] == 'WARNING':
            if 'processing_time' in results['performance_baseline']['metrics']:
                processing_time = results['performance_baseline']['metrics']['processing_time']
                if processing_time > 5.0:
                    recommendations.append("処理速度改善のためNumba最適化を有効にすることを推奨します")
        
        return recommendations
    
    def generate_diagnostic_report(self, results: Dict[str, Any]) -> str:
        """診断レポート生成"""
        
        report = []
        report.append("=" * 60)
        report.append("mimizam システム診断レポート")
        report.append("=" * 60)
        report.append(f"診断実行日時: {results['timestamp']}")
        report.append("")
        
        # システム環境
        report.append("【システム環境】")
        sys_info = results['system_info']
        if sys_info['status'] != 'ERROR':
            report.append(f"Python バージョン: {sys_info['python_version']}")
            report.append(f"プラットフォーム: {sys_info['platform']}")
            report.append(f"CPU数: {sys_info['cpu_count']}")
            report.append(f"メモリ: {sys_info['memory_total_gb']:.1f} GB")
            report.append(f"ディスク空き容量: {sys_info['disk_free_gb']:.1f} GB")
            report.append(f"ステータス: {sys_info['status']}")
        else:
            report.append(f"エラー: {sys_info.get('error', '不明なエラー')}")
        
        report.append("")
        
        # 依存関係
        report.append("【依存関係】")
        deps = results['dependencies']
        if deps['status'] != 'ERROR':
            report.append("必須パッケージ:")
            for pkg, info in deps['required'].items():
                status = "✅" if info['installed'] else "❌"
                version = info.get('version', 'N/A')
                report.append(f"  {status} {pkg}: {version}")
        else:
            report.append(f"エラー: {deps.get('error', '不明なエラー')}")
        
        report.append("")
        
        # 推奨事項
        if results['recommendations']:
            report.append("【推奨事項】")
            for i, rec in enumerate(results['recommendations'], 1):
                report.append(f"{i}. {rec}")
        
        report.append("")
        report.append("=" * 60)
        
        return "\n".join(report)

# 使用例
diagnostic_tool = DiagnosticTool()

# 完全診断実行
results = diagnostic_tool.run_full_diagnostic()

# レポート生成と表示
report = diagnostic_tool.generate_diagnostic_report(results)
print(report)
```

## 🚨 一般的な問題と解決方法

### 音声処理エラー

#### 問題: ファイル読み込みエラー
```python
def safe_audio_load(file_path: str):
    """安全な音声ファイル読み込み"""
    
    import os
    import librosa
    
    # ファイル存在確認
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"音声ファイルが見つかりません: {file_path}")
    
    # ファイル形式確認
    supported_formats = ['.wav', '.mp3', '.flac', '.m4a', '.ogg']
    file_ext = os.path.splitext(file_path)[1].lower()
    
    if file_ext not in supported_formats:
        raise ValueError(f"未対応の音声形式: {file_ext}")
    
    try:
        audio, sr = librosa.load(file_path, sr=22050)
        return audio, sr
    except Exception as e:
        raise RuntimeError(f"音声読み込みエラー: {e}")

# 使用例
try:
    audio, sr = safe_audio_load("sample.wav")
except (FileNotFoundError, ValueError, RuntimeError) as e:
    print(f"音声処理エラー: {e}")
```

#### 問題: 指紋生成失敗
```python
def robust_fingerprint_generation(audio: np.ndarray, fingerprinter):
    """堅牢な指紋生成"""
    
    # 音声データ検証
    if len(audio) == 0:
        raise ValueError("空の音声データです")
    
    if len(audio) < 22050:  # 1秒未満
        print("警告: 音声が短すぎます（1秒未満）")
    
    # 音声レベル確認
    rms = np.sqrt(np.mean(audio**2))
    if rms < 1e-6:
        print("警告: 音声レベルが非常に低いです")
    
    try:
        fingerprints = fingerprinter.fingerprint_audio(audio)
        
        if len(fingerprints) == 0:
            print("警告: 指紋が生成されませんでした")
            # パラメータ調整を試行
            fingerprinter.min_amplitude = -70  # 感度を上げる
            fingerprints = fingerprinter.fingerprint_audio(audio)
        
        return fingerprints
        
    except Exception as e:
        print(f"指紋生成エラー: {e}")
        return []
```

### データベース接続問題

#### 問題: MySQL接続エラー
```python
def diagnose_mysql_connection(config):
    """MySQL接続診断"""
    
    import mysql.connector
    from mysql.connector import Error
    
    try:
        # 基本接続テスト
        connection = mysql.connector.connect(
            host=config.host,
            port=config.port,
            user=config.username,
            password=config.password,
            database=config.database,
            connection_timeout=10
        )
        
        if connection.is_connected():
            print("✅ MySQL接続成功")
            
            # データベース情報取得
            cursor = connection.cursor()
            cursor.execute("SELECT VERSION()")
            version = cursor.fetchone()[0]
            print(f"MySQL バージョン: {version}")
            
            cursor.close()
            connection.close()
            return True
            
    except Error as e:
        error_code = e.errno
        error_msg = e.msg
        
        # エラー別診断
        if error_code == 2003:
            print("❌ サーバー接続失敗")
            print("  - MySQLサーバーが起動しているか確認してください")
            print("  - ホスト名・ポート番号が正しいか確認してください")
            print("  - ファイアウォール設定を確認してください")
        
        elif error_code == 1045:
            print("❌ 認証失敗")
            print("  - ユーザー名・パスワードが正しいか確認してください")
            print("  - ユーザーに適切な権限があるか確認してください")
        
        elif error_code == 1049:
            print("❌ データベース不存在")
            print("  - データベース名が正しいか確認してください")
            print("  - データベースが作成されているか確認してください")
        
        else:
            print(f"❌ MySQL接続エラー ({error_code}): {error_msg}")
        
        return False
```

## 🔗 関連ドキュメント

- [パフォーマンス最適化](./12_performance_optimization.md) - 性能向上手法
- [パフォーマンス分析](./20_performance_analysis.md) - 詳細分析
- [テスト](./22_testing.md) - テスト手法
- [品質保証](./24_quality_assurance.md) - 品質管理
- [FAQ](./27_faq.md) - よくある質問

## 💡 デバッグのベストプラクティス

### 1. 系統的なアプローチ
- 問題の再現性確認
- ログの詳細な分析
- 段階的な原因特定

### 2. 適切なツール使用
- プロファイラーによる性能分析
- メモリ使用量の監視
- システムリソースの確認

### 3. 予防的対策
- 定期的な診断実行
- 監視システムの構築
- ドキュメントの充実

mimizamシステムの問題を効率的に診断・解決するために、これらのデバッグ手法を活用してください。
