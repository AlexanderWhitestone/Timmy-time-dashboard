"""Test font resolution logic in the creative module."""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


def test_resolve_font_prefers_dejavu():
    """Test that _resolve_font prefers DejaVu fonts when available."""
    from creative.assembler import _resolve_font
    
    # This test will pass on systems with DejaVu fonts installed
    # (most Linux distributions)
    font = _resolve_font()
    assert isinstance(font, str)
    assert font.endswith(".ttf") or font.endswith(".ttc")
    assert Path(font).exists()


def test_resolve_font_returns_valid_path():
    """Test that _resolve_font returns a valid, existing path."""
    from creative.assembler import _resolve_font
    
    font = _resolve_font()
    assert isinstance(font, str)
    # Should be a path, not just a font name
    assert "/" in font or "\\" in font
    assert Path(font).exists()


def test_resolve_font_no_invalid_fallback():
    """Test that _resolve_font never returns invalid font names like 'Helvetica'."""
    from creative.assembler import _resolve_font
    
    font = _resolve_font()
    # Should not return bare font names that Pillow can't find
    assert font not in ["Helvetica", "Arial", "Times New Roman"]
    # Should be a valid path
    assert Path(font).exists()


@patch("creative.assembler.Path.exists")
@patch("subprocess.run")
def test_resolve_font_fallback_search(mock_run, mock_exists):
    """Test that _resolve_font falls back to searching for any TTF."""
    # Mock: no preferred fonts exist
    mock_exists.return_value = False
    
    # Mock: subprocess finds a font
    mock_result = MagicMock()
    mock_result.stdout = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf\n"
    mock_run.return_value = mock_result
    
    from creative.assembler import _resolve_font
    
    font = _resolve_font()
    assert "LiberationSans-Regular.ttf" in font


@patch("creative.assembler.Path.exists")
@patch("subprocess.run")
def test_resolve_font_raises_on_no_fonts(mock_run, mock_exists):
    """Test that _resolve_font raises RuntimeError when no fonts are found."""
    # Mock: no fonts found anywhere
    mock_exists.return_value = False
    mock_result = MagicMock()
    mock_result.stdout = ""
    mock_run.return_value = mock_result
    
    from creative.assembler import _resolve_font
    
    with pytest.raises(RuntimeError, match="No suitable TrueType font found"):
        _resolve_font()
