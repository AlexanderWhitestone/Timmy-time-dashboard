#!/usr/bin/env python3
"""Add pytest markers to test files based on naming conventions and content.

Usage:
    python scripts/add_pytest_markers.py
"""

import re
from pathlib import Path


def categorize_test(file_path: Path) -> str:
    """Determine test category based on file path and content."""
    path_str = str(file_path)
    content = file_path.read_text()

    # E2E tests
    if "e2e" in path_str or "end_to_end" in path_str:
        return "e2e"

    # Functional tests
    if "functional" in path_str:
        return "functional"

    # Integration tests
    if "integration" in path_str or "_integration" in file_path.stem:
        return "integration"

    # Selenium/browser tests
    if "selenium" in path_str or "ui" in path_str or "browser" in path_str:
        return "selenium"

    # Docker tests
    if "docker" in path_str:
        return "docker"

    # Default to unit
    return "unit"


def add_marker_to_file(file_path: Path, marker: str) -> bool:
    """Add pytest marker to file if not already present."""
    content = file_path.read_text()

    # Check if marker already exists
    if f'@pytest.mark.{marker}' in content or f'pytestmark = pytest.mark.{marker}' in content:
        return False

    # Check if file has any pytest imports
    if "import pytest" not in content:
        # Add pytest import at the top
        lines = content.split("\n")
        # Find the right place to add import (after docstring/comments)
        insert_idx = 0
        for i, line in enumerate(lines):
            if line.startswith('"""') or line.startswith("'''") or line.startswith("#"):
                insert_idx = i + 1
            elif line.strip() and not line.startswith(("import", "from")):
                break

        lines.insert(insert_idx, "import pytest")
        content = "\n".join(lines)

    # Add pytestmark at module level (after imports)
    lines = content.split("\n")
    insert_idx = 0
    for i, line in enumerate(lines):
        if line.startswith(("import ", "from ")):
            insert_idx = i + 1

    # Add blank line and pytestmark
    pytestmark_line = f"pytestmark = pytest.mark.{marker}"
    if insert_idx < len(lines) and lines[insert_idx].strip():
        lines.insert(insert_idx, "")
    lines.insert(insert_idx + 1, pytestmark_line)

    file_path.write_text("\n".join(lines))
    return True


def main():
    """Add markers to all test files."""
    test_dir = Path("tests")
    marked_count = 0

    for test_file in sorted(test_dir.rglob("test_*.py")):
        marker = categorize_test(test_file)
        rel_path = str(test_file.relative_to(test_dir))
        if add_marker_to_file(test_file, marker):
            print(f"✅ {rel_path:<50} -> @pytest.mark.{marker}")
            marked_count += 1
        else:
            print(f"⏭️  {rel_path:<50} (already marked)")

    print(f"\n📊 Total files marked: {marked_count}")
    print(f"\n✨ Pytest markers configured. Run 'pytest -m unit' to test specific categories.")


if __name__ == "__main__":
    import sys
    sys.path.insert(0, "src")
    main()
