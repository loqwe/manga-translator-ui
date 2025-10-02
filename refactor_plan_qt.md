# Manga Translator UI 重构计划 (最终修正版)

**目标**: 将现有基于 `customtkinter` 的 `desktop-ui` 重构为一个基于 `PyQt` 的、现代化的、可维护的桌面应用程序。新架构将结合 `feature_and_refactoring_guide.md` 的分析与 `BallonsTranslator-dev` 的优秀实践，实现清晰的关注点分离 (MVC/服务导向)、模块化和高性能渲染。

---

## 1. 新项目目录结构 (思维导图形式)

```
manga-image-translator/  (项目根目录)
├── manga_translator/      (后端核心, 完全保留)
│
└── desktop_qt_ui/         (这是我们将要创建的【新UI】目录，它将完全取代旧的 desktop-ui/)
    ├── main.py
    ├── main_window.py
    ├── app_logic.py
    ├── editor_view.py
    ├── widgets/
    │   ├── property_panel.py
    │   ├── file_list_view.py
    │   ├── collapsible_frame.py
    │   └── toast_notification.py
    ├── editor/
    │   ├── editor_controller.py
    │   ├── editor_model.py
    │   ├── graphics_view.py
    │   ├── graphics_items.py
    │   └── geometry_utils.py
    ├── core/
    │   └── utils.py
    ├── services/              (旧 desktop-ui/services/ 的重构版本，现在是新UI的一部分)
    │   ├── __init__.py
    │   ├── async_service.py
    │   ├── config_service.py
    │   ├── history_service.py
    │   ├── file_service.py
    │   ├── font_monitor_service.py
    │   ├── export_service.py
    │   ├── transform_service.py
    │   ├── i18n_service.py
    │   ├── log_service.py
    │   ├── ocr_service.py
    │   ├── render_parameter_service.py
    │   └── state_manager.py
    ├── modules/               (BallonsTranslator-dev 借鉴的模块化结构，现在是新UI的一部分)
    │   ├── __init__.py
    │   ├── base_module.py
    │   ├── ocr/
    │   │   └── ocr_some_impl.py
    │   ├── inpainting/
    │   │   └── inpaint_lama.py
    │   └── translation/
    │       └── trans_gemini.py
    ├── resources/
    │   ├── icons/
    │   └── themes/
    └── locales/
        ├── en_US.json
        └── zh_CN.json
```

---

## 2. 新旧文件映射关系导图 (详尽版)

