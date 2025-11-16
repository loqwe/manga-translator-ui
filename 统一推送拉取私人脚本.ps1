# 统一推送拉取私人脚本.ps1
# 统一的推送/拉取脚本 - 支持选择推送或拉取操作

param(
    [ValidateSet("push", "pull", "")]
    [string]$Action = "",
    [string]$BranchName = "my-custom-features",
    [string]$PrivateRepoUrl = "",
    [string]$RemoteName = "my-private"
)

# 设置控制台编码为 UTF-8
chcp 65001 | Out-Null
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "私有远程仓库同步工具" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 如果没有指定操作，显示菜单让用户选择
if ([string]::IsNullOrWhiteSpace($Action)) {
    Write-Host "请选择操作：" -ForegroundColor Yellow
    Write-Host "  1. 推送 (Push) - 将本地分支推送到远程仓库" -ForegroundColor Gray
    Write-Host "  2. 拉取 (Pull) - 从远程仓库拉取分支更新" -ForegroundColor Gray
    Write-Host ""
    $choice = Read-Host "请输入选项 (1/2)"
    
    switch ($choice) {
        "1" { $Action = "push" }
        "2" { $Action = "pull" }
        default {
            Write-Host "[错误] 无效的选项！" -ForegroundColor Red
            exit 1
        }
    }
}

# 检查是否在 Git 仓库中
if (-not (Test-Path .git)) {
    Write-Host "[错误] 当前目录不是 Git 仓库！" -ForegroundColor Red
    exit 1
}

# 检查 Git 是否安装
$gitVersion = git --version 2>&1
if ($LASTEXITCODE -ne 0 -or $gitVersion -match "error|not found|不是") {
    Write-Host "[错误] 未找到 Git！" -ForegroundColor Red
    exit 1
}
Write-Host "[成功] Git 已安装: $gitVersion" -ForegroundColor Green

Write-Host ""

# 步骤 1: 检查或配置远程仓库
Write-Host "步骤 1: 检查远程仓库配置..." -ForegroundColor Yellow
$remoteList = git remote 2>&1 | Out-String
$remoteExists = $remoteList -match $RemoteName

if (-not $remoteExists) {
    if ([string]::IsNullOrWhiteSpace($PrivateRepoUrl)) {
        Write-Host "   未找到远程仓库 '$RemoteName'，请输入私有仓库 URL" -ForegroundColor Gray
        Write-Host "   例如：https://gitee.com/你的用户名/你的仓库名.git" -ForegroundColor Gray
        $PrivateRepoUrl = Read-Host "   私有仓库 URL"
    }
    
    if ([string]::IsNullOrWhiteSpace($PrivateRepoUrl)) {
        Write-Host "[错误] 未提供私有仓库 URL！" -ForegroundColor Red
        exit 1
    }
    
    # 修复URL格式：移除/tree/分支名路径
    $PrivateRepoUrl = $PrivateRepoUrl -replace '/tree/[^/]+/?$', ''
    if (-not $PrivateRepoUrl.EndsWith('.git')) {
        $PrivateRepoUrl += '.git'
    }
    
    git remote add $RemoteName $PrivateRepoUrl 2>&1 | Out-Null
    Write-Host "   [成功] 已添加远程仓库 '$RemoteName': $PrivateRepoUrl" -ForegroundColor Green
} else {
    $existingRemote = git remote get-url $RemoteName 2>&1 | Out-String
    $existingRemote = $existingRemote.Trim()
    
    # 检查现有URL是否正确，如果包含/tree/路径则修复
    if ($existingRemote -match '/tree/') {
        Write-Host "   [警告] 检测到错误的远程URL格式，正在修复..." -ForegroundColor Yellow
        $fixedUrl = $existingRemote -replace '/tree/[^/]+/?$', ''
        if (-not $fixedUrl.EndsWith('.git')) {
            $fixedUrl += '.git'
        }
        git remote set-url $RemoteName $fixedUrl
        Write-Host "   [成功] 已修复远程仓库URL: $fixedUrl" -ForegroundColor Green
        $PrivateRepoUrl = $fixedUrl
    } else {
        Write-Host "   [成功] 找到远程仓库 '$RemoteName': $existingRemote" -ForegroundColor Green
        $PrivateRepoUrl = $existingRemote
    }
}

