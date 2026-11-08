# 仓颉（Cangjie）编译器自举可行性分析与实施计划

## 摘要

仓颉编程语言已于 2025 年 7 月正式开源编译器、运行时与标准库[cite:4]，官方编译器 `cjc` 以 C++ 编写、基于 LLVM 后端实现[cite:1][cite:2]。分析表明：**仓颉编译器自举在技术上是可行的**，且仓颉生态已具备自举所需的全部关键先决条件——包括开放的编译器源码、可直接复用的官方后端与运行时、完备的 C 语言 FFI、以库形式暴露的官方词法/语法解析器（`std.ast`），以及多个已经实现自举的先例工程（cjpm、cjbind）[cite:8][cite:13]。

自举的合理路径不是一次性重写整个工具链，而是**增量式自举**：先用仓颉实现一个"前端 + 中端"（解析、语义分析、LLVM IR 发射），复用官方已开源的 LLVM 后端与仓颉运行时完成代码生成；当该编译器能够编译自身并通过官方测试套件时，即达成自举闭环。业界先例（Rust、Go）以及 LLVM 官方文档均支持这一路径[cite:12]。

---

## 一、问题定义

"编译器自举"（self-hosting / bootstrapping）在本文中指：**存在一个以仓颉语言编写的仓颉编译器，它能够编译用仓颉语言编写的自身源码，产出功能正确的可执行编译器**。它包含两个递进层面：

1. **前端自举**：用仓颉实现词法分析、语法分析、语义分析、IR 生成，后端与链接复用官方 LLVM 工具链（`opt`/`llc`/`ld`）与仓颉运行时。
2. **完全自举**：自研编译器可替代 `cjc` 编译真实的仓颉工程（标准库、cjpm 管理的项目），并与官方编译器保持行为一致性。

完全重写 LLVM 后端不属于必要目标——业界主流自举编译器（Rust 的 rustc、Swift、Julia）均保留 LLVM 并通过 FFI 调用[cite:12]。

---

## 二、现状盘点：自举的基础设施已全部就绪

### 2.1 官方编译器已开源，架构完全透明

2025 年 7 月 31 日，仓颉正式开源，范围覆盖编译器、运行时、标准库、工具链、测试用例与测试框架[cite:4][cite:5]。其中 `cangjie_compiler` 仓库包含：

- **前端（C++）**：`src/Lex`（词法）、`src/Parse`（语法）、`src/Sema`（语义/类型检查/泛型实例化）、`src/Macro`（宏展开）、`src/Mangle`（名称修饰）、`src/Modules`（包管理，FlatBuffers 序列化的 `.cjo` 格式）、`src/ConditionalCompilation`（条件编译）、`src/CHIR`（高层中间表示及优化、解释器）、`src/CodeGen`（CHIR → LLVM IR）[cite:1][cite:2][cite:3]。
- **LLVM 后端**：官方维护的 llvm-project fork，包含 `opt`、`llc`、`ld` 与调试器，并新增了仓颉专属优化 Pass[cite:2][cite:7]。

这意味着语义规则、ABI、名称修饰、`.cjo` 格式 schema 全部可参考源码实现，自举不存在"黑盒逆向"问题。

### 2.2 仓颉侧能力对自举的支撑

| 能力 | 证据 | 对自举的意义 |
|------|------|--------------|
| **C 互操作（FFI）** | `foreign func`、`@C struct`、`CPointer<T>`、`CFunc` 回调、`unsafe` 边界；类型映射规则明确[cite:11] | 可绑定 LLVM-C API、libclang，或调用任意 C 编译基础设施 |
| **`std.ast` 语法解析库** | 提供 `cangjieLex(String)`（字符串→Tokens）、`parseProgram`、`parseDecl`、`parseExpr`、`parseType`、`parsePattern` 及 Fragment 系列函数，AST 节点类体系完整开放[cite:9][cite:10] | **自举编译器可直接复用官方级词法与语法分析**，无需从零写 parser；先例：cjbind 即基于此模式构建 |
| **宏（元编程）** | 宏以仓颉编写、编译为动态库、在编译期执行，输入输出均为 Tokens；支持 `quote` 插值与上下文通信[cite:9][cite:10] | 证明"仓颉程序在编译期运行并操纵语法树"这一机制已被官方工具链原生支持 |
| **泛型/模式匹配/并发/异常** | 语言核心特性（LTS 1.0.0 起）[cite:7] | 提供编写大型系统程序（编译器）所需的表达力 |
| **运行时开源** | 全并发 GC、M:N 线程调度等运行时源码开放，标准库 26 个模块以 `.cj` 源码形式提供[cite:5][cite:14] | 自研编译器产出的目标码可直接链接官方运行时，无需重写 GC |