### ├─ 新架构文件及其来源
│
├─ **`main.py`** (应用入口)
│  └─ **[取代]** `desktop-ui/main.py`
│     └─ **[借鉴]** `BallonsTranslator-dev/launch.py`
│        └─ **说明**: 作为唯一的Qt应用入口。根据`guide.md`的建议，废弃旧的worker模式。借鉴`launch.py`实现环境依赖检查、DPI设置、参数解析和优雅的`QApplication`启动流程。
│
├─ **`main_window.py`** (主窗口)
│  ├─ **[取代]** `desktop-ui/app.py`
│  └─ **[吸收]** `desktop-ui/components/editor_toolbar.py`
│     └─ **说明**: 作为`QMainWindow`，承载所有视图和核心UI元素（菜单栏、工具栏）。旧`app.py`的UI控制逻辑和`editor_toolbar.py`的UI定义被此类吸收，用`QAction`和`QToolBar`以更现代的方式重写。
│
├─ **`app_logic.py`** (主逻辑控制器)
│  └─ **[迁移]** `desktop-ui/app_logic.py`
│     └─ **说明**: `guide.md`认可其优秀的服务协调设计。核心逻辑保留，但通信机制从回调改为Qt信号与槽。它将直接调用您项目根目录中完善的`services/`。
│
├─ **`editor_view.py`** (编辑器视图)
│  └─ **[取代]** `desktop-ui/editor_frame.py` (仅UI布局部分)
│     └─ **说明**: 作为`QWidget`，使用`QSplitter`创建三栏布局（属性、画布、文件列表），只负责UI的“壳”，不含任何逻辑。
│
├─ **`widgets/property_panel.py`** (属性面板)
│  └─ **[取代]** `desktop-ui/components/property_panel.py`
│     └─ **说明**: 使用`QWidget`和Qt表单控件重写。所有事件（如文本修改）都通过信号发送给`editor_controller.py`，不再直接调用服务或执行逻辑。
│
├─ **`widgets/file_list_view.py`** (文件列表)
│  └─ **[取代]** `desktop-ui/components/file_list_frame.py`
│     └─ **说明**: 使用`QListWidget`和自定义的`QWidget`作为列表项重写，通过信号与`app_logic.py`通信来加载/卸载文件。
│
├─ **`widgets/collapsible_frame.py`** (可折叠框)
│  └─ **[取代]** `desktop-ui/ui_components.py` (CollapsibleFrame类)
│     └─ **说明**: `guide.md`中分析的通用组件，使用`QToolButton`和`QFrame`在Qt中重新实现，并可通过`QPropertyAnimation`增加动画效果。
│
├─ **`widgets/toast_notification.py`** (Toast通知)
│  └─ **[取代]** `desktop-ui/ui_components.py` (show_toast函数)
│     └─ **说明**: `guide.md`中分析的通用功能，使用`QLabel`和`QTimer`重新实现为一个非阻塞的、可复用的通知组件。
│
├─ **`editor/editor_controller.py`** (编辑器控制器)
│  ├─ **[吸收]** `desktop-ui/editor_frame.py` (全部业务逻辑)
│  └─ **[吸收]** `desktop-ui/components/ocr_translation_manager.py`
│     └─ **说明**: 新架构的**核心**。`guide.md`中分析的`editor_frame.py`这个“上帝对象”的所有业务逻辑（状态管理、事件处理、服务调用）被全部剥离并迁移至此。它作为MVC中的“C”，负责响应UI信号、调用服务、更新模型。
│
├─ **`editor/editor_model.py`** (编辑器模型)
│  └─ **[吸收]** `desktop-ui/editor_frame.py` (全部状态变量)
│     └─ **说明**: 负责封装编辑器所有数据（图片、区域、蒙版等）。`editor_frame.py`中超过20个的状态变量被移入此类。通过`QObject`的信号机制通知视图更新。
│
├─ **`editor/graphics_view.py`** (画布视图)
│  ├─ **[取代]** `desktop-ui/canvas_frame_new.py`
│  └─ **[吸收]** `desktop-ui/components/mouse_event_handler_new.py`
│     └─ **说明**: `QGraphicsView`的子类，负责画布的交互。缩放、平移等交互在此处理。取代了旧的`CanvasFrame`和独立的鼠标处理器。
│
├─ **`editor/graphics_items.py`** (画布图形项)
│  ├─ **[吸收]** `desktop-ui/components/canvas_renderer_new.py`
│  ├─ **[吸收]** `desktop-ui/components/text_renderer_backend.py`
│  └─ **[吸收]** `desktop-ui/components/text_renderer_modified.py`
│     └─ **说明**: 定义`RegionTextItem`等`QGraphicsItem`子类。旧的多个渲染器的功能被统一到`RegionTextItem`的`paint()`方法中，实现WYSIWYG渲染，性能和管理性远超从前。
│
├─ **`editor/geometry_utils.py`** (几何工具)
│  ├─ **[迁移]** `desktop-ui/editing_logic.py`
│  └─ **[迁移]** `desktop-ui/core/stable_geometry_engine.py`
│     └─ **说明**: `guide.md`高度评价的、纯粹的、与UI无关的几何计算逻辑被完整迁移到此，供`editor_controller.py`调用。
│
└─ **`core/utils.py`** (通用工具)
   └─ **[迁移]** `desktop-ui/utils/json_encoder.py`
      └─ **说明**: `CustomJSONEncoder`等与项目逻辑无关的通用工具函数被迁移至此。

