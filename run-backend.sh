#!/usr/bin/env bash
# 解决 Windows + 中文环境下 PyTorch torch.compile 加载模板文件时的
# UnicodeDecodeError ('gbk' codec ...)。必须在 Python 启动前设上。
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8

cd "$(dirname "$0")/backend"
exec uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000