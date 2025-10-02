# `desktop-ui` 逐文件功能审计与重构方案

**版本: 3.0 (实时增量更新版)**

本指南将严格遵循逐一文件分析、实时追加的模式，详尽记录 `desktop-ui` 目录下每个文件的功能细节、组件关联及最终的重构处置方案。

---

### 文件: `desktop-ui/app_logic.py`

- **目的**: 作为应用的“大脑”，一个与UI完全分离的业务逻辑控制器，负责协调各个服务来完成核心任务。

- **功能细节与组件关联**:
  - **初始化 (`__init__`)**: 
    - 创建并持有一个日志记录器 (`logger`)。
    - 获取所有核心服务的单例，包括 `ConfigService`, `TranslationService`, `FileService`, `StateManager`, `ProgressManager`。
    - 这种服务化的设计将不同功能（如配置、翻译、文件操作）的实现细节完全封装在各自的服务中。
  - **UI通信 (`register_ui_callback`, `notify_ui`)**:
    - 实现了一个简单的回调系统，允许UI层（`app.py`）注册一个回调函数（如 `on_task_completed`）。
    - 当 `app_logic.py` 中有事件发生时（如任务完成），它会通过 `notify_ui` 调用这个回调，从而将信息传递给UI层进行显示。这是实现UI与逻辑解耦的关键机制。
  - **配置管理 (`load_config_file`, `save_config_file`, `update_config`)**:
    - **功能**: 提供加载、保存和更新JSON配置文件的接口。
    - **关联**: 这些方法由UI层的菜单项（如“加载配置”）触发。当配置加载或更新后，它会：
      1. 调用 `config_service` 来执行实际的文件读写。
      2. 调用 `state_manager` 来更新全局的当前配置状态 (`CURRENT_CONFIG`)。
      3. 通过 `notify_ui('config_loaded', ...)` 通知UI层更新显示，例如更新属性面板中的设置值。
  - **文件管理 (`add_files`, `clear_file_list`)**:
    - **功能**: 添加新文件到任务列表或清空列表。
    - **关联**: 由UI层的文件拖放或“添加文件”按钮触发。它会调用 `file_service` 过滤有效图片，然后更新 `state_manager` 中的 `CURRENT_FILES` 状态，UI层监听到这个状态变化后会刷新文件列表。
  - **核心任务 (`start_backend_task`, `_run_backend_task_async`, `_handle_task_results`)**:
    - **功能**: 这是应用最核心的工作流，负责启动、执行和处理翻译/修图任务。
    - **`_build_backend_args`**: 一个非常关键的内部函数。它会读取 `config_service` 中的UI设置（如复选框“加载文本”），并将其动态转换为 `manga_translator` 后端库所需的命令行参数（如 `--load-text`）。这决定了后端任务的具体行为模式。
    - **`start_backend_task`**: 当UI的“开始”按钮被点击时调用。它进行一系列检查（文件列表是否为空、配置是否存在），然后创建一个新的独立线程 (`threading.Thread`) 去执行 `_run_backend_task_async`，从而避免阻塞UI主线程。
    - **`_run_backend_task_async`**: 在这个新线程中，它会创建一个全新的 `asyncio` 事件循环，并在这个循环里 `await` `translation_service.translate_batch_async` 的完成。这实现了多线程+异步的非阻塞执行模型。
    - **`_handle_task_results`**: 任务完成后，此函数被调用来处理结果。它会更新 `state_manager` 中的状态（如 `IS_TRANSLATING` -> `False`），并调用 `notify_ui('task_completed', ...)` 将成功/失败信息返回给UI层显示。
  - **应用生命周期 (`initialize`, `shutdown`)**:
    - **功能**: 处理应用的启动和关闭逻辑。
    - **`initialize`**: 在应用启动时被调用，负责加载默认配置，并设置 `state_manager` 中的 `APP_READY` 状态。
    - **`shutdown`**: 在应用关闭时被调用，确保正在进行的任务被停止，并清理服务资源。

- **重构处置**: **核心修改**

- **理由**: `app_logic.py` 的服务协调和非阻塞任务管理的设计思想非常优秀，应当保留。但在新架构中，需要进行以下适配：
  1. **通信机制**: 废弃 `register_ui_callback` 系统，改为通过Qt的**信号(Signal)和槽(Slot)**机制与新的Qt主窗口进行双向通信，这是Qt生态中最标准、最强大的方式。
  2. **服务调用**: 不再调用 `TranslationService`。而是改为初始化并调用从 `BallonsTranslator-dev` 迁移过来的、功能更全面的 `ModuleManager`。`_build_backend_args` 的逻辑也将被取代，变为直接设置 `ModuleManager` 实例的内部参数。
  3. **线程模型**: `threading.Thread` + `asyncio` 的模型可以工作，但为了与Qt更好地集成，推荐将其替换为 `BallonsTranslator-dev` 中使用的 `QThread` 模型。任务的启动、进度汇报和结束都通过信号/槽来完成，代码会更简洁、更安全。

---

### 文件: `desktop-ui/app.py` (超详细重写)

- **目的**: 此文件是 `desktop-ui` 的UI层事实上的总控制器。它负责创建应用主窗口、动态构建所有设置界面、响应用户的几乎所有交互（按钮点击、文件选择），并启动和监控翻译子进程。它是一个混合了视图（View）和控制器（Controller）职责的庞大文件。

- **功能细节与组件关联**:

  - **`App` 类**:
    - **`__init__`**: 作为 `customtkinter.CTk` 的子类，创建了应用的最顶级窗口。它唯一的任务就是实例化 `AppController`，并将自身（`self`）作为父窗口传递给控制器。
    - **`on_close`**: 拦截窗口的关闭按钮事件，并将事件处理完全委托给 `AppController.on_close()` 方法，由控制器来决定是否以及如何关闭应用。

  - **`AppController` 类 (核心)**:
    - **`__init__`**: 
      - **路径与变体**: 初始化应用根目录、`.env` 文件路径，并调用 `_get_app_variant` 通过读取 `build_info.json` 来判断当前是 `cpu` 还是 `gpu` 版本。
      - **服务初始化**: 调用 `services.init_services` 来初始化所有单例服务（如 `ConfigService`）。
      - **UI容器创建**: 调用 `_create_ui_container_sync` 创建一个占满整个窗口的 `CTkFrame` 作为所有视图（主视图、编辑器视图）的容器。
      - **视图延迟创建**: 调用 `app.after(1, ...)` 将 `_create_views` 的执行推迟到下一个事件循环，以确保主窗口能尽快显示出来，提升用户感受到的启动速度。
      - **重量级组件延迟加载**: 调用 `app.after(500, ...)` 进一步延迟加载非核心组件（如快捷键管理器），避免阻塞UI。
    - **`create_main_view_settings_tabbed`**: 
      - **目的**: 动态构建“主翻译视图”中复杂的标签页设置界面。
      - **逻辑**: 
        1. 读取 `config-example.json` 作为UI布局的“模板”。
        2. 获取 `MainView` 中预先创建好的左右滚动框架 (`basic_left_frame`, `advanced_right_frame` 等)。
        3. 遍历JSON配置的各个部分（`translator`, `cli`, `detector` 等）。
        4. 对每个部分的参数，调用 `create_param_widgets` 方法，在该部分对应的UI框架内动态创建控件。
        5. 例如，它会为 `config['detector']` 内的每个键值对，在“高级设置”标签页的左侧框架中创建一个带标签的UI控件。
    - **`create_param_widgets`**: 
      - **目的**: 根据配置数据，创建一个具体的UI控件（如开关、输入框、下拉菜单）。
      - **逻辑**: 
        1. 接收一个键（如 `render.font_size`）和一个值（如 `40`）。
        2. **类型判断**: 通过 `isinstance` 判断值的类型。
        3. **控件创建**: 
           - 如果是 `bool` 类型，创建一个 `ctk.CTkSwitch` (开关)。
           - 如果是 `int` 或 `float`，创建一个 `ctk.CTkEntry` (文本输入框)。
           - 如果是 `str`，会先调用 `get_options_for_key` 检查该键是否有预设的枚举选项。如果有，则创建一个 `ctk.CTkOptionMenu` (下拉菜单)；如果没有，则创建一个 `ctk.CTkEntry`。
        4. **事件绑定**: 为创建的每个控件绑定一个回调函数 `_save_widget_change`。对于文本输入框，使用 `_debounced_save_widget_change` 进行防抖处理，避免用户输入过程中过于频繁地保存文件。
        5. **特殊UI处理**: 
           - 对 `render.font_path`，会额外创建一个“打开目录”按钮。
           - 对 `translator.high_quality_prompt_path`，会绑定一个点击事件，在用户点击下拉菜单时动态扫描 `dict/` 目录下的 `json` 文件来刷新列表。
    - **`_save_widget_change`**: 
      - **目的**: 将UI控件上的值持久化保存到JSON配置文件中。
      - **逻辑**: 
        1. 从UI控件（如 `CTkSwitch`）获取当前值。
        2. **反向映射**: 对某些下拉菜单（如翻译器、目标语言），需要将用户看到的显示名称（如“谷歌翻译”）转换回程序内部使用的标识符（如 `gemini`）。
        3. 读取 `self.current_config_path` 指定的JSON文件到内存。
        4. 根据控件的 `full_key` (如 `render.font_size`)，在内存中的字典里找到对应位置并更新其值。
        5. 将整个更新后的字典写回JSON文件，覆盖原有内容。
        6. 调用 `config_service.set_config` 来同步更新服务层的内存中配置。
    - **`on_translator_change`**: 
      - **目的**: 实现翻译器设置的动态关联。
      - **逻辑**: 当用户在“翻译器”下拉菜单中选择一个新的翻译器时，此函数被触发。它会查询 `translator_env_map` (一个硬编码的字典) 获取新翻译器所需的API密钥（环境变量），然后销毁并重新创建API密钥输入框区域，仅显示当前需要的输入框。
    - **`start_translation` / `_proceed_with_translation` / `_monitor_translation_simple`**: 
      - **目的**: 实现非阻塞的翻译流程（子进程模型）。
      - **逻辑**: 
        1. **`start_translation`**: 用户点击“开始”按钮后，此函数将按钮文本改为“停止”，并将命令指向 `stop_translation`，然后调用 `_proceed_with_translation`。
        2. **`_proceed_with_translation`**: 
           a. 调用 `get_config_from_widgets` 收集UI上所有设置，并连同输入文件列表一起，写入到一个临时的JSON配置文件 (`temp/translation_config.json`)。
           b. 使用 `subprocess.Popen` 启动一个新的Python进程，执行 `main.py --run-as-worker`，并将临时配置文件的路径作为参数。
           c. 启动 `_monitor_translation_simple` 线程来监控这个子进程。
        3. **`_monitor_translation_simple`**: 在一个独立的 `threading.Thread` 中运行，它会循环读取子进程的标准输出流，并将每一行日志通过 `app.after(0, ...)` 调度回UI主线程进行显示，从而实现了日志的实时更新而不会卡住界面。
    - **文件操作 (`add_files`, `add_folder`, `clear_file_list`, `remove_selected_files`)**: 
      - **目的**: 响应UI上文件列表操作按钮的点击事件。
      - **逻辑**: 直接操作 `self.input_files` 这个列表（添加、清空、移除），然后调用 `update_file_list_display` 来刷新 `MainView` 中的 `Listbox` 组件，使其与 `self.input_files` 列表保持同步。

  - **`MainView` 类**:
    - **目的**: 负责“主翻译”界面的静态布局和UI组件的创建。
    - **逻辑**: 在 `__init__` 方法中，它创建了所有的容器性组件，如左侧的源/目标文件区域，右侧的标签页控件 (`CTkTabview`)，以及底部的日志框 (`CTkTextbox`)。它将这些组件的实例存储在 `controller.main_view_widgets` 字典中，以便 `AppController` 能够找到并操作它们（如填充动态控件、更新日志）。

  - **`EditorView` 类**:
    - **目的**: 作为“视觉编辑器”界面的容器。
    - **逻辑**: 它非常简单，只是创建了一个 `EditorFrame` (从 `editor_frame.py` 导入) 的实例，并让其占满整个视图区域。

- **重构处置**: **删除**

- **理由**: 
  1. **完全基于Tkinter**: 整个文件都是为了构建和驱动 CustomTkinter 界面而编写的，无法在Qt框架下复用。
  2. **职责混乱与功能重复**: `AppController` 类承担了过多的职责，它既是UI的创建者，又是事件的响应者，还实现了与 `app_logic.py` 相冲突的另一套“子进程”工作流，这使得架构变得复杂和不清晰。
  3. **新架构中的替代方案**: 
     - `App`, `AppController`, `MainView`, `EditorView` 的所有职责，都将被一个新的 `MainWindow` (继承自 `QMainWindow`) 类所吸收和重新实现。
     - 动态创建UI的功能，可以在新的 `MainWindow` 中通过类似的逻辑实现，但创建的将是Qt组件。
     - 所有事件处理（如按钮点击）将通过信号/槽机制连接到 `MainWindow` 的方法或 `app_logic` 的槽函数。
     - “子进程”工作流将被完全废弃，统一采用 `app_logic.py` 改造后的、基于 `QThread` 的线程模型。

---

### 文件: `desktop-ui/main.py`

- **目的**: 作为整个 `desktop-ui` 应用的命令行入口点，负责准备执行环境，并根据命令行参数决定是启动主UI还是作为后台工作者进程运行。

- **功能细节与组件关联**:
  - **环境初始化**: 
    - **Triton禁用**: 在文件顶部，通过 `os.environ['XFORMERS_FORCE_DISABLE_TRITON'] = '1'` 强制禁用 Triton。这是一个兼容性修复，通常用于解决 `xformers` 库在打包成可执行文件（如使用 PyInstaller）时可能出现的问题。
    - **Windows编码设置**: 使用 `locale.setlocale` 尝试将应用的区域设置设为 `zh_CN.UTF-8` 或备用的 `Chinese_China.936`。这是为了确保在Windows系统上，特别是对于命令行输出和文件路径处理，能正确显示和处理中文字符，避免乱码。
    - **Windows DPI感知**: 使用 `ctypes` 调用 `windll.shcore.SetProcessDpiAwareness(1)`。这是一个关键的Windows API调用，它告诉操作系统该应用自行处理高DPI缩放，可以避免在高分屏上出现界面模糊或布局错乱的问题。
    - **`sys.path` 设置**: 将项目的根目录添加到Python的模块搜索路径中，确保可以正确导入项目内的其他模块（如 `services`, `manga_translator`）。
  - **延迟导入 (`get_app_class`, `get_async_services`)**:
    - **功能**: 这是一种启动性能优化技术。它将重量级模块（如 `app.py` 和 `services/async_service.py`）的 `import` 语句推迟到函数内部。只有当 `main_ui` 函数实际需要这些模块时，`get_app_class()` 才会被调用，从而执行真正的导入操作。
    - **关联**: 这使得应用的初始启动（即显示窗口的那一刻）变得非常快，因为Python解释器在启动时不需要立即加载和解析庞大的UI和逻辑代码。
  - **双模式启动 (`if __name__ == "__main__"`)**:
    - **功能**: 这是整个应用两种工作模式的分发中枢。它检查命令行参数 `sys.argv` 中是否包含 `--run-as-worker` 标志。
    - **UI模式 (`main_ui`)**: 如果**没有**`--run-as-worker`标志，则调用 `main_ui()`。
      - **逻辑**: 
        1. 调用 `get_app_class()` 延迟加载并获取 `App` 类。
        2. 调用 `get_async_services()` 延迟加载异步服务。
        3. 实例化并启动 `App`，进入 `app.mainloop()`，显示用户界面并开始事件循环。
        4. 使用 `try...finally` 确保在应用退出时，能够调用 `shutdown_async_service()` 来安全地关闭后台服务。
    - **工作者模式 (`main_worker`)**: 如果**存在**`--run-as-worker`标志，则调用 `main_worker()`。
      - **逻辑**: 
        1. 从 `translation_worker.py` 导入其 `main` 函数。
        2. **参数调整**: `app.py` 在启动子进程时，命令行参数会是 `[.../main.py, '--run-as-worker', 'path/to/config.json']`。此函数会修改 `sys.argv`，移除 `--run-as-worker` 部分，使得 `sys.argv` 对于 `translation_worker` 来说就像是直接被调用一样，其期望的配置文件路径位于 `sys.argv[1]`。
        3. 调用 `worker_main()`，开始在后台执行实际的翻译任务。
      - **关联**: 这个模式永远不会被用户直接调用，它专门被 `app.py` 中的 `_proceed_with_translation` 方法通过 `subprocess.Popen` 在一个独立的子进程中调用。

- **重构处置**: **核心修改**

- **理由**: 
  1. **入口角色保留**: 它作为程序唯一入口的角色必须保留。
  2. **环境设置可借鉴**: 其中关于编码、DPI、`sys.path` 的设置，对于新的Qt应用同样是必要和有益的，可以借鉴或直接迁移。
  3. **启动模式需简化**: 在新的架构中，我们将废弃“子进程”模型，统一使用 `QThread`。因此，`--run-as-worker` 的判断逻辑和 `main_worker` 函数将**不再需要，应予删除**。
  4. **启动逻辑更新**: `main_ui` 函数需要被重构，不再调用 `get_app_class` 来启动Tkinter应用，而是改为创建 `QApplication` 实例和我们新的 `MainWindow` 实例，并调用 `main_window.show()` 和 `app.exec()`。

---

### 文件: `desktop-ui/components/canvas_renderer_new.py`

- **目的**: 作为画布的渲染引擎，负责将所有视觉元素（背景图、修复图、蒙版、文本）绘制到Tkinter画布上。

- **功能细节与组件关联**:
  - **初始化 (`__init__`)**: 
    - 持有 `canvas` (Tkinter画布) 和 `transform_service` (坐标转换服务) 的引用。
    - 初始化一个 `BackendTextRenderer` 实例，将实际的文本绘制工作委托给它。
    - 初始化多个状态属性，如 `image` (PIL图像对象), `inpainted_image`, `refined_mask` (蒙版)。
    - 初始化性能优化用的缓存字典 `_resized_image_cache`。
  - **图像加载与管理 (`set_image`, `set_inpainted_image`, `set_inpainted_alpha`)**:
    - **功能**: 负责加载和管理画布上显示的各种图像层。
    - **`set_image`**: 接收一个文件路径，使用 `PIL.Image.open` 打开它，然后清除所有旧的图像缓存，并触发一次完整的重绘。
    - **`set_inpainted_image`**: 接收一个 `PIL.Image` 对象作为修复后的图像，并清除旧的修复图缓存。
    - **`set_inpainted_alpha`**: 设置修复图的透明度，用于在UI上与原图进行叠加对比。
  - **蒙版处理 (`set_refined_mask`, `set_removed_mask`, `set_mask_visibility`, `redraw_mask_overlay`)**:
    - **功能**: 管理和显示不同的蒙版（mask）。
    - **`set_refined_mask`**: 接收一个 `numpy` 数组作为蒙版，并调用 `redraw_mask_overlay` 来显示它。
    - **`redraw_mask_overlay`**: 将 `numpy` 格式的蒙版数组转换为带透明度的蓝色或红色 `PIL` 图像，再转为 `ImageTk.PhotoImage`，最后使用 `canvas.create_image` 绘制到画布上，实现蒙版的叠加预览效果。
  - **核心渲染 (`redraw_all`)**: 
    - **功能**: 这是最核心的渲染函数，负责将所有图层按正确顺序绘制出来。
    - **逻辑**: 
      1. **清空画布**: 调用 `self.canvas.delete("all")` 清除所有旧的绘制对象。
      2. **坐标计算**: 从 `transform_service` 获取当前的缩放等级和偏移量，计算出图像在屏幕上应有的大小和位置。
      3. **图像缓存与绘制**: 
         - 为了避免每次缩放都重新计算，它使用 `_resized_image_cache` 字典来缓存已经缩放过的 `ImageTk.PhotoImage` 对象。缓存的键由尺寸和图层类型（如 `main_...`, `inpaint_...`）构成。
         - 如果在缓存中找到匹配项，则直接使用；如果找不到，则使用 `PIL.Image.resize` 进行高质量缩放（`Image.LANCZOS`），创建新的 `ImageTk.PhotoImage`，存入缓存，然后绘制到画布上。
      4. **图层叠加**: 按顺序绘制：主图 -> 修复图（如果透明度大于0） -> 蒙版叠加层。
      5. **文本渲染委托**: 调用 `self.text_renderer.draw_regions` 方法，将文本区域的绘制任务完全交给 `BackendTextRenderer` 处理。
  - **数据预计算 (`recalculate_render_data`)**:
    - **功能**: 一个非常耗时的计算步骤，它为后续的文本渲染做准备。
    - **逻辑**: 
      1. 将UI层传入的 `regions` 字典列表转换为 `manga_translator.utils.TextBlock` 对象列表。
      2. 调用 `manga_translator.rendering.resize_regions_to_font_size` 这个后端函数。
      3. 这个后端函数会根据文本内容、字体大小和原始文本框的位置，计算出翻译后的文本实际应该占据的新的四边形区域（`dst_points`）。
      4. 将计算出的 `TextBlock` 对象和 `dst_points` 缓存起来，供 `redraw_all` 和 `text_renderer` 使用。
  - **预览绘制 (`draw_preview`, `draw_mask_preview`)**:
    - **功能**: 在用户进行拖拽或绘制蒙版时，提供一个轻量级的实时预览。
    - **逻辑**: 直接在Tkinter画布上使用 `create_polygon` 或 `create_line` 绘制简单的几何形状（如青色或蓝色的框线），但不触发重量级的文本渲染，以保证交互的流畅性。

- **重构处置**: **逻辑迁移**

- **理由**: 此文件是Tkinter渲染管线的核心，文件本身应删除。但是，它所体现的渲染逻辑和为保证WYSIWYG而做的努力，必须在新架构中得到“转译”：
  1. **分层绘制思想**: 在新的Qt `QGraphicsScene` 中，不同的图层（背景图、修复图、蒙版、文本）应该被实现为不同Z值的 `QGraphicsItem`，以实现同样的分层效果。
  2. **图像缓存**: `QPixmap` 本身有非常高效的缓存机制，可以替代手动的 `_resized_image_cache`。
  3. **数据预计算**: `recalculate_render_data` 的逻辑需要保留，它负责调用后端来计算文本布局，这是保证视觉一致性的关键。计算出的 `dst_points` 将被用来设置 `QGraphicsPixmapItem` 的变换矩阵。
  4. **渲染委托**: 不再需要委托给 `BackendTextRenderer`，因为它的功能将被直接整合进新的 `QGraphicsPixmapItem` 子类中。

---

### 文件: `desktop-ui/editor_frame.py` (深度重分析)

- **目的**: 作为“视觉小说编辑器”的UI框架，此文件负责以纯视图（View）的形式，精确构建和布局编辑器的所有可视化组件。它将用户的交互事件（如点击、文本输入）完全委托给`EditingLogic`和`AppController`处理，自身不包含任何业务逻辑。

- **功能细节与组件关联**:

  - **`EditorFrame` 类 (继承自 `customtkinter.CTkFrame`)**:
    - **`__init__(self, master, controller)`**: 构造函数，负责初始化整个编辑器框架。
      - `super().__init__(master)`: 调用父类 `CTkFrame` 的构造函数，创建UI框架的基础。
      - `self.controller = controller`: 保存对顶层 `AppController` 的引用。这是实现跨视图操作（如文件导航）的关键，允许 `EditorFrame` 中的事件触发应用级别的行为。
      - `self.logic = EditingLogic(self, controller)`: 实例化 `EditingLogic` 作为此视图的专属控制器。将 `self` (视图实例) 和 `controller` (应用控制器) 传递给它，使得逻辑层可以：
        1.  回调视图 (`self`) 来更新UI（例如，当逻辑层处理完数据后，调用视图的方法来刷新属性面板）。
        2.  访问应用控制器 (`controller`) 来执行全局操作。
      - `self.grid_columnconfigure(0, weight=1)` 和 `self.grid_rowconfigure(0, weight=1)`: 配置 `EditorFrame` 自身的网格布局。设置 `weight=1` 意味着其内部的子组件（即 `main_frame`）将自动填充所有可用空间，确保窗口缩放时布局的响应性。
      - `self._create_widgets()`: 将所有UI组件的创建工作委托给这个私有方法，保持构造函数的整洁。

    - **`_create_widgets(self)`**: 核心的UI构建方法。
      - **主容器 (`main_frame`)**:
        - 创建一个 `CTkFrame` 作为左右分栏布局的根容器。
        - `self.main_frame.grid_columnconfigure(1, weight=1)`: 配置此容器的第二列（索引为1，即右侧的画布区域）的权重为1，使得在水平缩放窗口时，宽度会优先分配给画布区域，而左侧属性面板宽度保持不变。
      - **右侧画布框架 (`canvas_frame`)**:
        - `self.canvas_frame = CanvasFrameNew(...)`: 实例化 `canvas_frame_new.py` 中定义的 `CanvasFrameNew`。这是编辑器的核心视觉区域。
        - **参数传递**:
          - `master=self.main_frame`: 将其父容器设置为 `main_frame`。
          - `logic=self.logic`: 将 `EditingLogic` 实例传递给画布。这使得画布上的所有交互（鼠标点击、拖拽、缩放）可以直接调用 `EditingLogic` 中对应的方法（如 `on_canvas_click`），实现了画布与逻辑的直接通信。
          - `controller=self.controller`: 传递顶层控制器。
        - `self.canvas_frame.grid(...)`: 将画布放置在 `main_frame` 的右侧（第1列）。
      - **左侧属性面板 (`properties_frame`)**:
        - `self.properties_frame = customtkinter.CTkScrollableFrame(...)`: 创建一个**可滚动**的框架。当属性面板内容过多超出屏幕高度时，会自动出现滚动条。
        - `self.properties_frame.grid(...)`: 将其放置在 `main_frame` 的左侧（第0列）。
        - **文件导航区 (`navigation_frame`)**:
          - `self.prev_image_button = customtkinter.CTkButton(..., command=lambda: self.controller.navigate_image('prev'))`: 创建“上一张”按钮。`command` 参数使用 `lambda` 函数直接绑定到 `AppController` 的 `navigate_image` 方法。这清晰地表明，文件切换是应用级别的功能，而非编辑器内部逻辑。
          - `self.next_image_button = ...`: 同理，创建“下一张”按钮。
        - **文本区域列表区 (`regions_frame`)**:
          - `self.region_list = RegionList(...)`: 实例化 `ui_components.py` 中定义的自定义组件 `RegionList`。
          - **参数传递**: `command=self.logic.on_region_selected`，将列表项的点击事件绑定到 `EditingLogic` 的 `on_region_selected` 方法。当用户在列表中选择一个文本区域时，逻辑层会收到通知。
        - **属性编辑区 (`attributes_frame`)**:
          - 这是一个包含大量细节控件的框架，用于编辑当前选中的文本区域。
          - **原文/译文**:
            - `self.original_text_box = customtkinter.CTkTextbox(...)`: 创建用于显示原文的文本框。
            - `self.translated_text_box = customtkinter.CTkTextbox(...)`: 创建用于编辑译文的文本框。
            - `.bind("<KeyRelease>", self.logic.on_translated_text_changed)`: 为译文框绑定了键盘释放事件。这意味着用户**每输入一个字符**并松开按键，都会调用 `EditingLogic` 的 `on_translated_text_changed` 方法，为实现实时预览或自动保存等功能提供了钩子。
          - **字体大小**:
            - `self.font_size_entry = customtkinter.CTkEntry(...)`: 创建字体大小输入框。
            - `.bind("<KeyRelease>", self.logic.on_font_size_changed)`: 同样绑定键盘事件，实时响应字体大小的修改。
          - **字体颜色**:
            - `self.font_color_button = customtkinter.CTkButton(..., command=self.logic.on_font_color_clicked)`: 创建字体颜色按钮，点击后会触发 `EditingLogic` 中的颜色选择逻辑。
          - **对齐方式**:
            - `self.align_left_button = customtkinter.CTkButton(..., command=lambda: self.logic.on_alignment_changed('left'))`: 创建左对齐按钮，通过 `lambda` 将 'left' 参数传递给 `EditingLogic` 的通用对齐处理方法。
            - `self.align_center_button`, `self.align_right_button`: 同理。
          - **操作按钮**:
            - `self.save_button = customtkinter.CTkButton(..., command=self.logic.save_region_attributes)`: 保存按钮，点击后调用逻辑层的保存方法。
            - `self.reset_button = customtkinter.CTkButton(..., command=self.logic.reset_region_attributes)`: 重置按钮，调用逻辑层的重置方法。
            - `self.remove_button = customtkinter.CTkButton(..., command=self.logic.remove_current_region)`: 删除按钮，调用逻辑层的删除方法。

    - **`load_data(self, image_path, regions, force_reload=False)`**: 公共接口方法，由 `AppController` 调用，用于将新图片的数据加载到编辑器中。
      - `self.canvas_frame.load_image(image_path, regions, force_reload)`: 将图像和区域数据直接传递给画布框架进行渲染。
      - `self.logic.load_new_data(regions, image_path)`: 将数据传递给逻辑层，用于初始化或更新内部状态。
      - `self.update_region_list(regions)`: 调用自身方法更新左侧的区域列表。

    - **`update_region_list(self, regions)`**:
      - `self.region_list.update_list(regions)`: 调用 `RegionList` 组件的公共方法来刷新列表显示。

    - **`update_selected_region(self, region_data)`**: 由 `EditingLogic` 回调，用于在选中区域变化时，更新整个属性面板的显示。
      - **清空与填充**:
        - `if region_data is None:`: 如果没有选中任何区域（例如，取消选择），则清空所有属性控件（文本框、输入框）并禁用它们。
        - `else:`: 如果选中了一个区域，则：
          - `self.original_text_box.delete("1.0", "end")` 和 `.insert("1.0", ...)`: 先清空再插入原文和译文。
          - `self.font_size_entry.delete(0, "end")` 和 `.insert(0, ...)`: 更新字体大小输入框的值。
          - `self.font_color_button.configure(fg_color=...)`: 更新颜色按钮的背景色以显示当前区域的颜色。
          - 遍历对齐按钮，根据 `region_data['align']` 的值，高亮显示当前对齐方式的按钮。