### ├─ 新架构中被重构并包含在 `desktop_qt_ui/services/` 目录下的旧文件
│
├─ **`services/async_service.py`**
│  └─ **[重构]** `desktop-ui/services/async_service.py`
│     └─ **说明**: `guide.md`分析其设计优秀，核心逻辑保留。但其线程模型可考虑替换为Qt的`QThreadPool`或`QThread`以更好地集成。
│
├─ **`services/config_service.py`**
│  └─ **[重构]** `desktop-ui/services/config_service.py`
│     └─ **说明**: `guide.md`分析其设计优秀，核心逻辑保留。可考虑将回调机制替换为Qt信号与槽。
│
├─ **`services/history_service.py`**
│  └─ **[重构]** `desktop-ui/services/editor_history.py`
│     └─ **说明**: `guide.md`分析其设计优秀，核心逻辑保留。可重命名以更符合服务命名规范。
│
├─ **`services/file_service.py`**
│  └─ **[重构]** `desktop-ui/services/file_service.py`
│     └─ **说明**: `guide.md`分析其设计优秀，核心逻辑保留。
│
├─ **`services/font_monitor_service.py`**
│  └─ **[重构]** `desktop-ui/services/font_monitor_service.py`
│     └─ **说明**: `guide.md`分析其设计优秀，核心逻辑保留。可考虑使用`watchdog`库增强，并替换回调为Qt信号与槽。
│
├─ **`services/export_service.py`**
│  └─ **[重构]** `desktop-ui/services/export_service.py`
│     └─ **说明**: `guide.md`分析其设计优秀，核心逻辑保留。需移除其Tkinter UI耦合部分，并替换线程模型为`AsyncService`。
│
├─ **`services/transform_service.py`**
│  └─ **[重构]** `desktop-ui/services/transform_service.py`
│     └─ **说明**: `guide.md`分析其设计优秀，核心逻辑保留。可考虑与`QGraphicsView`的变换系统结合。
│
├─ **`services/i18n_service.py`**
│  └─ **[重构]** `desktop-ui/services/i18n_service.py`
│     └─ **说明**: `guide.md`分析其设计优秀，核心逻辑保留。可考虑增加`language_changed`信号。
│
├─ **`services/log_service.py`**
│  └─ **[重构]** `desktop-ui/services/log_service.py`
│     └─ **说明**: `guide.md`分析其设计优秀，核心逻辑保留。
│
├─ **`services/ocr_service.py`**
│  └─ **[重构]** `desktop-ui/services/ocr_service.py`
│     └─ **说明**: `guide.md`分析其设计优秀，核心逻辑保留。可考虑增加模型预加载逻辑。
│
├─ **`services/render_parameter_service.py`**
│  └─ **[重构]** `desktop-ui/services/render_parameter_service.py`
│     └─ **说明**: `guide.md`分析其设计优秀，核心逻辑保留。
│
├─ **`services/state_manager.py`**
│  └─ **[重构]** `desktop-ui/services/state_manager.py`
│     └─ **说明**: `guide.md`分析其设计优秀，核心逻辑保留。可考虑增加Qt信号与槽集成。
│
├─ **`services/error_handler.py`**
│  └─ **[重构]** `desktop-ui/services/error_handler.py`
│     └─ **说明**: `guide.md`分析其设计优秀，核心逻辑保留。建议重命名为`validation_service.py`。
│
├─ **`services/lightweight_inpainter.py`**
│  └─ **[重构]** `desktop-ui/services/lightweight_inpainter.py`
│     └─ **说明**: `guide.md`分析其设计优秀，核心逻辑保留。可考虑替换`ThreadPoolExecutor`为`AsyncService`。
│
└─ **`services/translation_service.py`**
   └─ **[重构]** `desktop-ui/services/translation_service.py`
      └─ **说明**: `guide.md`分析其设计优秀，核心逻辑保留。

