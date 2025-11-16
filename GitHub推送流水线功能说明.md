# GitHub推送流水线功能说明

## 📋 当前状态

已经准备好只包含**流水线功能**的分支，需要推送到GitHub。

**分支**: `dev-pipeline-only`  
**基于提交**: `8774c27 - feat: 实现四线流水线功能`  
**目标**: 推送到 `https://github.com/hgmzhn/manga-translator-ui.git` 的 `dev` 分支

---

## 📦 包含的功能

### 1. 配置文件修改

**`desktop_qt_ui/core/config_models.py`**:
```python
pipeline_mode: bool = False  # 流水线并行模式
pipeline_line1_concurrency: int = 2  # 线1并发：检测+OCR
pipeline_line2_concurrency: int = 3  # 线2并发：翻译
pipeline_translation_batch_size: int = 3  # 线2翻译批量大小
pipeline_line3_concurrency: int = 1  # 线3并发：修复/Inpainting
pipeline_line4_concurrency: int = 1  # 线4并发：渲染+超分
```

### 2. UI配置名称

**`desktop_qt_ui/app_logic.py`**:
- 添加了流水线相关配置项的中文显示名称

### 3. 配置示例

**`examples/config-example.json`**:
- 添加了流水线配置的默认值

### 4. 核心功能

**`manga_translator/manga_translator.py`**:
- 实现了四线流水线并行处理架构
- Line1: 检测+OCR并发
- Line2: 批量翻译收集机制
- Line3: 修复并发控制
- Line4: 渲染+超分并发控制

---

## 🚀 推送方法

### 方法1：使用GitHub Desktop（推荐）⭐

1. 打开GitHub Desktop
2. 切换到 `dev-pipeline-only` 分支
3. 点击 "Push origin" 按钮
4. 如果提示没有上游分支，选择 "Publish branch"
5. 完成后，在GitHub网站上创建Pull Request，将 `dev-pipeline-only` 合并到 `dev` 分支

### 方法2：使用Personal Access Token

#### 步骤1：创建GitHub Personal Access Token

1. 访问：https://github.com/settings/tokens
2. 点击 "Generate new token" → "Generate new token (classic)"
3. 设置权限：
   - ✅ `repo` (全部勾选)
   - ✅ `workflow`
4. 点击 "Generate token"
5. **复制token**（只显示一次！）

#### 步骤2：配置Git凭据

**PowerShell命令**：
```powershell
cd "d:\漫画\1"

# 方法A：使用token推送（临时）
git push https://<YOUR_TOKEN>@github.com/hgmzhn/manga-translator-ui.git dev-pipeline-only:dev

# 方法B：配置凭据助手（持久）
git config credential.helper store
git push origin dev-pipeline-only:dev
# 输入用户名：hgmzhn
# 输入密码：<YOUR_TOKEN>
```

#### 步骤3：验证推送

```bash
# 检查远程分支
git ls-remote origin dev

# 应该看到dev分支已更新
```

### 方法3：使用SSH（如果已配置）

```bash
# 1. 添加SSH远程
git remote add github-ssh git@github.com:hgmzhn/manga-translator-ui.git

# 2. 推送
git push github-ssh dev-pipeline-only:dev

# 3. 删除临时远程（可选）
git remote remove github-ssh
```

---

## 📝 具体命令

### 当前状态确认

```bash
cd "d:\漫画\1"
git branch  # 确认在 dev-pipeline-only 分支
git log --oneline -3  # 查看提交历史
```

**预期输出**：
```
8774c27 (HEAD -> dev-pipeline-only) feat: 实现四线流水线功能
a03aa3b 合并私有仓库的最新更新到本地分支
5510338 合并四线流水线功能
```

### 推送命令（使用Token）

```bash
# 替换<YOUR_TOKEN>为你的GitHub Personal Access Token
git push https://<YOUR_TOKEN>@github.com/hgmzhn/manga-translator-ui.git dev-pipeline-only:dev
```

**成功输出示例**：
```
Enumerating objects: 17, done.
Counting objects: 100% (17/17), done.
Delta compression using up to 20 threads
Compressing objects: 100% (9/9), done.
Writing objects: 100% (10/10), 14.70 KiB, done.
Total 10 (delta 6), reused 0 (delta 0)
To https://github.com/hgmzhn/manga-translator-ui.git
   dd2da16..8774c27  dev-pipeline-only -> dev
```

---

## ⚠️ 注意事项

### 1. 不包含的功能

**本次推送不包含**：
- ❌ v2.5.7 分段并行翻译功能
- ❌ 分段阈值配置
- ❌ 章节检测功能
- ❌ 其他后续添加的功能

**只包含**：
- ✅ 基础四线流水线架构
- ✅ 流水线配置参数
- ✅ UI配置项

### 2. Token安全

- ⚠️ **不要**将Token提交到Git仓库
- ⚠️ **不要**分享Token给他人
- ✅ 使用后可以在GitHub删除Token
- ✅ Token只用于临时推送

### 3. 分支管理

推送后在GitHub上：
```
origin/main (最新)
   ↓
origin/dev (包含流水线功能)
```

如果需要，可以在GitHub网站上创建Pull Request将dev合并到main。

---

## 🔍 验证推送成功

### 在GitHub网站上验证

1. 访问：https://github.com/hgmzhn/manga-translator-ui
2. 切换到 `dev` 分支
3. 查看最新提交：应该看到 "feat: 实现四线流水线功能"
4. 检查文件修改：
   - `desktop_qt_ui/core/config_models.py`
   - `desktop_qt_ui/app_logic.py`
   - `examples/config-example.json`
   - `manga_translator/manga_translator.py`

### 本地验证

```bash
# 拉取验证
git fetch origin
git log origin/dev --oneline -3

# 应该看到
8774c27 feat: 实现四线流水线功能
...
```

---

## 🎯 推荐流程（GitHub Desktop）

这是最简单最安全的方法：

1. **打开GitHub Desktop**
2. **选择仓库**: manga-translator-ui
3. **切换分支**: dev-pipeline-only
4. **点击"Publish branch"** 或 **"Push origin"**
5. **在GitHub网站上**:
   - 进入仓库页面
   - 点击"Compare & pull request"
   - 选择 base: `dev` ← compare: `dev-pipeline-only`
   - 创建Pull Request
   - 合并（Merge pull request）
6. **完成！**

---

## 📚 后续步骤（可选）

### 删除临时分支

```bash
# 本地删除
git branch -d dev-pipeline-only

# 远程删除（如果推送了dev-pipeline-only分支）
git push origin --delete dev-pipeline-only
```

### 清理本地

```bash
# 切换回主开发分支
git checkout my-custom-features

# 清理
git gc
```

---

## 💡 常见问题

### Q: 为什么推送失败？
**A**: 需要GitHub认证。使用GitHub Desktop或Personal Access Token。

### Q: 忘记Token怎么办？
**A**: Token只显示一次。如果忘记，删除旧token，重新生成新的。

### Q: 可以直接推送到main吗？
**A**: 建议推送到dev分支，然后通过Pull Request合并到main，更安全。

### Q: 如何验证只包含流水线功能？
**A**: 查看提交历史，8774c27之后的提交（42a77d0等）不应该包含在内。

---

**文档版本**: v1.0  
**创建时间**: 2025-11-16  
**作者**: Windsurf Cascade