- **重构处置**: **删除**

- **理由**:
  1. **完全基于Tkinter**: 整个文件都是为了构建和驱动 CustomTkinter 界面而编写的，其UI代码（`CTkFrame`, `CTkButton`等）无法在Qt框架下复用。
  2. **新架构中的替代方案**:
     - `EditorFrame` 的整体布局和职责，将被一个新的 `EditorWidget` (继承自 `QWidget`) 在Qt中重新实现。
     - 左右分栏将使用 `QSplitter` 实现，提供更好的用户体验。
     - 画布 (`CanvasFrameNew`) 将被一个继承自 `QGraphicsView` 的新类替代，利用 `QGraphicsScene` 实现更强大和高效的2D渲染。
     - 区域列表 (`RegionList`) 将被 `QListWidget` 替代，其 `itemSelectionChanged` 信号将连接到 `EditingLogic` 的槽函数。
     - 所有属性控件都将使用对应的Qt组件（`QTextEdit`, `QLineEdit`, `QPushButton`, `QToolButton` 等）重新创建。
     - 所有的事件绑定 (`command`, `.bind`) 都将转换为Qt的信号(Signal)与槽(Slot)机制，这将提供更类型安全、更灵活的事件处理方式。

---

### 文件: `desktop-ui/editing_logic.py` (正确分析)

- **目的**: 这是一个无状态的、纯粹的数学计算工具模块。它提供了一系列高级几何函数，专门用于处理在二维空间中对可能经过旋转的任意四边形（文本框）进行顶点、边缘的拖拽、变形和位置计算。它是实现视觉化、所见即所得（WYSIWYG）文本框编辑功能的核心算法库。

- **功能细节与组件关联**:
    - **`rotate_point(x, y, angle_deg, cx, cy)`**:
        - **功能**: 实现一个点 `(x, y)` 围绕另一个中心点 `(cx, cy)` 旋转指定角度 `angle_deg` 的标准二维旋转变换。
        - **关联**: 这是所有与旋转相关的计算的基础，被 `calculate_new_vertices_on_drag` 等多个上层函数调用，用于在“世界空间”（用户屏幕所见）和“模型空间”（未旋转的原始坐标）之间转换坐标。
    - **`get_polygon_center(vertices)`**:
        - **功能**: 计算一个多边形的旋转中心。它不使用简单的几何平均中心，而是调用 `cv2.minAreaRect()` 来获取多边形的**最小外接矩形**的中心。
        - **关联**: 这是一个至关重要的函数。使用最小外接矩形的中心作为旋转中心，可以确保前端画布上的旋转操作与后端 `manga_translator` 渲染引擎的旋转行为完全一致，避免了视觉上的偏移和不匹配。
    - **`_project_vector(v_to_project, v_target)`**:
        - **功能**: 实现标准向量投影算法，将一个向量 `v_to_project` 投影到另一个向量 `v_target` 上。
        - **关联**: 在处理非旋转矩形的顶点拖拽时（`calculate_new_vertices_on_drag` 中的旧逻辑），用于将鼠标的拖拽向量分解到矩形的两条边上。
    - **`calculate_rectangle_from_diagonal(start_point, end_point, angle_deg)`**:
        - **功能**: 在用户通过拖拽对角线来绘制一个**新的、带旋转角度的**矩形时，根据拖拽的起始点和结束点，计算出矩形的四个顶点坐标。
        - **逻辑**: 它将拖拽向量投影到旋转后的坐标轴上，从而确定矩形的宽度和高度向量，最终计算出四个顶点。
        - **关联**: 被 `canvas_frame_new.py` 中的鼠标处理器在 `draw` 模式下调用，用于实现“拖拽绘制新文本框”的功能。
    - **`calculate_new_vertices_on_drag(...)`**:
        - **功能**: 这是最复杂的函数之一，用于处理当用户拖拽现有文本框的**一个顶点**时的变形逻辑。
        - **逻辑**:
            1.  **识别点**: 确定被拖拽点、其对角的“锚点”以及另外两个相邻点。
            2.  **区分旋转与否**:
                - **无旋转 (`angle == 0`)**: 使用简单的向量投影逻辑，将从锚点到新鼠标位置的向量，分别投影到原始的两条边上，计算出新的相邻点，最终确定新的被拖拽点。
                - **有旋转 (`angle != 0`)**: 这是核心算法。它将问题转换到“模型空间”来解决：
                    a. 将锚点和鼠标位置从“世界空间”反向旋转回“模型空间”。
                    b. 在模型空间中，计算出鼠标拖拽的向量。
                    c. 将这个模型空间的拖拽向量，分解到构成矩形的两条原始边向量上（解一个2x2线性方程组）。
                    d. 根据分解出的系数，计算出模型空间中所有顶点的新位置。
                    e. （虽然函数返回模型空间坐标，但调用方 `canvas_frame` 会负责将其旋转回世界空间进行显示）。
        - **关联**: 被 `canvas_frame_new.py` 的鼠标处理器在 `geometry_edit` 模式下，当检测到用户拖拽的是顶点时调用。
    - **`calculate_new_edge_on_drag(...)`**:
        - **功能**: 处理用户拖拽文本框的**一条边**时的平移逻辑。
        - **逻辑**:
            a. 将被拖拽的边和鼠标位置转换到“世界空间”。
            b. 计算世界空间中，这条边的法线向量。
            c. 将鼠标的拖拽向量投影到这个法线向量上，得到一个表示拖拽距离的标量。
            d. 用这个标量和法线方向构建一个世界空间的“偏移向量”。
            e. 将这个“偏移向量”反向旋转回“模型空间”。
            f. **关键修正**: 为了防止在拖拽接近水平或垂直的边时发生“漂移”，代码会判断这条边在模型空间中是更偏水平还是垂直，并强制将模型空间偏移向量的另一个分量置零。
            g. 将这个修正后的模型空间偏移量应用到被拖拽边的两个顶点上。
        - **关联**: 被 `canvas_frame_new.py` 的鼠标处理器在 `geometry_edit` 模式下，当检测到用户拖拽的是边缘时调用。

- **重构处置**: **核心保留与迁移**

- **理由**:
    1.  **算法核心**: 此文件包含了编辑器WYSIWYG操作的全部核心数学算法，这些算法与UI框架无关，是纯粹的逻辑，必须被完整保留。
    2.  **高复用性**: 这些函数是通用的，无论前端使用Tkinter还是Qt，只要是在2D平面上操作带旋转的多边形，这些计算都是必要的。
    3.  **迁移方案**: 在新的Qt架构中，这个文件应该被原封不动地迁移到新的项目结构中，例如放在一个名为 `editor/geometry_utils.py` 的模块里，供新的Qt画布视图 (`QGraphicsView` 的子类) 调用。它的内容和功能完全不需要修改。

---

### 文件: `desktop-ui/editor_frame.py` (上帝对象重度分析)

- **目的**: 此文件是视觉编辑器的**事实核心**，一个典型的“上帝对象”(God Object)。它远不止是一个UI框架，而是集**视图构建、状态管理、事件处理、服务调度和核心业务逻辑**于一身的单一大类。`EditorFrame` 类几乎凭一己之力驱动了整个编辑器的所有功能。

- **功能细节与组件关联**:

  - **`EditorFrame` 类 (继承自 `ctk.CTkFrame`)**:
    - **`__init__(self, parent, ...)`**: 构造函数 - 庞大的初始化过程。
      - **状态初始化**: 初始化了**超过20个**实例变量 (`self.image`, `self.regions_data`, `self.selected_indices`, `self.view_mode`, `self.refined_mask`, `self.inpainting_in_progress` 等)。这暴露了其巨大的状态管理职责，所有编辑器的核心状态都直接作为其属性存在。
      - **服务实例化**:
        - `self.history_manager = EditorStateManager()`: 创建一个撤销/重做历史管理器。
        - `self.transform_service = TransformService()`: 创建一个坐标变换服务，用于处理画布的缩放和平移。
        - `self.file_manager = FileManager()`: 创建文件管理器。
        - `self.ocr_service = OcrService()`, `self.translation_service = TranslationService()`: 创建OCR和翻译服务。
        - `self.async_service = get_async_service()`: 获取全局的异步任务执行服务。
        - `self.config_service = get_config_service()`: 获取全局的配置服务，并注册一个回调 `self.reload_config_and_redraw`，当全局配置变化时，会自动触发编辑器的重绘。
      - **UI构建与连接**:
        - `self._build_ui()`: 调用私有方法构建所有UI组件。
        - `self._setup_component_connections()`: 调用私有方法，将UI组件的事件（回调）连接到 `EditorFrame` 自身的方法上，形成一个复杂的内部事件网络。
      - **延迟初始化**:
        - `self.after(200, self._init_backend_config)`: 在UI显示后，延迟初始化后端服务（OCR、翻译器）的配置。
        - `self.after(100, self._setup_shortcuts)`: 延迟绑定快捷键。

    - **UI构建 (`_build_ui`)**:
      - **布局**: 定义了三列布局（左侧属性面板，中间画布，右侧文件列表）。
      - **组件实例化**:
        - `self.toolbar = EditorToolbar(...)`: 创建顶部工具栏。
        - `self.property_panel = PropertyPanel(...)`: 创建左侧属性面板。
        - `self.canvas_frame = CanvasFrame(...)`: 创建核心的画布。**关键**: 将一系列自身的方法（如 `self._on_region_selected`, `self._on_region_moved`）作为回调函数直接传递给画布，使得画布的底层交互能直接驱动 `EditorFrame` 中的逻辑。
        - `self.file_list_frame = FileListFrame(...)`: 创建右侧文件列表。
        - `self.context_menu = EditorContextMenu(...)`: 创建右键上下文菜单。

    - **事件连接 (`_setup_component_connections`)**:
      - **巨型接线板**: 这个方法是`EditorFrame`作为“上帝对象”最明显的证据。它包含了**超过40个**回调注册，将所有子组件（工具栏、属性面板、画布、上下文菜单）的每一个按钮点击、数值改变、选项切换事件，全部连接到 `EditorFrame` 自身定义的处理方法上。例如：
        - `self.toolbar.register_callback('export_image', self._export_rendered_image)`
        - `self.property_panel.register_callback('text_changed', self._on_property_panel_text_changed)`
        - `self.context_menu.register_callback('ocr_recognize', self._ocr_selected_regions)`
      - **职责集中**: 这表明所有逻辑流都必须经过 `EditorFrame`，它成为了整个系统的瓶颈和信息中枢。

    - **核心工作流 (作为类的方法)**:
      - **文件与数据加载 (`_on_image_loaded`, `set_file_lists`, `_find_file_pair`)**:
        - **功能**: 实现了极其复杂的“智能”文件加载逻辑。
        - **`_on_image_loaded`**: 当文件被加载时，此方法被触发。它会清空旧状态，加载新图片，然后调用 `self.file_manager.load_json_data` 尝试加载关联的 `.json` 文件。
        - **JSON处理**: 如果找到JSON，它会加载文本区域(`regions`)和原始蒙版(`raw_mask`)，并自动触发一个异步任务 `_generate_refined_mask_then_render` 来进行蒙版优化和背景修复。如果找不到，则认为是在查看翻译图或无数据的源图。
        - **`_find_file_pair`**: 一个复杂的辅助函数，通过查询 `translation_map.json` 来寻找一个给定文件是源文件还是翻译文件，并找到其对应的另一半。这是实现“编辑源文件-查看翻译图”切换功能的基础。
        - **`_on_edit_clicked`**: 当用户在查看翻译图时点击“编辑”按钮，此方法会使用 `_find_file_pair` 找到源文件并加载它，从而进入编辑模式。
      - **历史与撤销/重做 (`undo`, `redo`, `_apply_action`, `_apply_single_action`)**:
        - **功能**: 实现了完整的撤销/重做功能。
        - **`_apply_action`**: 从 `history_manager` 获取一个动作(Action)对象，并根据是`undo`还是`redo`来应用 `old_data` 或 `new_data`。
        - **`_apply_single_action`**: 根据动作类型（`ADD`, `DELETE`, `EDIT_MASK`, `MOVE`等），精确地修改 `self.regions_data` 列表或 `self.refined_mask` 数组，从而在数据层面恢复或重做一次操作。
        - **状态保存**: 在所有会修改数据的操作方法中（如 `_on_region_moved`, `_delete_selected_regions`），都会调用 `self.history_manager.save_state(...)` 来将操作前后的数据存入历史栈。
      - **异步任务 (`async def _run_ocr_for_selection`, `_generate_inpainted_preview`, `_async_export_with_mask`)**:
        - **功能**: 将所有耗时的操作（OCR、翻译、蒙版生成、图像修复、导出）封装在 `async` 方法中，并通过 `self.async_service.submit_task()` 提交到后台执行，避免UI卡死。
        - **`_generate_refined_mask`**: 调用 `refine_mask_dispatch` 后端函数，并处理返回的精细化蒙版。
        - **`_generate_inpainted_preview`**: 调用 `inpaint_dispatch` 后端函数，获取修复后的背景图。
        - **`_run_ocr_for_selection`**: 对选中的每个区域，调用 `self.ocr_service.recognize_region`。
        - **`_run_translation_for_selection`**: 收集页面所有文本作为上下文，然后调用 `self.translation_service.translate_text_batch` 进行批量翻译。
        - **回调与UI更新**: 这些异步方法在完成后，会通过 `show_toast` 显示提示，并更新UI状态（如 `self.inpainted_image`），然后调用 `self.canvas_frame.set...` 方法来刷新画布。
      - **几何编辑逻辑**:
        - `EditorFrame` 自身不包含几何计算，但它作为中枢，调度了整个流程：
          1. `CanvasFrame` 的鼠标处理器捕捉到底层鼠标事件。
          2. 鼠标处理器调用 `editing_logic.py` 中的函数（如 `calculate_new_vertices_on_drag`）计算出新的顶点位置。
          3. 鼠标处理器调用 `EditorFrame` 的回调方法（如 `_on_region_resized`）。
          4. `EditorFrame` 在 `_on_region_resized` 方法中，更新 `self.regions_data` 中的数据，并调用 `self.history_manager.save_state` 保存历史记录。

- **重构处置**: **解体与重构 (逻辑上等同于删除后重写)**

- **理由**:
    1.  **违反单一职责原则**: `EditorFrame` 类是一个典型的“上帝对象”，它做了太多不相关的事情，导致代码极度耦合，难以理解、维护和测试。
    2.  **状态管理混乱**: 核心业务状态（`regions_data`等）与UI状态（`view_mode`等）混合在一起，作为几十个实例属性存在，缺乏清晰的管理和边界。
    3.  **逻辑无法复用**: 由于所有业务逻辑都与Tkinter的事件处理和UI更新代码（如 `self.after`, `show_toast`）紧密耦合，这些逻辑几乎无法在新UI框架（如Qt）下复用。

- **新架构中的替代方案**:
    - **模型(Model)**: 创建一个专门的 `EditorModel` 或 `Document` 类，用于封装和管理所有核心数据，如 `regions_data`, `image`, `refined_mask`，以及对这些数据的基础操作。`EditorStateManager` (历史管理器) 应该与这个Model紧密协作。
    - **视图(View)**: 创建一个 `EditorView` (继承自 `QWidget`)，它只负责UI的布局和渲染。它会持有对Controller的引用，并将所有UI事件通过信号(Signal)发送出去。它会观察(Observe) Model的变化并更新自身显示。
    - **控制器(Controller)**: 创建一个 `EditorController` 类。它将包含从 `EditorFrame` 中剥离出来的所有业务逻辑：
        - 响应来自View的信号（如 `on_region_selected`）。
        - 调用Model来修改数据。
        - 调用各种服务（OCR, Translation, Config）。
        - 调度异步任务。
        - `editing_logic.py` 中的几何工具函数将被这个Controller或其下的辅助类调用。
    - 通过这种**MVC/MVVM**模式的重构，可以将原本纠缠在一起的职责清晰地分离开，使得新代码模块化、可测试、易于维护。

---

### 文件: `desktop-ui/canvas_frame_new.py` (深度分析)

- **目的**: 此文件定义了 `CanvasFrame` 类，它是视觉编辑器的核心交互界面。它作为一个高度专业化的容器，封装了底层的Tkinter画布(`ctk.CTkCanvas`)，并聚合了两个关键的子组件：`CanvasRenderer` (负责“画什么”) 和 `MouseEventHandler` (负责处理“如何交互”)。它的主要职责是将用户的底层输入（鼠标、滚轮）转化为具体的业务动作，并将渲染任务委托给渲染器。

- **功能细节与组件关联**:

  - **`CanvasFrame` 类 (继承自 `ctk.CTkFrame`)**:
    - **`__init__(self, parent, transform_service, ...)`**: 构造函数，负责组装画布系统。
      - **依赖注入**:
        - `transform_service`: 接收一个全局的 `TransformService` 实例，用于处理所有坐标变换（屏幕坐标 <=> 图像坐标）。
        - **回调函数**: 接收**大量**由父组件 (`EditorFrame`) 注入的回调函数，如 `on_region_selected`, `on_region_moved`, `on_mask_edit_end` 等。这是一种典型的控制反转（IoC）模式，`CanvasFrame` 在处理完一个交互后，不自己执行业务逻辑，而是通过调用这些回调来通知“上帝对象”`EditorFrame` 去更新状态、保存历史记录。
      - **UI构建**:
        - 创建 `ctk.CTkCanvas` 作为绘图表面。
        - 创建 `ctk.CTkScrollbar` 并与画布绑定，实现滚动条功能。
      - **核心组件实例化**:
        - `self.renderer = CanvasRenderer(...)`: 实例化 `components/canvas_renderer_new.py` 中的渲染器。将画布实例和坐标变换服务传递给它。
        - `self.mouse_handler = MouseEventHandler(...)`: 实例化 `components/mouse_event_handler_new.py` 中的鼠标事件处理器。这是交互逻辑的核心，它也接收了画布实例、坐标服务以及**几乎所有**从 `EditorFrame` 传来的回调函数。

    - **数据设置与状态传递 (`set_regions`, `set_mask`, `set_inpainted_image`, etc.)**:
      - **功能**: 提供了一系列 `set_...` 方法，供父组件 `EditorFrame` 调用，以将最新的数据状态同步到画布系统中。
      - **`set_regions(self, regions)`**:
        - `self.regions = regions`: 更新自身持有的区域数据。
        - `self.mouse_handler.regions = regions`: **关键**，将最新的区域数据同步给鼠标处理器，以便它能进行正确的命中检测。
        - `self.renderer.recalculate_render_data(...)`: 通知渲染器根据新的区域数据预计算文本布局，这是一个耗时操作。
        - `self.redraw_canvas()`: 触发一次完整的重绘。
      - **`set_mask`, `set_refined_mask`, `set_inpainted_image`**: 这些方法都遵循相同的模式：将新的图像/蒙版数据传递给 `self.renderer`，然后调用 `self.redraw_canvas()` 来刷新显示。

    - **重绘管理 (`redraw_canvas`, `_schedule_optimized_redraw`)**:
      - **`redraw_canvas(self, fast_mode=False, use_debounce=False)`**:
        - **功能**: 核心的重绘调度方法。它收集所有需要的渲染参数（区域、选中状态、视图模式、配置等）到一个字典中。
        - **`fast_mode`**: 一个布尔标志，当为 `True` 时（例如在缩放过程中），会通知渲染器使用低质量的渲染方式（如不渲染文本）以保证流畅性。
        - **`use_debounce`**: 一个布尔标志，用于决定是立即重绘还是使用“防抖”技术延迟重绘，以合并短时间内的多次重绘请求。
        - **委托**: 最终调用 `self.renderer.redraw_all(...)` 或 `self.renderer.redraw_debounced(...)` 执行实际的绘制。
      - **`_schedule_optimized_redraw`**: 一个内部优化方法，使用 `self.canvas.after()` 来延迟执行重绘，避免在用户连续拖拽等操作时因过于频繁的重绘导致卡顿。

    - **回调中继 (`_on_region_selected`, `_on_region_moved`, etc.)**:
      - **功能**: 这一系列 `_on_...` 方法是作为 `MouseEventHandler` 的回调函数存在的。它们起到了一个“中继站”的作用。
      - **逻辑流**:
        1. 用户在画布上操作鼠标（例如，拖拽一个区域）。
        2. `MouseEventHandler` 捕捉到鼠标事件，完成几何计算，确定这是一个“移动”操作。
        3. `MouseEventHandler` 调用它持有的 `on_region_moved` 回调，这个回调实际上是 `CanvasFrame` 的 `_on_region_moved` 方法。
        4. `CanvasFrame` 的 `_on_region_moved` 方法被执行。它首先更新自身状态（`self.regions[index] = new_region_data`），然后调用从 `EditorFrame` 注入的 `self.on_region_moved` 回调，将事件和数据进一步传递上去。
      - **职责**: `CanvasFrame` 在这个链条中的职责是：在将事件通知给顶层逻辑之前，先用操作结果更新自己的内部数据状态，并调度一次UI重绘。

    - **预览处理 (`_on_draw_new_region_preview`, `_on_drag_preview`)**:
      - **功能**: 在用户进行拖拽等交互的**过程中**，提供实时的视觉反馈。
      - **逻辑**: `MouseEventHandler` 在鼠标移动时会持续调用这些预览回调。这些回调函数会直接调用 `self.renderer.draw_preview(...)`，让渲染器在不进行完整重绘的情况下，在画布上绘制临时的预览形状（如一个虚线框），从而实现流畅的交互体验。

- **重构处置**: **解体与重构**

- **理由**:
    1. **紧密耦合**: `CanvasFrame` 与 `CanvasRenderer` 和 `MouseEventHandler` 紧密耦合，形成了一个复杂的内部系统。同时，它又通过大量的回调函数与父级 `EditorFrame` 紧密耦合。
    2. **职责不清**: 它混合了UI组件（画布、滚动条）、状态持有（`self.regions`）和事件中继等多重职责。
    3. **Tkinter依赖**: 作为一个 `ctk.CTkFrame` 子类，其UI部分无法直接迁移。

- **新架构中的替代方案**:
    - **`QGraphicsView` 作为核心**: 新的画布将是一个继承自 `QGraphicsView` 的自定义类。`QGraphicsView` 提供了强大的、开箱即用的缩放、平移和滚动条功能，不再需要手动管理 `TransformService` 和滚动条。
    - **`QGraphicsScene` 管理对象**: 所有的视觉元素（背景图、文本框、蒙版）都将被实现为 `QGraphicsItem` 的子类（如 `QGraphicsPixmapItem`, `QGraphicsPolygonItem`），并添加到 `QGraphicsScene` 中。渲染和命中检测将由 `QGraphicsScene` 自动高效处理。
    - **事件处理简化**: 鼠标事件可以直接在 `QGraphicsView` 或 `QGraphicsItem` 的子类中通过覆盖 `mousePressEvent`, `mouseMoveEvent` 等方法来处理。这将取代独立的 `MouseEventHandler`，使得交互逻辑与对应的图形项更加内聚。
    - **信号/槽机制**: 不再需要手动注入十几次回调函数。新的画布视图将定义一系列信号，例如 `region_moved(int, QPolygonF)`。父组件（新的 `EditorController`）只需连接到这些信号即可，实现完全解耦。
    - `CanvasRenderer` 的职责将被 `QGraphicsScene` 的渲染机制和自定义的 `QGraphicsItem.paint()` 方法所取代。

---

### 文件: `desktop-ui/translation_worker.py` (深度分析)

- **目的**: 此文件是一个独立的、可执行的Python脚本，作为后台“工作者进程”的入口点。它的唯一职责是接收一个包含所有翻译参数的JSON配置文件，然后调用核心的 `manga-translator` 库来执行实际的、耗时的翻译任务。它被设计为与主UI进程完全隔离，通过标准输出(`stdout`)进行单向通信，将日志和进度信息打印出来。

- **功能细节与组件关联**:

  - **环境设置**:
    - **编码强制**: 在文件顶部，它检测到如果是Windows系统，就强制将 `sys.stdout` 和 `sys.stderr` 的编码设置为UTF-8。这是为了确保当它打印包含非ASCII字符（如中文日志）的进度信息时，主UI进程的监控线程能够正确解码，避免乱码。
    - **`flush_print` 函数**: 定义了一个包装了`print`的函数，每次打印后都强制调用 `sys.stdout.flush()`。这至关重要，因为它确保了每条日志信息都能被立即发送出去，而不是在缓冲区中等待，从而让主UI进程可以实时捕获和显示。
    - **日志配置 (`setup_logging`)**: 将Python的 `logging` 模块的根处理器重定向到 `sys.stdout`。这使得 `manga-translator` 库内部使用的所有 `logging.info()` 或 `logging.warning()` 调用，都能被转换成 `print` 语句，从而被主UI进程捕获。
    - **路径设置**: 将项目根目录添加到 `sys.path`，以确保可以成功 `import manga_translator`。

  - **`main()` 函数 (核心工作流)**:
    - **1. 接收配置**:
      - 检查 `sys.argv`，确保收到了一个命令行参数，即由 `app.py` 创建的临时JSON配置文件路径 (`temp/translation_config.json`)。
    - **2. 加载配置**:
      - 读取并解析该JSON文件，从中提取出 `config_dict` (包含所有UI设置)、`input_files` (待处理文件列表) 和 `output_folder` (输出目录)。
    - **3. 动态导入**:
      - **延迟导入**: 将 `from manga_translator.manga_translator import MangaTranslator` 等重量级模块的导入放在函数内部。这是一种优化，使得工作者进程在执行实际任务前，启动开销非常小。
    - **4. 初始化翻译器 (`MangaTranslator`)**:
      - 创建一个 `MangaTranslator` 实例。
      - **参数聚合**: 将从JSON加载的 `config_dict` 作为参数传递给 `MangaTranslator` 的构造函数。
      - **字体路径处理**: 特别处理了字体路径。它会从配置中读取字体文件名，然后使用 `resource_path` 函数（一个用于处理PyInstaller打包后资源路径的工具函数）来构建正确的绝对路径，再将其设置到参数中。
      - **UI模式标志**: 显式地设置 `is_ui_mode=True`，这可能会在 `manga-translator` 库内部启用某些针对UI调用的特殊逻辑（例如，更详细的日志）。
    - **5. 文件解析**:
      - 遍历 `input_files` 列表，如果是目录，则递归地查找所有图片文件，最终生成一个扁平化的、包含所有待处理图片绝对路径的列表 `resolved_files`。
    - **6. 创建配置对象 (`Config`)**:
      - 将 `config_dict` 中不同部分的字典，分别反序列化为 `manga_translator` 库定义的强类型配置对象，如 `RenderConfig`, `TranslatorConfig`, `OcrConfig` 等。最终组合成一个总的 `Config` 对象。
    - **7. 启动翻译**:
      - **创建事件循环**: `loop = asyncio.new_event_loop()`，为执行异步翻译任务准备一个 `asyncio` 事件循环。
      - **模式判断**: 检查配置中的翻译器类型和文件数量，以决定是采用“单文件模式”还是“批量模式”。
      - **单文件模式**:
        - 遍历 `resolved_files` 列表。
        - 对每个文件，调用 `loop.run_until_complete(translator.translate(image, config, ...))`。
        - 翻译完成后，根据结果和配置（如是否跳过无文本图片、是否覆盖已存在文件）来决定如何保存。
        - **保存逻辑**: 精确地构建输出文件的路径，包括在输出目录中重建原始的子目录结构。然后根据文件类型（JPG, WEBP, PNG）和保存质量进行保存。
        - **日志输出**: 在每个关键步骤（加载、翻译、保存、跳过）都使用 `flush_print` 打印详细的、带状态前缀（`✅`, `❌`, `⏩`）的日志。
      - **批量模式**:
        - 将所有图片加载到内存中。
        - 调用 `loop.run_until_complete(translator.translate_batch(...))`，一次性将所有图片和配置传递给后端。
        - 后端 `translate_batch` 方法会负责内部的批次划分和处理。
        - 循环处理返回的结果，并执行与单文件模式类似的保存逻辑。
    - **8. 清理**:
      - 在 `finally` 块中，确保无论成功还是失败，都删除临时的JSON配置文件，避免留下垃圾文件。