# 根据操作类型执行不同的逻辑
if ($Action -eq "push") {
    # ========== 推送操作 ==========
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "执行推送操作" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    
    # 检查分支是否存在
    Write-Host "步骤 2: 检查分支 '$BranchName'..." -ForegroundColor Yellow
    $branchExists = git branch --list $BranchName
    if (-not $branchExists) {
        Write-Host "[错误] 分支 '$BranchName' 不存在！" -ForegroundColor Red
        Write-Host "请先运行 setup-local-branch.ps1 创建功能分支。" -ForegroundColor Yellow
        exit 1
    }
    Write-Host "   [成功] 分支 '$BranchName' 存在" -ForegroundColor Green
    
    # 切换到功能分支
    Write-Host ""
    Write-Host "步骤 3: 切换到分支 '$BranchName'..." -ForegroundColor Yellow
    $currentBranch = git branch --show-current
    if ($currentBranch -ne $BranchName) {
        git checkout $BranchName
        Write-Host "   [成功] 已切换到分支 '$BranchName'" -ForegroundColor Green
    } else {
        Write-Host "   已在分支 '$BranchName'" -ForegroundColor Gray
    }
    
    # 推送分支
    Write-Host ""
    Write-Host "步骤 4: 推送分支到私有仓库..." -ForegroundColor Yellow
    Write-Host "   正在推送 '$BranchName' 到 '$RemoteName'..." -ForegroundColor Gray
    Write-Host "   提示：如果首次推送，需要输入用户名和密码（密码使用 Personal Access Token）" -ForegroundColor Yellow
    Write-Host ""
    
    try {
        git push -u $RemoteName $BranchName
        if ($LASTEXITCODE -eq 0) {
            Write-Host "   [成功] 分支已推送到私有仓库！" -ForegroundColor Green
        } else {
            Write-Host "   [错误] 推送失败！" -ForegroundColor Red
            Write-Host "   可能的原因：" -ForegroundColor Yellow
            Write-Host "   1. 仓库 URL 不正确" -ForegroundColor Gray
            Write-Host "   2. 没有访问权限（需要配置 SSH 密钥或访问令牌）" -ForegroundColor Gray
            Write-Host "   3. 网络连接问题" -ForegroundColor Gray
            Write-Host ""
            Write-Host "   提示：如果使用 GitHub/Gitee，需要：" -ForegroundColor Yellow
            Write-Host "   - 使用 Personal Access Token (PAT) 作为密码" -ForegroundColor Gray
            Write-Host "   - 或配置 SSH 密钥" -ForegroundColor Gray
            Write-Host "   详细说明请查看 README_PUSH_TO_PRIVATE.md" -ForegroundColor Gray
            exit 1
        }
    } catch {
        Write-Host "   [错误] 推送失败：$_" -ForegroundColor Red
        exit 1
    }
    
    # 验证远程仓库配置
    Write-Host ""
    Write-Host "步骤 5: 验证远程仓库配置..." -ForegroundColor Yellow
    $remoteUrl = git remote get-url $RemoteName 2>&1 | Out-String
    $remoteUrl = $remoteUrl.Trim()
    Write-Host "   远程仓库: $RemoteName -> $remoteUrl" -ForegroundColor Gray
    
    $remoteBranches = git branch -r --list "$RemoteName/$BranchName" 2>&1 | Out-String
    $remoteBranches = $remoteBranches.Trim()
    if (-not [string]::IsNullOrWhiteSpace($remoteBranches)) {
        Write-Host "   [成功] 远程分支已存在: $RemoteName/$BranchName" -ForegroundColor Green
    } else {
        Write-Host "   [警告] 未找到远程分支，请检查推送是否成功" -ForegroundColor Yellow
    }
    
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "[成功] 推送完成！" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Cyan
    
} elseif ($Action -eq "pull") {
    # ========== 拉取操作 ==========
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "执行拉取操作" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    
    # 获取远程分支信息
    Write-Host "步骤 2: 获取远程分支信息..." -ForegroundColor Yellow
    Write-Host "   正在从 '$RemoteName' 获取更新..." -ForegroundColor Gray
    
    try {
        git fetch $RemoteName
        if ($LASTEXITCODE -eq 0) {
            Write-Host "   [成功] 已获取远程仓库信息" -ForegroundColor Green
        } else {
            Write-Host "   [错误] 获取远程信息失败！" -ForegroundColor Red
            Write-Host "   可能的原因：" -ForegroundColor Yellow
            Write-Host "   1. 仓库 URL 不正确" -ForegroundColor Gray
            Write-Host "   2. 没有访问权限（需要配置 SSH 密钥或访问令牌）" -ForegroundColor Gray
            Write-Host "   3. 网络连接问题" -ForegroundColor Gray
            exit 1
        }
    } catch {
        Write-Host "   [错误] 获取失败：$_" -ForegroundColor Red
        exit 1
    }
    
    # 检查远程分支是否存在
    Write-Host ""
    Write-Host "步骤 3: 检查远程分支..." -ForegroundColor Yellow
    $remoteBranch = "$RemoteName/$BranchName"
    $remoteBranchList = git branch -r --list $remoteBranch 2>&1 | Out-String
    $remoteBranchExists = $remoteBranchList.Trim()
    
    if ([string]::IsNullOrWhiteSpace($remoteBranchExists)) {
        Write-Host "   [错误] 远程分支 '$remoteBranch' 不存在！" -ForegroundColor Red
        Write-Host "   可用的远程分支：" -ForegroundColor Yellow
        git branch -r --list "$RemoteName/*" | ForEach-Object { Write-Host "     $_" -ForegroundColor Gray }
        exit 1
    }
    
    Write-Host "   [成功] 找到远程分支: $remoteBranch" -ForegroundColor Green
    
    # 检查本地分支
    Write-Host ""
    Write-Host "步骤 4: 检查本地分支..." -ForegroundColor Yellow
    $localBranchExists = git branch --list $BranchName
    $currentBranch = git branch --show-current
    
    if (-not $localBranchExists) {
        Write-Host "   本地分支 '$BranchName' 不存在，将创建新分支..." -ForegroundColor Yellow
        
        # 检查是否有未提交的更改
        $status = git status --porcelain
        if ($status) {
            Write-Host "   [警告] 检测到未提交的更改，正在暂存..." -ForegroundColor Yellow
            git stash push -m "自动暂存：切换到$BranchName分支前"
            Write-Host "   [成功] 已暂存当前更改" -ForegroundColor Green
        }
        
        git checkout -b $BranchName $remoteBranch
        if ($LASTEXITCODE -eq 0) {
            Write-Host "   [成功] 已创建并切换到分支 '$BranchName'" -ForegroundColor Green
        } else {
            Write-Host "   [错误] 创建分支失败！" -ForegroundColor Red
            exit 1
        }
    } else {
        Write-Host "   本地分支 '$BranchName' 已存在" -ForegroundColor Gray
        
        # 切换到目标分支
        if ($currentBranch -ne $BranchName) {
            # 检查是否有未提交的更改
            $status = git status --porcelain
            if ($status) {
                Write-Host "   [警告] 检测到未提交的更改，正在暂存..." -ForegroundColor Yellow
                git stash push -m "自动暂存：切换到$BranchName分支前"
                Write-Host "   [成功] 已暂存当前更改" -ForegroundColor Green
            }
            
            git checkout $BranchName
            if ($LASTEXITCODE -eq 0) {
                Write-Host "   [成功] 已切换到分支 '$BranchName'" -ForegroundColor Green
            } else {
                Write-Host "   [错误] 切换分支失败！" -ForegroundColor Red
                exit 1
            }
        } else {
            Write-Host "   已在分支 '$BranchName'" -ForegroundColor Gray
        }
        
        # 设置跟踪关系（如果还没有）
        $trackingBranch = git rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>&1 | Out-String
        $trackingBranch = $trackingBranch.Trim()
        if ($trackingBranch -match "error|fatal" -or [string]::IsNullOrWhiteSpace($trackingBranch) -or $trackingBranch -ne $remoteBranch) {
            git branch --set-upstream-to=$remoteBranch $BranchName 2>&1 | Out-Null
            Write-Host "   [成功] 已设置分支跟踪关系" -ForegroundColor Green
        }
    }
    
    # 拉取更新
    Write-Host ""
    Write-Host "步骤 5: 拉取远程更新..." -ForegroundColor Yellow
    Write-Host "   正在从 '$remoteBranch' 拉取更新..." -ForegroundColor Gray
    
    # 检查本地是否有未推送的提交
    $localCommits = git rev-list --count HEAD ^"$remoteBranch" 2>&1
    $localCommitsCount = if ($localCommits -match '^\d+$') { [int]$localCommits } else { 0 }
    
    if ($localCommitsCount -gt 0) {
        Write-Host "   [提示] 检测到 $localCommitsCount 个本地提交，将进行合并操作..." -ForegroundColor Yellow
        # 使用merge策略拉取，保留提交历史
        git pull $RemoteName $BranchName --no-rebase
    } else {
        # 没有本地提交，可以使用fast-forward
        git pull $RemoteName $BranchName
    }
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "   [成功] 已成功拉取更新！" -ForegroundColor Green
        
        # 检查是否有暂存的更改需要恢复
        $stashList = git stash list
        if ($stashList -match "自动暂存：切换到$BranchName分支前") {
            Write-Host "   [提示] 检测到之前暂存的更改，正在恢复..." -ForegroundColor Yellow
            $popResult = git stash pop 2>&1
            if ($LASTEXITCODE -eq 0) {
                Write-Host "   [成功] 已恢复暂存的更改" -ForegroundColor Green
            } else {
                Write-Host "   [警告] 恢复暂存更改时出现问题：$popResult" -ForegroundColor Yellow
                Write-Host "   [提示] 请手动检查并处理：git stash list" -ForegroundColor Gray
            }
        }
    } else {
        Write-Host "   [错误] 拉取失败！" -ForegroundColor Red
        Write-Host "   可能的原因：" -ForegroundColor Yellow
        Write-Host "   1. 存在合并冲突（需要手动解决）" -ForegroundColor Gray
        Write-Host "   2. 网络连接问题" -ForegroundColor Gray
        Write-Host "   3. 远程分支不存在或无权限访问" -ForegroundColor Gray
        Write-Host ""
        Write-Host "   建议操作：" -ForegroundColor Yellow
        Write-Host "   - 检查冲突: git status" -ForegroundColor Gray
        Write-Host "   - 解决冲突后: git add . ; git commit" -ForegroundColor Gray
        Write-Host "   - 查看远程分支: git branch -r" -ForegroundColor Gray
        exit 1
    }
    
    # 显示状态
    Write-Host ""
    Write-Host "步骤 6: 显示当前状态..." -ForegroundColor Yellow
    $currentBranch = git branch --show-current
    $lastCommit = git log -1 --oneline
    Write-Host "   当前分支: $currentBranch" -ForegroundColor Gray
    Write-Host "   最新提交: $lastCommit" -ForegroundColor Gray
    
    $status = git status --short
    if ($status) {
        Write-Host "   工作区状态:" -ForegroundColor Gray
        $status | ForEach-Object { Write-Host "     $_" -ForegroundColor Gray }
    } else {
        Write-Host "   工作区干净，与远程同步" -ForegroundColor Green
    }
    
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "[成功] 拉取完成！" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Cyan
}

# 显示总结信息
Write-Host ""
Write-Host "总结:" -ForegroundColor Yellow
Write-Host "   • 操作类型: $Action" -ForegroundColor Gray
Write-Host "   • 功能分支: $BranchName" -ForegroundColor Gray
Write-Host "   • 远程仓库: $RemoteName -> $PrivateRepoUrl" -ForegroundColor Gray
Write-Host ""
Write-Host "使用提示:" -ForegroundColor Yellow
Write-Host "   • 查看远程仓库: git remote -v" -ForegroundColor Gray
Write-Host "   • 推送更新: 运行此脚本选择推送，或 git push $RemoteName $BranchName" -ForegroundColor Gray
Write-Host "   • 拉取更新: 运行此脚本选择拉取，或 git pull $RemoteName $BranchName" -ForegroundColor Gray
Write-Host "   • 查看分支状态: git status" -ForegroundColor Gray
Write-Host ""

