@echo off
chcp 936 >nul
setlocal EnableDelayedExpansion

REM 检测虚拟环境有效性
set VENV_VALID=0
if exist "venv\Scripts\python.exe" (
    venv\Scripts\python.exe -c "import sys; sys.exit(0)" >nul 2>&1
    if !ERRORLEVEL! == 0 (
        set VENV_VALID=1
    )
)

if !VENV_VALID! == 0 (
    echo [ERROR] 虚拟环境不存在或已损坏
    echo 请先运行 步骤1-首次安装.bat 创建虚拟环境
    pause
    exit /b 1
)

REM 激活虚拟环境
call venv\Scripts\activate.bat

REM 检查是否有便携版 Git
if exist "PortableGit\cmd\git.exe" (
    set "GIT=%CD%\PortableGit\cmd\git.exe"
    set "PATH=%CD%\PortableGit\cmd;%PATH%"
) else (
    git --version >nul 2>&1
    if %ERRORLEVEL% == 0 (
        set GIT=git
    ) else (
        REM Git不可用，跳过版本检查
        goto :skip_version_check
    )
)

REM 快速检查版本（不停顿）
if exist "packaging\VERSION" (
    set /p CURRENT_VERSION=<packaging\VERSION
) else (
    set CURRENT_VERSION=unknown
)

REM 静默检查远程版本
%GIT% fetch origin >nul 2>&1
%GIT% show origin/main:packaging/VERSION > tmp_version.txt 2>nul
if exist "tmp_version.txt" (
    set /p REMOTE_VERSION=<tmp_version.txt
    del tmp_version.txt
) else (
    set REMOTE_VERSION=unknown
)

REM 显示版本信息（不停顿）
echo.
echo ========================================
echo 漫画翻译器 - 启动中
echo ========================================
echo 当前版本: !CURRENT_VERSION!

if not "!REMOTE_VERSION!"=="unknown" (
    if not "!CURRENT_VERSION!"=="!REMOTE_VERSION!" (
        echo 远程版本: !REMOTE_VERSION!
        echo.
        echo [提示] 发现新版本可用！
        echo 请运行 步骤4-更新维护.bat 进行更新
        echo.
    )
)

:skip_version_check
REM 切换到项目根目录
cd /d "%~dp0"

REM 启动 Qt 界面
echo 正在启动...
echo ========================================
echo.
python "%CD%\desktop_qt_ui\main.py"
pause