- **重构处置**: **完全删除**

- **理由**:
    1.  **子进程模型的废弃**: 在新的 `QThread` 架构中，后台任务将在主进程的一个独立线程中运行，而不是在一个完全隔离的子进程中。因此，整个“启动一个新Python脚本来干活”的模式将被彻底废弃。
    2.  **通信机制过时**: 基于 `subprocess.Popen` 和 `stdout` 管道的进程间通信方式，虽然能工作，但功能非常有限（只能传递文本），且不稳定、难以管理。新的 `QThread` 模型将使用Qt的信号/槽机制，可以安全、高效地传递任何复杂的Python对象（如进度百分比、`PIL.Image`对象、异常对象），使得UI和后台任务的交互更加丰富和健壮。
    3.  **逻辑被吸收**: `translation_worker.py` 中的所有逻辑（加载配置、初始化`MangaTranslator`、调用`translate`、处理保存）将被一个新的 `QObject` 子类（我们称之为 `TranslationTask`）所吸收。这个 `TranslationTask` 对象将被移动到 `QThread` 中执行，其 `run` 方法将包含与 `translation_worker.py` 的 `main` 函数类似的逻辑。

---

### 文件: `desktop-ui/ui_components.py` (深度分析)

- **目的**: 此文件是一个UI组件库，提供了多个可被应用内其他视图复用的、自包含的UI控件。它旨在封装通用UI模式，减少代码重复。

- **功能细节与组件关联**:

  - **`show_toast(parent, message, duration=2000, level="info")` 函数**:
    - **目的**: 在父窗口的底部中心，弹出一个短暂的、非阻塞的通知消息（“Toast”提示），用于向用户提供操作反馈（如“保存成功”、“导出已取消”）。
    - **功能细节**:
      1.  **窗口创建**: 创建一个 `ctk.CTkToplevel` 窗口。这是一个顶级窗口，但通过 `toast.overrideredirect(True)` 移除了其边框、标题栏等所有窗口装饰，使其看起来像一个悬浮的标签。`toast.wm_attributes("-topmost", True)` 确保它显示在所有其他窗口之上。
      2.  **样式化**:
          - 定义了一个 `colors` 字典，根据传入的 `level` 参数（`info`, `success`, `error`）为Toast选择不同的背景色和文本颜色，提供了视觉上的区分。
          - 创建一个 `ctk.CTkLabel` 来显示 `message`，并应用选择的颜色。
      3.  **定位逻辑**:
          - `parent.update_idletasks()`: 强制Tkinter更新父窗口的几何信息。
          - `parent.winfo_x()`, `parent.winfo_y()` 等: 获取父窗口的位置和尺寸。
          - `label.winfo_reqwidth()`: 获取Toast标签自身需要多宽。
          - 通过数学计算 `x = parent_x + (parent_width // 2) - (toast_width // 2)`，精确地计算出将Toast水平居中于父窗口所需 `x` 坐标。
          - `y = parent_y + parent_height - toast_height - 20`: 计算 `y` 坐标，使其位于父窗口底部并向上偏移20像素。
          - `toast.geometry(f"+{x}+{y}")`: 应用计算出的位置。
      4.  **自动销毁**:
          - `toast.after(duration, safe_destroy)`: 使用Tkinter的 `after` 方法调度一个任务，在 `duration` 毫秒后调用 `safe_destroy` 函数。
          - `safe_destroy`: 一个安全的包装函数，在销毁窗口前会检查 `toast.winfo_exists()`，确保窗口仍然存在，避免因窗口已提前关闭而引发异常。
      5.  **健壮性**: 整个函数被包裹在 `try...except` 块中，如果创建或显示Toast的任何环节失败，它会静默地忽略错误，避免因一个不重要的通知功能而导致整个应用崩溃。
    - **关联**: 被应用中几乎所有需要向用户提供反馈的地方调用，尤其是 `EditorFrame` 中的各种操作方法。

  - **`CollapsibleFrame(ctk.CTkFrame)` 类**:
    - **目的**: 创建一个可折叠/展开的区域。它由一个始终可见的标题栏和一个可显示/隐藏的内容区域组成，常用于组织复杂的设置界面，节省屏幕空间。
    - **功能细节**:
      - **`__init__(self, parent, title="", start_expanded=True)`**:
        - **UI构建**:
          - `self.header`: 创建一个 `CTkFrame` 作为标题栏。
          - `self.arrow_label`: 创建一个 `CTkLabel` 用于显示指示展开/折叠状态的箭头（`▼` 或 `▶`）。
          - `self.title_label`: 创建一个 `CTkLabel` 用于显示 `title` 文本。
          - `self.content_frame`: 创建一个 `CTkFrame` 作为内容容器。**关键**: 外部代码在实例化 `CollapsibleFrame` 后，应该使用 `collapsible_frame.content_frame` 作为父容器，来向这个可折叠区域中添加具体的UI控件。
        - **事件绑定**: `self.header.bind("<Button-1>", self.toggle)`，将标题栏的鼠标左键点击事件绑定到 `toggle` 方法。箭头和标题标签也同样绑定，确保点击标题栏的任何部分都能触发折叠/展开。
        - **初始状态**: 根据 `start_expanded` 参数，决定内容区域在初始化时是可见 (`.grid()`) 还是隐藏 (`.grid_remove()`)。
      - **`toggle(self, event=None)` 方法**:
        - **功能**: 切换框架的折叠/展开状态。
        - **逻辑**:
          1.  反转 `self.is_expanded` 布尔值。
          2.  如果变为展开 (`True`)，则调用 `self.content_frame.grid()` 使内容框架可见，并将箭头文本设为 `▼`。
          3.  如果变为折叠 (`False`)，则调用 `self.content_frame.grid_remove()` 从布局中移除内容框架（比隐藏更高效），并将箭头文本设为 `▶`。
    - **关联**: 可以在任何需要对UI元素进行分组和折叠的地方使用，例如在 `PropertyPanel` 中用于组织不同的设置项。

- **重构处置**: **逻辑迁移**

- **理由**:
    1.  **Tkinter依赖**: 这些组件都是基于 `customtkinter` 构建的，无法直接在Qt中使用。
    2.  **通用UI模式**: 它们实现的是非常通用的UI模式（Toast通知、可折叠面板），在任何UI框架中几乎都有对应的实现或可以轻松地重新实现。

- **新架构中的替代方案**:
    - **`show_toast`**:
        - 可以创建一个类似的函数 `show_qt_toast(parent, ...)`。
        - 它将创建一个 `QLabel`，并将其父级设为 `parent`。
        - 使用样式表 (`setStyleSheet`) 来设置背景色、圆角和字体颜色。
        - 使用 `parent.mapToGlobal()` 和 `toast.frameGeometry()` 来计算正确的全局位置。
        - 使用 `QTimer.singleShot(duration, toast.close)` 来实现延时关闭。
        - 可以将其封装在一个更通用的 `NotificationService` 中。
    - **`CollapsibleFrame`**:
        - Qt没有完全对应的单一控件，但可以非常容易地通过组合控件来创建。
        - 一种常见方法是创建一个 `QWidget` 子类，其中包含一个 `QToolButton` (用于标题和箭头) 和一个 `QFrame` (作为内容容器)。
        - `QToolButton` 的 `toggled` 信号可以连接到一个槽函数，该槽函数调用 `content_frame.setVisible(checked)` 来显示或隐藏内容区域。
        - Qt的动画框架 `QPropertyAnimation` 还可以用来为展开/折叠过程添加平滑的动画效果，提升用户体验。

---

### 文件: `desktop-ui/components/mouse_event_handler_new.py` (深度分析)

- **目的**: 此文件定义了 `MouseEventHandler` 类，它是画布交互的“大脑”。它被 `CanvasFrame` 实例化，并负责监听所有底层的鼠标和滚轮事件。其核心职责是作为一个复杂的状态机，根据当前的编辑模式 (`self.mode`) 和用户输入，将原始的屏幕坐标事件转换为高级的、有业务含义的动作（如“选中区域”、“移动顶点”、“绘制蒙版”），然后通过回调函数通知上层逻辑。

- **功能细节与组件关联**:

  - **`__init__(self, canvas, regions, transform_service, ...)`**:
    - **依赖注入**: 接收 `canvas` (用于事件绑定和坐标转换)、`regions` (对区域数据的引用)、`transform_service` (用于坐标系转换) 以及**大量**从 `CanvasFrame` 中继而来的回调函数 (`on_region_selected`, `on_region_moved` 等)。
    - **状态机初始化**:
      - `self.action_info`: 一个字典，用于存储当前正在进行的动作的状态（例如，动作类型、起始坐标、被操作的原始数据）。这是实现拖拽操作的关键。
      - `self.mode = 'select'`: 初始化状态机的默认模式为“选择模式”。
      - `self.selected_indices`: 一个集合，用于存储当前被选中的区域索引。
    - **事件绑定**:
      - `.bind("<Button-1>", ...)`: 绑定鼠标左键按下事件到 `on_left_click`。
      - `.bind("<B1-Motion>", ...)`: 绑定鼠标左键拖拽事件到 `on_drag`。
      - `.bind("<ButtonRelease-1>", ...)`: 绑定鼠标左键释放事件到 `on_drag_stop`。
      - `.bind("<Button-2>", ...)`: 绑定鼠标中键（滚轮按下）用于平移画布。
      - `.bind("<MouseWheel>", ...)`: 绑定鼠标滚轮用于缩放画布。
      - `.bind("<Motion>", ...)`: 绑定鼠标移动事件到 `_update_cursor`，以实现动态光标变化。

  - **核心事件处理方法**:
    - **`on_left_click(self, event)`**:
      - **功能**: 鼠标左键按下的总入口，负责决定即将开始什么操作。
      - **逻辑**:
        1.  **模式判断**: 首先检查 `self.mode`。
            - 如果是 `'mask_edit'` 或 `'draw'` 等非选择模式，则直接在 `self.action_info` 中记录下动作类型和起始坐标，然后返回。
        2.  **命中检测**: 如果是 `'select'` 模式，则调用 `_get_hit_target(event)` 来判断鼠标下是什么物体。
        3.  **`_get_hit_target`**: 这是一个非常复杂的函数，它按优先级顺序进行检测：
            a. **旋转手柄**: 计算选中区域的旋转手柄位置，判断是否点中。
            b. **顶点/边缘**: 将选中区域的几何形状旋转到世界坐标系，然后判断鼠标是否靠近某个顶点或边缘。
            c. **移动**: 判断鼠标是否在某个已选中区域的内部。
            d. **选择新区域**: 判断鼠标是否在某个未选中区域的内部。
        4.  **动作初始化**: 根据命中检测的结果和是否按下了`Ctrl`键，来填充 `self.action_info` 字典，为后续的 `on_drag` 和 `on_drag_stop` 做准备。例如，如果命中了顶点，`action_info` 会被设置为 `{'type': 'vertex_edit', 'original_data': ..., 'region_index': ...}`。

    - **`on_drag(self, event)`**:
      - **功能**: 鼠标拖拽过程中的处理函数，主要负责**实时预览**。
      - **逻辑**:
        1.  根据 `self.action_info` 中记录的动作类型，执行不同的预览逻辑。
        2.  **`'pan'`**: 调用 `transform_service.pan()` 平移画布。
        3.  **`'draw'`**: 计算拖拽出的矩形，并调用 `on_draw_new_region_preview` 回调来绘制预览框。
        4.  **`'move'`, `'rotate'`, `'vertex_edit'` 等**: 调用 `_get_drag_preview_data()` 计算出区域在拖拽过程中的新形状，然后调用 `on_drag_preview` 回调来绘制预览。这个过程**不修改**原始数据，只用于显示。

    - **`on_drag_stop(self, event)`**:
      - **功能**: 鼠标左键释放时的处理函数，负责**提交操作结果**。
      - **逻辑**:
        1.  根据 `self.action_info` 中记录的动作类型，执行最终的计算和回调。
        2.  调用 `_get_final_drag_data()` 来获取拖拽操作最终确定的新区域数据。
        3.  **`_get_final_drag_data`**: 这个方法会调用 `editing_logic.py` 中的高级几何函数（如 `calculate_new_vertices_on_drag`）来精确计算变形后的最终结果。
        4.  **调用回调**: 将 `original_data` (保存在 `action_info` 中) 和计算出的 `new_data` 一起，通过对应的回调函数（如 `self.on_region_moved(index, old_data, new_data)`）提交给上层 (`CanvasFrame` -> `EditorFrame`)。
        5.  **清理状态**: 清空 `self.action_info` 和 `self.is_dragging`，标志着一次完整的交互动作结束。

  - **其他关键方法**:
    - **`on_mouse_wheel(self, event)`**:
      - **功能**: 处理画布缩放。
      - **逻辑**: 使用 `_debounce_timer` 和 `_zoom_end_timer` 实现了缩放的“防抖”和“开始/结束”事件。在滚动过程中，会以 `fast_mode` 进行渲染，滚动停止后才进行一次高质量的完整渲染，极大地优化了缩放体验。
    - **`_update_cursor(self, event)`**:
      - **功能**: 根据鼠标下的物体，动态改变光标样式（如变成十字、四向箭头、旋转图标等），为用户提供直观的交互提示。

- **重构处置**: **逻辑迁移**

- **理由**:
    1.  **Tkinter事件模型**: 整个类的逻辑都建立在Tkinter的事件对象和 `.bind()` 模型之上，无法直接迁移。
    2.  **职责清晰但实现耦合**: 尽管它清晰地承担了“鼠标事件处理”这一职责，但其内部实现与 `editing_logic.py` 的函数以及 `CanvasFrame` 的回调紧密耦合。

- **新架构中的替代方案**:
    - **`QGraphicsItem` 内置事件处理**: 在新的Qt架构中，`MouseEventHandler` 的大部分职责将被分散到各个自定义的 `QGraphicsItem` 子类中。
      - 例如，一个代表文本框的 `RegionItem` (继承自 `QGraphicsPolygonItem`) 将自己覆盖 `mousePressEvent`, `mouseMoveEvent`, `hoverEnterEvent` 等方法。
      - 当鼠标悬停在 `RegionItem` 上时，`hoverMoveEvent` 可以判断鼠标是靠近顶点还是边缘，并相应地改变光标 (`self.setCursor(...)`)。
      - 当用户按下并拖拽时，`mouseMoveEvent` 会直接计算新的几何形状，更新自身，并发出一个信号 `region_changed(old_data, new_data)`。
    - **场景事件处理**: 画布的平移和缩放功能，可以通过在 `QGraphicsView` 子类中覆盖 `mousePress/Move/ReleaseEvent` 和 `wheelEvent` 来实现。`QGraphicsView` 本身就提供了 `translate()` 和 `scale()` 方法，使得平移缩放的实现比手动管理变换矩阵简单得多。
    - **状态机保留**: `self.mode` 这种状态机的思想仍然有用。新的 `QGraphicsView` 子类可以持有一个类似的 `mode` 属性，其鼠标事件处理方法会根据当前模式执行不同的逻辑（例如，在 `'draw'` 模式下，鼠标拖拽会创建一个新的 `RegionItem`）。

---

### 文件: `desktop-ui/components/property_panel.py` (深度分析)

- **目的**: 此文件定义了 `PropertyPanel` 类，即编辑器左侧的属性面板。它是一个高度集成的复合组件，负责动态展示和编辑当前选中区域的所有属性，包括文本内容、样式、位置信息，并提供相关操作的快捷入口。

- **功能细节与组件关联**:

  - **`PropertyPanel` 类 (继承自 `ctk.CTkScrollableFrame`)**:
    - **`__init__(self, parent, ...)`**:
      - **继承**: 继承自 `CTkScrollableFrame`，使其内容在超出屏幕时可以自动滚动。
      - **服务获取**: 通过 `get_..._service()` 函数获取全局单例服务，如 `OcrService`, `TranslationService`, `ConfigService`。这表明它需要直接与这些服务交互来获取配置（如可用的OCR模型列表）或触发操作。
      - **回调注册表**: `self.callbacks: Dict[str, Callable] = {}`，定义了一个回调字典，用于实现与父组件(`EditorFrame`)的通信。
      - **UI构建**: 调用 `_create_widgets()` 方法来分段构建整个面板的复杂UI。

  - **UI构建方法 (`_create_..._section`)**:
    - **`_create_region_info_section()`**: 创建顶部的“区域信息”部分，包含一系列 `CTkLabel`，用于显示选中区域的索引、位置、尺寸和角度。这些标签是只读的，通过 `load_region_data` 方法更新。
    - **`_create_mask_edit_section()`**:
        - 使用 `CollapsibleFrame` (来自`ui_components.py`) 创建一个默认折叠的“蒙版编辑”部分。
        - 包含画笔/橡皮擦按钮、笔刷大小滑块、蒙版显示开关等。
        - **事件连接**: 所有控件的 `command` 都通过 `lambda` 表达式调用 `self._execute_callback("event_name", ...)`，将事件（如`mask_tool_changed`）和参数冒泡到父组件 `EditorFrame`。
    - **`_create_text_section()`**:
        - **OCR/翻译配置**: 调用 `_create_ocr_translate_config_section` 创建模型选择下拉菜单和操作按钮。
          - **动态菜单**: `ocr_models = self.ocr_service.get_available_models()`，它会直接调用服务来获取可用模型列表，并动态填充 `CTkOptionMenu`。翻译器和目标语言的选择也遵循此模式。
          - **名称映射**: `TRANSLATOR_DISPLAY_NAMES` 字典用于将程序内部的翻译器标识符（如`gemini_hq`）映射为用户友好的显示名称（如“高质量翻译 Gemini”）。
        - **原文/译文框**: 创建两个核心的 `CTkTextbox` 用于显示和编辑原文与译文。
        - **事件绑定**: 为文本框绑定了 `<KeyRelease>` 事件到 `_on_text_change`，实现用户输入时的实时响应。
        - **快捷键处理**: `_handle_textbox_key_press` 方法拦截文本框中的按键事件，并检查它们是否匹配全局快捷键，如果匹配则执行快捷键并阻止事件继续传播。这使得即使用户焦点在文本框内，全局快捷键（如Ctrl+S保存）依然有效。
    - **`_create_style_section()`**:
        - 创建字体大小、颜色、对齐方式、文字方向等所有样式相关的控件。
        - **颜色选择器**: “选择”颜色按钮的 `command` 绑定到 `_choose_color` 方法，该方法会调用 `tkinter.colorchooser.askcolor` 弹出一个标准的系统颜色选择对话框。
        - **事件连接**: 样式控件的值改变事件（如 `command` 或 `<Return>`）大多绑定到 `_on_style_change` 方法，该方法再通过回调通知 `EditorFrame`。

  - **数据流与核心方法**:
    - **`register_callback(self, event_name, callback)`**: 由父组件 `EditorFrame` 调用，将自身的方法（如 `_on_property_panel_text_changed`）注册到 `PropertyPanel` 的回调字典中。
    - **`_execute_callback(self, event_name, *args)`**: `PropertyPanel` 内部的统一事件派发方法。当任何一个UI控件被操作时，它会查找回调字典并执行对应的、由 `EditorFrame` 注册的方法。这是实现**子组件到父组件**通信的核心机制。
    - **`load_region_data(self, region_data, region_index)`**:
      - **功能**: 由 `EditorFrame` 在选中区域变化时调用，是**父组件到子组件**数据流的核心。
      - **逻辑**:
        1.  接收 `region_data` 字典和索引。
        2.  用字典中的值填充面板中的所有UI控件：更新信息标签、设置文本框内容、设置滑块和下拉菜单的值、更新颜色输入框等。
        3.  **文本预处理**: 在将译文设置到文本框之前，会进行一些预处理，例如将 `[BR]` 等换行符统一替换为 `\n`，并根据配置和文本方向自动应用 `<H>` 标签以实现局部横排。
        4.  **WYSIWYG实现**: 调用 `_highlight_horizontal_tags()` 方法。
    - **`_highlight_horizontal_tags()`**:
      - **功能**: 实现横排标签的“所见即所得”编辑。
      - **逻辑**:
        1.  在 `CTkTextbox` 中定义两种特殊的 `tag`：“高亮”和“隐藏”。
        2.  使用正则表达式查找文本中所有的 `<H>...</H>` 标记。
        3.  将被 `<H>` 和 `</H>` 包围的**内容**应用“高亮” `tag`（改变其背景色）。
        4.  将 `<H>` 和 `</H>` **标签本身**应用“隐藏” `tag` (`elide=True`)，使其在视觉上不可见，但仍然存在于文本数据中。

- **重构处置**: **解体与重构**

- **理由**:
    1.  **混合职责**: `PropertyPanel` 混合了UI构建、从服务获取数据（违反了视图不应直接接触服务的原则）、事件派发和部分文本处理逻辑，职责不够单一。
    2.  **Tkinter强耦合**: 完全基于 `customtkinter` 构建，无法直接迁移。
    3.  **回调地狱**: 严重依赖手动注册和执行的回调字典 (`self.callbacks`) 来与父级通信，这种方式在大型应用中难以维护且容易出错。

- **新架构中的替代方案**:
    - **纯粹的View**: 新的 `PropertyPanel` (继承自 `QWidget`) 将是一个更纯粹的视图组件。它只负责创建Qt控件（`QLineEdit`, `QComboBox`, `QTextEdit`等）并布局。
    - **信号/槽**: 它将定义一系列信号，如 `text_changed(str)`, `style_changed(dict)`。当UI控件的值发生变化时（例如 `QLineEdit.textChanged` 信号被触发），`PropertyPanel` 的槽函数会被调用，然后它会发出自己定义的、更高级别的信号。
    - **数据绑定/模型**: `EditorController` 将连接到 `PropertyPanel` 的信号。当收到信号时，`Controller` 会更新 `EditorModel`。反之，当 `EditorModel` 的数据（例如用户选择了新的区域）发生变化时，`Controller` 会调用 `PropertyPanel` 的一个槽函数 `load_region_data(region_model)`，用模型中的数据来更新UI显示。这种单向数据流/双向绑定的方式比回调函数更清晰、更健壮。
    - **`<H>` 标签处理**: `_highlight_horizontal_tags` 的逻辑可以被 `QSyntaxHighlighter` 完美替代。可以创建一个 `QSyntaxHighlighter` 的子类，并将其应用到 `QTextEdit` 上，以非侵入的方式实现对特定模式（如`<H>...</H>`）的实时高亮和格式化。

---

### 文件: `desktop-ui/services/__init__.py` (深度分析)

- **目的**: 此文件是整个应用的服务层核心，它实现了一个完整的**服务容器**和**依赖注入(DI)**模式。其目的是将应用的所有核心功能（配置、日志、翻译、状态管理等）封装成独立的、可替换的服务，并提供一个全局唯一的访问点来获取这些服务，从而实现业务逻辑与UI代码的高度解耦。

- **功能细节与组件关联**:

  - **`ServiceContainer` 类**:
    - **目的**: 这是一个依赖注入容器，负责**创建、持有和管理**所有服务实例的生命周期。
    - **`__init__`**: 初始化一个 `self.services` 字典，用于存储所有服务实例。
    - **`initialize_services(self, root_widget=None)`**:
      - **功能**: 这是服务初始化的总入口，它采用了一个巧妙的**三阶段异步加载**策略，以优化应用的启动性能。
      - **第一阶段 (同步)**: `_init_essential_services()`。立即、同步地初始化最核心、最轻量的服务，如 `LogService`, `StateManager`, `ConfigService`。这确保了应用在启动的最早阶段就能读写配置和记录日志。
      - **第二阶段 (后台线程)**: `_init_heavy_services()`。在一个新的后台守护线程 (`threading.Thread`) 中初始化那些可能耗时较长的服务，如 `TranslationService` 和 `OcrService`（它们可能需要加载模型或初始化网络连接）。这避免了重量级服务的初始化过程阻塞UI主线程，从而让主窗口能更快地显示出来。
      - **第三阶段 (UI延迟)**: `_init_ui_services()`。在UI主线程中，使用 `root_widget.after(100, ...)` 延迟初始化与UI相关的服务，如 `ShortcutManager` (快捷键管理器) 和 `MultiWidgetDragDropHandler` (拖拽服务)，因为这些服务需要UI完全渲染后才能绑定。
    - **`get_service(self, service_name)`**: 提供一个方法来从容器中按名称获取服务实例。
    - **`shutdown_services(self)`**: 在应用关闭时被调用，负责安全地关闭所有服务，例如调用 `translation_service.cleanup()` 来释放资源，调用 `log_service.shutdown()` 来关闭日志文件。

  - **`ServiceManager` 类**:
    - **目的**: 这是一个**单例 (Singleton)** 类，作为所有服务全局唯一的访问点。应用中的任何地方想要获取服务，都应该通过 `ServiceManager` 而不是直接创建实例。
    - **`__new__`**: 实现了标准的单例模式，确保 `ServiceManager` 只有一个实例。
    - **`initialize(cls, root_dir, ...)`**: 一个类方法，用于创建并初始化其内部持有的 `ServiceContainer` 实例。这个方法只会在应用启动时被调用一次。
    - **`get_service(cls, service_name)`**: 一个类方法，允许通过 `ServiceManager.get_service('config')` 这种方式在代码的任何地方获取服务实例。
    - **便捷的Getter方法**: 提供了一系列如 `get_config_service()`, `get_translation_service()` 的静态类型提示的便捷方法，使得代码更具可读性，并能获得更好的IDE支持。

  - **全局便捷函数**:
    - **`init_services(...)`**, **`get_config_service()`**, **`get_logger()`** 等:
    - **目的**: 在模块的顶层，定义了一系列与 `ServiceManager` 中同名的便捷函数。
    - **关联**: 应用中的其他模块（如 `property_panel.py`）可以直接 `from services import get_config_service`，然后调用 `get_config_service()`，而无需关心其内部是- 如何通过 `ServiceManager` 实现的。这进一步简化了服务的使用，并降低了耦合度。

  - **`inject_service` 装饰器**:
    - **目的**: 提供了一种基于装饰器的依赖注入方式（虽然在当前代码库中可能未被广泛使用）。
    - **用法**: `_@inject_service('config') def my_function(config=None): ...`。这个装饰器会自动从 `ServiceManager` 获取 `config` 服务，并将其作为关键字参数注入到被装饰的函数中。

- **重构处置**: **核心保留与增强**

- **理由**:
    1.  **优秀的架构设计**: 这种基于服务容器和单例管理器的依赖注入模式是现代软件工程中的一个非常优秀的设计实践。它极大地促进了代码的模块化、可测试性和可维护性。
    2.  **框架无关**: 整个服务管理系统是纯Python实现的，与Tkinter或Qt完全无关。因此，它可以被**原封不动地**迁移到新的Qt架构中。
    3.  **性能优化**: 三阶段异步加载的初始化策略考虑到了应用的启动性能，是一个值得保留的亮点。

