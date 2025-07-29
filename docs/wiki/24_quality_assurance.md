# 品質保証

mimizamプロジェクトの品質保証プロセスと品質管理手法について詳しく解説します。コード品質、テスト戦略、CI/CD、コードレビュー、品質メトリクスなど、高品質なソフトウェア開発を支える包括的なアプローチを提供します。

## 🎯 品質保証の概要

### 品質保証体系

```
品質保証体系
├── コード品質
│   ├── コーディング規約
│   ├── 静的解析
│   └── コードレビュー
├── テスト品質
│   ├── テストカバレッジ
│   ├── テスト自動化
│   └── テスト戦略
├── プロセス品質
│   ├── CI/CD パイプライン
│   ├── リリース管理
│   └── 変更管理
└── 品質メトリクス
    ├── 品質指標測定
    ├── 品質ダッシュボード
    └── 継続的改善
```

## 📋 コード品質管理

### コーディング規約

```python
"""
mimizam プロジェクト コーディング規約

1. PEP 8 準拠
2. 型ヒント必須
3. docstring 必須（Google スタイル）
4. 命名規則の統一
"""

# 良い例
class AudioFingerprinter:
    """音声指紋生成器
    
    音声データから音響指紋を生成し、楽曲識別に使用する特徴量を抽出します。
    
    Attributes:
        n_fft: FFTウィンドウサイズ
        hop_length: ホップ長
        min_amplitude: 最小振幅閾値（dB）
        enable_numba_optimization: Numba最適化の有効化
    """
    
    def __init__(self, 
                 n_fft: int = 2048,
                 hop_length: int = 512,
                 min_amplitude: float = -60.0,
                 enable_numba_optimization: bool = True) -> None:
        """初期化
        
        Args:
            n_fft: FFTウィンドウサイズ（2の累乗を推奨）
            hop_length: ホップ長（n_fftの1/4を推奨）
            min_amplitude: 最小振幅閾値（dB、負の値）
            enable_numba_optimization: Numba最適化を有効にするか
            
        Raises:
            ValueError: パラメータが無効な場合
        """
        if n_fft <= 0 or (n_fft & (n_fft - 1)) != 0:
            raise ValueError("n_fftは正の2の累乗である必要があります")
        
        if hop_length <= 0:
            raise ValueError("hop_lengthは正の値である必要があります")
        
        if min_amplitude >= 0:
            raise ValueError("min_amplitudeは負の値である必要があります")
        
        self.n_fft = n_fft
        self.hop_length = hop_length
        self.min_amplitude = min_amplitude
        self.enable_numba_optimization = enable_numba_optimization
    
    def fingerprint_audio(self, audio: np.ndarray) -> List[Fingerprint]:
        """音声から指紋を生成
        
        Args:
            audio: 音声データ（1次元numpy配列）
            
        Returns:
            生成された指紋のリスト
            
        Raises:
            ValueError: 音声データが無効な場合
        """
        if len(audio) == 0:
            raise ValueError("空の音声データは処理できません")
        
        # 実装...
        return []

# 悪い例（避けるべき）
class af:  # クラス名が不明確
    def __init__(self, n=2048, h=512):  # 型ヒントなし、パラメータ名が不明確
        self.n = n  # 属性名が不明確
        self.h = h
    
    def fp(self, a):  # メソッド名・パラメータ名が不明確、docstringなし
        return []  # 実装なし
```

### 静的解析設定