### 2.3 生态中已有自举先例

- **cjpm（包管理器）**：以仓颉语言实现，仓库自带 `cjpm.toml`，可直接用 SDK 中的 cjpm 编译自身——文档明确称之为"自举"[cite:8]。
- **cjcov、cjtrace-recover、hle** 等工具同样以仓颉实现并自我构建[cite:8]。
- **cjbind**（社区 FFI 绑定生成器）：以仓颉编写，通过 FFI 调用 libclang 解析 C 头文件；其对 libclang 的绑定 `libclang.cj` 就是cjbind 自己生成的，实现"生成器自举"[cite:13]。
- **标准库本身**以 `.cj` 源码交付，由 `cjc` 编译[cite:14]——即**库层已经处于"用仓颉写、被仓颉编译"的自举状态**，缺的只是编译器本体。

### 2.4 版本与测试基线

当前版本通道：LTS 1.0.5、STS 1.2.0（2026-09 发布）、Nightly[cite:16]。`cangjie_test` 仓库提供语言测试用例，`cangjie_test_framework` 提供自动化执行框架[cite:5]，这为自研编译器提供了现成的**一致性验收基准**。1.1.0 起提供的 `--output-type=obj/chir`、`--dump-xxx` 等选项[cite:6]则为差异调试（比对自研编译器与 cjc 的中间产物）提供了官方工具。

---

## 三、可行性分析

### 3.1 LLVM 官方给出的三条自举路径

LLVM FAQ 针对"用语言自身编写自举编译器"给出三种对接方式[cite:12]：

| 路径 | 优势 | 劣势 |
|------|------|------|
| 通过 FFI 调用 LLVM 库（LLVM-C） | 最佳地跟踪 IR/格式演进；无发射/解析开销 | 需要编写绑定胶水代码 |
| 直接发射 LLVM 汇编文本（.ll） | 起步极其简单 | 文本解析慢；跟踪 IR 演进较难 |
| 直接发射 LLVM bitcode（.bc） | 高效 | 需在自举语言中重建 IR 对象模型与位流读写器 |

仓颉的 C FFI 成熟度已被 cjbind 验证（成功绑定 libclang 并投入生产使用[cite:13]），因此三条路径对仓颉全部可用。**建议以路径 2（发射 .ll）起步、路径 1（LLVM-C 绑定）为中期目标**。

### 3.2 最大的技术红利：后端可整体复用

仓颉与运行时/GC 的深度耦合代码并不需要自举者重写。官方在 LLVM fork 中实现了全部仓颉专属 Pass[cite:7]：

- `CJRewriteStatepoint`（GC 安全点重写）、`CJBarrierOpt`/`CJBarrierSplit`（写屏障优化）、`CJFillMetadata`（TypeInfo/反射元数据填充）、`CJRuntimeLowering`（intrinsics 下降）、`CJDevirtualOpt`（去虚化）、`CJPartialEscapeAnalysis`（逃逸分析）等。

这些 Pass 位于 LLVM 侧（`opt` 工具内），前端只需产出符合规范的 LLVM IR 并调用官方 `opt` → `llc` → `ld` 即可获得与 cjc 等价的代码生成、GC 支持与反射能力。官方编译器自身的 Driver 也是以"前端产出 .bc，再调起后端命令"的方式组织的（`cjc-frontend` 即前端到 LLVM IR 为止的形态[cite:1][cite:15]），自研编译器可以对齐这一切分。