- **新架构中的建议**:
    - **线程模型适配**: 在 `_init_heavy_services` 中，目前使用的是Python原生的 `threading.Thread`。为了与Qt更好地集成，可以考虑将其替换为 `QThreadPool` 或一个专门的 `QThread`，但这并非强制性的修改，现有实现依然可以工作。
    - **UI服务初始化**: `_init_ui_services` 中对 `root_widget.after` 的调用需要被替换。在Qt中，可以在主窗口 (`QMainWindow`) 初始化完成后，直接调用服务初始化，或者使用 `QTimer.singleShot(100, ...)` 来达到同样的效果。
    - **服务扩展**: 这个架构非常易于扩展。在重构过程中，可以将更多从“上帝对象”`EditorFrame` 中剥离出来的逻辑（如历史管理、文件管理）封装成新的服务，并在这个容器中注册和管理。

---

### 文件: `desktop-ui/services/config_service.py` (深度分析)

- **目的**: 此文件定义了 `ConfigService` 类，一个用于集中管理应用所有配置的强大服务。它不仅负责加载和保存用户的JSON配置文件，还管理着存储API密钥等敏感信息的`.env`文件，并包含了对这些配置的验证逻辑。

- **功能细节与组件关联**:

  - **`ConfigService` 类**:
    - **`__init__(self, root_dir)`**:
      - **路径管理**: 存储项目根目录，并据此推断出 `.env` 文件的路径 (`../.env`)。
      - **状态持有**: `self.config_path` 存储当前加载的配置文件路径，`self.current_config` 是一个字典，在内存中持有当前的所有配置。
      - **回调列表**: `self.callbacks = []` 用于存储在配置更新时需要被通知的函数。
      - **延迟加载**: `self._translator_configs = None`，翻译器相关的硬编码配置信息直到第一次被访问时才会通过 `_init_translator_configs` 方法加载，这是一种优化手段。

    - **翻译器配置管理**:
      - **`TranslatorConfig` 数据类**: 一个 `dataclass`，用于结构化地定义每种翻译器（如`youdao`, `openai`）的配置信息，包括其显示名称、必需的环境变量(`required_env_vars`)、可选环境变量以及API密钥的验证规则(`validation_rules`)。
      - **`_init_translator_configs()`**: 一个私有方法，硬编码了所有支持的翻译器的 `TranslatorConfig` 信息。这是一个集中的“注册表”，使得添加或修改翻译器配置变得容易。
      - **Getter方法**: 提供 `get_translator_configs()`, `get_required_env_vars()` 等一系列方法，让外部可以方便地查询特定翻译器的配置需求和验证规则。

    - **核心配置(JSON)文件操作**:
      - **`load_config_file(self, config_path)`**: 从给定的路径加载JSON文件，并将其内容存入 `self.current_config`。
      - **`save_config_file(self, config_path=None)`**: 将内存中的 `self.current_config` 字典以格式化的方式（`indent=2`）写回到JSON文件。
      - **`set_config(self, config)`**: **关键方法**。当其他部分（如 `app_logic.py`）需要以编程方式更新整个配置时调用此方法。它不仅更新内存中的 `self.current_config`，还会**遍历并调用所有已注册的回调函数**。
      - **`register_callback(self, callback)`**: 允许其他组件（如 `EditorFrame`）注册一个回调函数。当 `set_config` 被调用时，这些回调函数会被触发，从而使UI能够响应配置的变化并自动刷新。这是一个典型的**观察者模式**实现。
      - **`reload_from_disk()`**: 一个强制从磁盘重新加载当前配置并触发所有回调的公共方法，用于确保配置的同步。

    - **环境变量(`.env`)操作**:
      - **`load_env_vars()`**: 使用 `python-dotenv` 库的 `dotenv_values` 函数来安全地从 `.env` 文件加载环境变量。
      - **`save_env_var(self, key, value)`**: 使用 `dotenv.set_key` 将单个键值对写入 `.env` 文件。这个函数会自动创建文件和目录，非常健壮。
      - **`save_env_vars(self, env_vars)`**: 批量保存多个环境变量。

    - **验证逻辑**:
      - **`validate_api_key(...)`**: 根据 `TranslatorConfig` 中定义的正则表达式，验证一个给定的API密钥格式是否正确。
      - **`validate_translator_env_vars(...)`**: 检查一个翻译器所有必需的环境变量是否都已在 `.env` 文件中设置且值不为空。
      - **`is_translator_configured(...)`**: 一个便捷方法，直接返回一个翻译器的配置是否完整。

- **重构处置**: **核心保留**

- **理由**:
    1.  **职责单一且清晰**: `ConfigService` 完美地封装了所有与配置相关的逻辑，职责非常单一。它将JSON配置和`.env`文件的复杂性对应用的其他部分完全隐藏起来。
    2.  **框架无关**: 该服务完全不依赖任何UI框架（Tkinter或Qt），是纯粹的后端逻辑，可以在新架构中无缝复用。
    3.  **设计优秀**:
        - 使用**观察者模式**（回调机制）来通知配置变更，是一种响应式编程的良好实践，有效降低了组件间的耦合。
        - 使用**延迟加载**来初始化翻译器配置，优化了性能。
        - 将翻译器元数据（所需密钥、验证规则）集中管理，使得系统易于扩展。

- **新架构中的建议**:
    - **无需修改**: 这个文件几乎可以原封不动地迁移到新项目的 `services` 目录中。
    - **信号/槽的潜在替代**: 在一个纯Qt的环境中，可以考虑将 `register_callback` 机制替换为Qt的信号/槽机制。`ConfigService` 可以继承自 `QObject` 并定义一个 `config_changed = pyqtSignal()` 信号。当 `set_config` 被调用时，它会 `self.config_changed.emit()`。其他Qt组件可以直接连接到这个信号。这样做的好处是能更好地融入Qt的生态系统，但现有的回调机制也完全够用且同样有效。

---

### 文件: `desktop-ui/services/state_manager.py` (深度分析)

- **目的**: 此文件实现了 `StateManager` 类，一个全局的、集中的**状态管理中心**。它的设计目的是为整个应用程序提供一个“单一事实来源 (Single Source of Truth)”。任何组件都可以从这里读取应用状态（如“是否正在翻译”），或者在状态变化时收到通知，从而做出响应。这极大地降低了组件之间直接通信的需要，是实现响应式UI和清晰数据流的关键。

- **功能细节与组件关联**:

  - **`AppStateKey` (Enum)**:
    - **功能**: 使用Python的 `Enum` (枚举) 定义了所有可被追踪的全局状态的键。例如 `IS_TRANSLATING`, `CURRENT_FILES`, `APP_READY`。
    - **优点**: 使用枚举而不是裸字符串，可以避免因拼写错误导致的bug，并让代码更具可读性和可维护性。

  - **`StateManager` 类**:
    - **`__init__`**:
      - `self._state`: 一个字典，是存储所有状态值的核心容器。
      - `self._observers`: 一个字典，键是 `AppStateKey`，值是一个回调函数列表。这是**观察者模式**的核心实现。
      - `self._lock = threading.Lock()`: 一个线程锁，用于保护 `_state` 和 `_observers` 字典，确保在多线程环境中对状态的读写是线程安全的。
      - `_initialize_default_state()`: 在构造时调用，为所有状态键设置一个明确的初始值。

    - **核心方法**:
      - **`set_state(self, key, value, notify=True)`**:
        - **功能**: 设置一个状态的值，这是状态变更的唯一入口。
        - **逻辑**:
          1.  获取线程锁。
          2.  检查新值是否与旧值不同。只有在值确实发生变化时，才继续执行。这是一个重要的性能优化，避免了不必要的状态更新和通知。
          3.  更新 `self._state` 字典。
          4.  如果 `notify` 为 `True`，则调用 `_notify_observers` 通知所有订阅者。
          5.  释放线程锁。
      - **`subscribe(self, key, callback)`**:
        - **功能**: 允许应用中的任何部分（通常是UI组件或逻辑控制器）“订阅”某个特定状态的变化。
        - **逻辑**: 将 `callback` 函数添加到一个与特定状态 `key` 相关联的观察者列表中。
      - **`_notify_observers(self, key, new_value, old_value)`**:
        - **功能**: 当一个状态发生变化时，遍历其对应的观察者列表，并执行每一个已注册的回调函数，同时将新值作为参数传递。
        - **健壮性**: 它会复制观察者列表 (`.copy()`) 再进行遍历，这是一个好习惯，可以防止在通知过程中有订阅者尝试取消订阅而导致列表在迭代中被修改的问题。

    - **便捷方法**:
      - **`is_translating()`, `set_translating(...)`**, **`get_current_files()`, `set_current_files(...)`** 等。
      - **功能**: 为每个状态键提供了一对类型提示明确的 `getter` 和 `setter` 方法。
      - **优点**: 这使得调用代码更加清晰易读（例如，调用 `state_manager.is_translating()` 而不是 `state_manager.get_state(AppStateKey.IS_TRANSLATING)`），并且能充分利用IDE的自动补全和类型检查功能。

  - **单例模式实现**:
    - **`_state_manager = None`**: 在模块级别定义一个全局变量。
    - **`get_state_manager()`**: 一个全局函数，它实现了单例模式。第一次调用时，它会创建一个 `StateManager` 实例并将其赋给 `_state_manager`；后续所有调用都将返回这个已存在的实例。
    - **关联**: 在 `services/__init__.py` 中，`ServiceManager` 通过调用这个 `get_state_manager()` 来获取并注册单例实例，确保整个应用共享同一个状态管理器。

- **重构处置**: **核心保留**

- **理由**:
    1.  **优秀的架构模式**: 状态管理器是构建可维护的、数据驱动的UI应用的基石。它将状态与视图分离，使得状态变化可预测、可追踪。
    2.  **框架无关**: `StateManager` 是一个纯粹的Python类，不依赖任何UI框架，可以无缝地在新架构中复用。
    3.  **线程安全**: 通过使用 `threading.Lock`，它确保了状态更新的原子性和线程安全性，这对于一个既有UI主线程又有后台工作线程的应用来说至关重要。

- **新架构中的建议**:
    - **无需修改**: 这个文件可以被原封不动地迁移到新项目中。
    - **与Qt信号/槽的结合**:
        - **方案A (维持现状)**: 新的Qt组件可以在其构造函数中调用 `get_state_manager().subscribe(...)`，并提供一个自己的方法作为回调。当状态变化时，回调被触发，在回调方法中可以更新UI。这是最直接的迁移方式。
        - **方案B (增强集成)**: 可以创建一个 `QtStateManager` 包装器，它继承自 `StateManager` 和 `QObject`。对于每个状态键，它都可以定义一个对应的Qt信号，如 `is_translating_changed = pyqtSignal(bool)`。在 `set_state` 方法中，除了调用回调外，还 `emit` 对应的信号。这样，Qt组件就可以使用更原生的 `state_manager.is_translating_changed.connect(self.on_translating_changed)` 方式来订阅状态，代码风格更统一。但这会增加一些复杂性，对于当前项目规模可能并非必要。

---

### 文件: `desktop-ui/services/editor_history.py` (深度分析)

- **目的**: 此文件提供了编辑器撤销/重做功能的核心实现。它定义了用于表示用户操作的数据结构，并实现了管理这些操作历史的逻辑，同时还附带了一个简单的内部剪贴板功能。

- **功能细节与组件关联**:

  - **`ActionType(Enum)`**:
    - **功能**: 一个枚举类，用于清晰地定义用户可能执行的所有可撤销操作的类型，如 `MOVE`, `RESIZE`, `DELETE`, `ADD`, `MODIFY_TEXT`, `EDIT_MASK` 等。

  - **`EditorAction` 和 `GroupedAction` (dataclasses)**:
    - **功能**: 这是**命令模式**的体现。每个 `EditorAction` 对象都封装了一次独立操作的所有信息：
      - `action_type`: 操作的类型。
      - `region_index`: 操作影响的区域索引。
      - `old_data`: 操作前的区域数据。
      - `new_data`: 操作后的区域数据。
    - **`GroupedAction`**: 继承自 `EditorAction`，它包含一个 `actions` 列表。这用于将一系列连续的、细粒度的操作（例如，拖动滑块时的多次数值变化）组合成一个单一的、原子性的撤销/重做步骤，极大地提升了用户体验。

  - **`EditorHistory` 类**:
    - **目的**: 这是实际的撤销/重做栈管理器。
    - **`__init__`**:
      - `self.history`: 一个列表，用作存储所有 `EditorAction` 的历史记录。
      - `self.current_index`: 一个整数指针，指向 `history` 列表中当前所在的位置。它不通过增删列表元素，而是通过移动指针来实现撤销/重做，这种方式更高效。
      - `self.grouping`: 一个布尔标志，用于标记当前是否正在记录一个动作组。
    - **核心方法**:
      - **`add_action(action)`**:
        - **逻辑**: 如果 `self.grouping` 为 `True`，则将动作添加到临时的 `grouped_actions` 列表；否则，直接调用 `_add_action_to_history`。
      - **`_add_action_to_history(action)`**:
        - **功能**: 将一个新动作添加到历史记录中。
        - **关键逻辑**: 如果 `current_index` 不在历史记录的末尾（意味着用户已经执行了撤销操作），那么在添加新动作之前，它会**丢弃**当前指针之后的所有“未来”历史（即重做栈中的所有内容）。这是标准的撤销/重做模式行为。
        - **容量限制**: 如果历史记录超过 `max_history`，它会从列表的开头移除最旧的动作。
      - **`undo()`**: 如果 `can_undo()`，它简单地将 `current_index` 指针减一，并返回指针之前指向的动作。
      - **`redo()`**: 如果 `can_redo()`，它将 `current_index` 指针加一，并返回新位置的动作。
      - **`start_action_group()` / `end_action_group()`**: 这两个方法用于控制动作分组。`start` 将 `grouping` 设为 `True`，`end` 则将期间收集的所有动作打包成一个 `GroupedAction` 并添加到历史记录中。

  - **`EditorStateManager` 类**:
    - **目的**: 这是一个更高层次的**外观(Facade)**类。`EditorFrame` 主要与这个类交互，而不是直接与 `EditorHistory` 交互。
    - **`__init__`**: 它创建并持有一个 `EditorHistory` 实例。
    - **`save_state(...)`**:
      - **功能**: 这是 `EditorFrame` 保存历史记录的入口。
      - **逻辑**: 它接收操作的详细信息，创建一个 `EditorAction` 对象，并调用 `self.history.add_action()`。**关键**: 在创建 `EditorAction` 时，它使用 `copy.deepcopy()` 来保存 `old_data` 和 `new_data`。这至关重要，因为它确保了历史记录中保存的是数据的**快照**，而不是对易变对象的引用，从而防止了历史记录被后续的操作意外修改。
    - **`undo()` / `redo()`**: 直接将调用委托给内部的 `self.history` 实例。
    - **剪贴板功能**:
      - `self.clipboard_data`: 一个简单的实例变量，用作内部剪贴板。
      - `copy_to_clipboard(data)` / `paste_from_clipboard()`: 提供了复制和粘贴区域数据的功能，同样使用 `deepcopy` 来确保数据独立。

- **重构处置**: **核心保留**

- **理由**:
    1.  **经典且有效的设计**: 这种基于命令模式和指针移动的撤销/重做栈实现，是该功能的标准教科书式解决方案，非常清晰和高效。
    2.  **逻辑独立**: `EditorHistory` 和 `EditorStateManager` 是纯粹的逻辑类，不依赖任何UI框架，可以被无缝迁移和复用。
    3.  **深拷贝的正确使用**: 正确地使用 `copy.deepcopy` 来保存状态快照，是实现一个健壮历史记录系统的关键，该文件正确地做到了这一点。

- **新架构中的建议**:
    - **无需修改**: 这两个类可以被原封不动地迁移到新项目的 `services` 目录中。
    - **与`QUndoStack`的比较**: Qt自身提供了一个强大的 `QUndoStack` 框架，它使用 `QUndoCommand` 对象。虽然 `QUndoStack` 提供了更丰富的功能（如视图集成、干净/肮脏状态管理），但当前的自定义实现已经满足了项目的所有需求，并且逻辑清晰、易于理解。因此，是**直接复用**现有实现，还是花时间重构为 `QUndoStack`，是一个可以根据项目进度和需求权衡的决策。对于快速迁移而言，直接复用是完全可行的。

---

### 文件: `desktop-ui/services/async_service.py` (深度分析)

- **目的**: 此文件定义了 `AsyncService`，一个为整个应用提供**后台异步任务执行能力**的核心服务。它的主要作用是创建一个在独立线程中运行的`asyncio`事件循环，并提供一个线程安全的接口，允许主UI线程（同步的Tkinter代码）将耗时的异步操作（协程）提交到这个后台循环中执行，从而避免UI冻结。

- **功能细节与组件关联**:

  - **`AsyncService` 类**:
    - **`__init__`**:
      - **事件循环创建**: `self._loop = asyncio.new_event_loop()`，创建一个新的、独立的`asyncio`事件循环。
      - **后台线程**: `self._thread = threading.Thread(target=self._run_loop, daemon=True, ...)`，创建一个新的守护线程。`daemon=True`意味着当主程序退出时，这个后台线程也会被强制终止。
      - **启动线程**: `self._thread.start()`，立即启动后台线程，使其准备好接收任务。
    - **`_run_loop(self)`**:
      - **功能**: 这是后台线程的入口点和核心。
      - **逻辑**:
        1.  `asyncio.set_event_loop(self._loop)`: 将当前线程（即后台线程）的`asyncio`事件循环设置为之前创建的`_loop`。
        2.  `self._loop.run_forever()`: 启动事件循环，使其永久运行，等待并执行被提交的任务。
    - **`submit_task(self, coro: Coroutine)`**:
      - **功能**: 这是 `AsyncService` 对外提供的**核心公共接口**。UI线程（如`EditorFrame`）通过调用此方法来执行一个耗时的异步操作。
      - **参数**: `coro`，一个协程（coroutine），即一个由 `async def` 定义的函数调用。
      - **线程安全**:
        - `asyncio.run_coroutine_threadsafe(coro, self._loop)`: 这是实现此服务的关键函数。它是一个线程安全的函数，允许一个运行在不同线程中的代码（UI主线程）向另一个线程中的`asyncio`事件循环（`_loop`）提交一个协程任务。
        - 它会立即返回一个 `concurrent.futures.Future` 对象，调用者可以（虽然在此项目中未普遍使用）用它来查询任务状态或获取结果。
    - **任务包装与管理**:
      - `_wrap_task(self, coro)`: 在提交任务前，使用此方法包装原始的协程。
      - **逻辑**: 它将当前任务添加到 `self._active_tasks` 集合中进行追踪，在任务执行完毕后（无论成功或失败），在 `finally` 块中确保将其从集合中移除。
      - **并发限制**: `submit_task` 会检查 `len(self._active_tasks)` 是否超过了 `_max_concurrent_tasks` 的限制，提供了一个基础的并发任务数量控制。
    - **`shutdown(self)`**:
      - **功能**: 提供一个安全关闭后台事件循环和线程的方法。
      - **逻辑**: `self._loop.call_soon_threadsafe(self._loop.stop)`，通过一个线程安全的方式请求事件循环停止。

  - **单例模式实现**:
    - 与其他服务类似，它通过模块级的 `_async_service` 变量和 `get_async_service()` 函数来实现单例模式，确保整个应用共享同一个后台事件循环和线程。
    - `shutdown_async_service()`: 一个全局的关闭函数，在应用退出时被调用。

- **重构处置**: **核心保留**

- **理由**:
    1.  **解决了核心问题**: 无论UI框架是Tkinter还是Qt，都需要一个机制来处理耗时操作而不阻塞UI。这个服务通过“在独立线程中运行asyncio事件循环”的经典模式，完美地解决了这个问题。
    2.  **框架无关**: `AsyncService` 的实现是纯粹的Python `threading` 和 `asyncio`，与UI框架完全无关，可以无缝迁移到新的Qt项目中。
    3.  **设计良好**: 接口清晰（只有一个 `submit_task` 方法），实现了线程安全，并考虑了任务追踪和并发限制，是一个设计良好的后台任务处理器。

- **新架构中的建议**:
    - **无需修改**: 这个文件可以被原封不动地迁移到新项目的 `services` 目录中。`EditorController` 或其他新的逻辑类可以像 `EditorFrame` 一样，通过 `get_async_service().submit_task(...)` 来执行后台任务。
    - **与`QThreadPool`的对比**: Qt提供了 `QThreadPool` 作为其原生的线程池解决方案。虽然也可以将任务重构为 `QRunnable` 并在 `QThreadPool` 中运行，但这样做会失去使用 `asyncio` 带来的便利（例如，轻松地 `await` 多个异步API调用）。对于一个大量使用 `async/await` 语法的项目来说，保留现有的 `AsyncService` 是更简单、更自然的选择。

---

### 文件: `desktop-ui/services/translation_service.py` (深度分析)

- **目的**: 此文件定义了 `TranslationService` 类，它作为应用内所有翻译功能的统一接口。它封装了对底层 `manga-translator` 库的调用细节，为上层逻辑（如 `EditorFrame` 或 `app_logic.py`）提供了一个简洁、易于使用的 `async` 方法来执行单句或批量文本翻译。

- **功能细节与组件关联**:

  - **`TranslationService` 类**:
    - **`__init__`**:
      - **状态持有**: `self.current_translator_enum` 和 `self.current_target_lang`，用于存储当前用户选择的翻译器和目标语言。
    - **`get_available_translators()`**:
      - **功能**: 获取所有后端支持的翻译器列表。
      - **逻辑**: 它直接返回从 `manga_translator.config` 导入的 `Translator` 枚举的所有成员值。这是一个很好的实践，确保了前端可选的翻译器列表总是与后端库的实际能力保持同步。
    - **`get_target_languages()`**:
      - **功能**: 返回一个硬编码的、从语言代码（如`CHS`）到显示名称（如`简体中文`）的字典。
    - **`set_translator(translator_name)` / `set_target_language(lang_code)`**:
      - **功能**: 两个简单的 `setter` 方法，用于更新服务内部持有的当前翻译器和目标语言状态。这些方法由上层逻辑（如 `PropertyPanel` 中的下拉菜单事件）调用。
    - **`translate_text(text, ...)`**:
      - **功能**: 提供单句文本的翻译能力。
      - **逻辑**:
        1.  构建一个“翻译链”字符串，如 `"gemini:CHS"`。
        2.  创建一个 `Context` 对象，并将待翻译文本放入其中。
        3.  调用从 `manga_translator.translators` 导入的 `dispatch_translator` 核心分发函数。
        4.  `dispatch_translator` 会根据“翻译链”字符串动态地选择并调用正确的后端翻译器。
        5.  将返回的结果包装成一个 `TranslationResult` 数据类实例。
    - **`translate_text_batch(texts, ...)`**:
      - **功能**: **核心方法**。提供批量文本翻译的能力，并能接收额外的上下文信息（如图片、区域数据）以支持更高级的翻译模式。
      - **逻辑**:
        1.  与单句翻译类似，构建“翻译链”和 `Context` 对象。
        2.  **上下文增强**: 如果调用者提供了 `image` 和 `regions` 参数，它会将这些信息填充到 `Context` 对象中。这对于需要完整页面信息才能工作的“高质量翻译器”（如`gemini_hq`）至关重要。
        3.  调用 `dispatch_translator`，将**整个文本列表**一次性传递给后端。
        4.  后端翻译器（特别是高质量翻译器）可以利用这个完整的文本列表和图片上下文，来提供更连贯、更准确的翻译。
        5.  将返回的翻译结果列表与原始文本列表 `zip` 起来，包装成 `TranslationResult` 列表返回。
        6.  包含错误处理，如果后端返回的结果数量与输入不匹配或在翻译过程中发生异常，它会返回一个相应长度的、包含`None`的列表，保证了接口的稳定性。

  - **模块级健壮性**:
    - **`TRANSLATOR_AVAILABLE`**: 在文件顶部，对 `manga_translator` 的导入被包裹在一个 `try...except` 块中。如果导入失败（例如，后端库未安装或损坏），`TRANSLATOR_AVAILABLE` 会被设为 `False`。
    - **安全检查**: `TranslationService` 的所有核心方法在执行前都会检查 `if not TRANSLATOR_AVAILABLE`，如果后端不可用，它们会直接返回 `None` 或空列表，从而防止整个应用因后端模块的缺失而崩溃。

- **重构处置**: **核心保留**

- **理由**:
    1.  **清晰的抽象**: `TranslationService` 成功地将复杂的后端调用（构建`Context`、处理`TranslatorChain`、调用`dispatch`）抽象成了一两个简单的 `async` 方法，极大地简化了上层代码的逻辑。
    2.  **框架无关**: 这是一个纯粹的逻辑服务，完全不依赖任何UI框架，可以无缝迁移到新架构。
    3.  **面向接口而非实现**: 上层代码只与 `TranslationService` 交互，而不需要知道具体的翻译器（如`GeminiTranslator`, `YoudaoTranslator`）是如何实现的。这使得未来替换或增加新的翻译后端变得非常容易，只需在 `manga_translator` 库和 `ConfigService` 中注册即可，而不需要修改调用方的代码。

- **新架构中的建议**:
    - **无需修改**: 这个文件可以被原封不动地迁移到新项目的 `services` 目录中。新的 `EditorController` 或 `AppLogic` 可以继续通过 `get_translation_service()` 获取其实例并调用其方法。
    - **与`async_service`的协同**: `TranslationService` 的 `async` 方法应该总是通过 `async_service.submit_task()` 来调用，以确保它们在后台线程中执行，从而不阻塞UI。

---

### 文件: `desktop-ui/services/ocr_service.py` (深度分析)

- **目的**: 此文件定义了 `OcrService` 类，它作为应用内所有光学字符识别（OCR）功能的统一接口。它封装了对底层 `manga_translator` OCR模块的调用，负责管理OCR模型的生命周期、处理输入数据格式转换，并为上层逻辑提供简洁的 `async` 方法来识别图像区域中的文本。

- **功能细节与组件关联**:

  - **`OcrService` 类**:
    - **`__init__`**:
      - **配置与设备**: 初始化一个默认的 `OcrConfig`，并调用 `_check_gpu_available` 来检测系统中是否存在可用的CUDA环境，据此设置 `self.device` 为 `'cuda'` 或 `'cpu'`。
      - **模型状态**: `self.model_prepared = False`，一个布尔标志，用于实现模型的**延迟加载**。模型只在第一次执行识别任务前被加载到内存。
    - **`_get_current_config()`**:
      - **功能**: 从全局的 `ConfigService` 中获取用户在UI上设置的OCR相关参数，并将其组装成一个 `OcrConfig` 对象。
      - **关联**: 这使得OCR服务的行为（如使用哪个模型、置信度阈值等）可以被用户动态配置。
    - **`prepare_model(ocr_type)`**:
      - **功能**: 异步加载指定的OCR模型到内存中。
      - **逻辑**: 调用后端 `prepare_ocr(ocr_to_use, self.device)` 函数来执行实际的模型加载。加载完成后，将 `self.model_prepared` 设为 `True`，避免重复加载。
    - **`recognize_region(self, image, region, ...)`**:
      - **功能**: **核心方法**。识别单个文本区域（`region`）中的文字。一个“区域”可能包含多个不连续的多边形（例如，一个气泡内的多行文本）。
      - **逻辑**:
        1.  **模型准备**: 检查 `self.model_prepared`，如果模型未加载，则先 `await self.prepare_model()`。
        2.  **数据转换**: 遍历 `region['lines']` 中的所有多边形，将它们转换为后端 `dispatch_ocr` 函数所需的 `Quadrilateral` 对象列表。
        3.  **调用后端**: `await dispatch_ocr(...)`，将图像和该区域的所有 `Quadrilateral` 对象列表传递给后端进行识别。
        4.  **结果聚合**: 后端会为每个多边形返回一个识别结果。此方法会将所有结果的文本拼接在一起，并计算平均置信度，最后将这些信息包装成一个 `OcrResult` 对象返回。
    - **`recognize_multiple_regions(...)`**:
      - **功能**: 提供一个批量识别多个区域的接口（尽管在当前 `EditorFrame` 的实现中，似乎更倾向于对每个选区单独调用 `recognize_region`）。
      - **逻辑**: 将多个区域的所有多边形收集起来，一次性传递给 `dispatch_ocr`，然后将返回的结果重新分发回对应的原始区域。
    - **`set_model(model_name)`**:
      - **功能**: 允许上层UI（如 `PropertyPanel`）更改当前使用的OCR模型。
      - **逻辑**: 它接收一个模型名称，更新内部的 `default_config`，并将 `self.model_prepared` 重置为 `False`，这样在下一次识别任务时，新的模型就会被加载。

  - **模块级健壮性与单例模式**:
    - **`OCR_AVAILABLE`**: 与 `TranslationService` 类似，它在文件顶部安全地导入后端模块，如果失败则将 `OCR_AVAILABLE` 设为 `False`。所有核心方法都会检查此标志，确保在后端不可用时程序不会崩溃。
    - **`get_ocr_service()`**: 通过模块级的全局变量和这个getter函数，实现了 `OcrService` 的单例模式，确保整个应用共享同一个OCR服务实例和已加载的模型。

