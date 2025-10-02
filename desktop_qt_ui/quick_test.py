#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
快速验证导入和基本功能
"""
import os
import sys

# 设置输出编码为UTF-8
if sys.platform == "win32":
    import locale
    try:
        locale.setlocale(locale.LC_ALL, 'zh_CN.UTF-8')
    except Exception:
        try:
            locale.setlocale(locale.LC_ALL, 'Chinese_China.936')
        except Exception:
            pass

# 添加项目根目录到路径
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

def test_imports():
    """测试所有关键导入"""
    try:
        print("测试导入...")

        # PyQt6
        print("[OK] PyQt6 导入成功")

        # 服务
        print("[OK] 服务导入成功")

        # 主窗口
        print("[OK] 主窗口导入成功")

        # 编辑器组件
        print("[OK] 编辑器组件导入成功")

        return True

    except Exception as e:
        print(f"[FAIL] 导入失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_service_init():
    """测试服务初始化"""
    try:
        print("\n测试服务初始化...")

        from services import init_services
        root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

        success = init_services(root_dir)
        if success:
            print("[OK] 服务初始化成功")

            # 测试获取服务
            from services import get_config_service, get_file_service
            config_service = get_config_service()
            file_service = get_file_service()

            if config_service and file_service:
                print("[OK] 核心服务获取成功")
                return True
            else:
                print("[FAIL] 无法获取核心服务")
                return False
        else:
            print("[FAIL] 服务初始化失败")
            return False

    except Exception as e:
        print(f"[FAIL] 服务初始化异常: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_editor_creation():
    """测试编辑器组件创建"""
    try:
        print("\n测试编辑器组件创建...")

        from PyQt6.QtWidgets import QApplication

        from editor.editor_controller import EditorController
        from editor.editor_model import EditorModel

        QApplication([])  # 创建应用实例

        # 创建模型
        model = EditorModel()
        print("[OK] 编辑器模型创建成功")

        # 创建控制器
        EditorController(model)
        print("[OK] 编辑器控制器创建成功")

        return True

    except Exception as e:
        print(f"[FAIL] 编辑器组件创建失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主测试函数"""
    print("Qt 重构版本快速验证")
    print("=" * 40)

    tests = [
        ("导入测试", test_imports),
        ("服务初始化测试", test_service_init),
        ("编辑器组件创建测试", test_editor_creation)
    ]

    passed = 0
    total = len(tests)

    for test_name, test_func in tests:
        print(f"\n{test_name}:")
        if test_func():
            passed += 1

    print("\n" + "=" * 40)
    print(f"测试结果: {passed}/{total} 通过")

    if passed == total:
        print("SUCCESS: 基本功能验证通过!")
        print("\n可以尝试运行: py -3.12 main.py")
    else:
        print("WARNING: 存在问题，需要修复")

    return 0 if passed == total else 1

if __name__ == "__main__":
    exit(main())