```python
# pyproject.toml
[tool.black]
line-length = 88
target-version = ['py38']
include = '\.pyi?$'
extend-exclude = '''
/(
  # directories
  \.eggs
  | \.git
  | \.hg
  | \.mypy_cache
  | \.tox
  | \.venv
  | build
  | dist
)/
'''

[tool.isort]
profile = "black"
multi_line_output = 3
line_length = 88
known_first_party = ["mimizam"]

[tool.flake8]
max-line-length = 88
extend-ignore = ["E203", "W503"]
exclude = [".git", "__pycache__", "build", "dist"]

[tool.mypy]
python_version = "3.8"
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true
disallow_incomplete_defs = true
check_untyped_defs = true
disallow_untyped_decorators = true
no_implicit_optional = true
warn_redundant_casts = true
warn_unused_ignores = true
warn_no_return = true
warn_unreachable = true
strict_equality = true

[tool.pylint]
max-line-length = 88
disable = [
    "C0103",  # invalid-name
    "R0903",  # too-few-public-methods
]

[tool.pytest.ini_options]
minversion = "6.0"
addopts = "-ra -q --strict-markers --strict-config"
testpaths = ["tests"]
markers = [
    "slow: marks tests as slow (deselect with '-m \"not slow\"')",
    "integration: marks tests as integration tests",
    "unit: marks tests as unit tests",
]
```

### コードレビューチェックリスト

```python
def get_code_review_checklist() -> dict:
    """コードレビューチェックリスト取得"""
    
    return {
        'functional_checks': [
            "機能要件を満たしているか",
            "エラーハンドリングが適切か",
            "エッジケースが考慮されているか",
            "パフォーマンスに問題はないか",
            "セキュリティ上の問題はないか"
        ],
        'code_quality_checks': [
            "コーディング規約に準拠しているか",
            "命名が適切で理解しやすいか",
            "関数・クラスのサイズが適切か",
            "重複コードがないか",
            "コメント・docstringが適切か"
        ],
        'test_checks': [
            "適切なテストが追加されているか",
            "テストカバレッジが十分か",
            "テストが独立して実行可能か",
            "テストが理解しやすいか",
            "エッジケースのテストがあるか"
        ],
        'documentation_checks': [
            "APIドキュメントが更新されているか",
            "README等の更新が必要か",
            "変更ログが記録されているか",
            "使用例が提供されているか"
        ]
    }

def generate_review_template() -> str:
    """レビューテンプレート生成"""
    
    checklist = get_code_review_checklist()
        
        template = []
        template.append("## コードレビューチェックリスト")
        template.append("")
        
        template.append("### 機能面")
        for check in cls.FUNCTIONAL_CHECKS:
            template.append(f"- [ ] {check}")
        template.append("")
        
        template.append("### コード品質")
        for check in cls.CODE_QUALITY_CHECKS:
            template.append(f"- [ ] {check}")
        template.append("")
        
        template.append("### テスト")
        for check in cls.TEST_CHECKS:
            template.append(f"- [ ] {check}")
        template.append("")
        
        template.append("### ドキュメント")
        for check in cls.DOCUMENTATION_CHECKS:
            template.append(f"- [ ] {check}")
        template.append("")
        
        template.append("### 総合評価")
        template.append("- [ ] 承認")
        template.append("- [ ] 修正要求")
        template.append("- [ ] 要議論")
        
        return "\n".join(template)

# 使用例
review_template = CodeReviewChecklist.generate_review_template()
print(review_template)
```

## 🔄 CI/CD パイプライン

