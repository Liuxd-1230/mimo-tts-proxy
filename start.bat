@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"

:: 检查 Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] 未找到 Python，请先安装 Python 3.10+
    pause
    exit /b 1
)

:: 安装依赖
echo [*] 检查依赖...
pip install -r requirements.txt -q 2>nul

:: 启动服务
echo.
echo 🎙️  MiMo TTS Proxy Server
echo    启动中...
echo.
python main.py %*
pause
