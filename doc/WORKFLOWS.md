# 工作流程说明

本文档介绍程序的 5 种工作流程和相关功能。

---

## 📋 翻译流程模式

程序提供了一个"翻译流程模式"下拉菜单，包含 5 种工作流程：

---

## 1. 正常翻译流程（默认）

**用途**：直接翻译图片

**步骤**：
1. 添加图片文件或文件夹
2. 选择翻译器和目标语言
3. 点击"开始翻译"
4. 翻译完成后，结果保存在输出文件夹

---

## 2. 导出翻译

**用途**：翻译后导出翻译结果到 TXT 文件

**步骤**：
1. 选择"导出翻译"模式
2. 勾选"图片可编辑"（自动生成 JSON 文件）
3. 开始翻译
4. 程序会：
   - 完整翻译图片
   - 生成 `_translations.json` 文件
   - 生成 `_translated.txt` 文件（包含翻译结果）

---

## 3. 导出原文

**用途**：仅检测和识别文本，导出原文到 TXT 文件，不进行翻译

**步骤**：
1. 选择"导出原文"模式
2. 勾选"图片可编辑"（自动生成 JSON 文件）
3. 点击"仅生成原文模板"
4. 程序会：
   - 检测文本区域
   - OCR 识别原文
   - 生成 `_translations.json` 文件
   - 生成 `_original.txt` 文件（包含原文）
   - **不进行翻译**，直接停止

**后续手动翻译**：
1. 打开 `manga_translator_work/originals/图片名_original.txt` 文件
2. 将原文翻译成目标语言
3. **直接在 `_original.txt` 文件中修改**（或直接修改 JSON 文件的 `translation` 字段）

**TXT 文件优先级**（在"导入翻译并渲染"模式中）：
- **优先使用 `_original.txt`**（原文文件，用于手动翻译后导入）⭐ 最高优先级
- 如果不存在，使用 `_translated.txt`（翻译文件）
- 如果都不存在，直接使用 JSON 文件中的翻译

---

## 4. 导入翻译并渲染

**用途**：从 TXT 或 JSON 文件导入翻译内容，重新渲染图片，不进行翻译

**步骤**：
1. 选择"导入翻译并渲染"模式
2. 添加之前翻译过的图片（确保有对应的 `_translations.json` 文件）
3. 点击"导入翻译并渲染"
4. 程序会：
   - **预处理**：如果存在 `_translated.txt` 或 `_original.txt` 文件，先将 TXT 内容导入到 JSON 文件
   - **加载翻译**：从 JSON 文件加载翻译内容
   - **渲染图片**：使用加载的翻译内容渲染图片
   - **不进行翻译**，直接渲染

**TXT 文件导入优先级**：
- **优先使用 `_original.txt`**（原文文件，用于手动翻译后导入）⭐ 最高优先级
- 如果不存在，使用 `_translated.txt`（翻译文件）
- 如果都不存在，直接使用 JSON 文件中的翻译

**使用场景**：
- 修改了 TXT 文件中的翻译内容，需要导入并重新渲染
- 修改了 JSON 文件中的翻译内容，需要重新渲染
- 修改了渲染参数（字体、颜色、排版等），需要重新渲染

---

## 5. 仅超分（Upscale Only）

**用途**：仅对图片进行超分辨率处理，不进行文本检测和翻译

**步骤**：
1. 选择"仅超分"模式
2. 在"高级设置"中配置超分参数：
   - **超分模型**：选择 `waifu2x` 或 `realcugan`（推荐）
   - **超分倍数**：选择 2x、3x 或 4x
   - **Real-CUGAN 模型**：选择合适的预训练模型（如 `3x-denoise3x`）
   - **分块大小**：如果显存不足，设置分块大小（如 400）
3. 点击"开始翻译"
4. 程序会：
   - **跳过文本检测**
   - **跳过 OCR 识别**
   - **跳过翻译**
   - **仅执行超分处理**
   - 保存放大后的图片

**使用场景**：
- 单纯提高图片分辨率，不需要翻译
- 放大低分辨率漫画图片
- 图片降噪处理（使用 Real-CUGAN 降噪模型）

**推荐配置**：
- **高质量放大**：`realcugan` + `3x-denoise3x` 或 `3x-denoise3x-pro`
- **快速放大**：`waifu2x` + 2x/3x/4x
- **显存不足**：设置 `tile_size=400`（或更小）

---

## 📝 图片可编辑选项

**作用**：勾选后，程序会生成 `_translations.json` 文件，包含：
- 检测到的文本区域
- OCR 识别的原文
- 翻译结果
- 文本框位置信息

**用途**：
- 方便后续修改翻译内容
- 可以在编辑器中打开图片进行可视化编辑
- 可以使用"导入翻译并渲染"模式重新渲染

---

## 🤖 AI 断句功能

**支持范围**：支持 OpenAI、Gemini 翻译器（包括高质量模式）

**作用**：使用 AI 智能断句，自动优化文本换行

**工作原理**：
- 在翻译请求中添加 `[Original regions: X]` 前缀
- 告诉 AI 原文有多少个文本区域
- AI 根据原文区域数量智能断句
- **不会增加 API 调用次数**，只是在同一次调用中添加额外信息

**启用方法**：
1. 选择支持的翻译器（OpenAI、Gemini、高质量翻译 OpenAI、高质量翻译 Gemini）
2. 在渲染设置中勾选"AI断句"
3. 开始翻译

---

## 📂 自定义导出原文模版

**用途**：自定义导出原文的格式，方便使用外部工具翻译

**模版文件位置**：`examples/translation_template.json`

**工作原理**：
- 模版定义了**一组文本框**的格式
- 导出时，程序会按照模版中的条目数量分组
- **重复的是文本框部分**，而不是整个 JSON 结构
- 例如：模版有 3 个占位符对，则每 3 个文本框作为一组输出