### GitHub Actions ワークフロー

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [ main, dev ]
  pull_request:
    branches: [ main, dev ]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: [3.8, 3.9, "3.10", "3.11"]
    
    services:
      mysql:
        image: mysql:8.0
        env:
          MYSQL_ROOT_PASSWORD: test_password
          MYSQL_DATABASE: test_mimizam
        ports:
          - 3306:3306
        options: --health-cmd="mysqladmin ping" --health-interval=10s --health-timeout=5s --health-retries=3
      
      postgres:
        image: postgres:13
        env:
          POSTGRES_PASSWORD: test_password
          POSTGRES_DB: test_mimizam
        ports:
          - 5432:5432
        options: --health-cmd pg_isready --health-interval 10s --health-timeout 5s --health-retries 5
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python ${{ matrix.python-version }}
      uses: actions/setup-python@v4
      with:
        python-version: ${{ matrix.python-version }}
    
    - name: Install system dependencies
      run: |
        sudo apt-get update
        sudo apt-get install -y ffmpeg libsndfile1
    
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install poetry
        poetry install --with dev
    
    - name: Lint with flake8
      run: |
        poetry run flake8 src tests
    
    - name: Type check with mypy
      run: |
        poetry run mypy src
    
    - name: Format check with black
      run: |
        poetry run black --check src tests
    
    - name: Import sort check with isort
      run: |
        poetry run isort --check-only src tests
    
    - name: Run unit tests
      run: |
        poetry run pytest tests/unit -v --cov=src --cov-report=xml
    
    - name: Run integration tests
      run: |
        poetry run pytest tests/integration -v
      env:
        TEST_MYSQL: true
        TEST_POSTGRESQL: true
        MYSQL_HOST: localhost
        MYSQL_DATABASE: test_mimizam
        MYSQL_USER: root
        MYSQL_PASSWORD: test_password
        POSTGRES_HOST: localhost
        POSTGRES_DATABASE: test_mimizam
        POSTGRES_USER: postgres
        POSTGRES_PASSWORD: test_password
    
    - name: Upload coverage to Codecov
      uses: codecov/codecov-action@v3
      with:
        file: ./coverage.xml
        flags: unittests
        name: codecov-umbrella
        fail_ci_if_error: true

  performance-test:
    runs-on: ubuntu-latest
    needs: test
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: "3.10"
    
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install poetry
        poetry install --with dev
    
    - name: Run performance tests
      run: |
        poetry run pytest tests/performance -v --benchmark-only
    
    - name: Store benchmark result
      uses: benchmark-action/github-action-benchmark@v1
      with:
        tool: 'pytest'
        output-file-path: benchmark.json
        github-token: ${{ secrets.GITHUB_TOKEN }}
        auto-push: true

  security-scan:
    runs-on: ubuntu-latest
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Run Bandit Security Scan
      uses: securecodewarrior/github-action-bandit@v1
      with:
        path: "src"
        level: "high"
        confidence: "high"
    
    - name: Run Safety Check
      run: |
        pip install safety
        safety check --json --output safety-report.json || true
    
    - name: Upload security reports
      uses: actions/upload-artifact@v3
      with:
        name: security-reports
        path: |
          bandit-report.json
          safety-report.json
