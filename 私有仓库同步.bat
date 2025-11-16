@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

:: 设置颜色代码（Windows 10+支持ANSI转义）
set "ESC="
set "CYAN=%ESC%[36m"
set "GREEN=%ESC%[32m"
set "YELLOW=%ESC%[33m"
set "RED=%ESC%[31m"
set "RESET=%ESC%[0m"

:: 设置脚本路径
set "SCRIPT_DIR=%~dp0"
set "PS_SCRIPT=%SCRIPT_DIR%私有仓库同步.ps1"

:: 显示标题
echo ========================================
echo 私有仓库同步工具
echo ========================================
echo.
echo 分支说明:
echo   don - 流水线功能（新四线流水线：删除分段+修复并发）
echo   my-custom-features - UI功能（漫画管理面板+CBZ工具等）
echo   qwe - 长图拼接功能（智能拼接+翻译count mismatch修复）
echo.
echo 使用说明:
echo   1. 直接运行 - 交互式选择分支和操作
echo   2. 快捷参数 - 私有仓库同步.bat [分支] [操作]
echo      示例: 私有仓库同步.bat don pull
echo            私有仓库同步.bat qwe push
echo ========================================
echo.

:: 检查PowerShell脚本是否存在
if not exist "%PS_SCRIPT%" (
    echo [错误] 找不到PowerShell脚本: 私有仓库同步.ps1
    echo [路径] %PS_SCRIPT%
    echo.
    echo 请确保以下文件在同一目录:
    echo   - 私有仓库同步.bat
    echo   - 私有仓库同步.ps1
    pause
    exit /b 1
)

:: 检查是否在Git仓库中
if not exist "%SCRIPT_DIR%.git" (
    echo [警告] 当前目录似乎不是Git仓库
    echo [位置] %SCRIPT_DIR%
    echo.
    choice /C YN /M "是否继续运行"
    if errorlevel 2 exit /b 0
    echo.
)

:: 构建PowerShell命令参数
set "PS_ARGS="
if not "%~1"=="" (
    set "PS_ARGS=-Branch %~1"
)
if not "%~2"=="" (
    set "PS_ARGS=!PS_ARGS! -Action %~2"
)

:: 启动PowerShell脚本
echo 启动PowerShell同步脚本...
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%PS_SCRIPT%" !PS_ARGS!

:: 检查执行结果
if errorlevel 1 (
    echo.
    echo [错误] 脚本执行失败，错误码: %errorlevel%
    pause
    exit /b %errorlevel%
)

:: 成功时不暂停（除非使用 PAUSE_ON_SUCCESS 环境变量）
if defined PAUSE_ON_SUCCESS (
    pause
)