- **重构处置**: **核心保留**

- **理由**:
    1.  **清晰的抽象层**: `OcrService` 很好地扮演了“外观”(Facade)角色，将复杂的后端OCR调用（模型加载、数据格式转换、结果解析）封装成了一两个简洁的 `async` 方法。
    2.  **框架无关**: 这是一个纯粹的逻辑服务，完全不依赖任何UI框架，可以无缝迁移到新架构。
    3.  **状态管理**: 它有效地管理了OCR模型的状态（如是否已加载、当前使用哪个模型），避免了在每次识别时都重复加载模型，提升了性能。

- **新架构中的建议**:
    - **无需修改**: 这个文件可以被原封不动地迁移到新项目的 `services` 目录中。新的 `EditorController` 或 `AppLogic` 可以继续通过 `get_ocr_service()` 获取其实例，并通过 `async_service` 提交其 `async` 方法。
    - **模型管理**: `prepare_model` 的逻辑可以进一步增强。例如，当用户在UI切换模型时，可以主动在后台开始加载新模型，而不是等到下一次识别时才被动加载，这样可以减少用户在首次使用新模型时的等待时间。

---

### 文件: `desktop-ui/services/transform_service.py` (深度分析)

- **目的**: 此文件定义了 `TransformService` 类，一个专门负责处理画布二维坐标变换的服务。它封装了所有与缩放（Zoom）和平移（Pan）相关的数学计算，并提供了在不同坐标系（屏幕坐标和图像坐标）之间进行转换的方法。

- **功能细节与组件关联**:

  - **`TransformService` 类**:
    - **`__init__`**:
      - **状态变量**:
        - `self.zoom_level`: 存储当前的缩放级别，1.0代表100%。
        - `self.x_offset`, `self.y_offset`: 存储当前画布在屏幕上的平移偏移量。
      - **观察者模式**: `self._callbacks: List[Callable] = []`，与 `ConfigService` 类似，它也实现了一个简单的观察者模式，允许其他组件（如 `CanvasFrame`）订阅变换事件。

    - **核心变换方法**:
      - **`get_transform_matrix()`**:
        - **功能**: 根据当前的 `zoom_level` 和 `offset`，构建一个 3x3 的**仿射变换矩阵**。这个矩阵描述了如何将一个图像坐标点 `(img_x, img_y)` 变换为屏幕坐标点。
      - **`get_inverse_transform_matrix()`**:
        - **功能**: 计算上述变换矩阵的**逆矩阵**。这个逆矩阵则用于将屏幕坐标点 `(screen_x, screen_y)` 反向变换为图像坐标点。
        - **健壮性**: 使用 `np.linalg.pinv` (伪逆矩阵) 而不是 `np.linalg.inv`，这在 `zoom_level` 极小或为零时能提供更好的数值稳定性，避免程序因矩阵不可逆而崩溃。
      - **`screen_to_image(x, y)`**:
        - **功能**: 将屏幕上的一个点（如鼠标光标位置）转换为图像上的对应点。
        - **逻辑**: 将屏幕坐标 `(x, y)` 构造成齐次坐标 `[x, y, 1]`，然后左乘逆变换矩阵。
      - **`image_to_screen(x, y)`**:
        - **功能**: 将图像上的一个点（如文本框顶点）转换为屏幕上的对应点。
        - **逻辑**: 将图像坐标 `(x, y)` 构造成齐次坐标 `[x, y, 1]`，然后左乘正变换矩阵。

    - **状态变更方法**:
      - **`zoom(self, factor, center_x, center_y)`**:
        - **功能**: 实现“以鼠标为中心的缩放”功能。
        - **逻辑**:
          1.  `img_x, img_y = self.screen_to_image(center_x, center_y)`: 首先，将当前的鼠标屏幕坐标 `(center_x, center_y)` 转换为图像坐标。这个点在缩放过程中应该保持不动。
          2.  `self.zoom_level *= factor`: 更新缩放级别。
          3.  `self.x_offset = center_x - img_x * self.zoom_level`: **核心算法**。重新计算 `x_offset`，确保经过新的缩放后，之前计算出的图像点 `(img_x, img_y)` 仍然会落在屏幕点 `(center_x, center_y)` 上。
          4.  `self._notify()`: 通知所有订阅者变换已发生改变。
      - **`pan(self, dx, dy)`**:
        - **功能**: 实现画布平移。
        - **逻辑**: 直接将屏幕坐标系的偏移量 `(dx, dy)` 加到当前的 `x_offset` 和 `y_offset` 上，然后通知订阅者。

    - **订阅与通知**:
      - `subscribe(callback)` 和 `_notify()`: 实现了完整的观察者模式。当 `zoom` 或 `pan` 等方法被调用时，`_notify()` 会被触发，进而执行所有已注册的回调函数。
      - **关联**: `CanvasFrame` 会订阅这个服务。当变换发生时，`CanvasFrame` 的回调函数（即 `_on_transform_changed`）被触发，该函数进而调用 `self.redraw_canvas()` 来重绘整个画布以反映新的缩放或平移状态。

- **重构处置**: **核心保留**

- **理由**:
    1.  **完美的职责分离**: 这个类完美地封装了所有与2D变换相关的复杂数学，其职责非常单一和清晰。
    2.  **框架无关**: 完全使用 `numpy` 进行计算，不依赖任何UI框架，可以在新架构中被直接复用。
    3.  **设计模式**: 观察者模式的使用使得它能够轻松地与任何UI组件集成，当变换发生时，UI可以被动地接收通知并更新，而不是主动地去查询状态。

- **新架构中的建议**:
    - **无需修改**: 这个文件可以被原封不动地迁移到新项目的 `services` 目录中。
    - **与`QGraphicsView`的集成**: 在新的Qt架构中，虽然 `QGraphicsView` 自带了强大的变换系统，但保留 `TransformService` 仍然有其价值。
        - **方案A (替换)**: 完全废弃 `TransformService`，直接使用 `QGraphicsView.scale()` 和 `QGraphicsView.translate()` 方法，并通过 `QGraphicsView.mapToScene()` 和 `QGraphicsView.mapFromScene()` 进行坐标转换。这是最“Qt原生”的做法。
        - **方案B (保留并适配)**: 保留 `TransformService` 作为变换状态的“单一事实来源”。`QGraphicsView` 的子类可以订阅 `TransformService`。当服务状态变化时，视图的回调函数被触发，在函数内部调用 `self.setTransform(...)` 来更新 `QGraphicsView` 自身的变换矩阵。这样做的好处是，如果应用中除了画布外还有其他地方需要知道当前的缩放/平移状态（例如，工具栏上的缩放比例显示），它们都可以统一订阅 `TransformService`，而无需直接与 `QGraphicsView` 通信。考虑到当前架构，方案B可能更平滑。

---

### 文件: `desktop-ui/components/editor_toolbar.py` (深度分析)

- **目的**: 此文件定义了 `EditorToolbar` 类，即编辑器顶部的工具栏。它是一个纯粹的视图（View）组件，负责创建和布局所有全局操作按钮（如返回、导出、撤销/重做、缩放等），并将用户的点击事件通过回调机制传递给上层控制器(`EditorFrame`)处理。

- **功能细节与组件关联**:

  - **`EditorToolbar` 类 (继承自 `ctk.CTkFrame`)**:
    - **`__init__(self, parent, ...)`**:
      - **回调机制**:
        - `self.callbacks: Dict[str, Callable] = {}`: 与 `PropertyPanel` 类似，它也使用一个回调字典来注册和执行事件。
        - `self.back_callback`: 一个特殊的回调，用于处理“返回”按钮，直接在构造时传入，表明这是一个非常核心和固定的操作。
      - **UI构建**: 调用 `_create_toolbar()` 和 `_setup_layout()` 来创建和排列所有UI元素。

    - **`_create_toolbar(self)`**:
      - **功能**: 负责实例化所有的UI控件。
      - **逻辑**:
        - **分组**: 将功能相似的按钮分别创建在不同的 `CTkFrame` 容器中，如 `file_frame` (文件操作), `edit_frame` (编辑操作), `view_frame` (视图控制)。
        - **按钮创建**: 创建了大量的 `CTkButton`、`CTkLabel`、`CTkOptionMenu` 和 `CTkSlider`。
        - **事件连接**:
          - 大部分按钮的 `command` 参数都使用 `lambda: self._execute_callback('action_name')` 的形式。当按钮被点击时，它会调用 `_execute_callback`，并传入一个预定义的字符串动作名（如 `'export_image'`, `'undo'`, `'zoom_in'`）。
          - “显示选项”的 `CTkOptionMenu` 则直接将其 `command` 绑定到 `_on_display_option_changed` 方法，该方法内部再调用 `_execute_callback`。

    - **`_setup_layout(self)`**:
      - **功能**: 使用 `.grid()` 和 `.pack()` 混合布局，将创建好的按钮组和控件在工具栏上进行排列。

    - **数据流与核心方法**:
      - **`register_callback(self, action, callback)`**: 由父组件 `EditorFrame` 调用，将自身的方法注册到工具栏的回调字典中。例如，`EditorFrame` 会执行 `self.toolbar.register_callback('undo', self.undo)`，将工具栏的 `'undo'` 动作与 `EditorFrame` 的 `undo` 方法关联起来。
      - **`_execute_callback(self, action, *args)`**: 工具栏内部的事件派发中心。当用户点击一个按钮时，此方法被调用，它在回调字典中查找对应的动作名，并执行已注册的 `EditorFrame` 方法。
      - **`update_undo_redo_state(self, can_undo, can_redo)`**:
        - **功能**: 一个由外部（`EditorFrame`）调用的公共方法，用于**控制**撤销/重做按钮的**可用状态** (`"normal"` 或 `"disabled"`)。
        - **关联**: 当 `EditorFrame` 中的 `EditorHistory` 状态改变时，`EditorFrame` 会调用此方法来同步UI，确保在无法撤销/重做时，按钮是灰色的。
      - **`update_zoom_level(self, zoom_level)`**:
        - **功能**: 由外部调用的公共方法，用于更新缩放级别显示的百分比文本。
        - **关联**: 当 `TransformService` 的缩放等级变化时，`EditorFrame` 会收到通知，然后调用此方法来更新工具栏上的 `zoom_label`。

- **重构处置**: **解体与重构**

- **理由**:
    1.  **Tkinter依赖**: 完全基于 `customtkinter` 构建，无法直接迁移。
    2.  **回调耦合**: 与其他组件一样，它通过一个手动的回调字典与 `EditorFrame` 紧密耦合。

- **新架构中的替代方案**:
    - **`QToolBar`**: 新的工具栏将是一个 `QToolBar` 或一个继承自 `QWidget` 的自定义工具栏类。
    - **`QAction`**: 在Qt中，工具栏按钮的最佳实践是使用 `QAction`。可以为每个动作（如“导出”、“撤销”）创建一个 `QAction` 实例，并设置其文本、图标和快捷键。然后，可以将同一个 `QAction` 添加到主菜单和工具栏中，实现菜单项和工具栏按钮的逻辑联动。
    - **信号/槽**: `QAction` 的 `triggered` 信号将被连接到 `EditorController` 中对应的槽函数。例如，`undo_action.triggered.connect(editor_controller.undo)`。
    - **状态更新**: `update_undo_redo_state` 和 `update_zoom_level` 的功能将通过 `EditorController` 直接调用新工具栏视图的公共方法（槽函数）来实现。例如，当 `EditorModel` 的历史记录发生变化时，`EditorController` 会调用 `toolbar_view.set_undo_enabled(can_undo)`。这种方式比回调更加直观和类型安全。

---

### 文件: `desktop-ui/components/file_list_frame.py` (深度分析)

- **目的**: 此文件定义了 `FileListFrame` 类，即编辑器右侧的文件列表面板。它负责显示用户加载的图片文件列表，提供缩略图预览，并处理文件的选择、添加和移除等交互。

- **功能细节与组件关联**:

  - **`FileListFrame` 类 (继承自 `ctk.CTkFrame`)**:
    - **`__init__(self, parent, ...)`**:
      - **依赖注入 (回调)**: 构造函数接收大量回调函数作为参数，如 `on_file_select`, `on_load_files`, `on_file_unload`。这遵循了与 `EditorToolbar` 和 `PropertyPanel` 相同的模式，将所有业务逻辑的处理完全委托给父组件 `EditorFrame`。
      - **状态持有**:
        - `self.file_paths`: 一个列表，用于存储所有文件条目的路径。
        - `self.file_frames`: 一个字典，用于将文件路径映射到其对应的UI框架(`CTkFrame`)，方便后续的查找和删除。
        - `self.current_selection`: 存储当前被选中的文件条目UI框架的引用，用于处理高亮效果。
      - **UI构建**:
        - **头部按钮**: 创建“添加图片”、“添加文件夹”、“清空列表”三个按钮，并将它们的 `command` 直接绑定到从构造函数传入的 `on_load_files`, `on_load_folder`, `on_clear_list_requested` 回调上。
        - **滚动区域**: 创建一个 `ctk.CTkScrollableFrame` 作为可滚动的列表容器。

    - **文件列表管理**:
      - **`add_files(self, file_paths)`**:
        - **功能**: 向列表中添加一个或多个文件。
        - **逻辑**: 遍历传入的文件路径列表，如果文件尚未存在于 `self.file_paths` 中，则将其添加，并调用 `_add_file_entry` 为其创建UI条目。
      - **`_add_file_entry(self, file_path)`**:
        - **功能**: 为单个文件在滚动区域中创建一个可视化的条目。
        - **逻辑**:
          1.  创建一个 `CTkFrame` 作为该文件条目的容器。
          2.  **缩略图**: 使用 `PIL.Image.open` 打开图片，通过 `.thumbnail()` 创建一个40x40的缩略图，然后将其转换为 `ImageTk.PhotoImage` 并显示在一个 `CTkLabel` 中。包含一个 `try...except` 块，如果缩略图创建失败，则显示一个红色的“ERR”标签。
          3.  **文件名**: 创建一个 `CTkLabel` 显示 `os.path.basename(file_path)`。
          4.  **卸载按钮**: 创建一个小的“✕”按钮，其 `command` 通过 `lambda` 绑定到 `_on_unload_file` 方法，并传递当前文件的路径。
          5.  **点击事件**: **关键**，将整个条目框架(`entry_frame`)以及其内部的缩略图和文件名标签的 `<Button-1>` (左键点击) 事件都绑定到 `_on_entry_click` 方法。这确保了用户点击条目的任何位置都能触发选中效果。
      - **`remove_file(self, file_path)` / `clear_files(self)`**:
        - **功能**: 提供从列表移除单个文件或清空整个列表的公共接口。
        - **逻辑**: 它们会从 `self.file_paths` 和 `self.file_frames` 中移除对应的数据，并调用 `.destroy()` 来销毁UI控件，释放内存。

    - **事件处理与回调**:
      - **`_on_entry_click(self, file_path, frame)`**:
        - **功能**: 处理文件条目的点击事件。
        - **逻辑**:
          1.  将之前选中的条目（`self.current_selection`）的背景色恢复为默认。
          2.  将被点击的条目 `frame` 的背景色设置为高亮颜色。
          3.  更新 `self.current_selection` 为当前被点击的 `frame`。
          4.  调用 `self.on_file_select(file_path)` 回调，将选中的文件路径通知给父组件 `EditorFrame`。
      - **`_on_unload_file(self, file_path)`**:
        - **功能**: 处理单个文件卸载按钮的点击事件。
        - **逻辑**: 直接调用 `self.on_file_unload(file_path)` 回调，将要卸载的文件路径通知给 `EditorFrame`，由 `EditorFrame` 来处理后续的确认对话框和清理逻辑。

- **重构处置**: **解体与重构**

- **理由**:
    1.  **Tkinter依赖**: 完全基于 `customtkinter` 构建，其UI元素和布局逻辑无法直接迁移。
    2.  **回调耦合**: 严重依赖回调函数与父组件通信。

- **新架构中的替代方案**:
    - **`QListWidget`**: 这个组件的功能可以被 `QListWidget` 完美替代。
    - **自定义Item Widget**: 可以创建一个继承自 `QWidget` 的自定义 `FileListItemWidget`，其中包含一个 `QLabel` 用于显示缩略图，一个 `QLabel` 用于显示文件名，以及一个 `QPushButton` 用于卸载。
    - **`QListWidget.setItemWidget()`**: 通过循环调用 `QListWidget.addItem()` 和 `QListWidget.setItemWidget()`，可以将自定义的 `FileListItemWidget` 添加到列表中。
    - **信号/槽**:
      - `QListWidget` 的 `currentItemChanged` 信号可以连接到 `EditorController` 的槽函数，以处理文件选择事件。
      - 每个 `FileListItemWidget` 内部的卸载按钮的 `clicked` 信号可以发出一个包含其文件路径的自定义信号，该信号再被连接到 `EditorController` 的槽函数。

---

### 文件: `desktop-ui/components/context_menu.py` (深度分析)

- **目的**: 此文件定义了编辑器中右键上下文菜单的行为。它通过创建和管理一个原生的`tk.Menu`控件，根据当前的上下文（是否选中了区域、选中了多少个区域）动态地构建菜单项，并将用户的选择通过回调传递给上层逻辑。

- **功能细节与组件关联**:

  - **`ContextMenu` (基类)**:
    - **`__init__`**:
      - 持有对父组件(`parent_widget`)的引用，`tk.Menu`需要一个父窗口。
      - 实现了与其他组件相同的回调注册表 `self.callbacks`。
    - **`register_callback` / `_execute_callback`**: 标准的回调注册和执行方法，用于与父组件(`EditorFrame`)解耦。
    - **`set_selected_region(...)`**: 一个方法，允许父组件在显示菜单前，将当前选中的区域信息（索引和数据）传递给它。
    - **`show_menu(self, event, selection_count=0)`**:
      - **功能**: 核心的菜单显示方法。
      - **逻辑**:
        1.  `self.menu = tk.Menu(...)`: 创建一个 `tkinter` 的原生菜单实例。
        2.  **动态构建**: 
            - `if selection_count > 0`: 如果有选中的区域，则调用 `_add_region_menu_items()` 来添加与区域相关的菜单项（如“OCR识别”、“删除”）。
            - `else`: 如果没有选中任何区域（在画布空白处右键），则调用 `_add_general_menu_items()` 来添加通用菜单项（如“新建文本框”）。
        3.  `self.menu.tk_popup(event.x_root, event.y_root)`: 在鼠标光标的屏幕位置弹出菜单。

  - **`EditorContextMenu` (子类)**:
    - **目的**: 继承自 `ContextMenu`，专门实现编辑器画布中的上下文菜单逻辑。
    - **`_add_region_menu_items(self, selection_count=0)`**:
      - **功能**: 覆盖了基类的方法，用于动态构建选中区域时的菜单。
      - **逻辑**:
        - **通用操作**: “OCR识别”和“翻译”始终显示，可以对多个选中项进行批量操作。
        - **单选操作**: `if selection_count == 1:`，只有当用户只选中一个区域时，才显示“编辑属性”、“复制样式+内容”、“粘贴样式+内容”等针对单个目标的菜单项。
        - **删除操作**: “删除”项始终显示，并会在标签中动态地显示选中的项目数量，提升了用户体验。
    - **`_add_general_menu_items(self)`**:
      - **功能**: 覆盖基类方法，定义了在画布空白处右键时显示的菜单项，如“新建文本框”和“粘贴区域”。
    - **事件连接**: 所有 `menu.add_command` 的 `command` 参数都使用 `lambda` 调用 `_execute_callback`，将用户的选择（如`'ocr_recognize'`, `'delete_region'`）通知给 `EditorFrame`。

- **重构处置**: **逻辑迁移**

- **理由**:
    1.  **Tkinter依赖**: 直接使用了 `tkinter.Menu`，无法在Qt中复用。
    2.  **回调耦合**: 同样使用了回调字典与父组件通信。

- **新架构中的替代方案**:
    - **`QMenu`**: 新的上下文菜单将是一个 `QMenu` 实例。
    - **`QGraphicsView.contextMenuEvent`**: 在新的画布视图（`QGraphicsView`子类）中，需要覆盖 `contextMenuEvent(self, event)` 这个事件处理器。
    - **动态构建与信号/槽**:
      1.  在 `contextMenuEvent` 方法内部，首先判断鼠标下是否有选中的图形项 (`QGraphicsItem`)。
      2.  根据是否选中以及选中项的数量，动态地创建 `QAction` 并添加到 `QMenu` 中。
      3.  每个 `QAction` 的 `triggered` 信号将被连接到 `EditorController` 中对应的槽函数。例如，`delete_action.triggered.connect(editor_controller.delete_selected_items)`。
      4.  最后，调用 `menu.exec_(event.globalPos())` 在鼠标位置显示菜单。
    - 这种方式将菜单的创建和事件处理完全封装在视图的事件处理器中，并通过信号与控制器通信，比当前的回调方式更加符合Qt的设计哲学，也更为内聚。

---

### 文件: `desktop-ui/core/stable_geometry_engine.py` (深度分析)

- **目的**: 此文件定义了一个“稳定几何引擎”，其核心目标是解决一个在2D图形编辑中非常棘手的问题：当用户编辑一个已经旋转过的、非对称的组合图形时，由于其“视觉中心”和“几何包围盒中心”不一致，会导致图形在重新渲染时发生不期望的“跳变”。这个引擎通过引入“视觉锚点”和“坐标补偿”的概念，确保了用户所见即所得的流畅编辑体验。

- **功能细节与组件关联**:

  - **`VisualAnchor` (dataclass)**:
    - **功能**: 一个简单的数据类，用于表示一个点在屏幕上的“视觉锚点”。这个锚点是用户感知的、图形的旋转/缩放中心，它在编辑过程中应该保持稳定，不随几何形状的变化而跳动。

  - **`GeometryState` (dataclass)**:
    - **功能**: 核心数据结构。它将一个文本区域的所有几何信息封装在一起，与UI分离。
    - **属性**:
      - `raw_polygons`: **原始多边形坐标**。这是在物体未旋转时的坐标，是所有计算的基础。
      - `rotation_degrees`: 旋转角度。
      - `visual_anchor`: 该几何体在屏幕上应该围绕其旋转的**视觉锚点**。
    - **`get_backend_center()`**: 一个关键方法，它**模拟**了后端渲染引擎计算中心点的方式（即取所有点的几何包围盒的中心）。这个模拟的“后端中心”与“视觉锚点”的偏差，正是导致跳变的原因。

  - **`StableGeometryEngine` 类**:
    - **目的**: 包含所有核心算法的静态方法集合。
    - **`calculate_compensated_geometry(geometry_state)`**:
      - **核心补偿算法**: 这是整个引擎的灵魂。
      - **逻辑**:
        1.  调用 `geometry_state.get_backend_center()` 计算出后端将会使用的、不稳定的“几何中心”。
        2.  计算这个“几何中心”与用户期望的 `visual_anchor` 之间的偏移量 (offset)。
        3.  将这个 `offset` 应用于所有的 `raw_polygons`，生成一个新的、经过“补偿”的几何体。
      - **效果**: 这个经过补偿的新几何体，当被后端用其自己的算法计算中心点时，其结果将**恰好等于**我们期望的 `visual_anchor`。它通过预先“欺骗”后端，来抵消后端算法带来的视觉跳变。
    - **`get_visual_coordinates_for_display(geometry_state)`**:
      - **功能**: 获取用于在前端画布上直接绘制的坐标。
      - **逻辑**: 它首先获取补偿后的几何体，然后围绕 `visual_anchor` 将其旋转 `rotation_degrees` 度。返回的结果就是用户在屏幕上看到的最终形状。
    - **`get_backend_data_for_rendering(geometry_state)`**:
      - **功能**: 生成最终要保存到JSON文件、并发送给后端渲染引擎的数据。
      - **逻辑**: 它返回补偿后的几何体（`lines`）和原始的旋转角度（`angle`）。**关键**: 它返回的 `center` 字段是补偿后几何体的几何中心，这个中心点的值理论上应该和 `visual_anchor` 完全相同，从而保证了后端渲染结果与前端预览的一致性。
    - **`add_polygon_to_geometry(geometry_state, new_polygon_world)`**:
      - **功能**: 当用户在编辑模式下向现有区域添加一个新的多边形时，使用此函数。
      - **逻辑**:
        1.  将新多边形的“世界坐标”（屏幕上看到的坐标）通过**反向旋转**，转换回未旋转的“原始坐标”。
        2.  将这个新的原始多边形添加到 `raw_polygons` 列表中。
        3.  创建一个**新的** `GeometryState` 实例，**关键在于它沿用了旧的 `visual_anchor`**。
      - **效果**: 无论新添加的多边形在哪里，整个区域的视觉旋转中心都保持不变，从而避免了在添加新部分时整个区域发生位移。

  - **`RegionGeometryManager` 类**:
    - **目的**: 这是一个适配器/转换器类。
    - **`from_region_data(region_data)`**: 将从JSON加载的、传统的 `region_data` 字典，转换为引擎可以理解的、更健壮的 `GeometryState` 对象。
    - **`to_region_data(geometry_state, ...)`**: 将经过引擎稳定化处理的 `GeometryState` 对象，转换回后端可以渲染的 `region_data` 字典格式。

- **重构处置**: **核心保留与增强**

- **理由**:
    1.  **解决了核心痛点**: 这个引擎通过精妙的数学补偿，解决了高级2D图形编辑中的一个核心难题，其价值极高。
    2.  **高度抽象和独立**: 整个引擎是纯粹的数学和数据结构，与任何UI框架、甚至与应用的其他部分都完全解耦，是可复用、可测试的理想代码。

- **新架构中的建议**:    - **完全复用**: 这个文件应该被完整地迁移到新架构中，作为处理所有文本框几何操作的核心。    - **整合**: `editing_logic.py` 中的那些几何计算函数，其功能可以被这个更稳定、更高级的引擎所取代。在新的 `EditorController` 中，所有几何操作（移动、旋转、添加多边形等）都应该通过创建和更新 `GeometryState` 对象，并调用 `StableGeometryEngine` 的方法来完成。这将使得编辑逻辑更加稳健和可预测。

---

### 文件: `desktop-ui/components/mask_editor.py` (新分析)

- **目的**: 此文件定义了 `MaskEditor`，一个用于交互式编辑图像蒙版的专用全屏组件。它以一个独立的顶层窗口（`Toplevel`）形式出现，整合了用于绘图的画布、工具栏以及处理蒙版层上绘制操作（画笔和橡皮擦）的逻辑。

- **功能细节与组件关联**:
  - **`__init__`**:
    - 它是一个 `customtkinter.CTkToplevel`，意味着它会在主窗口之上创建一个新的独立窗口。
    - 接收一个 `PIL.Image` 对象作为背景，以及一个可选的 `numpy` 数组作为待编辑的蒙版。
    - 接收 `on_save` 和 `on_cancel` 回调函数，用于将编辑结果传回给打开它的父组件（很可能是 `EditorFrame`）。
    - 在顶部创建并放置一个 `MaskEditorToolbar` 实例，并将其工具栏的回调（`on_tool_change`, `on_brush_size_change`）连接到 `MaskEditor` 自身的方法（`_set_tool`, `_set_brush_size`）。
    - 初始化一个 `ctk.CTkCanvas` 用于绘图，并管理如工具、笔刷大小和蒙版数据等内部状态。
  - **图像与蒙版处理**:
    - `_setup_images`: 此方法负责准备显示内容。它将 `PIL` 图像和 `numpy` 蒙版数组转换为Tkinter画布可以显示的 `ImageTk.PhotoImage` 对象。它在画布上创建了两个图层：背景图层和蒙版图层，其中蒙版被显示为一个半透明的红色叠加层。
    - `_update_mask_display`: 在每次绘制操作后，此方法被调用，用于更新画布上蒙版的视觉表现，而无需重绘整个组件。
  - **绘制逻辑**:
    - `_setup_bindings`: 将画布的鼠标事件（如拖拽、释放）绑定到相应的绘制方法上。
    - `_paint`: 这是在鼠标拖拽过程中被调用的核心绘制方法。它获取鼠标坐标，根据当前选择的工具（画笔或橡皮擦）确定绘制颜色（白色255或黑色0），然后使用 `cv2.circle()` 函数直接在 `self.mask` 这个 `numpy` 数组上绘制一个圆形，从而直接修改蒙版数据。最后调用 `_update_mask_display` 来刷新屏幕显示。
    - `_on_drag_stop`: 鼠标释放时，最后调用一次 `_update_mask_display` 以确保最终状态被正确渲染。
  - **交互逻辑**:
    - `_save`: 当用户点击“保存”按钮时，调用 `self.on_save` 回调，将修改后的 `self.mask` 数组传回给父组件，然后销毁自身窗口。
    - `_cancel`: 当用户点击“取消”或窗口的关闭按钮时，调用 `self.on_cancel` 回调，然后销毁自身窗口。

