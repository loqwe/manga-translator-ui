import subprocess
import sys
import os
import shutil
import argparse
from pathlib import Path

# 全局配置
EXE_NAME = "main.exe"  # 如果你的可执行文件不叫 main.exe，请修改这里
APP_NAME = "MangaTranslatorUI"

def run_command_realtime(cmd, cwd=None):
    """实时执行一个 shell 命令并打印输出。"""
    use_shell = isinstance(cmd, str)
    print(f"\nExecuting: {cmd}")
    try:
        process = subprocess.Popen(
            cmd,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            errors='replace',
            shell=use_shell
        )
        while True:
            output = process.stdout.readline()
            if output == '' and process.poll() is not None:
                break
            if output:
                print(output.strip())
        
        returncode = process.poll()
        print(f"Exit code: {returncode}")
        return returncode == 0
    except Exception as e:
        print(f"Error executing command: {e}")
        return False

class Builder:
    """封装了构建和打包逻辑的类"""

    def __init__(self, app_version):
        self.app_version = app_version
        self.version_file = Path("VERSION")

    def build_executables(self, version_type):
        """使用 PyInstaller 构建指定版本 (cpu 或 gpu)"""
        print("=" * 60)
        print(f"Building {version_type.upper()} Executable")
        print("=" * 60)

        venv_path = Path(f".venv_{version_type}")
        req_file = f"requirements_{version_type}.txt"
        spec_file = f"manga-translator-{version_type}.spec"

        if not venv_path.exists() or not Path(spec_file).exists():
            print(f"Error: Environment for {version_type} not found. Please set it up first.")
            return False

        python_exe = venv_path / 'Scripts' / 'python.exe' if sys.platform == 'win32' else venv_path / 'bin' / 'python'
        
        # 安装所有依赖
        print(f"Installing dependencies for {version_type.upper()} from {req_file}...")
        cmd_install = [str(python_exe), '-m', 'pip', 'install', '-r', req_file]
        if not run_command_realtime(cmd_install):
            print(f"Dependency installation failed for {version_type.upper()}.")
            return False

        # 运行 PyInstaller
        print(f"Running PyInstaller for {version_type.upper()}...")
        cmd_pyinstaller = [str(python_exe), "-m", "PyInstaller", spec_file]
        if not run_command_realtime(cmd_pyinstaller):
            print(f"PyInstaller build failed for {version_type.upper()}.")
            return False
        
        print(f"{version_type.upper()} build completed!")
        return True

    def package_updates(self, version_type):
        """为指定版本创建 tufup 更新包"""
        print("=" * 60)
        print(f"Creating tufup update package for {version_type.upper()}")
        print("=" * 60)

        venv_path = Path(f".venv_{version_type}")
        tufup_exe = venv_path / 'Scripts' / 'tufup.exe' if sys.platform == 'win32' else venv_path / 'bin' / 'tufup'

        self.version_file.write_text(self.app_version, encoding='utf-8')

        dist_dir = Path("dist") / f"manga-translator-{version_type}"
        exe_path = dist_dir / EXE_NAME

        if not exe_path.exists():
            print(f"\nError: Executable not found at '{exe_path}'")
            return False

        cmd_add = [str(tufup_exe), 'targets', 'add', str(dist_dir), self.app_version, '--app-path', str(exe_path)]
        if not run_command_realtime(cmd_add): return False
        
        cmd_release = [str(tufup_exe), 'release']
        if not run_command_realtime(cmd_release): return False
            
        print(f"Successfully created update package for {version_type.upper()} {self.app_version}.")
        return True

def main():
    parser = argparse.ArgumentParser(description="Manga Translator UI Builder and Updater")
    parser.add_argument("version", help="The application version to build (e.g., 1.4.0)")
    parser.add_argument("--build", choices=['cpu', 'gpu', 'both'], default='both', help="Which version(s) to build.")
    parser.add_argument("--skip-build", action='store_true', help="Skip building executables.")
    parser.add_argument("--skip-updates", action='store_true', help="Skip creating update packages.")
    args = parser.parse_args()

    print(f"--- Starting process for version {args.version} ---")
    builder = Builder(args.version)

    versions_to_process = []
    if args.build in ['cpu', 'both']:
        versions_to_process.append('cpu')
    if args.build in ['gpu', 'both']:
        versions_to_process.append('gpu')

    for v_type in versions_to_process:
        if not args.skip_build:
            if not builder.build_executables(v_type):
                print(f"\nFATAL: Build failed for {v_type.upper()}. Halting.")
                sys.exit(1)
        
        if not args.skip_updates:
            if not builder.package_updates(v_type):
                print(f"\nFATAL: Update packaging failed for {v_type.upper()}. Halting.")
                sys.exit(1)

    print("\n" + "=" * 60)
    print("ALL TASKS COMPLETED SUCCESSFULLY!")
    print("=" * 60)
    if not args.skip_updates:
        print("Next steps:")
        print("1. Commit and push the 'update_repository/' directory to your git repository.")
        print("2. Create a new release on GitHub with the tag matching your version.")
        print("3. Upload the application bundles from the 'dist/' directory as release assets.")

if __name__ == "__main__":
    main()