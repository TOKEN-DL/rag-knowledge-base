@echo off
REM 解决 Windows + 中文环境下 PyTorch torch.compile 加载模板文件时的
REM UnicodeDecodeError ('gbk' codec ...)。必须在 Python 启动前设上。
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

cd /d %~dp0backend
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000