```

### 品質ゲート設定

```python
class QualityGate:
    """品質ゲート"""
    
    def __init__(self):
        self.criteria = {
            'test_coverage': 80.0,      # テストカバレッジ80%以上
            'code_duplication': 5.0,    # コード重複5%以下
            'complexity': 10,           # 循環的複雑度10以下
            'maintainability': 'A',     # 保守性ランクA以上
            'reliability': 'A',         # 信頼性ランクA以上
            'security': 'A'             # セキュリティランクA以上
        }
    
    def evaluate_quality(self, metrics: Dict[str, Any]) -> Dict[str, Any]:
        """品質評価実行"""
        
        results = {
            'passed': True,
            'criteria_results': {},
            'overall_score': 0,
            'recommendations': []
        }
        
        passed_count = 0
        total_count = len(self.criteria)
        
        for criterion, threshold in self.criteria.items():
            if criterion in metrics:
                actual_value = metrics[criterion]
                
                # 基準判定
                if criterion == 'test_coverage':
                    passed = actual_value >= threshold
                elif criterion == 'code_duplication':
                    passed = actual_value <= threshold
                elif criterion == 'complexity':
                    passed = actual_value <= threshold
                elif criterion in ['maintainability', 'reliability', 'security']:
                    passed = actual_value in ['A', 'B']  # A or B ランク
                else:
                    passed = True
                
                results['criteria_results'][criterion] = {
                    'actual': actual_value,
                    'threshold': threshold,
                    'passed': passed
                }
                
                if passed:
                    passed_count += 1
                else:
                    results['passed'] = False
                    
                    # 改善推奨事項
                    if criterion == 'test_coverage':
                        results['recommendations'].append(
                            f"テストカバレッジを{threshold}%以上に向上させてください（現在: {actual_value}%）"
                        )
                    elif criterion == 'code_duplication':
                        results['recommendations'].append(
                            f"コード重複を{threshold}%以下に削減してください（現在: {actual_value}%）"
                        )
                    elif criterion == 'complexity':
                        results['recommendations'].append(
                            f"循環的複雑度を{threshold}以下に削減してください（現在: {actual_value}）"
                        )
        
        results['overall_score'] = (passed_count / total_count) * 100
        
        return results
    
    def generate_quality_report(self, evaluation_results: Dict[str, Any]) -> str:
        """品質レポート生成"""
        
        report = []
        report.append("=" * 50)
        report.append("品質ゲート評価レポート")
        report.append("=" * 50)
        report.append("")
        
        # 全体結果
        overall_status = "✅ 合格" if evaluation_results['passed'] else "❌ 不合格"
        report.append(f"全体結果: {overall_status}")
        report.append(f"総合スコア: {evaluation_results['overall_score']:.1f}%")
        report.append("")
        
        # 基準別結果
        report.append("基準別結果:")
        for criterion, result in evaluation_results['criteria_results'].items():
            status = "✅" if result['passed'] else "❌"
            report.append(f"  {status} {criterion}: {result['actual']} (基準: {result['threshold']})")
        
        report.append("")
        
        # 改善推奨事項
        if evaluation_results['recommendations']:
            report.append("改善推奨事項:")
            for i, rec in enumerate(evaluation_results['recommendations'], 1):
                report.append(f"  {i}. {rec}")
        
        report.append("")
        report.append("=" * 50)
        
        return "\n".join(report)

# 使用例
quality_gate = QualityGate()

# サンプルメトリクス
sample_metrics = {
    'test_coverage': 85.5,
    'code_duplication': 3.2,
    'complexity': 8,
    'maintainability': 'A',
    'reliability': 'B',
    'security': 'A'
}

# 品質評価実行
evaluation = quality_gate.evaluate_quality(sample_metrics)

