# CangjieNext Manifest

本仓库保存 GitHub 上 CangjieNext 组织的 [repo](https://gerrit.googlesource.com/git-repo/) 工具
manifest，用于一键检出完整的仓颉工具链多仓库代码。

```
manifest
└── default.xml
└── cangjie
    └── cangjie.xml
```

## 工作原理

`<remote fetch=".">` 使用**相对地址**：repo 会以 `repo init -u` 传入的 URL 为基准
解析所有项目地址。因此同一份 manifest 可以同时服务于组织 Owner、fork 开发者和 CI：

```bash
# 1) Owner / 核心开发者（SSH）
repo init -u git@github.com:CangjieNext/cangjie_manifest.git -b main
repo sync -c

# 2) Fork 开发者（把 <you> 换成你的用户名；请先 fork 所有需要的仓库）
repo init -u git@github.com:<you>/cangjie_manifest.git -b main
repo sync -c
# HTTPS 同样可用：
# repo init -u https://github.com/<you>/cangjie_manifest.git -b main

# 3) CI / 只读（HTTPS，公共仓库无需凭据）
repo init -u https://github.com/CangjieNext/cangjie_manifest.git -b main
repo sync -c
```

## 仓库分组

| 分组        | 仓库                                                         | 默认拉取 |
|-------------|--------------------------------------------------------------|----------|
| `default`   | cangjie_compiler, cangjie_runtime, cangjie_tools, cangjie_test, cangjie_test_framework, cangjie_docs, cangjie_stdx, cangjie_build, cangjie_multiplatform_interop, cangjie_python_interop, cangjie_js_interop | 是 |
| `llvm`      | llvm-project（固定到编译器所需的上游 commit）                  | 否 |
| `vscode`    | vscode_cangjie                                                | 否 |
| `plugins`   | cangjie_debug_adapter, cangjie_deveco_plugins                 | 否 |

可选分组带有 `notdefault` 标记，普通的 `repo sync` 只拉取核心仓库。

## 构建编译器

`cangjie_compiler` 要求 LLVM 位于 `cangjie_compiler/third_party/llvm-project`
（见其 `third_party/README.md`）。manifest 会把固定版本的 LLVM 检出到该路径，
因此构建编译器时请在 init 时同时选择两组：

```bash
repo init -u git@github.com:CangjieNext/cangjie_manifest.git -b main -g default,llvm
repo sync -c
```

已经 init 过？无需重新下载即可追加分组：

```bash
repo init -g default,llvm     # 持久生效
repo sync -c
# 或一次性拉取：
repo sync -g llvm
```

随后按照 [`cangjie_build/docs`](https://github.com/CangjieNext/cangjie_build)
中的构建指南操作（`docs/linux.md`、`docs/macos.md`、`docs/windows.md` 等）。

## 常用技巧

- `repo forall -c '<command>'`：在每个已检出的仓库中执行命令。
- `repo start <branch> --all`：跨所有仓库创建同名主题分支。
- `repo status`、`repo diff`、`repo upload`：跨仓库的 git 同名操作。
- 安装 repo：macOS 用 `brew install repo`，Debian/Ubuntu 用 `apt-get install repo`，
  或参考[官方 README](https://gerrit.googlesource.com/git-repo/) 的一行脚本安装。