- **重构处置**: **删除并在Qt中重建**

- **理由**:
  1.  **Tkinter依赖**: 整个组件完全由 `customtkinter` 和 `tkinter` 的原生控件（`Toplevel`, `Canvas`）构建，无法迁移到Qt。
  2.  **模态窗口逻辑**: 它实现了一个独立的、类似模态窗口的UI模式，这在Qt中很容易复现。
  3.  **核心逻辑可移植**: 其核心的绘制逻辑——使用 `cv2` 直接在 `numpy` 数组上操作像素——是独立于UI框架的，可以在新架构中保留。

- **新架构中的替代方案**:
    - 创建一个新的 `MaskEditorDialog` 类，继承自 `QDialog`，以提供期望的模态对话框行为。
    - 视图部分将由 `QGraphicsView` 和 `QGraphicsScene` 构成。背景图是一个 `QGraphicsPixmapItem`，蒙版可以是另一个具有半透明效果的 `QGraphicsPixmapItem`，叠放在上层。
    - 绘制逻辑可以类似地实现：捕获 `QGraphicsView` 上的鼠标事件，然后使用 `QPainter` 直接在一个代表蒙版的 `QPixmap` 对象上进行绘制。绘制完成后，更新蒙版对应的 `QGraphicsPixmapItem` 即可。
    - `MaskEditorToolbar` 将作为一个独立的 `QWidget`（如前分析）被包含在对话框的布局中。
    - 不再使用回调，对话框将定义 `accepted(np.ndarray)` 和 `rejected()` 等信号。`EditorController` 在创建并执行（`.exec()`）此对话框后，通过连接这些信号来获取操作结果。

---

### 文件: `desktop-ui/components/ocr_result_dialog.py` (新分析)

- **目的**: 此文件定义了 `OcrResultDialog`，一个在OCR（光学字符识别）操作后弹出的模态对话框。它允许用户比较原始文本和新识别的文本，手动编辑两者，并决定如何合并新文本（替换、追加或确认手动编辑）。

- **功能细节与组件关联**:
  - **`__init__`**:
    - 继承自 `customtkinter.CTkToplevel` 来创建一个新窗口。
    - 接收 `original_text`（原文）、`recognized_text`（识别文本）和一个 `on_confirm` 回调作为输入。
    - 通过调用 `self.transient(parent)` 和 `self.grab_set()`，它将自身设置为一个模态对话框，阻止用户与父窗口交互，直到此对话框关闭。
    - 调用辅助方法来构建UI (`_create_widgets`) 和将对话框居中 (`_center_dialog`)。
  - **UI布局 (`_create_widgets`)**:
    - 布局由多个框架组成。
    - 包含两个核心的 `CTkTextbox` 控件，分别用于显示原文和识别文本，两者都预先填充了内容且允许用户编辑。
    - 底部有一个按钮栏，提供四个操作：
      - “替换原文”：一个快捷按钮，用识别文本替换原文文本框的内容。
      - “追加到原文”：一个快捷按钮，将识别文本追加到原文文本框的末尾。
      - “确认修改”：主要的操作确认按钮。
      - “取消”：关闭对话框。
  - **交互逻辑**:
    - `_on_replace` / `_on_append`: 处理快捷按钮的逻辑，直接操作 `original_textbox` 的内容。
    - `_on_confirm_changes`: 这是成功操作的主要出口。它会从两个文本框中读取最终的、可能已被用户编辑过的内容，然后调用 `on_confirm` 回调函数，将最终的文本传回给父组件（`EditorFrame`）。最后，它销毁对话框窗口。
    - `_on_cancel`: 处理取消操作，仅销毁窗口。
    - 绑定了 `<Escape>` (取消) 和 `<Return>` (确认) 的键盘快捷键。
  - **`get_result`**: 定义了此方法，但在典型的回调流程中似乎并未使用。它提供了一种在窗口关闭后获取最终状态的方式，但回调模式在此处是主要的数据返回方式。
  - **`show_ocr_result_dialog`**: 一个全局辅助函数，用于方便地创建和返回该对话框的实例。

- **重构处置**: **删除并在Qt中重建**

- **理由**:
  1.  **Tkinter依赖**: 该组件完全使用 `customtkinter` 构建，无法移植。
  2.  **标准UI模式**: 它实现了一个非常标准的“确认/编辑对话框”模式，这是任何UI工具包的基础功能。
  3.  **基于回调的通信**: 它依赖回调函数 (`on_confirm`) 来返回数据，这种模式将在新架构中被取代。

- **新架构中的替代方案**:
    - 创建一个新的 `OcrResultDialog` 类，继承自 `QDialog`。
    - 使用 `QTextEdit` 作为文本区域，`QPushButton` 作为按钮来重建布局。
    - 当通过 `.exec()` 打开时，`QDialog` 默认就是模态的。
    - “替换”和“追加”按钮的逻辑将在新的 `QDialog` 子类中作为私有槽函数实现。
    - 对话框将提供公共的getter方法，如 `get_final_texts() -> (str, str)`，而不是使用回调。
    - 将使用 `QDialog` 的标准信号 `accepted` 和 `rejected`。主“确认”按钮将连接到 `self.accept()` 槽，而“取消”按钮将连接到 `self.reject()` 槽。
    - 调用代码（新的 `EditorController`）的逻辑将变为：
      ```python
      dialog = OcrResultDialog(parent, original, recognized)
      if dialog.exec():  # 此处将阻塞，直到对话框关闭
          final_original, final_recognized = dialog.get_final_texts()
          # ...处理返回的结果...
      ```
      这是在Qt中处理模态对话框及其返回值的标准、惯用方法。

---

### 文件: `desktop-ui/components/ocr_translation_manager.py` (新分析)

- **目的**: 此文件定义了 `OcrTranslationManager` 类。其意图是作为一个中心管理器，处理由上下文菜单（右键菜单）或键盘快捷键触发的OCR和翻译工作流。

- **功能细节与组件关联**:
  - **`__init__`**: 它尝试通过 `services` 模块的 `get_..._service()` 函数来初始化 `OcrService`, `TranslationService` 和 `ConfigService`，表明它知道服务化架构的存在。
  - **回调地狱**: 整个类都围绕一个 `self.callbacks` 字典构建。它不直接执行操作，而是依赖于执行由父组件（推测是 `EditorFrame` 这个“上帝对象”）注册的回调。例如，为了执行OCR，它需要先调用一个名为 `'get_selected_region_index'` 的回调，才能知道要对*什么*进行OCR。这是设计混乱和紧密耦合的强烈信号。
  - **占位符逻辑**: 核心方法 `ocr_recognize`, `translate_text` 等不包含真实逻辑。它们定义了仅通过 `time.sleep()` 模拟工作的占位符函数 (`ocr_operation`)，然后将这些函数传递给一个外部注入的 `operation_manager` 来执行。这表明该类要么是一个模拟对象，要么是一个已被废弃的架构草稿。
  - **反向数据流**: 用于处理右键菜单和快捷键的方法，其数据流是反向的：它们通过 `_execute_callback` 从UI获取数据（如 `get_selected_region_index`），然后触发一个操作，最后再调用另一个回调（如 `ocr_result`）将结果推回给UI。这是一个非常迂回和混乱的数据流。

- **重构处置**: **删除**

- **理由**:
  1.  **过时的架构**: 这个类是旧架构中“上帝对象”问题的另一面。它是一个卫星对象，完全依赖于 `EditorFrame` 来获取数据和执行动作，完全通过一个复杂的回调网络进行通信。它自身不持有状态，也没有真正的业务逻辑。
  2.  **功能冗余**: 在目标MVC/服务架构中，它的职责已经被其他设计得更好的组件所覆盖：
      - 实际的OCR/翻译工作由 `OcrService` 和 `TranslationService` 完成。
      - 对这些服务的编排工作应该由新的 `EditorController` 负责。
      - 快捷键管理应由专门的 `ShortcutManager` 服务处理，或由主窗口及其 `QAction` 直接处理。
      - 右键菜单的动作应该从菜单的 `QAction` 直接连接到 `EditorController` 的槽函数。
  3.  **代码是占位符**: 核心功能只是 `time.sleep()`，表明它不是当前应用的一个功能性部分。

- **新架构中的替代方案**:
    - 这个类将**不会**被迁移或重建。它的职责将被新的 `EditorController` 完全吸收。
    - 例如，当右键菜单的“OCR” `QAction` 被触发时，`EditorController` 中的一个槽函数会被调用。该槽函数将：
        1.  从 `EditorView` (即 `QGraphicsScene`) 获取当前选中的图形项。
        2.  从 `EditorModel` 获取相应的数据。
        3.  调用 `async_service.submit_task(ocr_service.recognize_region(...))` 来执行异步任务。
        4.  任务完成后，更新 `EditorModel` 中的数据。
        5.  `EditorModel` 通知 `EditorView` 和 `PropertyPanel` 等视图更新显示。
    - 这个流程创建了一个清晰的、单向的数据流，并消除了对这个令人困惑的中间管理器的需求。

---

### 文件: `desktop-ui/components/progress_dialog.py` (新分析)

- **目的**: 此文件旨在为耗时操作（如OCR和翻译）提供可视化的进度反馈。但它将一个纯UI组件 (`ProgressDialog`) 与一个类似控制器的类 (`OperationManager`) 捆绑在了一起。

- **`ProgressDialog` 类分析**:
  - **目的**: 一个UI组件，用于显示一个带消息、进度条和取消按钮的模态对话框。
  - **功能细节**:
    - 继承自 `customtkinter.CTkToplevel` 并通过 `grab_set()` 设置为模态对话框。
    - 提供了 `set_progress`, `set_message`, `set_indeterminate` (不确定模式/滚动条) 和 `set_cancellable` 等方法来控制UI。
    - `_on_cancel` 方法设置一个 `is_cancelled` 标志并销毁窗口，该标志意图被工作线程检查以中断操作。
  - **评价**: 这是一个标准的可复用UI组件。其实现与Tkinter绑定，但其*概念*是有效的。

- **`OperationManager` 类分析**:
  - **目的**: 此类被设计为接收一个函数，在后台线程中运行它，并在运行时显示 `ProgressDialog`。
  - **功能细节**:
    - **线程模型**: 为每个操作都手动创建一个新的 `threading.Thread`。这是一种非常原始的后台任务处理方式。
    - **UI耦合与线程安全问题**: 工作线程直接调用 `self.current_dialog.set_progress(...)` 等方法来更新UI。这是一个严重的问题，因为Tkinter（和大多数UI工具包一样）**不是线程安全的**，从后台线程直接更新UI可能导致不可预测的行为和崩溃。尽管代码尝试在最后一步通过 `parent_widget.after(0, ...)` 来安全地调度回调，但所有的中间进度更新都是不安全的直接调用。
    - **占位符逻辑**: 工作函数中包含硬编码的 `time.sleep()` 和伪造的进度更新，表明这很可能是非功能性的示例代码。
  - **评价**: 这是一个设计糟糕的控制器。它混淆了任务执行逻辑与UI管理，并使用了不安全的线程模型。其职责与 `AsyncService` 和未来的 `EditorController` 完全重叠。

- **重构处置**: **拆分与重构**
    - `ProgressDialog` 类的概念应该**在Qt中被重建**。
    - `OperationManager` 类应该被**完全删除**。

- **理由**:
  1.  **职责混淆**: 该文件将视图 (`ProgressDialog`) 与控制器 (`OperationManager`) 捆绑在一起，违反了单一职责原则。
  2.  **不安全的线程**: `OperationManager` 从后台线程执行不安全的UI更新。
  3.  **架构冗余**: `OperationManager` 的全部目的（在后台运行任务并显示进度）是应用主控制器（如 `EditorController` 或 `AppLogic`）的核心职责，应由主控制器与一个健壮的后台任务服务（如已有的 `AsyncService`）协同完成。

- **新架构中的替代方案**:
    - **`QProgressDialog`**: Qt拥有一个内置的、功能强大的 `QProgressDialog` 类，完美适用于此场景。它是模态的，自带进度条、标签和取消按钮，并被设计为与后台任务轻松集成。
    - **控制器驱动的工作流**: 新的 `EditorController` 将负责整个工作流程：
        1.  当一个动作（如“执行OCR”）被触发时，`EditorController` 创建一个 `QProgressDialog`。
        2.  控制器创建一个包含实际业务逻辑（调用 `OcrService`）的工作对象（例如一个 `QRunnable` 或一个将被移至 `QThread` 的 `QObject`）。该工作对象将定义用于报告进度的信号（如 `progress_updated(int, str)`）。
        3.  将 `QProgressDialog` 的槽函数（如 `setValue` 和 `setLabelText`）连接到工作对象的进度信号上。将对话框的 `canceled` 信号连接到工作对象的一个槽函数上，以实现操作的中断。
        4.  控制器将工作对象提交给后台任务服务（`AsyncService` 或 `QThreadPool`）。
        5.  控制器调用 `progress_dialog.exec()` 来显示对话框。
    - 这种方法使用Qt原生的、线程安全的信号和槽机制在后台任务和进度对话框之间进行通信，从而实现一个健壮、清晰且可维护的实现。

---

### 文件: `desktop-ui/components/text_renderer_backend.py` (新分析)

- **目的**: 此文件定义了 `BackendTextRenderer`。其目的在于提供一个高度精确的、“所见即所得”（WYSIWYG）的文本渲染预览。它通过直接调用与最终 `manga-translator` 命令行工具相同的渲染函数（`put_text_horizontal`, `put_text_vertical`）来实现此目标，设计为画布的一个可插拔渲染器。

- **功能细节与组件关联**:
  - **`__init__`**: 持有对Tkinter画布的引用，并初始化一个缓存（`_text_render_cache`）来存储预渲染的文本图像，这是关键的性能优化。
  - **字体管理 (`update_font_config`)**:
    - 此方法负责通知后端渲染引擎使用哪种字体。
    - 它使用 `resource_path` 辅助函数来正确定位字体文件，无论应用是从源码运行还是作为PyInstaller打包运行。
    - 调用 `manga_translator` 库的 `set_font`。
    - 关键是，当字体更改时，它会清除渲染缓存，强制所有可见文本用新字体重新渲染。
  - **主绘制逻辑 (`draw_regions`)**:
    - 这是主入口点，由父组件（如 `CanvasRenderer`）调用以绘制所有文本框。
    - 遍历 `TextBlock` 对象列表（来自后端库的数据结构）。
    - 根据可见性标志（`self.text_visible`, `self.boxes_visible`）和选择状态，决定是否为每个文本块绘制文本、边界框和交互手柄。
    - 将不同视觉元素的实际绘制委托给辅助方法（`_draw_region_text`, `_draw_region_box`, `_draw_handles`）。
  - **文本渲染 (`_draw_region_text`)**:
    - **这是该文件的核心。**
    - **文本处理**: 首先将换行符（`↵`, `<br>`, `[BR]`）规范化为 `\n`。它还调用后端函数 `auto_add_horizontal_tags` 为竖排文本自动包裹符号以实现水平渲染。
    - **缓存**: 为当前文本内容及其样式参数生成唯一的 `cache_key`。如果 `_text_render_cache` 中存在预渲染的图像，则直接使用。
    - **后端调用**: 如果没有缓存版本，则调用实际的后端渲染函数（`put_text_horizontal` 或 `put_text_vertical`）。此函数返回一个 `numpy` 数组，表示在透明背景上渲染的文本。
    - **结果缓存**: 返回的 `numpy` 数组被存储在缓存中。
    - **变形与显示**: 渲染的文本图像（一个简单的矩形）随后通过 `cv2.warpPerspective` 进行变换，以适应画布上代表文本框位置的倾斜四边形（`dst_points`）。
    - 最后，将变形后的图像转换为 `PhotoImage` 并绘制到Tkinter画布上。
  - **框与手柄绘制 (`_draw_...`)**: 包含多个辅助方法，使用 `create_polygon`、`create_oval` 等直接在画布上绘制各种调试框和交互手柄。

- **重构处置**: **逻辑吸收与改造**

- **理由**:
  1.  **WYSIWYG的“实现方式”**: 此文件包含了实现真正所见即所得编辑器的关键逻辑。其“调用后端库生成预览位图，然后将其变形到位”的核心原则是确保编辑器预览与最终输出匹配的正确且最稳健的方法。这个核心原则*必须*被保留。
  2.  **Tkinter依赖**: 然而，其实现完全与Tkinter绑定。它直接在 `ctk.CTkCanvas` 上绘制，使用 `ImageTk.PhotoImage`，其绘制方法特定于Tkinter的坐标系。
  3.  **与 `CanvasRenderer` 的冗余**: 此类的职责似乎与 `canvas_renderer_new.py` 有重叠。指南表明 `CanvasRenderer` 是主渲染器，它再将文本渲染委托给此类。这种分离有些笨拙。

- **新架构中的替代方案**:
    - 此类的逻辑将不作为单独的渲染器存在。相反，其职责将被代表文本区域的新 `QGraphicsItem`（我们称之为 `RegionItem`）所吸收。
    - `RegionItem` 的 `paint()` 方法（或其调用的辅助方法）将负责渲染文本。
    - `RegionItem` 内部的工作流程将是：
        1.  检查缓存（可以是 `RegionItem` 上的一个简单字典或更复杂的全局缓存服务）中是否有预渲染的文本 `QPixmap`。
        2.  如果未找到，则调用相同的后端函数（`put_text_horizontal` 等）获取 `numpy` 数组。
        3.  将 `numpy` 数组转换为 `QImage`，然后是 `QPixmap`，并存入缓存。
        4.  `paint()` 方法随后将使用 `QPainter.drawPixmap()` 绘制缓存的 `QPixmap`。`cv2.warpPerspective` 的变形逻辑将被替换为在绘制前对 `QPainter` 设置一个 `QTransform`，这是Qt处理此类变换的原生方式。
    - 这种方法保留了核心的WYSIWYG逻辑，但以一种清晰、符合Qt习惯的方式实现，将文本框的渲染完全封装在其自己的 `QGraphicsItem` 中。

---

### 文件: `desktop-ui/components/text_renderer_modified.py` (新分析)

- **目的**: 此文件定义了 `TextRenderer` 类。它是一个更高级、更复杂的渲染器，试图成为一个自包含的渲染引擎，能够在一个“简单”渲染模式（使用Tkinter的`create_text`）和一个“所见即所得”模式（使用`manga-translator`后端，类似于`text_renderer_backend.py`）之间切换。它还绘制区域边框和交互手柄，承担了本应属于其他渲染器或组件的职责。

- **功能细节与组件关联**:
  - **`__init__`**:
    - 它检查后端 `text_render` 模块是否可用，并设置一个 `self.backend_available` 标志。
    - 它有一个 `wysiwyg_mode` 标志来切换渲染方法。
    - 它维护自己的 `render_cache`。
    - 它调用 `_initialize_fonts` 来查找并为后端设置默认字体，以确保一致性。
  - **模式切换 (`set_wysiwyg_mode`)**: 允许父组件在简单和WYSIWYG渲染之间切换。切换时会清空缓存。
  - **主绘制逻辑 (`draw_region`)**:
    - 这是主入口点。对于给定的区域，它首先调用 `_draw_region_border` 来绘制框和手柄。
    - 然后，根据 `self.wysiwyg_mode`，调用 `_render_text_wysiwyg` 或 `_render_text_simple`。
  - **`_draw_region_border`**: 这个方法职责混乱。它绘制文本区域的多边形轮廓。如果区域被选中，它还会直接导入和使用 `editing_logic` 来计算并绘制旋转和缩放手柄。这是视图（绘制）和控制器（几何计算）逻辑混杂的明显标志。
  - **`_render_text_wysiwyg`**: 此方法的逻辑与 `text_renderer_backend.py` 中的逻辑非常相似。它生成一个缓存键，如果缓存未命中，则调用 `_execute_backend_render`。
  - **`_execute_backend_render`**: 这是WYSIWYG模式的核心。它收集所有必要的渲染参数（字体大小、颜色、对齐方式等），确定文本方向（水平/垂直），并调用适当的后端函数（`text_render.put_text_horizontal` 或 `text_render.put_text_vertical`）。然后将生成的numpy数组处理成PIL图像。
  - **`_render_text_simple`**: 这是备用模式。它使用Tkinter的 `canvas.create_text` 来绘制文本。这种渲染速度快，但不能准确地表示最终输出的换行、字体度量或样式。
  - **参数和颜色解析**: 它有几个辅助方法（`_get_render_parameters`, `_parse_color`, `_normalize_alignment`）来将区域字典中的数据转换为后端渲染函数所需的确切格式。

- **重构处置**: **删除**

- **理由**:
  1.  **架构遗物**: 这个类是一个“上帝渲染器”。它试图做所有事情：绘制边框、绘制手柄、管理字体、在两个完全不同的渲染管线之间切换，以及解析复杂的参数。这是一个在清晰的渲染管线建立之前的架构混乱的产物。
  2.  **被更好的设计所取代**: 在其他已分析文件中建立的模式（`CanvasRenderer` 委托给 `BackendTextRenderer`）虽然仍有缺陷，但是更好的职责分离。而最佳方法，如在 `text_renderer_backend.py` 分析中所述，是将此逻辑移至 `QGraphicsItem` 子类中。
  3.  **极端耦合**: 它与Tkinter、后端渲染库耦合，甚至通过导入 `editing_logic` 包含了本不属于它的几何逻辑。这使得它无法维护或重用。

- **新架构中的替代方案**:
    - 这个类将被完全丢弃。其功能将被新架构中更合适的组件分担：
        - **WYSIWYG渲染逻辑**: 如 `text_renderer_backend.py` 分析中所详述，这将并入自定义 `RegionItem`（`QGraphicsItem`子类）的 `paint()` 方法中。
        - **简单渲染**: “简单”或“草稿”渲染模式仍然可以在 `RegionItem.paint()` 方法中实现。它将使用 `QPainter.drawText()` 而不是完整的后端管线。可以通过 `RegionItem` 或 `QGraphicsScene` 上的一个标志来切换此模式。
        - **边框和手柄绘制**: 这是 `QGraphicsItem` 的经典用例。主形状在 `paint()` 中绘制。如果 `option.state & QStyle.State_Selected`，则可以绘制选择手柄。应重写 `shape()` 方法以提供精确的轮廓用于命中检测。
    - 通过将这些职责移至 `RegionItem`，文本框的渲染和交互逻辑被完美地封装在一个单一、可复用的类中，遵循了Qt的设计模式。

---

### 文件: `desktop-ui/core/test_anti_jump.py` (新分析)

- **目的**: 这是一个**命令行测试脚本**，专门用于验证 `stable_geometry_engine.py` 的功能。其唯一目的是运行一系列自动化测试，确保几何引擎的“反跳变”逻辑在各种操作（如旋转、添加新多边形）下都能正确工作。

- **功能细节与组件关联**:
  - **独立性**: 它直接从 `stable_geometry_engine.py` 导入所需的类，不依赖任何UI框架（Tkinter或Qt）。
  - **`AntiJumpTester` 类**: 该类封装了所有的测试用例。
    - `test_basic_consistency`: 测试一个标准的旋转框被处理后，其计算出的后端中心点是否与视觉锚点一致。
    - `test_rotation_stability`: 将一个文本框旋转到多个不同角度，并验证其视觉锚点在整个过程中是否保持稳定。
    - `test_geometry_addition_no_jump`: 模拟向一个已旋转的文本框添加新的多边形，并验证此操作是否会导致视觉锚点发生“跳变”。
    - `test_complex_scenario`: 将多次旋转和添加操作串联起来，以测试在复杂变换下的稳定性。
  - **执行与报告**: 该脚本可以通过命令行直接运行。它会执行所有测试，在控制台打印详细日志，并最终生成一个名为 `anti_jump_test_report.json` 的测试报告文件。

- **重构处置**: **忽略（或作为开发者工具保留）**

- **理由**:
  1.  **非应用组件**: 这是一个开发者测试脚本，不是交付给最终用户的应用程序的一部分。它不参与主应用的UI或逻辑流程。
  2.  **高开发价值**: 尽管不是最终产品的一部分，但这个脚本非常有价值。它提供了一种自动化的方式来验证编辑器中最复杂、最关键的逻辑之一。它应该与 `stable_geometry_engine.py` 一起保留，作为开发工具，以确保未来的修改不会破坏几何计算的稳定性。
  3.  **无需重构**: 作为一个独立的、无UI依赖的脚本，它不需要被重构到Qt应用中。

- **新架构中的替代方案**:
    - 在更成熟的项目中，这类逻辑验证可能会被整合到像 `pytest` 这样的正式测试框架中。然而，在当前范围内，它作为一个独立脚本已经很好地完成了其任务。在本次重构分析中，我们只需了解其用途，无需对其进行应用级别的重构。

---

### 文件: `desktop-ui/services/drag_drop_service.py` (新分析)

- **目的**: 此文件定义了 `DragDropHandler` 和 `MultiWidgetDragDropHandler`，用于为Tkinter控件添加文件拖放功能。它旨在抽象处理不同拖放数据格式和事件的复杂性。

- **`DragDropHandler` 类分析**:
  - **目的**: 使单个Tkinter控件成为有效的文件拖放目标。
  - **功能细节**:
    - **初始化**: 接收一个 `target_widget`（目标控件）和一个 `drop_callback`（拖放回调函数）。它使用一个（未显式导入但从`dnd_bind`调用推断出的）Tkinter拖放库来注册控件。
    - **事件绑定**: 绑定 `<<Drop>>`, `<<DragEnter>>`, `<<DragLeave>>` 等事件来管理拖放的生命周期。
    - **视觉反馈**: `_on_drag_enter` 和 `_on_drag_leave` 方法通过改变控件边框来提供视觉提示，告知用户这是一个有效的拖放区域。
    - **数据提取 (`_extract_file_paths`)**: `_on_drop` 方法负责解析事件数据，这些数据可能是换行符分隔的字符串或URI列表等多种格式，并从中提取出干净的文件路径列表。它能处理 `file:///` 这样的URI协议并进行URL解码。
    - **处理**: 提取路径后，它会调用注入的 `file_service` 来过滤有效文件，最后用干净的文件列表调用 `drop_callback`。

- **`MultiWidgetDragDropHandler` 类分析**:
  - **目的**: 一个管理类，允许为多个不同的控件注册同一个 `drop_callback`。
  - **功能细节**: 它维护一个 `DragDropHandler` 实例列表。`add_widget` 方法会为一个给定的控件创建一个新的 `DragDropHandler`，从而简化了将相同拖放逻辑应用于UI不同部分的任务。

- **重构处置**: **删除并在Qt中重建**

- **理由**:
  1.  **Tkinter特定**: 整个实现基于一个Tkinter的拖放库和事件绑定系统，完全无法移植。
  2.  **Qt内置功能**: Qt拥有原生的、强大的、跨平台的拖放操作支持。这个自定义实现对于Qt应用来说是完全多余的。