# レポート生成
report = quality_gate.generate_quality_report(evaluation)
print(report)
```

## 📊 品質メトリクス

### 品質ダッシュボード

```python
class QualityDashboard:
    """品質ダッシュボード"""
    
    def __init__(self):
        self.metrics_history = []
        
    def collect_metrics(self) -> Dict[str, Any]:
        """品質メトリクス収集"""
        
        metrics = {
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'code_metrics': self._collect_code_metrics(),
            'test_metrics': self._collect_test_metrics(),
            'performance_metrics': self._collect_performance_metrics(),
            'security_metrics': self._collect_security_metrics()
        }
        
        self.metrics_history.append(metrics)
        return metrics
    
    def _collect_code_metrics(self) -> Dict[str, Any]:
        """コードメトリクス収集"""
        
        # 実際の実装では、radon、flake8、mypyなどのツールを使用
        return {
            'lines_of_code': 15420,
            'cyclomatic_complexity': 7.2,
            'maintainability_index': 82.5,
            'code_duplication': 2.8,
            'technical_debt_ratio': 1.2
        }
    
    def _collect_test_metrics(self) -> Dict[str, Any]:
        """テストメトリクス収集"""
        
        # 実際の実装では、coverage.py、pytestなどのツールを使用
        return {
            'test_coverage': 87.3,
            'branch_coverage': 82.1,
            'test_count': 156,
            'test_success_rate': 98.7,
            'test_execution_time': 45.2
        }
    
    def _collect_performance_metrics(self) -> Dict[str, Any]:
        """パフォーマンスメトリクス収集"""
        
        # 実際の実装では、パフォーマンステストの結果を使用
        return {
            'avg_fingerprint_time': 0.125,
            'avg_search_time': 0.089,
            'memory_usage_mb': 245.6,
            'throughput_ratio': 8.2
        }
    
    def _collect_security_metrics(self) -> Dict[str, Any]:
        """セキュリティメトリクス収集"""
        
        # 実際の実装では、bandit、safetyなどのツールを使用
        return {
            'security_issues': 0,
            'vulnerability_count': 0,
            'security_score': 95.8,
            'dependency_vulnerabilities': 0
        }
    
    def generate_dashboard_html(self, output_path: str = "quality_dashboard.html"):
        """HTMLダッシュボード生成"""
        
        if not self.metrics_history:
            self.collect_metrics()
        
        latest_metrics = self.metrics_history[-1]
        
        html_content = f"""
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>mimizam 品質ダッシュボード</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .dashboard {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; }}
        .metric-card {{ border: 1px solid #ddd; border-radius: 8px; padding: 20px; background: #f9f9f9; }}
        .metric-title {{ font-size: 18px; font-weight: bold; margin-bottom: 10px; }}
        .metric-value {{ font-size: 24px; color: #2196F3; }}
        .metric-good {{ color: #4CAF50; }}
        .metric-warning {{ color: #FF9800; }}
        .metric-error {{ color: #F44336; }}
    </style>
</head>
<body>
    <h1>mimizam 品質ダッシュボード</h1>
    <p>最終更新: {latest_metrics['timestamp']}</p>
    
    <div class="dashboard">
        <div class="metric-card">
            <div class="metric-title">テストカバレッジ</div>
            <div class="metric-value metric-good">{latest_metrics['test_metrics']['test_coverage']:.1f}%</div>
        </div>
        
        <div class="metric-card">
            <div class="metric-title">循環的複雑度</div>
            <div class="metric-value metric-good">{latest_metrics['code_metrics']['cyclomatic_complexity']:.1f}</div>
        </div>
        
        <div class="metric-card">
            <div class="metric-title">保守性指数</div>
            <div class="metric-value metric-good">{latest_metrics['code_metrics']['maintainability_index']:.1f}</div>
        </div>
        
        <div class="metric-card">
            <div class="metric-title">コード重複</div>
            <div class="metric-value metric-good">{latest_metrics['code_metrics']['code_duplication']:.1f}%</div>
        </div>
        
        <div class="metric-card">
            <div class="metric-title">平均指紋生成時間</div>
            <div class="metric-value metric-good">{latest_metrics['performance_metrics']['avg_fingerprint_time']:.3f}秒</div>
        </div>
        
        <div class="metric-card">
            <div class="metric-title">セキュリティスコア</div>
            <div class="metric-value metric-good">{latest_metrics['security_metrics']['security_score']:.1f}</div>
        </div>
    </div>
</body>
</html>
        """
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        return output_path

# 使用例
dashboard = QualityDashboard()

# メトリクス収集
metrics = dashboard.collect_metrics()

# ダッシュボード生成
dashboard_path = dashboard.generate_dashboard_html()
print(f"品質ダッシュボード生成: {dashboard_path}")
```

## 🔗 関連ドキュメント

- [テスト](./22_testing.md) - テスト戦略
- [パフォーマンステスト](./23_performance_testing.md) - 性能テスト
- [デバッグとトラブルシューティング](./21_debugging.md) - 問題解決
- [プロジェクト構造](./06_project_structure.md) - プロジェクト構成
- [FAQ](./27_faq.md) - よくある質問

## 💡 品質保証のベストプラクティス

### 1. 継続的品質改善
- 定期的な品質メトリクス測定
- 品質目標の設定と追跡
- フィードバックループの構築

### 2. 自動化の推進
- CI/CDパイプラインの充実
- 自動テストの拡充
- 品質チェックの自動化

### 3. チーム文化の醸成
- 品質意識の共有
- コードレビュー文化の定着
- 継続的学習の促進

mimizamプロジェクトの高品質を維持するため、これらの品質保証手法を継続的に実践してください。