### ├─ 新架构中被废弃的旧文件 (功能由Qt原生实现或被更好设计取代)
│
├─ **[废弃]** `desktop-ui/translation_worker.py`
│  └─ **原因**: `guide.md`中已指出，重量级的子进程模型将被主进程内的`QThread`或`AsyncService`取代，通信更高效、稳定。
│
├─ **[废弃]** `desktop-ui/services/drag_drop_service.py`
│  └─ **原因**: `guide.md`分析正确，Qt的`QMainWindow`和`QWidget`原生支持拖放事件(`dragEnterEvent`, `dropEvent`)，不再需要独立的服务。
│
├─ **[废弃]** `desktop-ui/services/shortcut_manager.py`
│  └─ **原因**: `guide.md`分析正确，Qt的`QAction`系统提供了更强大、更统一的快捷键管理方案，可同时用于菜单栏和工具栏，不再需要独立的服务。
│
├─ **[废弃]** `desktop-ui/services/progress_manager.py`
│  └─ **原因**: `guide.md`分析正确，Qt原生的`QProgressDialog`与信号槽机制结合，可以更简单、更安全地实现进度显示，不再需要过度设计的独立管理器。
│
├─ **[废弃]** `desktop-ui/services/performance_optimizer.py`
│  └─ **原因**: `guide.md`分析正确，其功能应被拆分。图片缓存和加载逻辑可并入一个`ImageService`，而UI更新的节流/防抖由Qt的`QTimer`等原生机制实现更佳。
│
├─ **[废弃]** `desktop-ui/services/json_preprocessor_service.py`
│  └─ **原因**: `guide.md`分析指出其功能是为旧渲染管线打的补丁，且是破坏性操作。新架构中应通过改造`export_service`在内存中处理，或优化渲染管线来彻底消除此需求。
│
├─ **[废弃]** `desktop-ui/services/workflow_service.py`
│  └─ **原因**: `guide.md`分析指出其功能混乱且与`json_preprocessor_service`重叠。其有用的模板导入/导出功能应被剥离到一个独立的`TemplateService`中。
│
├─ **[废弃]** `desktop-ui/services/mask_erase_preview_service.py`
│  └─ **原因**: `guide.md`分析正确，这是对`lightweight_inpainter`不必要的过度封装，直接使用`lightweight_inpainter`即可。
│
├─ **[废弃]** `desktop-ui/components/file_manager.py`
│  └─ **原因**: 这是一个简单的文件配对逻辑，`guide.md`分析`editor_frame.py`时已指出其复杂性。在新架构中，此逻辑应被`app_logic.py`或`editor_controller.py`中的一个简单方法取代，无需独立成类。
│
├─ **[废弃]** `desktop-ui/components/progress_dialog.py`
│  └─ **原因**: 功能被Qt原生的`QProgressDialog`完全覆盖。
│
├─ **[废弃]** `desktop-ui/components/context_menu.py`
│  └─ **原因**: 功能被`QMenu`和`QWidget`的`contextMenuEvent`事件处理器取代，实现更简单、更内聚。
│
├─ **[废弃]** `desktop-ui/components/mask_editor.py` & `mask_editor_toolbar.py`
│  └─ **原因**: 独立的蒙版编辑窗口将使用`QDialog`和`QGraphicsView`重新实现，逻辑更清晰。
│
├─ **[废弃]** `desktop-ui/components/ocr_result_dialog.py`
│  └─ **原因**: 将使用标准的`QDialog`重新实现，通过`.exec()`和getter方法返回值，而不是回调。
│
└─ **[其他文件]**
   ├─ `desktop-ui/prompts.json` -> **[保留]** (若仍需，可作为资源文件)
   ├─ `desktop-ui/README.md` -> **[废弃]** (需要为新UI重写)
   ├─ `desktop-ui/translations_cn.json` -> **[迁移]** (可迁移至 `locales/` 目录)
   ├─ `desktop-ui/updater.py` -> **[借鉴]** (更新逻辑可借鉴`BallonsTranslator-dev/launch.py`中的git更新检查，集成到新`main.py`中)
   └─ `desktop-ui/core/test_anti_jump.py` -> **[保留为开发者工具]** (不进入新UI代码库)