### 3.3 主要难点与风险

| 难点 | 说明 | 风险等级 |
|------|------|---------|
| **语义分析与类型推断** | 子类型关系、泛型约束检查与实例化、重载决议、闭包/流表达式推断、初始化分析、可见性规则——这是官方 Sema 中体量最大的部分，且必须与 cjc 行为严格对齐 | **高** |
| **名称修饰与 ABI** | 符号 mangle 规则、vtable/TypeInfo 布局需与运行时约定一致，否则无法链接官方标准库 | 高 |
| **宏系统协议** | 宏编译为 dylib 后由编译器加载执行，涉及进程间/动态库调用协议与宏上下文通信（MacroWithContext）[cite:10] | 中 |
| **`.cjo` 包格式与增量编译** | FlatBuffers schema 已开源[cite:1]，但跨版本格式有变化（1.1.0 起格式不一致，需 clean 重编[cite:6]） | 中 |
| **官方编译器持续演进** | STS 半年一个版本，组织名语法、common/specific 等新特性持续加入[cite:6]，自研编译器需持续跟进 | 中（长期） |
| **测试一致性** | 需要建立与 cjc 的差异测试（诊断信息、产物行为、性能），`cangjie_test` 提供基础但覆盖不到全部语义角落 | 中 |

### 3.4 结论

**仓颉编译器自举可行**，置信度依据：

1. 所有必需基础设施（编译器源码、后端、运行时、测试）已开源[cite:4][cite:5]；
2. 仓颉具备 FFI 与 `std.ast`，"用仓颉写编译器前端"的两个最大冷启动障碍（对接 LLVM、解析自身语法）均有现成解[cite:9][cite:11][cite:12]；
3. 生态内已有 cjpm、cjbind 等自举先例，证明仓颉具备构建编译器级别工具的工程成熟度[cite:8][cite:13]；
4. 业界先例充分：rustc（Rust 写、LLVM-C/FFI 调用）、Go 1.5（纯自举）、Swift 的 SwiftSyntax（Swift 写）均走通同类路径[cite:12]。

需明确的前提：自举目标是"前端与中端用仓颉重写并闭环编译自身"，LLVM 后端与运行时作为被复用的外部组件保留——这与 rustc 的自举形态一致，也是工作量与风险可控的关键。

---

## 四、达成计划

总体策略：**增量式自举，逐层替换、每层验收**。全程以"与官方 cjc 行为一致"为验收锚点，以 `cangjie_test` 与差异测试为工具。

### Phase 0：基建与侦察

**目标**：吃透官方实现，搭好验收体系。

- 从源码构建官方编译器（Linux/macOS 本机构建流程已文档化[cite:15]），通读 `src/Sema`、`src/CHIR`、`src/CodeGen`、`src/Mangle`；
- 基于 `cangjie_test` 与 `cangjie_test_framework` 建立回归基线[cite:5]；
- 搭建**差异测试框架**：同一组 `.cj` 输入分别喂给 cjc 与自研编译器，比对产物运行结果与关键中间产物（利用 `--dump-xxx` 选项[cite:6]）；
- 编写 LLVM-C / libLLVM 的仓颉 FFI 绑定骨架（可借助 cjbind 的思路甚至直接用它生成初版绑定[cite:13]）。

**验收**：能在 CI 中复现官方编译器全量测试；FFI 绑定可从仓颉创建 LLVM Module 并发射一个空函数的 .ll 文件。

### Phase 1：语法与前端基础库

**目标**：仓颉写就的完整"源码 → AST"能力。

- 优先方案：封装 `std.ast`（`cangjieLex` + `parseProgram`）获得官方级解析器[cite:9][cite:10]；
- 在其上构建自研 AST 模型、符号表、诊断系统（错误信息格式与 cjc 对齐）；
- 备选：为摆脱对官方运行库的依赖、锻炼队伍，可自研手写 lexer/parser，以 `cangjie_test` 用例做交叉验证。

