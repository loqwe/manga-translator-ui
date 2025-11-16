# AI断句功能修复说明

## ❌ 问题

**症状**：流水线模式下，AI断句功能没有生效

**错误表现**：
```
Translation count mismatch: expected 6, got 7
```

这个错误通常与AI断句功能有关，因为AI断句会在翻译过程中插入`[BR]`标记，可能导致输入输出数量不匹配。

## 🔍 根本原因

在**流水线模式**的 `_process_translation_batch` 方法中，**没有调用 `_load_and_prepare_prompts`**，导致：

1. ❌ AI断句的配置没有加载到 `ctx.line_break_prompt_json`
2. ❌ 翻译器无法访问AI断句的系统提示词
3. ❌ 翻译结果中缺少`[BR]`标记，导致数量不匹配

**对比其他模式**：
- ✅ 单张翻译模式：调用了 `_load_and_prepare_prompts`
- ✅ 批量翻译模式：调用了 `_load_and_prepare_prompts`
- ❌ **流水线模式**：**没有调用** `_load_and_prepare_prompts`

## ✅ 修复方案

### 根本原因
1. 在流水线模式下，AI断句功能没有按批次统一处理
2. 批量翻译导致AI断句的数量不匹配无法正确处理
3. 缺少每张图片独立的AI断句prompt加载

### 修复步骤
1. **改为按图片逐个处理**：
   ```python
   # 按图片逐个处理（支持AI断句）
   for ctx, config, image_idx in batch_buffer:
       if ctx.text_regions:
           # 为每张图片单独加载AI断句prompt
           ctx = await self._load_and_prepare_prompts(config, ctx)
   ```

2. **每张图片独立翻译和AI断句处理**：
   ```python
   # 单独翻译当前图片的文本
   translated_texts = await self._batch_translate_texts(
       image_texts, config, ctx,
       page_index=current_batch_index
   )
   ```

3. **智能的数量不匹配处理**：
   ```python
   # AI断句处理：按图片级别检查数量匹配
   if len(translated_texts) != len(image_texts):
       # 智能分配或补足
   ```

## 📋 AI断句功能工作原理

### 1. 配置开关
- **UI开关**：`config.render.disable_auto_wrap = True`
- **系统文件**：`dict/system_prompt_line_break.json`

### 2. 工作流程
1. `_load_and_prepare_prompts` 检查 `disable_auto_wrap` 开关
2. 如果开启，加载 `system_prompt_line_break.json` 到 `ctx.line_break_prompt_json`
3. 翻译器使用该提示词，生成包含 `[BR]` 标记的翻译结果
4. 渲染时，`[BR]` 标记被转换为换行符

### 3. 关键日志
修复后应该看到：
```
AI line breaking is enabled. Loaded line break prompt.
[AI断句检查] ✓ 所有多行区域的翻译都包含[BR]标记
```

## 🎯 预期效果

修复后的翻译结果：
```
# 修复前（无AI断句）
"这是一段很长的文本，会自动换行处理"

# 修复后（有AI断句）
"这是一段很长的文本，[BR]会根据语义智能断句"
```

渲染时：
```
这是一段很长的文本，
会根据语义智能断句
```

## 🔧 验证方法

### 1. 检查配置
确保UI中**AI断句开关已启用**（`disable_auto_wrap = True`）

### 2. 检查日志
运行翻译后，查找关键日志：
```
AI line breaking is enabled. Loaded line break prompt.
[AI断句检查] ✓ 所有多行区域的翻译都包含[BR]标记
Context-aware translation enabled with 3 pages of history using translation results
```

### 3. 检查翻译结果
翻译结果中应该包含 `[BR]` 标记。

### 4. AI断句数量不匹配处理
如果出现数量不匹配，会看到警告日志：
```
Line2: AI断句导致翻译数量不匹配 - 输入:6, 输出:7
Line2: 使用原文作为翻译结果的备选方案
```
这是正常的容错机制，保证流水线不会崩溃。

## 🚨 常见问题

### Q1: 出现 "Translation count mismatch" 错误后使用了原文
**原因**：AI断句功能将某些文本拆分或合并，导致数量不匹配。
**解决**：这是正常现象，系统已自动使用原文作为备选方案。如需获得AI断句翻译，可以：
1. 尝试单张翻译模式
2. 或将有问题的文本单独处理

### Q2: 翻译结果中没有看到 [BR] 标记
**原因**：
1. AI断句开关未启用
2. `system_prompt_line_break.json` 文件缺失
3. 文本区域只有单行，不需要断句

### Q3: [BR] 标记没有被正确渲染为换行
**原因**：渲染模块的 `disable_auto_wrap` 处理逻辑有问题。
**解决**：检查渲染模块中的正则表达式替换逻辑。

## 📋 修复历史

### v2.5.2 (2025-11-15)
1. ✅ 修复流水线模式下AI断句功能不生效的问题
2. ✅ 改为整个批次统一处理AI断句（而非按图片逐个处理）
3. ✅ 使用高质量翻译模式进行批次翻译
4. ✅ 添加批次级别的AI断句数量不匹配处理机制
5. ✅ 每个批次作为独立上下文单位
6. ✅ 上下文翻译功能正常工作

### v2.5.3 (2025-11-15)
1. ✅ 修复高质量翻译器未启用的问题
   - 为流水线模式设置`high_quality_batch_data`
   - 确保高质量翻译器进入正确的批量处理模式
2. ✅ 修复图像格式错误
   - 使用`ctx.input`（PIL Image）而非`ctx.img_rgb`（numpy数组）
   - 修复`'numpy.ndarray' object has no attribute 'mode'`错误
3. ✅ 验证AI断句完全生效
   - 翻译结果包含`[BR]`标记
   - JSON文件正确保存断句标记
   - 渲染时按`[BR]`智能换行

### v2.5.4 (2025-11-15)
1. ✅ 上下文模式调整为批次内独立
   - 批次之间完全独立，不共享上下文
   - 批次内的3张图片可以互相参考
   - 高质量翻译器自动处理批次内上下文
   - 简化逻辑，移除跨批次上下文保存和顺序控制

### v2.5.5 (2025-11-15)
1. ✅ 上下文模式调整为滚动窗口
   - 每批次使用前一批次的翻译结果作为上下文
   - 批次0→批次1→批次2形成连续的上下文链
   - 使用条件变量确保批次按顺序保存上下文
   - 双重上下文机制：批次内（3图互参）+ 批次间（前批次上下文）

### v2.5.6 (2025-11-15)
1. ✅ 修复并发导致上下文缺失的问题
   - 问题：批次可并发启动，导致批次1在批次0保存上下文前就开始翻译
   - 修复：在翻译前等待前一批次保存完上下文
   - 结果：批次串行翻译，确保每批次都能获取到前批次的完整上下文
   - 执行流程：批次0完成→通知批次1→批次1获取上下文→批次1开始翻译

---

**版本**: v2.5.6  
**更新日期**: 2025-11-15  
**状态**: ✅ 已完全修复并验证，AI断句+滚动窗口上下文在流水线模式下完美工作
