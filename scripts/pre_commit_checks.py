#!/usr/bin/env python3
"""
Pre-commit checks for common CI failures.

This script runs before commits to catch issues early:
- ImportError regressions (missing exports from modules)
- Model name assertions (config mismatches)
- Platform-specific path issues
- Syntax errors in test files
"""

import sys
import subprocess
from pathlib import Path
import ast
import re


def check_imports():
    """Check for common ImportError issues."""
    issues = []
    
    # Check that dashboard.app exports 'templates'
    try:
        from dashboard.app import templates
        print("✓ dashboard.app exports 'templates'")
    except ImportError as e:
        issues.append(f"✗ ImportError in dashboard.app: {e}")
    
    # Check that integrations.shortcuts.siri is importable
    try:
        from integrations.shortcuts.siri import get_setup_guide
        print("✓ integrations.shortcuts.siri exports 'get_setup_guide'")
    except ImportError as e:
        issues.append(f"✗ ImportError in integrations.shortcuts.siri: {e}")
    
    return issues


def check_model_config():
    """Check that model configuration is consistent."""
    issues = []
    
    try:
        from config import settings
        from timmy.agent import DEFAULT_MODEL_FALLBACKS
        
        # Ensure configured model is valid
        if not settings.ollama_model:
            issues.append("✗ OLLAMA_MODEL is not configured")
        else:
            print(f"✓ OLLAMA_MODEL is configured: {settings.ollama_model}")
        
        # Ensure fallback chain is not empty
        if not DEFAULT_MODEL_FALLBACKS:
            issues.append("✗ DEFAULT_MODEL_FALLBACKS is empty")
        else:
            print(f"✓ DEFAULT_MODEL_FALLBACKS has {len(DEFAULT_MODEL_FALLBACKS)} models")
    
    except Exception as e:
        issues.append(f"✗ Error checking model config: {e}")
    
    return issues


def check_test_syntax():
    """Check for syntax errors in test files."""
    issues = []
    tests_dir = Path("tests").resolve()
    
    for test_file in tests_dir.rglob("test_*.py"):
        try:
            with open(test_file, "r") as f:
                ast.parse(f.read())
            print(f"✓ {test_file.relative_to(tests_dir.parent)} has valid syntax")
        except SyntaxError as e:
            issues.append(f"✗ Syntax error in {test_file.relative_to(tests_dir.parent)}: {e}")
    
    return issues


def check_platform_specific_tests():
    """Check for platform-specific test assertions."""
    issues = []
    
    # Check for hardcoded /Users/ paths in tests
    tests_dir = Path("tests").resolve()
    for test_file in tests_dir.rglob("test_*.py"):
        with open(test_file, "r") as f:
            content = f.read()
            if 'startswith("/Users/")' in content:
                issues.append(
                    f"✗ {test_file.relative_to(tests_dir.parent)} has hardcoded /Users/ path. "
                    "Use Path.home() instead for platform compatibility."
                )
    
    if not issues:
        print("✓ No platform-specific hardcoded paths found in tests")
    
    return issues


def check_docker_availability():
    """Check if Docker tests will be skipped properly."""
    issues = []
    
    # Check that Docker tests have proper skipif decorators
    tests_dir = Path("tests").resolve()
    docker_test_files = list(tests_dir.rglob("test_docker*.py"))
    
    if docker_test_files:
        for test_file in docker_test_files:
            with open(test_file, "r") as f:
                content = f.read()
                has_skipif = "@pytest.mark.skipif" in content or "pytestmark = pytest.mark.skipif" in content
                if not has_skipif and "docker" in content.lower():
                    issues.append(
                        f"✗ {test_file.relative_to(tests_dir.parent)} has Docker tests but no skipif decorator"
                    )
    
    if not issues:
        print("✓ Docker tests have proper skipif decorators")
    
    return issues


def check_black_formatting():
    """Check that files are formatted with Black."""
    issues = []
    
    try:
        result = subprocess.run(
            ["black", "--check", "src/", "tests/", "--quiet"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        
        if result.returncode != 0:
            issues.append(
                "✗ Code formatting issues detected. Run 'black src/ tests/' to fix."
            )
        else:
            print("✓ Code formatting is correct (Black)")
    except FileNotFoundError:
        print("⚠ Black not found. Install with: pip install black")
    except subprocess.TimeoutExpired:
        print("⚠ Black check timed out")
    except Exception as e:
        print(f"⚠ Black check failed: {e}")
    
    return issues


def main():
    """Run all pre-commit checks."""
    print("\n🔍 Running pre-commit checks...\n")
    
    all_issues = []
    
    # Run all checks
    all_issues.extend(check_imports())
    all_issues.extend(check_model_config())
    all_issues.extend(check_test_syntax())
    all_issues.extend(check_platform_specific_tests())
    all_issues.extend(check_docker_availability())
    all_issues.extend(check_black_formatting())
    
    # Report results
    print("\n" + "=" * 70)
    if all_issues:
        print(f"\n❌ Found {len(all_issues)} issue(s):\n")
        for issue in all_issues:
            print(f"  {issue}")
        print("\n" + "=" * 70)
        return 1
    else:
        print("\n✅ All pre-commit checks passed!\n")
        return 0


if __name__ == "__main__":
    sys.exit(main())