**验收**：能解析标准库与 cjpm 的真实源码并输出等价 AST/Token 流；诊断位置与信息与 cjc 一致率达标。

### Phase 2：可执行语义参考（树遍历解释器）

**目标**：先让语义"跑起来"，再谈编译。

- 实现树遍历解释器：支持核心子集——函数/struct/class/enum/接口（子集）、泛型单态化、模式匹配、Option/Range、基础 std 调用；
- 与官方 CHIR 解释器（`src/CHIR/Interpreter`[cite:3]）的行为做差异比对。

**验收**：解释执行通过 `cangjie_test` 中相应子集用例。此解释器此后长期保留，作为语义决策的"可执行规格"与模糊测试的 oracle。

### Phase 3：语义分析与类型检查

**目标**：对齐 cjc 的 Sema。

- 按依赖顺序实现：名称解析 → 作用域/可见性 → 类型检查与推断 → 泛型实例化 → 初始化与控制流分析 → 重载决议；
- 每个子模块以"解释器 + cjc 差异测试"双重验收；
- 暂不支持宏：遇到宏调用即调用官方 cjc 预展开后回填（过渡策略）。

**验收**：对标准库子集完成无宏编译的完整语义检查，诊断与 cjc 一致。

### Phase 4：IR 发射与后端对接（核心里程碑）

**目标**：产出可链接运行的真实二进制。

- 起步：发射 LLVM IR 文本（.ll），实现名称修饰、TypeInfo/vtable 布局、GC intrinsics 标注；
- 调用官方工具链 `opt`（含 CJ 系列 Pass）→ `llc` → `ld`，链接仓颉运行时与标准库[cite:7][cite:14]；
- 过渡：切换到 LLVM-C FFI 直接构建 IR（省去文本解析，并获得 Pass 管理能力[cite:12]）；
- 平台顺序：先 Linux x86-64 native，再扩展 aarch64，交叉编译（ohos 等）最后。

**验收**：自研编译器编译出的"Hello World → 逐渐扩大的标准库子集程序"在 Linux 上正确运行，行为与 cjc 产物一致。

### Phase 5：宏系统与高级特性补全

**目标**：覆盖现代仓颉代码所需的全量特性。

- 实现 proc-macro 协议：加载宏 dylib、传递 Tokens、`quote`/MacroWithContext 上下文通信[cite:10]；
- 补齐条件编译、组织名语法、common/specific、反射元数据发射[cite:6]；
- `.cjo` 读写（FlatBuffers schema 已开源[cite:1]），支持增量编译。

**验收**：能编译使用了宏（如 `deriving`、`unittest`）的真实社区项目（cjpm、cjbind 皆可作为试金石[cite:8][cite:13]）。

### Phase 6：自举闭环与常态化

**目标**：达成教科书意义的自举，并可持续。

- **三阶段自举验证**：cjc 编译 CJC'（自研编译器）→ CJC' 编译 CJC'' → CJC'' 编译 CJC'''；校验 CJC'' 与 CJC''' 可执行文件行为一致（bit-identical 产物为理想目标）；
- 用自研编译器编译标准库并跑通全量 `cangjie_test`；
- 建立跟版机制：跟踪官方 STS 节奏（每半年[cite:6]），语义规则变更以差异测试捕获；
- 长期归宿：贡献回合入官方 `cangjie_compiler`（前端以仓颉重写），或作为社区参考实现（类似 mrustc 与 rustc 的关系）独立演进。

**验收**：自研编译器独立存在于干净环境（仅有官方 LLVM 工具链与运行时）中完成自我编译与标准库编译。

### 里程碑与验收总表

| Phase | 关键交付物 | 验收标准 |
|-------|-----------|---------|
| 0 | 差异测试框架、LLVM-C 绑定骨架 | CI 复现官方全量测试 |
| 1 | 仓颉版 Parser/AST/诊断 | 解析真实工程，诊断与 cjc 对齐 |
| 2 | 树遍历解释器 | 解释执行通过子集用例 |
| 3 | 语义/类型检查 | 无宏代码全量语义检查一致 |
| 4 | .ll 发射 + 后端对接 | 真实程序编译产物运行正确 |
| 5 | 宏系统 + .cjo + 高级特性 | 编译含宏真实项目 |
| 6 | 三阶段自举闭环 | 编译自身 + 标准库，测试全绿 |

