#!/usr/bin/env python3
"""
测试编辑器功能的简单脚本
"""
import os
import sys

# 添加项目根目录到路径
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import logging

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from main_window import MainWindow
from services import init_services


def test_basic_startup():
    """测试基本启动功能"""
    print("✓ 测试基本启动...")

    # 创建应用
    app = QApplication(sys.argv)

    # 初始化服务
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    if not init_services(root_dir):
        print("✗ 服务初始化失败")
        return False

    # 创建主窗口
    main_window = MainWindow()
    main_window.show()

    print("✓ 主窗口显示成功")

    # 自动关闭窗口
    QTimer.singleShot(2000, app.quit)  # 2秒后关闭

    # 运行事件循环
    try:
        app.exec()
        print("✓ 应用正常退出")
        return True
    except Exception as e:
        print(f"✗ 应用运行出错: {e}")
        return False

def test_image_loading():
    """测试图片加载功能"""
    print("✓ 测试图片加载...")

    # 查找测试图片
    test_image_paths = [
        "D:/xiazai/图片整理(ImageAssistant)_批量图片助手/夜莺领主/01.png",
        "C:/Users/Public/Pictures/Sample Pictures/sample.jpg",
        "../examples/test.png"
    ]

    test_image = None
    for path in test_image_paths:
        if os.path.exists(path):
            test_image = path
            break

    if not test_image:
        print("✗ 找不到测试图片")
        return False

    print(f"✓ 找到测试图片: {test_image}")

    # 创建应用
    app = QApplication(sys.argv)

    # 初始化服务
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    init_services(root_dir)

    # 创建主窗口
    main_window = MainWindow()
    main_window.show()

    # 切换到编辑器视图
    main_window.stacked_widget.setCurrentWidget(main_window.editor_view)

    # 加载图片
    try:
        main_window.editor_controller.load_image_and_regions(test_image)
        print("✓ 图片加载成功")

        # 延迟退出以观察结果
        QTimer.singleShot(3000, app.quit)
        app.exec()
        return True

    except Exception as e:
        print(f"✗ 图片加载失败: {e}")
        return False

def main():
    """主测试函数"""
    print("开始测试 Qt 重构版本的编辑器...")
    print("=" * 50)

    # 设置日志级别
    logging.basicConfig(level=logging.INFO)

    tests = [
        ("基本启动测试", test_basic_startup),
        ("图片加载测试", test_image_loading),
    ]

    passed = 0
    total = len(tests)

    for test_name, test_func in tests:
        print(f"\n{test_name}:")
        try:
            if test_func():
                passed += 1
                print(f"✓ {test_name} - 通过")
            else:
                print(f"✗ {test_name} - 失败")
        except Exception as e:
            print(f"✗ {test_name} - 异常: {e}")

    print("\n" + "=" * 50)
    print(f"测试结果: {passed}/{total} 通过")

    if passed == total:
        print("🎉 所有测试通过！编辑器基本功能正常。")
        return 0
    else:
        print("⚠️  部分测试失败，需要进一步调试。")
        return 1

if __name__ == "__main__":
    sys.exit(main())