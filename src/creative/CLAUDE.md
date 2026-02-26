# creative/ — Module Guide

GPU-accelerated media generation. Heavy dependencies (PyTorch, diffusers).

## Structure
- `director.py` — Orchestrates multi-step creative pipelines
- `assembler.py` — Video assembly and stitching
- `tools/` — MCP-compliant tool implementations
  - `image_tools.py` — FLUX.2 image generation
  - `music_tools.py` — ACE-Step music generation
  - `video_tools.py` — Wan 2.1 video generation
  - `git_tools.py`, `file_ops.py`, `code_exec.py` — Utility tools
  - `self_edit.py` — Self-modification MCP tool (protected file)

## Testing
```bash
pytest tests/creative/ -q
```