### 风险应对要点

- **语义对齐长尾**：坚持"解释器即规格"策略，任何拿不准的语义点以 cjc 实测行为为准并固化为回归用例；
- **语言演进追新**：限定自举子集先闭环（如对齐 LTS 1.0.5 语言集），再追 STS 新特性，避免追逐移动目标；
- **人机协同**：`cangjie_test` 用例库 + 差异测试可批量驱动 LLM 辅助编码与模糊测试，扩大覆盖半径；
- **官方路线重叠**：关注官方社区动态，避免与官方团队的编译器演进计划（Workshop/技术分享渠道[cite:5]）重复投入，及时合流。

---

## Sources

- [1] [仓颉编译器开源仓库深度指南：系统架构、目录结构与源码构建实战 - GitCode 博客](https://blog.gitcode.com/fbd8f6ce4fba0a77541d55a144011132.html)
- [2] [cangjie_compiler：基于 LLVM 的仓颉编程语言编译器项目 - GitCode](https://gitcode.com/Cangjie/cangjie_compiler/tree/55ee950e75ee9e69fc01303ecc182e7afeb4f4c0)
- [3] [openharmony/third_party_cangjie_compiler - DeepWiki](https://deepwiki.com/openharmony/third_party_cangjie_compiler/1-overview)
- [4] [仓颉编程语言已正式开源 - 腾讯云开发者社区](https://cloud.tencent.com/developer/article/2550134)
- [5] [CangjieCommunity 仓颉社区入门指南：开源仓库图谱 - GitCode 博客](https://blog.gitcode.com/5927babad1a01bc8b53fd7a5ecea60fc.html)
- [6] [Cangjie 1.1.0 Release Notes - 仓颉官网](https://cangjie-lang.cn/docs?url=%2F1.1.0%2Frelease-notes%2Fcangjie-release-notes.html)
- [7] [Cangjie 1.0.0 Release Notes（LLVM 优化 Pass 清单）- 仓颉官网](https://cangjie-lang.cn/docs?url=%2F1.0.0%2Frelease-notes.html)
- [8] [仓颉语言命令行工具链 cangjie_tools 解析（含 cjpm 自举说明）- GitCode 博客](https://blog.gitcode.com/c66c54abfabb6a2e7977bb03d8f3b033.html)
- [9] [语法节点 - 宏 - 仓颉编程语言开发指南 - 华为开发者](https://developer.huawei.com/consumer/cn/doc/cangjie-guides-V5/syntax_node-V5)
- [10] [std.ast 包 - 仓颉编程语言库 API - 华为开发者](https://developer.huawei.com/consumer/cn/doc/cangjie-guides-V5/ast_package_overview-V5)
- [11] [仓颉-C 互操作（FFI）实战指南 - GitCode 博客](https://blog.gitcode.com/46aa515d76c06b0321fa7019c63d7ea3.html)
- [12] [LLVM FAQ: How to write a self-hosting LLVM compiler - LLVM.org](https://llvm.org/docs/FAQ.html)
- [13] [cjbind 使用指南：仓颉 FFI 绑定生成器（自举先例）- GitCode 博客](https://blog.gitcode.com/2038c6f9522d0284efa241d751425a01.html)
- [14] [仓颉运行时与仓颉标准库源码解析 - GitCode 博客](https://blog.gitcode.com/1ea818b37e1a1475eaded52381d52a75.html)
- [15] [仓颉编译器独立构建指导 - GitCode 博客](https://blog.gitcode.com/b026b02937b6eff45422fff4258631cc.html)
- [16] [仓颉（Cangjie）工具链在 openEuler 上的安装与使用指南（版本通道 LTS 1.0.5 / STS 1.2.0）- 华为云社区](https://bbs.huaweicloud.com/blogs/510497)
