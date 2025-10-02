import ast
import sys

try:
    with open('desktop_qt_ui/editor/desktop_ui_geometry.py', encoding='utf-8') as f:
        ast.parse(f.read())
    print('Syntax OK')
except Exception as e:
    print('Syntax Error:', e)
    sys.exit(1)