- **新架构中的替代方案**:
    - 该服务将被完全移除。
    - 在新的Qt `MainWindow` 或任何相关的 `QWidget` 中，启用拖放功能只需：
        1.  调用 `self.setAcceptDrops(True)`。
        2.  在控件中重新实现三个事件处理器：
            *   `dragEnterEvent(self, event)`: 当拖动进入控件时调用。在此检查拖动的数据是否包含URL（`event.mimeData().hasUrls()`）。如果是，则调用 `event.acceptProposedAction()` 来改变光标，表示这是一个有效的放置目标。
            *   `dragLeaveEvent(self, event)`: 当拖动离开时调用，用于清除视觉反馈。
            *   `dropEvent(self, event)`: 当用户放下文件时调用。通过 `[url.toLocalFile() for url in event.mimeData().urls()]` 即可获取文件路径列表。
    - 原 `_process_dropped_files` 中的逻辑（即调用 `FileService` 验证文件）将被直接移入新的Qt控件或其控制器的 `dropEvent` 处理器中。
    - 这种方法是Qt中处理拖放的标准、惯用方式，无需外部库，代码更清晰、更易于维护。

---

### 文件: `desktop-ui/services/erase_config_service.py` (新分析)

- **目的**: 此文件定义了 `EraseConfigService`。其职责是集中管理所有与图像修复（擦除）算法相关的配置。它统一了可用的算法选项、它们的属性以及用户的当前设置。

- **功能细节与组件关联**:
  - **数据结构**:
    - `InpainterType` (Enum): 定义了所有可用的修复算法（如 `LAMA_LARGE`, `STABLE_DIFFUSION`）。
    - `InpaintPrecision` (Enum): 定义了计算精度（`fp32`, `fp16`）。
    - `InpainterConfig` (dataclass): 用结构化的方式持有当前用户的配置（使用哪种算法、修复尺寸、精度）。
    - `AlgorithmInfo` (dataclass): 为每种算法定义的元数据结构，存储其显示名称、描述和能力（如是否支持GPU、是否适合预览）。这个设计对于动态构建UI界面非常有利。
  - **`EraseConfigService` 类**:
    - **`__init__`**: 它初始化一个默认的 `InpainterConfig`，并填充一个 `self.algorithm_info` 字典，该字典作为所有可用算法及其属性的静态注册表。
    - **配置读写**:
      - `load_config_from_file`: 从主JSON配置文件中读取 `"inpainter"` 部分，并用其内容更新 `self.current_config`。
      - `save_config_to_file`: 读取主JSON配置文件，用当前设置更新 `"inpainter"` 部分，然后将整个文件写回。
    - **Getter/Setter API**: 为应用的其他部分提供了一套清晰的API，用于：
      - `get_algorithm_list()`: 获取所有可用算法及其元数据的列表（非常适合用于填充下拉菜单）。
      - `get_preview_suitable_algorithms()`: 获取一个速度足够快、适合实时预览的算法子集。
      - `set_algorithm()`, `set_inpainting_size()`, `set_precision()`: 用于更改当前配置的方法。
      - `get_current_config()`: 获取当前的 `InpainterConfig` 配置对象。
  - **单例模式**: 和其他服务一样，它通过模块级的全局变量和 `get_erase_config_service()` 函数来实现单例模式，确保整个应用共享同一个服务实例。

- **重构处置**: **保留**

- **理由**:
  1.  **优秀的设计**: 这是一个设计良好的服务。它完美地封装了与特定领域（修复配置）相关的所有逻辑。
  2.  **数据驱动UI**: `AlgorithmInfo` 和 `get_algorithm_list` 等方法的使用，使得构建数据驱动的UI变得非常容易。UI可以向服务查询“有哪些可用算法？”以及“它们的属性是什么？”，而无需任何硬编码知识。
  3.  **框架无关**: 该服务是纯Python实现，不依赖任何UI框架，可以无缝集成到新的Qt架构中。
  4.  **关注点分离清晰**: 它清晰地分离了修复过程的*配置*与*执行*（执行将由另一个服务，如 `InpaintingService` 来处理，而该服务会*使用*本配置服务）。

- **新架构中的替代方案**:
    - 无需重大修改。该服务可以原封不动地迁移到新项目的 `services` 目录中。
    - 新Qt应用中的UI组件（如设置对话框）将调用 `get_erase_config_service()` 来获取实例，然后使用其方法来填充UI控件。当用户更改设置时，UI将调用服务上相应的setter方法（如 `set_algorithm(...)`）。
    - 一个潜在的改进是添加一个基于信号的通知系统（类似于 `ConfigService` 或 `StateManager` 中的机制），这样如果配置被以编程方式更改，任何相关的UI组件都会被自动通知以更新其状态。例如，它可以继承自 `QObject` 并定义一个 `config_changed = pyqtSignal()` 信号。

---

### 文件: `desktop-ui/services/export_service.py` (新分析)

- **目的**: 此文件定义了 `ExportService`。其唯一的、关键的职责是获取已编辑图像的最终状态（包括基础图像、带翻译的区域数据和当前配置），并使用后端的 `manga-translator` 库来生成最终的渲染图像文件。

- **功能细节与组件关联**:
  - **全局输出目录**: 它使用一个全局变量 (`_global_output_directory`) 来缓存输出目录路径。其 `get_output_directory` 方法的实现有些复杂，它首先尝试从这个全局缓存获取路径，如果失败，则通过反向查找Tkinter控件树来寻找输出目录的输入框。这种备用方案是一种脆弱且不推荐的设计模式。
  - **`export_rendered_image`**: 这是主要的公共方法，被设计为非阻塞式。它接收所有必要的数据，然后启动一个新的 `threading.Thread` 来在 `_perform_backend_render_export` 中执行实际工作，从而避免UI冻结。
  - **`_perform_backend_render_export`**: 这是在后台线程中运行的核心工作流。
    1.  **创建临时环境**: 它创建一个临时目录。这是关键一步，因为后端库被设计为处理磁盘上的文件，此方法通过模拟这种文件环境来与后端交互。
    2.  **保存临时文件**: 它将当前图像保存为临时的 `temp_image.png`，然后调用 `_save_regions_data` 将区域数据保存到同一临时目录下的 `_translations.json` 文件中。
    3.  **准备后端调用**: 它调用 `_prepare_translator_params` 来为后端组装配置参数。最关键的是，它设置了 `load_text=True` 和 `translator='none'`。这告诉后端**不要**执行任何翻译，而是直接从提供的 `_translations.json` 文件中加载文本，并立即进入渲染阶段。
    4.  **执行后端渲染**: 它调用 `_execute_backend_render`，该方法导入并创建 `MangaTranslator` 实例，然后调用 `translator.translate()`。由于上一步设置的参数，这个 `translate` 调用实际上变成了一个“仅渲染”操作。
    5.  **合成与保存**: 后端仅返回渲染好的文本图层。此方法随后将该图层粘贴到原始图像上（`final_image.paste(...)`）。最后，它将结果图像保存到用户指定的 `output_path`，并能正确处理JPEG/WEBP的保存质量设置。
  - **`_save_regions_data`**: 一个复杂的辅助方法，负责将编辑器内部的 `regions_data` 格式转换为后端 `--load-text` 模式所期望的精确JSON结构。
  - **单例模式**: 使用标准的 `get_export_service()` 函数来提供全局单例。

- **重构处置**: **保留**

- **理由**:
  1.  **优秀的抽象**: 该服务是“防腐层”的一个绝佳例子。它巧妙地弥合了编辑器中交互式的内存数据与后端库面向文件的命令行式特性之间的鸿沟。其“创建临时目录并模拟命令行环境”的策略是一个聪明且健壮的解决方案。
  2.  **职责清晰**: 其职责非常明确：导出最终产品。
  3.  **框架无关**: 该服务是纯Python实现。尽管 `get_output_directory` 方法有一个脆弱的Tkinter特定备用方案，但其核心导出逻辑是完全独立的，非常有价值。

- **新架构中的替代方案**:
    - 核心逻辑应完全保留。
    - 必须**移除**那个通过反向查找Tkinter控件来获取输出目录的脆弱备用方案。输出目录应该作为参数显式传递给 `export_rendered_image` 方法，或从 `ConfigService` 中获取。
    - 线程模型可以改进。与其手动创建 `threading.Thread`，不如将 `_perform_backend_render_export` 的逻辑包装在一个函数中，并提交给全局的 `AsyncService`。这与处理其他耗时任务的方式更加一致。由于后端的 `translator.translate` 调用本身是 `async` 的，它能完美地融入 `AsyncService` 的事件循环。
    - 进度、成功和错误回调将被替换为在工作对象上定义的Qt信号，如先前分析中所述。

---

### 文件: `desktop-ui/services/file_service.py` (新分析)

- **目的**: 此文件定义了 `FileService`，一个用于处理各种文件相关操作的实用工具服务。它将验证、查找和处理文件的逻辑集中起来，从而将主应用逻辑与底层的 `os` 和 `shutil` 调用分离开。

- **功能细节与组件关联**:
  - **`__init__`**: 它定义了支持的图片和配置文件的扩展名集合。
  - **验证**:
    - `validate_image_file`: 通过检查文件扩展名和MIME类型，来验证一个文件路径是否是有效的、受支持的图片文件。
    - `validate_config_file`: 检查文件是否拥有一个受支持的配置文件扩展名。
  - **文件发现**:
    - `get_image_files_from_folder`: 扫描一个目录（可选择是否递归）并返回其中找到的所有有效图片文件的排序列表。
    - `filter_valid_image_files`: 接收一个文件路径列表，并返回其中有效的图片文件。
  - **拖放处理**:
    - `process_dropped_files`: 这是一个关键方法，设计用于处理拖放操作。它接收拖放事件的原始数据字符串，解析出文件/文件夹路径，然后进行处理。如果路径是文件夹，它会使用 `get_image_files_from_folder` 来查找内部的图片。最终返回一个包含有效图片路径和错误信息列表的元组。
    - `_parse_drop_data`: 一个辅助方法，用于解析拖放事件的原始字符串，能处理不同的换行符和URI格式。
  - **工具方法**:
    - `get_file_info`: 返回一个包含文件详细信息（大小、修改日期、尺寸等）的字典。
    - `_format_file_size`: 将字节大小格式化为人类可读的字符串（KB, MB, GB）。
    - `create_backup`: 为指定文件创建一个带时间戳的备份。
    - `cleanup_temp_files`: 删除指定目录中超过指定时长的旧文件。

- **重构处置**: **保留**

- **理由**:
  1.  **优秀的关注点分离**: 该服务完美地封装了文件系统的交互。业务逻辑组件（如控制器）无需知道*如何*在文件夹中查找图片或解析拖放数据，它们只需调用 `file_service.get_image_files_from_folder(...)` 即可。这使得代码库的其余部分更清晰、更专注。
  2.  **框架无关**: 该服务是纯Python实现，不依赖任何UI工具包，可以在新的Qt架构中无缝使用。
  3.  **可复用的工具集**: 它提供了许多在桌面应用中普遍需要的、可复用的辅助功能（文件验证、备份、临时文件清理等）。

- **新架构中的替代方案**:
    - 无需修改。这是一个设计良好的服务，完美契合现有的面向服务的架构。
    - 它将被主 `ServiceContainer` 实例化一次，并通过 `get_file_service()` 函数提供全局访问。
    - 其他组件，如新的 `AppLogic` 或 `EditorController`，将使用此服务来处理所有与文件相关的任务。例如，当文件被拖放到新的Qt主窗口上时，`dropEvent` 处理器将获取路径列表，并将其传递给 `get_file_service().process_dropped_files()`，以获取一个干净的图片列表来添加到应用状态中。

---

### 文件: `desktop-ui/services/font_monitor_service.py` (新分析)

- **目的**: 此文件定义了 `FontMonitorService`。其目的是监视应用的 `fonts` 目录，检测任何变更（如添加或删除字体文件），并在发生变更时通知应用的其他部分。这使得UI组件（如下拉字体选择框）能够自动更新，而无需用户手动刷新或重启应用。

- **功能细节与组件关联**:
  - **`__init__`**: 接收一个 `fonts_directory` 路径作为监控目标，并定义了支持的字体文件扩展名。
  - **回调系统**: 使用一个简单的列表 (`self.callbacks`) 来注册观察者函数。`register_callback` 和 `unregister_callback` 方法用于管理这个列表。
  - **监控逻辑 (`_monitor_loop`)**:
    - 这是在独立后台线程中运行的核心逻辑。
    - 它是一个无限循环，每2秒调用一次 `_get_font_files()` 来获取目录中当前的字体文件列表。
    - 将当前列表与上一次记录的列表 (`self.last_fonts`) 进行比较。
    - 如果检测到差异，它会更新 `self.last_fonts`，然后调用 `_notify_callbacks`，将新的字体列表通知给所有已注册的观察者。
  - **线程**:
    - `start_monitoring`: 启动一个新的后台守护线程 (`threading.Thread`) 来运行 `_monitor_loop`。
    - `stop_monitoring`: 通过设置标志位来安全地终止后台线程，并等待其优雅退出。
  - **API**:
    - `get_current_fonts()`: 一个按需获取当前字体列表的方法。
    - `refresh_fonts()`: 一个手动触发检查并通知变更的方法。

- **重构处置**: **保留（有增强空间）**

- **理由**:
  1.  **实用的用户体验功能**: 当用户添加新字体文件时自动更新字体列表，这是一个很好的用户体验功能。
  2.  **良好的抽象**: 该服务清晰地封装了后台监控和文件系统轮询的复杂性。其他组件无需关心字体列表是如何获取的，只需注册一个回调即可接收更新。
  3.  **框架无关**: 核心逻辑使用Python标准的 `os`, `time`, 和 `threading` 模块，完全独立于任何UI框架，易于集成到新架构中。

- **新架构中的替代方案**:
    - 该服务的主体可按原样保留。
    - **使用 `watchdog` 进行增强**: 当前的实现方式是手动轮询（每2秒检查一次目录）。一个更高效、更现代的方法是使用像 `watchdog` 这样的专用文件系统监视库。该库利用操作系统原生的文件系统事件（如Linux上的`inotify`），而不是轮询，这样能更有效地利用资源。`_monitor_loop` 将被一个仅在文件被创建、删除或修改时才被调用的 `watchdog` 事件处理器所取代。
    - **Qt集成**:
        - 回调系统可以替换为Qt的信号与槽机制。`FontMonitorService` 可以继承自 `QObject` 并定义一个如 `fonts_changed = pyqtSignal(list)` 的信号。`_notify_callbacks` 方法将被 `self.fonts_changed.emit(...)` 所取代。
        - 后台线程可以使用 `QThread` 来实现，以便更好地与Qt的事件循环集成，但标准的 `threading.Thread` 也能继续工作。

---

### 文件: `desktop-ui/services/json_preprocessor_service.py` (新分析)

- **目的**: 此文件定义了 `JsonPreprocessorService`。它服务于一个非常特殊和特定的目的：修改磁盘上的 `_translations.json` 文件。具体来说，它会将每个文本区域的 `"translation"` 字段的值复制并覆盖到 `"text"` 字段。这是为一种特殊的工作流设计的：当用户希望使用“模板”进行渲染，而该模板又被硬编码为使用 `"text"` 字段时，通过用译文覆盖原文，来确保最终渲染出的图片包含的是翻译后的文本。

- **功能细节与组件关联**:
  - **`restore_translation_to_text`**: 这是核心方法。它读取一个给定的 `_translations.json` 文件，遍历所有文本区域，如果区域内有非空的翻译，它就用翻译内容覆盖 `text` 和 `texts` 字段，然后将修改后的JSON文件保存回磁盘。
  - **状态跟踪**: 它维护一个 `self.processed_files` 集合，以确保在单次会话中不会重复修改同一个文件。
  - **批量操作**: 它提供了 `batch_process_folder` 和 `process_file_list` 方法，用于一次性对多个文件执行此操作。
  - **激活逻辑 (`should_process`)**: 它包含一个辅助方法，定义了执行此预处理的条件：仅当应用的配置中同时启用了“加载文本”模式和“模板”模式时。这清晰地界定了其狭窄的使用场景。
  - **单例模式**: 使用标准的 `get_json_preprocessor_service()` 函数来提供全局单例。

- **重构处置**: **废弃或吸收其逻辑**

- **理由**:
  1.  **破坏性操作**: 该服务的主要功能是执行一个破坏性操作（覆盖数据文件中的原文）。尽管这是为特定工作流设计的，但这是一种脆弱且可能引起困惑的方法。用户可能没有意识到他们的原文数据正在被覆盖。
  2.  **为渲染限制而生的变通方案**: 该服务的存在是一个“权宜之计”。真正的问题在于“模板渲染”模式被硬编码为仅使用 `"text"` 字段。一个更好的解决方案是让渲染管线更加灵活，允许它被配置为在需要时直接使用 `"translation"` 字段。
  3.  **功能小众且令人困惑**: 该服务的目的不甚直观，并且与一个非常特殊的设置组合（“加载文本”+“模板”）绑定，这给整体架构带来了不必要的复杂性。

- **新架构中的替代方案**:
    - **理想方案（消除其存在的必要性）**: 最好的方法是让这个服务变得过时。应该修改后端的渲染管线（或调用它的 `ExportService`）。在用模板导出时，应该可以指定用于渲染的字段（例如 `render_field='translation'`）。这将是一个更清晰、非破坏性且更直观的解决方案。
    - **备选方案（吸收其逻辑）**: 如果后端不容易修改，这个逻辑也不应该作为一个独立的服务存在。`ExportService` 已经负责为后端准备数据。如果这种文本交换是必要的，它应该在 `ExportService` 的 `_perform_backend_render_export` 方法中**于内存里**完成。`ExportService` 会在内存中创建一个临时的、修改过的 `regions_data` 副本并将其传递给后端，而完全不修改用户磁盘上的 `_translations.json` 文件。这将在没有破坏性副作用的情况下达到同样的效果。

---

### 文件: `desktop-ui/services/i18n_service.py` (新分析)

- **目的**: 此文件定义了 `I18nManager`，一个用于处理应用界面国际化（i18n）和本地化（l10n）的全功能服务。它负责管理语言文件的加载、文本键的翻译以及处理不同语言环境的属性（如文本方向）。

- **功能细节与组件关联**:
  - **`LocaleInfo` (dataclass)**: 一个数据类，用于存储每种受支持语言的元数据，包括其名称、英文名和文本方向（例如 "ltr" 或 "rtl"）。
  - **`I18nManager` 类**:
    - **`__init__`**:
      - 定义了存放翻译文件的 `locale_dir` 目录。
      - 维护一个支持的语言环境列表 (`self.available_locales`)。
      - 尝试使用Python的 `locale` 模块检测系统的默认语言，并如果该语言受支持，则将其设为当前语言。
      - 调用 `_load_all_translations` 将 `locales` 目录下的所有JSON翻译文件加载到内存中。
    - **翻译加载 (`_load_locale_translation`)**: 为每个语言环境查找对应的 `.json` 文件（如 `zh_CN.json`）。如果文件不存在，它会为其创建一个空字典，并且对于像 `zh_CN` 和 `en_US` 这样的关键语言，它甚至会用一些硬编码的默认UI字符串创建一个基础翻译文件。
    - **`translate(key, **kwargs)`**: 这是核心的翻译方法。它接收一个文本`键`（如 "File"），在当前语言的字典中查找它，并返回翻译后的字符串。如果在当前语言中找不到翻译，它会回退到 `en_US` 的翻译。它还支持使用关键字参数进行基本的字符串格式化。
    - **API**: 它提供了一套丰富的API，用于 `set_locale`（设置语言）、`get_current_locale`（获取当前语言）、`get_available_locales`（获取可用语言列表）以及获取文本方向信息（`is_rtl_language`）。
  - **单例和便捷函数**:
    - 使用标准的 `get_i18n_manager()` 单例模式来提供一个全局实例。
    - 最关键的是，它提供了一个 `_()` 函数（这是i18n库中一个常见的约定，源于 `gettext`）作为 `get_i18n_manager().translate(key)` 的简短别名。这使得UI代码可以写得非常简洁，例如：`button = ctk.CTkButton(text=_("Save"))`。

- **重构处置**: **保留**

- **理由**:
  1.  **优秀的设计**: 这是一个设计非常好的、自包含的国际化服务。它处理了语言检测、文件加载、回退逻辑，并提供了一套清晰、符合惯例的API (`_()`)。
  2.  **框架无关**: 它是纯Python实现，不依赖于Tkinter或任何其他UI框架，可以直接在新的Qt应用中使用。
  3.  **遵循最佳实践**: 它遵循了成熟的i18n实践，例如为UI字符串使用键、提供回退语言以及支持像阿拉伯语这样的RTL（从右到左）语言的文本方向。

- **新架构中的替代方案**:
    - 该服务本身无需修改，已准备好在新架构中使用。
    - **Qt集成**: Qt拥有自己强大的国际化框架（`QTranslator`, `pylupdate`, `.ts` 文件）。虽然一个“纯Qt”的解决方案会涉及将所有JSON键值对迁移到 `.ts` 文件并使用 `QObject.tr()`，但这对于获得相同的功能来说工作量巨大。现有的 `I18nManager` 功能完善，并且对于Python应用来说，JSON文件比 `.ts` 文件更易于管理。
    - **用法**: 在新的Qt代码中，UI元素可以这样创建：`button = QPushButton(_("Save"))`。为了在运行时处理语言切换，需要一个机制来触发UI刷新。这可以通过让 `I18nManager` 发出一个 `language_changed` 信号（一个增强功能）来实现，主窗口连接到该信号的一个槽函数，该槽函数负责重新翻译并更新所有必要的UI文本。

---

### 文件: `desktop-ui/services/lightweight_inpainter.py` (新分析)

- **目的**: 此文件定义了 `LightweightInpainter`。其目的是为编辑器的交互式蒙版编辑模式提供一个快速的、“足够好”的修复预览。它刻意**不**使用完整的、缓慢的、高质量的后端模型（如Lama或Stable Diffusion），而是提供了简化的、快速的算法（如简单模糊或OpenCV的`inpaint`函数），这些算法的运行速度足以在用户绘制蒙版时提供实时预览。

- **功能细节与组件关联**:
  - **依赖关系**: 它依赖于 `EraseConfigService` 来了解用户为最终输出*选择*了哪种算法，但它不一定*使用*该算法来进行预览。
  - **算法处理器**:
    - 拥有一个 `self.algorithm_handlers` 字典，将 `InpainterType` 枚举映射到实际的实现方法。
    - `_inpaint_none`: 用白色填充蒙版区域。
    - `_inpaint_original`: 不做任何事，返回原图。
    - `_inpaint_simple_blur`: 一个自定义的、非常快速的算法，用白色填充区域，然后对边缘进行模糊处理以减少生硬感。这是大多数高质量后端算法的默认预览实现。
    - `_inpaint_advanced_fill`: 使用OpenCV内置的 `cv2.inpaint` 函数，它比深度学习模型快，但效果比简单模糊要好。
  - **`preview_async`**: 这是主要的公共方法。
    - 它接收一个图像和一个蒙版。
    - 使用 `ThreadPoolExecutor` 在后台线程中运行实际的处理（`_process_preview`），使调用非阻塞。
    - 包含一个缓存机制 (`self.preview_cache`)，如果最近处理过相同的图像、蒙版和设置，则立即返回结果。
  - **`_process_preview`**: 这是在后台线程中运行的核心逻辑。
    - **调整尺寸**: 首先将图像和蒙版缩小到一个较小的尺寸（默认为512px），以确保预览生成速度。
    - **算法选择**: 它会智能地选择使用哪种快速算法。例如，如果用户选择了 `LAMA_MPE`（一个较快的后端模型）并且预览质量要求高，它可能会使用效果更好的 `_inpaint_advanced_fill`。对于像 `LAMA_LARGE` 这样的慢速模型，它会默认使用速度最快的 `_inpaint_simple_blur`。
    - **恢复尺寸**: 在处理完小尺寸的预览后，它会将结果图像放大回原始尺寸。
  - **单例模式**: 使用标准的 `get_lightweight_inpainter()` 函数来提供全局单例。

- **重构处置**: **保留**

- **理由**:
  1.  **解决了关键的用户体验问题**: 为一个可能缓慢的操作提供实时的、交互式的预览，对于良好的用户体验至关重要。该服务正是致力于解决图像修复的这个问题。
  2.  **清晰的职责分离**: 它清晰地分离了“快速预览”逻辑和“高质量最终”逻辑。主应用控制器将使用这个 `LightweightInpainter` 在编辑器中进行交互式预览，但在生成最终结果时，会调用另一个（推测存在的）使用*真实*后端模型的 `InpaintingService`。
  3.  **框架无关**: 该服务是纯Python实现，使用了 `numpy`, `cv2` 和标准线程库。它没有UI依赖，可以按原样在新架构中使用。

- **新架构中的替代方案**:
    - 该服务设计良好，可以保留。
    - `ThreadPoolExecutor` 的使用是可行的，但为了与应用其余部分的重构保持一致，`preview_async` 方法可以被改造为使用全局的 `AsyncService`。这可以通过将 `_process_preview` 作为一个常规（非异步）函数，并通过 `run_in_executor` 提交给 `AsyncService` 的事件循环来完成。当然，当前的实现也是完全可以接受的。
    - 新的 `EditorController` 将负责调用此服务。当用户正在绘制或修改蒙版时，控制器会持续调用 `get_lightweight_inpainter().preview_async(...)`，并用返回的结果更新画布上的一个预览图层（`QGraphicsPixmapItem`）。

---

### 文件: `desktop-ui/services/shortcut_manager.py` (新分析)

- **目的**: 此文件定义了 `ShortcutManager`，一个用于为应用程序注册、管理和处理全局键盘快捷键的服务。

- **功能细节与组件关联**:
  - **`Shortcut` (dataclass)**: 一个数据结构，用于表示单个快捷键，包含其键、修饰符（Ctrl, Alt等）、要执行的回调函数、描述和一个“上下文”（例如“global”、“editor”）。
  - **`__init__`**: 它接收Tkinter的 `root_widget` 作为参数，需要它来绑定事件。它维护一个所有已注册快捷键的字典。
  - **绑定 (`_setup_global_bindings`, `_bind_shortcut`)**: 它使用 `root_widget.bind_all()` 在应用程序级别捕获键盘事件。这是在Tkinter中实现全局快捷键的正确方法。`_setup_global_bindings` 方法有点暴力，试图预先绑定许多常见的组合。
  - **注册 (`register_shortcut`)**: 提供了一个清晰的API来注册新的快捷键。它接收键、修饰符、回调和其他信息，创建一个 `Shortcut` 对象并存储它。
  - **上下文管理**:
    - 这是一个关键特性。它实现了一个 `context_stack`。快捷键可以被注册到特定的上下文，如“editor”。
    - `_on_shortcut` 处理器在触发回调之前检查快捷键的上下文是否激活 (`_is_context_active`)。这允许相同的组合键（例如Ctrl+S）在应用程序的不同部分执行不同的操作，或被完全禁用。
    - `push_context` 和 `pop_context` 用于更改当前活动的上下文。例如，当用户进入编辑器视图时，会调用 `push_context("editor")`。
  - **事件处理 (`_on_shortcut`)**: 这是所有绑定键事件的中央回调。它从Tkinter的 `event` 对象重构快捷键组合字符串，并在其 `shortcuts` 字典中查找它。如果找到匹配的、已启用的、上下文适当的快捷键，它将执行回调。
  - **`register_common_shortcuts`**: 一个辅助方法，用于注册一系列硬编码的、常见的应用程序快捷键（例如Ctrl+O用于打开，Ctrl+S用于保存）。这是集中管理默认键绑定的好方法。

- **重构处置**: **保留逻辑，为Qt重新实现**

- **理由**:
  1.  **基本功能**: 一个集中的快捷键管理器是任何正经桌面应用程序的关键组件。管理快捷键的逻辑，特别是上下文堆栈，是经过深思熟虑且有价值的。
  2.  **Tkinter依赖**: 整个实现从根本上与Tkinter事件模型（`bind_all`、`event`对象结构）绑定。它不能直接在Qt中使用。
  3.  **Qt有不同的模型**: Qt有一个更复杂的内置快捷键系统，使用 `QAction` 和 `QShortcut`。直接移植并不理想；相反，此管理器的*逻辑*应适应Qt的做事方式。

