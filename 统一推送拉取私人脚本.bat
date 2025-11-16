@echo off
echo ========================================
echo 统一推送拉取私人脚本
echo ========================================
echo.
echo 请选择操作：
echo   1. 推送 (Push) - 将本地分支推送到远程仓库
echo   2. 拉取 (Pull) - 从远程仓库拉取分支更新
echo.
set /p choice=请输入选项 (1/2):

if "%choice%"=="1" (
    echo.
    echo 正在执行推送操作...
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0统一推送拉取私人脚本.ps1" -Action push
) else if "%choice%"=="2" (
    echo.
    echo 正在执行拉取操作...
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0统一推送拉取私人脚本.ps1" -Action pull
) else (
    echo.
    echo [错误] 无效的选项！
    pause
    exit /b 1
)

if errorlevel 1 (
    echo.
    echo [错误] 脚本执行失败！
    pause
    exit /b 1
) else (
    echo.
    echo [成功] 操作完成！
)

echo.
echo 按任意键退出...
pause >nul

