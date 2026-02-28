#!/usr/bin/env python3
"""Fix syntax errors caused by pytestmark insertion in the middle of imports."""

import re
from pathlib import Path


def fix_syntax_errors(file_path: Path) -> bool:
    """Fix pytestmark inserted in the middle of imports."""
    content = file_path.read_text()

    # Pattern: pytestmark inside an import statement
    # Look for pytestmark = pytest.mark.X between "from X import (" and ")"
    pattern = r'(from\s+[\w.]+\s+import\s*\(\s*\n)(.*?pytestmark\s*=\s*pytest\.mark\.\w+)(.*?\))'
    
    if re.search(pattern, content, re.DOTALL):
        # Remove pytestmark from inside the import
        content = re.sub(
            r'(from\s+[\w.]+\s+import\s*\(\s*\n)(.*?)(pytestmark\s*=\s*pytest\.mark\.\w+\n)(.*?\))',
            r'\1\2\4',
            content,
            flags=re.DOTALL
        )
        
        # Now add pytestmark after all imports
        lines = content.split('\n')
        last_import_idx = -1
        
        for i, line in enumerate(lines):
            if line.startswith(('import ', 'from ')):
                last_import_idx = i
        
        if last_import_idx >= 0:
            # Find the end of the import block (including closing parens)
            i = last_import_idx
            while i < len(lines):
                if ')' in lines[i]:
                    last_import_idx = i
                    break
                i += 1
            
            # Check if pytestmark already exists after imports
            if last_import_idx + 1 < len(lines):
                if 'pytestmark' not in '\n'.join(lines[last_import_idx:last_import_idx+3]):
                    # Insert pytestmark after imports
                    lines.insert(last_import_idx + 1, '')
                    lines.insert(last_import_idx + 2, 'pytestmark = pytest.mark.unit')
                    content = '\n'.join(lines)
        
        file_path.write_text(content)
        return True
    
    return False


def main():
    """Fix all syntax errors in test files."""
    test_dir = Path("tests")
    fixed_count = 0

    for test_file in sorted(test_dir.rglob("test_*.py")):
        try:
            if fix_syntax_errors(test_file):
                print(f"✅ Fixed: {test_file.relative_to(test_dir)}")
                fixed_count += 1
        except Exception as e:
            print(f"❌ Error fixing {test_file.relative_to(test_dir)}: {e}")

    print(f"\n📊 Total files fixed: {fixed_count}")


if __name__ == "__main__":
    main()