**示例模版**（3 个文本框一组）：
```json
{
    "<original>": "<translated>",
    "<original>": "<translated>",
    "<original>": "<translated>"
}
```

**导出效果示例**：
假设检测到 6 个文本框，使用上述 3 个占位符的模版，导出结果如下：

```json
{
    "你好": "Hello",
    "世界": "World",
    "欢迎": "Welcome",

    ...

    "再见": "Goodbye",
    "谢谢": "Thank you",
    "早安": "Good morning"
}
```

**使用说明**：
1. 编辑 `examples/translation_template.json` 文件
2. 定义一组文本框的格式（可以是 1 个、3 个或任意数量）
3. 使用 `<original>` 和 `<translated>` 作为占位符
4. 导出原文时，每组文本框会重复使用这个格式
5. 手动翻译后，使用"导入翻译并渲染"功能导入

**注意事项**：
- 模版中有几个占位符对，就会每几个文本框分为一组
- 如果文本框总数不是模版条目数的整数倍，最后一组会包含剩余的所有文本框

---

## 💾 工作文件路径（自动生成）

程序会在图片所在目录创建 `manga_translator_work` 文件夹，包含：

- **JSON 文件**：`manga_translator_work/json/图片名_translations.json`
  - 包含文本区域、原文、翻译、位置信息

- **原文 TXT**：`manga_translator_work/originals/图片名_original.txt`
  - 导出原文时生成

- **翻译 TXT**：`manga_translator_work/translations/图片名_translated.txt`
  - 手动翻译后保存在此

- **修复图片**：`manga_translator_work/inpainted/图片名_inpainted.png`
  - 擦除文字后的图片

---

## ⚡ 流水线并行模式（Pipeline Mode）

**用途**：大幅提升在线翻译器的处理速度

### 原理说明

**传统串行流程**：

每张图片必须完成所有步骤后，才能开始处理下一张：

```
图片1: [检测] → [OCR] → [翻译] → [渲染] ✅
图片2: [检测] → [OCR] → [翻译] → [渲染] ✅
图片3: [检测] → [OCR] → [翻译] → [渲染] ✅

问题：在等待AI翻译返回时，GPU和处理器处于空闲状态
```

**流水线并行流程**：

将不同步骤分开执行，在等待翻译时同时处理其他图片：

```
时间轴：
  0s: [图片1-检测+OCR]
  5s: [图片1-翻译]          [图片2-检测+OCR]
 10s: [图片1-渲染]          [图片2-翻译]          [图片3-检测+OCR]
 15s: [图片1✅]            [图片2-渲染]          [图片3-翻译]
 20s:                       [图片2✅]            [图片3-渲染]
 25s:                                           [图片3✅]

优势：三个阶段同时进行，总时间从45s减少到25s！
```

### 性能对比

| 翻译器类型 | 传统模式 | 流水线模式 | 提速 |
|--------------|----------|--------------|------|
| **在线API** (OpenAI/Gemini/DeepL) | 100% | **60-70%** | **30-40% 提速** |
| **离线翻译** (Sugoi/NLLB) | 100% | 90-95% | 5-10% 提速 |
| **本地快速** (不翻译) | 100% | 95-100% | 微小提升 |

✅ **最佳适用**：使用在线API翻译器时，因为网络等待时间最长

### 使用步骤

1. **打开主界面**
2. **切换到"高级设置"标签页**
3. **勾选"流水线并行模式"**
4. **选择翻译器**（建议 OpenAI 或 Gemini）
5. **添加图片**（至少 2 张）
6. **开始翻译**

### 日志输出示例

```
==================================================
🚀 Pipeline Mode Enabled: Parallel Processing
  • Detection/OCR and Translation run in parallel
  • Expected speedup: 30-50% for online translators
==================================================

[Pipeline-Preprocess] 🔍 Processing image 1/10
[Pipeline-Preprocess] ✅ Image 1 ready for translation
[Pipeline-Translate] 🌐 Translating image 1/10
[Pipeline-Preprocess] 🔍 Processing image 2/10
[Pipeline-Preprocess] ✅ Image 2 ready for translation
[Pipeline-Translate] ✅ Image 1 translation completed
[Pipeline-Render] 🎨 Rendering image 1/10
[Pipeline-Translate] 🌐 Translating image 2/10
[Pipeline-Preprocess] 🔍 Processing image 3/10
...
[Pipeline] 📊 Progress: 10/10 images completed

==================================================
🎉 Pipeline Processing Completed: 10 images
==================================================
```

### 注意事项

✅ **适用场景**：
- 批量处理多张图片（≥2张）
- 使用在线API翻译器（OpenAI/Gemini/DeepL）
- 正常翻译流程或导出翻译模式

⛔ **不适用场景**：
- 单张图片处理
- 导出原文模式（template mode）
- 导入翻译并渲染模式（load_text mode）

💡 **最佳实践**：
- 同时设置 `batch_size > 1` 和 `pipeline_mode = true` 以获得最佳性能
- 如果内存不足，系统会自动限制队列大小
- 网络不稳定时会自动重试失败的图片

### 技术细节

流水线采用 **三个并行工作线程**：

1. **预处理工作器** (Preprocess Worker)
   - 执行：图片加载、文本检测、OCR识别
   - 输出：带有文本区域的 Context 对象

2. **翻译工作器** (Translate Worker)
   - 执行：AI翻译、后处理
   - 输出：带有翻译结果的 Context 对象

3. **渲染工作器** (Render Worker)
   - 执行：图像修复、文字渲染、文件保存
   - 输出：最终的翻译图片

三个线程通过 **asyncio.Queue** 连接，实现流水线并行处理。

---