- **新架构中的替代方案**:
    - **`QAction`是王道**: 在Qt中处理快捷键的主要方式是使用 `QAction`。一个动作封装了一个命令、其文本、图标、状态提示及其快捷键。同一个 `QAction` 可以被添加到菜单、工具栏，并作为全局快捷键。
    - **集中式动作注册表**: 可以创建一个新的服务，也许叫 `ActionService`，来代替 `ShortcutManager`。此服务将负责创建和持有应用程序的所有 `QAction` 实例（例如 `self.save_action = QAction(...)`、`self.open_action = QAction(...)`）。
    - **连接动作**: 每个 `QAction` 的 `triggered` 信号将连接到相应控制器中的一个槽（例如 `self.save_action.triggered.connect(app_logic.save_config)`）。
    - **上下文管理**: 上下文逻辑仍然非常有用。`ActionService` 可以维护相同的 `context_stack`。当上下文更改时（例如进入编辑器），该服务可以遍历其动作并根据其注册的上下文是否激活来启用/禁用它们（`action.setEnabled(True/False)`）。这是管理上下文敏感快捷键的清晰方法。
    - **特定于小部件的快捷键**: 对于仅在特定小部件具有焦点时才适用的快捷键，`QShortcut` 或将 `QAction` 直接添加到小部件（`widget.addAction(action)`）是首选的Qt方法。新的 `ActionService` 也可以管理这些。

---

### 文件: `desktop-ui/services/progress_manager.py` (新分析)

- **目的**: 此文件定义了 `ProgressManager` 和一个相关的 `ProgressDialog`。它旨在成为一个用于创建、跟踪、更新和显示长耗时任务进度的集中式服务。

- **类拆解分析**:
  - **`ProgressStatus` (Enum) & `ProgressInfo` (dataclass)**: 这些是用于表示任务进度状态和详细信息的、定义良好的数据结构，这是一个很好的实践。
  - **`ProgressDialog`**:
    - **目的**: 一个UI组件，用于在模态对话框中显示单个任务的进度。
    - **细节**: 这是一个 `customtkinter.CTkToplevel`，显示进度条、百分比文本、状态消息和时间估算。它有一个 `update_progress` 方法，接收一个 `ProgressInfo` 对象来更新其所有控件。它也有一个取消按钮。
    - **评价**: 这是一个UI组件。它与 `progress_dialog.py` 中的同名类相似但更详细。它仍然与Tkinter绑定。
  - **`ProgressManager` 类**:
    - **目的**: 一个用于管理多个、可能并发的后台任务生命周期的服务。
    - **细节**:
      - **任务管理**: 它维护一个由 `task_id` 索引的 `active_tasks` 字典。拥有 `create_task`, `start_task`, `update_task`, `complete_task` 等方法。
      - **观察者模式**: 它使用一个 `self.observers` 字典，允许代码的其他部分订阅特定 `task_id` 的更新。
      - **UI集成 (`show_dialog`)**: 此方法创建一个 `ProgressDialog` 实例，并自动将其订阅到给定 `task_id` 的更新，从而将后端进度数据链接到UI表示。
      - **线程**: 该类本身**不**运行任务。它纯粹是一个状态管理和通知服务。它期望其他代码（如 `app_logic.py`）在后台线程中实际运行任务，并从该线程调用 `update_task` 方法。这是一个比 `OperationManager` 更好的设计，因为它分离了状态跟踪和执行，但仍需要来自工作线程的谨慎的、线程安全的调用。
    - **单例模式**: 使用标准的 `get_progress_manager()` 函数来提供全局单例。

- **重构处置**: **废弃并吸收其逻辑**

- **理由**:
  1.  **过度工程化**: 这是另一个针对桌面应用中相对简单问题进行过度设计的例子。虽然一个通用的、多任务的进度管理器在服务器或复杂批处理系统中是个好主意，但对于一个通常一次只运行一个主任务的UI应用来说，它增加了太多样板代码（任务ID、观察者等）。
  2.  **与其他组件功能冗余**:
      - `ProgressDialog` UI组件与 `progress_dialog.py` 中的组件功能重复。
      - 跟踪任务状态的核心概念已由 `StateManager` 服务处理（例如 `IS_TRANSLATING` 状态）。
      - 显示进度对话框并将其连接到后台任务的职责，应属于发起该任务的控制器（如 `AppLogic` 或新的 `EditorController`）。
  3.  **不必要的复杂性**: 此处实现的、需要按 `task_id` 订阅的观察者模式，比实际所需要的更为复杂。

- **新架构中的替代方案**:
    - `ProgressManager` 服务应被**删除**。
    - `ProgressDialog` UI组件应在Qt中作为 `QProgressDialog` 或自定义的 `QDialog` 子类被**重建**。
    - 管理进度的职责将由启动任务的控制器（例如 `AppLogic`）处理。工作流程将是：
        1.  `AppLogic` 决定启动一个长耗时任务（如批量翻译）。
        2.  它创建一个将执行任务的工作对象（`QObject`），该对象将定义用于进度更新的信号，例如 `progress_updated(int, int, str)`。
        3.  `AppLogic` 创建一个新的Qt `ProgressDialog` 实例。
        4.  `AppLogic` 将工作对象的 `progress_updated` 信号连接到对话框的 `update_progress` 槽。同时将对话框的 `canceled` 信号连接到工作对象的 `cancel` 槽。
        5.  `AppLogic` 将工作对象移至 `QThread` 并启动它。
        6.  `AppLogic` 调用 `dialog.exec()` 来显示模态对话框。
    - 这种方法是标准的Qt实践。由于信号/槽机制，它是类型安全和线程安全的，并且将任务管理逻辑与发起任务的代码放在一起，使其比一个分离的全局管理器更易于理解。`ProgressInfo` 数据类作为一个有用的数据结构，可以保留下来用于在信号中传递。

---

### 文件: `desktop-ui/services/performance_optimizer.py` (新分析)

- **目的**: 此文件是一个旨在提升应用性能和响应速度的类集合。它是一个“元服务”，整合了多种优化策略：图片缓存、延迟/异步图片加载、内存管理和UI更新批处理。

- **类拆解分析**:
  - **`ImageCache`**:
    - **目的**: 一个用于 `PIL.Image` 对象的内存缓存。
    - **细节**: 使用 `OrderedDict` 实现LRU（最近最少使用）淘汰策略。同时具有缓存项数量和总内存使用（MB）两种上限。当缓存满时，它会移除最旧的项。这是一个标准的、可靠的缓存实现。
  - **`LazyImageLoader`**:
    - **目的**: 在后台加载图片而不阻塞主线程。
    - **细节**: 使用 `ThreadPoolExecutor` 在后台线程中运行实际的文件IO和图片解码。`load_image_async` 方法在提交任务后立即返回。当图片加载完成后，通过回调函数通知调用者。它与 `ImageCache` 协同工作以避免重复加载。
  - **`MemoryManager`**:
    - **目的**: 监控应用的内存使用情况并触发垃圾回收。
    - **细节**: 使用 `psutil` 库来获取进程的内存使用量。`should_cleanup` 方法检查内存使用是否超过阈值。`cleanup_memory` 手动触发Python的垃圾回收 (`gc.collect()`)。
  - **`UIPerformanceOptimizer`**:
    - **目的**: 防止UI因过于频繁的更新请求（例如，在鼠标拖动期间）而变得卡顿。
    - **细节**: 它实现了两种常见的UI优化模式：
      - **批处理/调度**: `schedule_update` 将一个函数添加到队列中。`process_updates` 批量执行队列中的函数，但会确保两次执行之间有最小的时间间隔，从而有效地将更新限制在约60 FPS。
      - **防抖**: `debounce_update` 确保一个函数只在一段时间的“静默”后才被调用（例如，在用户停止输入500毫秒后保存更改）。
  - **`PerformanceOptimizer` (主类)**:
    - **目的**: 这是一个外观（Facade）类，将所有其他组件聚合到一个统一的服务中。
    - **细节**: 它初始化了所有其他子组件，并提供了一个如 `load_image_optimized` 的高级API，该API整合了缓存和异步加载。它还启动一个后台监控线程，定期检查内存并处理UI更新队列。

- **重构处置**: **拆分并保留核心逻辑**

- **理由**:
  1.  **过度工程化的单体**: 虽然此文件中的*想法*都很好，但它是一个试图做得太多的单体服务。缓存、异步加载、内存管理和UI更新调度是各自独立的关注点，应由更专注的服务或机制来处理。
  2.  **部分逻辑与UI框架特定**: `UIPerformanceOptimizer` 的问题尤其突出。UI更新的节流和防抖是常见需求，但这里的实现（手动队列、`threading.Timer`）是一个自定义解决方案。像Qt这样的现代UI工具包有内置的、更健壮的方式来处理这些问题。
  3.  **核心逻辑有价值**: `ImageCache` 和 `LazyImageLoader` 是纯粹的、与框架无关的逻辑，它们解决了一个实际问题（图片加载缓慢）。`MemoryManager` 也是一个潜在有用的独立工具。

- **新架构中的替代方案**:
    - **`ImageCache`**: 保留此类，或许放在它自己的文件中，或作为一个新的、更专注的 `ImageService` 的一部分。全局图片缓存是一个非常有用的模式。
    - **`LazyImageLoader`**: 后台加载图片的逻辑至关重要。这应该与全局的 `AsyncService` 集成。一个新的 `ImageService` 可以有一个 `load_image_async(path)` 方法，该方法在 `AsyncService` 的事件循环上使用 `run_in_executor` 在后台线程中加载图片，并与 `ImageCache` 交互。
    - **`MemoryManager`**: 可以作为一个可选的、独立的工具服务保留。其监控循环可以像现在一样在后台线程中运行。
    - **`UIPerformanceOptimizer`**: 应被**删除**。其功能应由Qt原生的模式替代：
        - **防抖**: 使用 `QTimer.singleShot()` 来实现。
        - **节流/批处理**: 对于高频事件（如鼠标移动），事件处理器中的逻辑应尽可能轻量。与其将函数调用加入队列，不如只更新一个状态变量。昂贵的重绘操作由Qt自己的高效事件循环和渲染系统来处理。无需构建自定义的调度器。

---

### 文件: `desktop-ui/services/log_service.py` (新分析)

- **目的**: 此文件定义了 `LogService`，一个用于处理应用内所有日志记录的、全面的、集中式的服务。它负责设置日志处理器、格式化日志消息，并为应用的其他部分提供一个记录结构化日志的接口。

- **功能细节与组件关联**:
  - **`__init__`**: 如果 `logs` 目录不存在，则创建它，并立即调用 `_setup_main_logger` 来配置日志系统。
  - **`_setup_main_logger`**: 这是核心的配置方法。它为应用的根日志记录器设置了多个处理器：
    - `RotatingFileHandler` for `app.log`: 一个通用的日志文件，当达到10MB时会自动轮转。
    - `RotatingFileHandler` for `error.log`: 一个只记录 `ERROR` 或更高级别消息的独立文件。
    - `StreamHandler`: 用于将日志消息打印到控制台。
    - `MemoryHandler`: 一个自定义处理器，它将最近的日志记录保存在内存列表（`self.recent_logs`）中。这对于在UI中显示实时日志视图而无需从文件读取非常有用。
  - **结构化日志**: 该服务提供了如 `log_operation`, `log_error`, `log_translation_start` 等辅助方法。这些方法接收结构化数据（字典）并将其格式化为日志消息中的一致的JSON字符串。这使得日志更易于被自动解析和分析。
  - **内存日志访问**: `get_recent_logs` 和 `get_log_summary` 方法提供了对由 `MemoryHandler` 存储在内存中的日志的访问，允许UI显示最近的活动和统计信息。
  - **工具方法**: 包含了用于 `cleanup_old_logs`（清理旧日志）和 `export_logs`（导出日志到文件）的方法。
  - **单例模式**: 使用标准的 `get_log_service()` 函数来提供一个全局单例实例，该实例随后被注册到主 `ServiceContainer` 中。

- **重构处置**: **保留**

- **理由**:
  1.  **优秀的设计**: 这是一个教科书级别的范例，展示了如何在桌面应用中正确地实现日志记录。它分离了关注点，有效地利用了Python标准的 `logging` 功能（多处理器、格式化器），并添加了如内存日志收集和结构化日志辅助等有价值的功能。
  2.  **健壮性**: 它使用轮转文件处理器来防止日志文件无限增长，并分离错误日志以便于调试。
  3.  **框架无关**: 该服务是纯Python实现，没有UI依赖。它是一个完美的后端服务，可以被用在新的Qt架构中而无需任何更改。

- **新架构中的替代方案**:
    - 无需修改。这是一个设计良好、可复用的组件，完美地契合了面向服务的架构。
    - 在新的Qt应用中，一个UI控件（例如 `QTextEdit` 或 `QListView`）可以被创建来显示日志。这个控件将周期性地调用 `get_log_service().get_recent_logs()` 来刷新其内容，提供一个应用活动的实时视图。`LogService` 本身无需修改。

---

### 文件: `desktop-ui/services/mask_erase_preview_service.py` (新分析)

- **目的**: 此文件定义了 `MaskErasePreviewService`。它试图成为一个高-level manager for submitting, tracking, and canceling mask inpainting preview requests. It wraps the `LightweightInpainter` service, adding a layer of state management and request queuing on top of it.

- **功能细节与组件关联**:
  - **依赖关系**: It depends on and uses both `EraseConfigService` and `LightweightInpainter`.
  - **请求管理**:
    - It defines `PreviewRequest` and `PreviewState` dataclasses to encapsulate a request and its current status (e.g., `IDLE`, `PROCESSING`, `COMPLETED`).
    - `submit_preview_request`: This is the main entry point. It creates a unique ID for the request, stores the request and its state in dictionaries, and then submits the actual work (`_process_request`) to a `ThreadPoolExecutor`.
  - **`_process_request`**: This background worker function is where the core logic happens. It updates the request's state, checks if the selected algorithm is suitable for preview (and switches to a recommended one if not), and then calls `self.lightweight_inpainter.preview_sync()` to get the actual preview image.
  - **状态与回调**: It maintains a dictionary of request states (`self.request_states`) and provides a callback system (`global_callbacks` and per-request callbacks) to notify callers about status changes.
  - **过度工程化**: The service includes features like request cancellation (`cancel_request`), statistics tracking (`self.stats`), and delayed cleanup of finished requests. While these features might be useful in a heavy-duty server application, they represent significant over-engineering for a simple desktop UI preview feature, especially since the underlying `LightweightInpainter` tasks are designed to be very fast.
  - **冗余API**: It exposes methods like `preview_async` and `preview_sync` that *also* exist on the `LightweightInpainter` service it wraps, creating a confusing and redundant API.

- **重构处置**: **删除**

- **理由**:
  1.  **不必要的抽象层**: This service is an almost entirely unnecessary layer of abstraction on top of `LightweightInpainter`. The `LightweightInpainter` already provides caching and an async API. The additional complexity of request IDs, state tracking dictionaries, and statistics is overkill for a simple preview feature and makes the code much harder to follow.
  2.  **增加了复杂性，但未解决新问题**: The core problem of generating a fast preview is already solved by `LightweightInpainter`. This service just adds a heavy management wrapper around it without providing significant new functionality that the UI actually needs. A user is unlikely to ever need to cancel a preview request that finishes in a fraction of a second.
  3.  **API混乱**: Having two services (`LightweightInpainter` and `MaskErasePreviewService`) that both seem to do the same thing (`preview_async`) is confusing for any developer working on the codebase.

- **新架构中的替代方案**:
    - This service should be removed entirely.
    - The `EditorController` should directly interact with the `LightweightInpainter` service.
    - The workflow would be much simpler:
        1.  When the user draws on the mask, the `EditorController` calls `get_lightweight_inpainter().preview_async(...)`.
        2.  The `async` call is submitted to the global `AsyncService`.
        3.  When the `Future` completes, the `EditorController` receives the `PreviewResult` and updates the preview image on the canvas.
    - 这种方法消除了对请求ID、状态管理字典和复杂回调的需求，从而实现了一个更清晰、更直接、更易于理解和维护的实现。

---

### 文件: `desktop-ui/services/render_parameter_service.py` (新分析)

- **目的**: 此文件定义了 `RenderParameterService`。其职责是管理每个文本区域复杂的样式和布局参数。它负责处理默认参数的计算、每个区域的个性化定制以及参数预设的管理。

- **功能细节与组件关联**:
  - **数据结构**:
    - `Alignment` & `Direction` (Enums): 为文本对齐和方向提供了清晰、明确的选项。
    - `RenderParameters` (dataclass): 一个庞大而全面的数据结构，持有文本区域所有可能的样式选项（字体大小、颜色、对齐方式、行间距、描边宽度等）。这是该服务的核心数据模型。
    - `ParameterPreset` (dataclass): 一个用于保存已命名预设的结构，每个预设包含一个完整的 `RenderParameters` 对象。
  - **`RenderParameterService` 类**:
    - **`__init__`**: 它初始化一个字典来保存每个区域的自定义参数 (`self.region_parameters`)，一个默认的 `RenderParameters` 对象，以及一个预定义的 `presets` 字典（例如“漫画标准”、“轻小说标准”）。
    - **默认参数计算 (`calculate_default_parameters`)**: 这是一个关键特性。当一个新的文本区域被创建时，此方法会分析其几何形状（宽度和高度），以智能地推断出合理的默认参数。例如，它会根据区域的高度设置字体大小，并根据其宽高比确定文本方向（水平/垂直）。这比总是使用固定的初始值提供了更好的用户体验。
    - **参数管理**:
      - `get_region_parameters`: 主要的getter方法。对于给定的区域索引，它首先检查是否已设置了自定义参数。如果没有，它会调用 `calculate_default_parameters` 来生成它们，存储后返回。
      - `set_region_parameters` / `update_region_parameter`: 允许为特定区域设置整个参数对象或仅更新单个参数。
    - **预设**: 提供 `apply_preset`（应用预设到区域）、`create_custom_preset`（创建自定义预设）和 `get_preset_list`（获取预设列表）等方法。
    - **后端导出 (`export_parameters_for_backend`)**: 此方法获取一个区域的 `RenderParameters` 并将其转换为适合后端使用的简单字典格式。
  - **单例模式**: 使用标准的 `get_render_parameter_service()` 函数来提供全局单例。

- **重构处置**: **保留**

- **理由**:
  1.  **优秀的关注点分离**: 该服务出色地隔离了管理文本样式的复杂逻辑。它将*数据*（参数）与*视图*（属性面板UI）和*渲染器*（使用这些参数的组件）分离开来。
  2.  **智能默认值**: `calculate_default_parameters` 方法是一个突出的特性，它通过提供智能的、与上下文相关的默认值，显著改善了应用的易用性。
  3.  **框架无关**: 该服务是纯Python实现，可以在新的Qt架构中不做任何更改直接使用。

- **新架构中的替代方案**:
    - 该服务设计良好，应按原样保留。
    - 新的 `EditorController` 将是该服务的主要消费者。当创建新的文本区域时，控制器将调用 `get_render_parameter_service().get_region_parameters(...)` 来获取初始的、智能计算出的样式。
    - 新的 `PropertyPanel` 视图也将（很可能通过控制器）使用此服务来填充其控件，以显示当前选中区域的参数。当用户在属性面板中更改样式时（例如，更改字体大小），UI将发出一个信号给控制器，控制器随后调用 `get_render_parameter_service().update_region_parameter(...)` 来更新数据模型。

---

### 文件: `desktop-ui/services/workflow_service.py` (新分析)

- **目的**: 此文件似乎是一个高级工作流的集合，但其结构很差。它包含了两个主要但又奇怪地交织在一起的功能：
    1.  **JSON预处理**: 它有与 `json_preprocessor_service.py` 中几乎完全相同的函数 (`restore_translation_to_text`, `batch_process_json_folder`)。其目的是破坏性地将翻译文本写回到 `_translations.json` 文件的原始文本字段中。
    2.  **基于模板的导入/导出**: 它有一套函数 (`parse_template`, `generate_text_from_template`, `export_with_custom_template`, `import_with_custom_template`)，用于根据模板将区域数据导出为自定义 `.txt` 格式，并从该 `.txt` 文件导回翻译到JSON中。

- **功能细节与组件关联**:
  - **JSON预处理功能**: `restore_translation_to_text`、`batch_process_json_folder`、`process_json_file_list` 和 `should_restore_translation_to_text` 存在。如 `json_preprocessor_service.py` 的分析中所述，这是一个破坏性的、值得商榷的工作流。此逻辑在两个不同的服务文件中重复，是一个主要的红旗，表明所有权不明确和架构混乱。
  - **模板解析 (`parse_template`)**: 此函数可以接收一个带有 `<original>` 和 `<translated>` 占位符的自由格式文本文件，并智能地将其解析为前缀、后缀、分隔符和项目模板本身。这是一个相当复杂的逻辑。
  - **模板生成 (`generate_text_from_template`)**: 此函数接收一个JSON文件和一个模板文件，并使用解析后的模板生成一个自定义文本文件，用JSON中的数据替换占位符。
  - **导入/导出包装器**: `export_with_custom_template` 和 `import_with_custom_template` 是高级包装器，用于协调读取源文件、查找模板和调用生成/更新逻辑的整个过程。
  - **`safe_update_large_json_from_text`**: 这是一个非常复杂的低级函数，执行导入过程。它读取文本文件，使用模板解析翻译，加载大型JSON（如果可用，则使用 `ijson` 进行优化），在内存中更新翻译，然后使用临时文件原子地将更改写回磁盘。它包括备份和完整性检查的逻辑。这是关键且复杂的I/O逻辑。

- **重构处置**: **拆分、重构和废弃**

- **理由**:
  1.  **重复和冲突的逻辑**: 它复制了 `json_preprocessor_service.py` 的整个JSON预处理工作流。这是一个必须解决的关键架构缺陷。其中之一必须是单一事实来源，另一个必须被删除。
  2.  **职责混杂**: 该文件混合了两个不同的工作流（JSON预处理和模板I/O），它们应该在不同的服务中。它不是一个“工作流服务”，而是一个不相关函数的集合。
  3.  **破坏性和脆弱的工作流**: 如前所述，“将翻译恢复到文本”的工作流是破坏性的。基于模板的导入/导出也很脆弱；它依赖于复杂的正则表达式和字符串拆分来解析文本文件，如果用户不正确地编辑文件，很容易中断。

- **新架构中的替代方案**:
  1.  **消除重复**: 所有JSON预处理函数 (`restore_translation_to_text` 等) 都应从此文件中**删除**。此逻辑如果必须保留，应*仅*存在于 `json_preprocessor_service.py` 中。
  2.  **创建 `TemplateService`**: 基于模板的导入/导出功能是一个有效的、独特的功能。所有相关函数 (`parse_template`, `generate_text_from_template`, `export_with_custom_template`, `import_with_custom_template`, `safe_update_large_json_from_text` 等) 都应移至一个新的、专门的 `TemplateService` 中。此服务将负责与自定义文本模板的所有交互。
  3.  **重构 `safe_update_large_json_from_text`**: 此函数做得太多了。其逻辑应在新的 `TemplateService` 中分解为更小、更易于测试的部分：一个用于解析文本文件，一个用于在内存中更新JSON数据，一个用于安全地将JSON写入磁盘。
  4.  **废弃JSON预处理**: 整个 `json_preprocessor_service.py` 应标记为待废弃。如其自身分析中所建议，应通过使后端渲染管线更灵活来消除对其的需求。

---

### 文件: `desktop-ui/utils/__init__.py` (新分析)

- **目的**: 这是一个初始化文件，其作用是声明 `utils` 目录为一个Python包。这使得应用的其他部分可以导入 `utils` 包内的模块。

- **功能细节与组件关联**: 该文件只包含一行注释，没有任何可执行代码。

- **重构处置**: **保留**

- **理由**:
  1.  **Python标准**: 这是Python包系统中的一个标准且必要的文件。
  2.  **框架无关**: 它是Python语言的一个基本组成部分，完全独立于任何UI框架或库。

- **新架构中的替代方案**:
    - 无需更改。该文件应在新项目的 `utils` 目录中按原样保留。

---

### 文件: `desktop-ui/utils/json_encoder.py` (新分析)

- **目的**: 此文件定义了 `CustomJSONEncoder`，一个Python标准库 `json.JSONEncoder` 的自定义子类。其目的是让 `json.dump()` 函数能够正确地序列化它本身不支持的数据类型，特别是 `numpy` 数组和 `numpy` 的数值类型。

- **功能细节与组件关联**:
  - **`default(self, obj)`**: 这是该类中唯一的方法。它覆盖了父类的 `default` 方法。当 `json.dump()` 遇到一个它不知道如何序列化的对象时，就会调用此方法。
  - **Numpy类型处理**:
    - 如果对象是 `np.ndarray`，它会调用 `.tolist()` 将其转换为标准的Python列表。
    - 如果对象是 `np.integer` (如 `np.int32`)，它会将其转换为标准的Python `int`。
    - 如果对象是 `np.floating` (如 `np.float64`)，它会将其转换为标准的Python `float`。
    - 如果对象是 `np.bool_`，它会将其转换为标准的Python `bool`。
  - **回退机制**: 如果对象不是它能处理的特殊numpy类型，它会调用 `super().default(obj)`，让父类来处理，如果父类也不认识该类型，则可能会引发一个 `TypeError`。
  - **用法**: 该类在其他服务（如 `ExportService`）中保存数据到JSON文件时被使用，用法如下：`json.dump(data, file, cls=CustomJSONEncoder)`。

- **重构处置**: **保留**

- **理由**:
  1.  **解决了常见问题**: 在使用像OpenCV或其他科学计算包时，序列化 `numpy` 数据类型是一个非常普遍的需求。创建一个自定义的JSON编码器是解决这个问题的标准、惯用的Python方案。
  2.  **干净且自包含**: 这个类很小，自包含，并且完美地只做一件事。
  3.  **框架无关**: 除了Python的标准 `json` 库和 `numpy` 之外，它没有任何其他依赖。它在任何架构中都是完全可复用的。

- **新架构中的替代方案**:
    - 无需更改。这是一个完美的工具模块。它应该被保留在 `utils` 目录中，并被新架构中任何需要将包含大量 `numpy` 数据的结构序列化为JSON的服务所使用。

---

### 文件: `desktop-ui/services/error_handler.py` (新分析)

- **目的**: 此文件定义了 `InputValidator` 类。其目的是提供可复用的方法，用于验证各种用户输入，例如文件路径和API密钥。它还定义了数据结构用于返回验证结果。

- **功能细节与组件关联**:
  - **数据结构**:
    - `ErrorLevel` (Enum): 定义了不同的错误严重级别（`INFO`, `WARNING`, `ERROR`, `CRITICAL`）。这个枚举似乎已被定义但未被 `InputValidator` 实际使用。
    - `ValidationResult` (dataclass): 一个结构化对象，用于返回验证检查的结果。它包含一个布尔 `is_valid` 标志和 `errors`、`warnings` 列表。这是一个很好的实践，因为它允许一个验证函数一次性返回多个问题。
  - **`InputValidator` 类**:
    - **`__init__`**: 它预编译了一个正则表达式字典（`api_patterns`），用于验证不同API密钥（如OpenAI, DeepL）的格式。
    - **验证方法**:
      - `validate_file_path`: 检查给定路径是否为空、是否存在且为文件。
      - `validate_image_file`: 首先调用 `validate_file_path`，如果通过，则检查文件扩展名是否为支持的图像格式之一。
      - `validate_api_key`: 检查密钥是否为空，如果提供了已知的提供商，则根据预定义的正则表达式验证其格式。
  - **单例模式**: 它使用模块级的 `_validator` 变量和 `get_validator()` 函数来实现单例模式，确保整个应用程序只使用一个验证器实例。

- **重构处置**: **保留并重命名**

- **理由**:
  1.  **有用且可复用的逻辑**: 验证逻辑是纯粹、可复用且封装良好的。集中验证规则（如API密钥格式）是一种良好的设计实践。
  2.  **框架无关**: 整个文件是纯Python，没有UI或框架特定的依赖。它可以在新架构中按原样使用。
  3.  **误导性的文件名**: 文件名 `error_handler.py` 不能准确反映其内容。该文件是关于*输入验证*，而不是*异常处理*或通用错误管理。将其重命名为 `validation_service.py` 会更合适，并提高代码清晰度。

- **新架构中的替代方案**:
    - 文件应重命名为 `validation_service.py` 以更好地反映其用途。
    - `InputValidator` 类可重命名为 `ValidationService` 以匹配其他服务的命名约定。
    - 该服务将被需要验证数据的其他服务或控制器使用。例如，`ConfigService` 可以使用 `ValidationService` 检查API密钥，或者 `EditorController` 可以用它来验证文件路径，然后再尝试加载图像。
    - `ErrorLevel` 枚举由于未使用，可以被移除，或者如果全局错误/日志系统需要它，则移到更合适的位置。

---


