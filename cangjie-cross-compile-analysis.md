# 仓颉语言"Go 式跨架构单文件二进制"支持现状、可行性与工作量分析

> 调研方式：使用 `repo` + 官方 `cangjie_manifest` 实际拉取源码（compiler / runtime / tools / docs 四仓，浅克隆），所有结论均来自仓内代码与文档的直接证据，引用处可点击查看源文件。
> 调研时间：2026-11，代码分支：`main`。

---

## 一、结论摘要（先看这里）

1. **仓颉已经具备交叉编译的"骨架"，但不是 Go 模式，而是传统 Clang/GCC 模式。** cjc 已有 `--target/--sysroot/--toolchain` 三元组体系、LLVM 多目标后端、按目标隔离的库目录布局；但实际交叉编译要求用户**自行准备外部交叉工具链（NDK / llvm-mingw / Xcode / OHOS clang+musl sysroot）和目标专属 SDK 包**，与 Go "一个 SDK、两个环境变量、零外部依赖"的体验有代差。
2. **"单文件二进制"目前只达成一半。** 产物本身是单文件，但 Linux 默认是 PIE 动态可执行文件，依赖系统 glibc、动态加载器和 `libcangjie-runtime.so`；`--static` 只静态链接仓颉自家归档，**代码注释明确写着 `ld -static` 全静态目前不支持**。Windows/mingw 路线因 SDK 捆绑了 mingw CRT 和 lld，最接近自包含。
3. **架构覆盖面窄于 LLVM 本身。** 编译器自身的 ArchType 枚举只有 x86_64 / aarch64 / arm32，**无 RISC-V、LoongArch**；运行时含手写汇编桩和大量架构相关 C++，新架构移植是实打实的硬核工作。
4. **目标可行，但无法靠小修小补实现。** 参照 Rust 的演进路径（rustup target + musl + 自带 lld），在现有 3 架构上达到"实用级 Go 式体验"估计需要 **12–24 人月**；若包含新架构（如 riscv64）和生态改造，整体在 **2–3 人年**量级。最大技术障碍不是编译器，而是 **glibc 依赖、C++ 运行时、stdlib 的 C FFI/OpenSSL 依赖，以及多目标 SDK 的分发与 CI 体系**。

---

## 二、仓库获取与调研范围

官方清单仓 `https://gitcode.com/Cangjie/cangjie_manifest` 管理 6 个子仓（见 [cangjie.xml](file:///workspace/cangjie/.repo/manifests/cangjie/cangjie.xml)）：

| 子仓 | 内容 | 本次是否拉取 | 代码规模（实测） |
|---|---|---|---|
| cangjie_compiler | C++ 前端 + 定制 LLVM 的驱动/工具链层 | 是 | 约 27.6 万行 C++/头文件 |
| cangjie_runtime | 运行时（GC/线程/栈展开）+ 标准库 | 是 | runtime 约 10.7 万行 C++/汇编；stdlib 约 14.3 万行仓颉 |
| cangjie_tools | cjpm、cjfmt、LSP 等 | 是（重点分析 cjpm，约 2.7 万行） | — |
| cangjie_docs | 开发指南、编译选项、发布说明 | 是 | — |
| cangjie_test / cangjie_test_framework | 测试用例与框架 | 否（磁盘限制，不影响结论） | — |

另外注意两点：**定制 LLVM（含 opt/llc/lld/cjdb）本身是独立仓 `llvm-project`，不在本清单内**，编译器仓只保留 [llvmPatch.diff](file:///workspace/cangjie/cangjie_compiler/third_party/llvmPatch.diff)，SDK 中以预编译 `third_party/llvm` 形式交付；SDK 集成构建指导所在的 `cangjie_build` 仓同样不在清单内，但其脚本内嵌于 [integration_build/scripts](file:///workspace/cangjie/cangjie_compiler/integration_build/scripts)。

---

## 三、仓颉工具链的架构现状

### 3.1 编译流水线

编译器 README 对架构的自述（[README_zh.md 第 7、49 行](file:///workspace/cangjie/cangjie_compiler/README_zh.md#L7-L49)）：

```
仓颉源码 → 前端(词法/语法/语义/宏/CHIR) → LLVM IR → opt → llc → ld(lld) → 可执行文件
```

- 前端为自研 C++（27 万行级），中间表示 CHIR，再降到 LLVM IR；
- 后端完全建立在华为 fork 的 LLVM 上，**LLVM 本身天然具备多目标交叉代码生成能力**，这是仓颉做交叉编译最重要的先天资产；
- 驱动层 `src/Driver` 模仿 Clang Driver 设计：`ToolChain` 基类 + Gnu/MachO 两大流派 + Linux/OHOS/Android/MinGW/Darwin/iOS 六个特化（[Toolchains/CJNATIVE 目录](file:///workspace/cangjie/cangjie_compiler/src/Driver/Toolchains/CJNATIVE)）。

### 3.2 目标平台的抽象边界

目标三元组在编译器内被拆成 arch/vendor/os/env 四个枚举，定义在 [Option.h 第 104–132 行](file:///workspace/cangjie/cangjie_compiler/include/cangjie/Option/Option.h#L104-L132)：

```cpp
enum class ArchType : uint8_t { X86_64, AARCH64, ARM64, ARM32, UNKNOWN };
enum class OSType   : uint8_t { WINDOWS, LINUX, DARWIN, IOS, UNKNOWN };
enum class Environment: uint8_t { OHOS, GNU, ANDROID, SIMULATOR, NOT_AVAILABLE };
```

**关键事实：编译器认识的架构只有 3 种（ARM64 是 AARCH64 别名）。** RISC-V、LoongArch、MIPS 在全仓代码中零命中。OHOS/Android 并不是独立 OS，而是 Linux 的 env 变体——这意味着它们复用 Linux 运行时移植层，降低了扩平台成本。

构建脚本 [build.py 的 TARGET_DICTIONARY](file:///workspace/cangjie/cangjie_compiler/build.py#L57-L75) 列出了 SDK 构建期能处理的全部目标：native、ohos 三架构、windows-x86_64、iOS 真机/模拟器、Android API 23/26/31 三架构。

### 3.3 用户侧已有的交叉编译开关

[cjc 选项表 Options.inc](file:///workspace/cangjie/cangjie_compiler/include/cangjie/Option/Options.inc#L534-L548) 已提供完整的 Clang 式交叉参数：

- `--target <triple>`（第 538 行）、`--sysroot`（第 545 行）、`--toolchain/-B`（第 534 行）、`--target-cpu`；
- 交叉判定逻辑极其简单：[Option.h 第 953 行](file:///workspace/cangjie/cangjie_compiler/include/cangjie/Option/Option.h#L953-L956) `IsCrossCompiling() { return host != target; }`；
- 交叉时才给 llc 传 `--mtriple`（[ToolOptions.cpp 第 48–52 行](file:///workspace/cangjie/cangjie_compiler/src/Driver/ToolOptions.cpp#L48-L52)）；
- cjpm 也已透传 `--target`，并做字符串合法性校验（[common.cj 第 140–178 行](file:///workspace/cangjie/cangjie_tools/cjpm/src/command/common.cj#L140-L178)），cjpm.toml 支持按 target 隔离的依赖、编译选项和 `bin-dependencies`（预编译二进制依赖）。

**结论：交叉编译的"管道"已经铺好，缺的是管道里输送的"物料"（目标库、sysroot、CRT）和"自动阀门"（免配置体验）。**

---

## 四、交叉编译现状：能做什么、要准备什么

### 4.1 官方支持矩阵（文档实证）

[编译选项文档 compile_options.md 第 689–704 行](file:///workspace/cangjie/cangjie_docs/docs/dev-guide/source_zh_cn/Appendix/compile_options.md#L689-L704) 给出的已支持交叉组合：

| Host | Target | 需要的 SDK 包 |
|---|---|---|
| linux x64 / arm64 | windows x64（mingw） | linux 版 SDK + llvm-mingw |
| linux / mac / windows | android aarch64/arm/x86_64 | **android 专属 SDK 包** + NDK |
| macOS（两架构） | iOS 真机/模拟器 | **ios 专属 SDK 包** + Xcode |
| （集成构建脚本） | ohos aarch64/x86_64/arm | OHOS 预编译 clang + musl sysroot |

两个值得注意的空白：

1. **没有 linux-gnu → linux-gnu 的跨架构条目**（即 x86_64 服务器上直接编 arm64 Linux 服务器程序这个最经典的 Go 场景，不在官方支持矩阵内）。虽然 cmake 里有 [linux_aarch64_toolchain.cmake](file:///workspace/cangjie/cangjie_compiler/cmake/linux_aarch64_toolchain.cmake)，说明自研 SDK 时能做，但用户要自己搞定全套 sysroot 和预编译运行时。
2. cjpm 开发者指南更保守，明确写"**当前仅支持 linux 平台上通过 `--target windows-x86_64` 交叉编译**"（[developer_guide_zh.md 第 136 行](file:///workspace/cangjie/cangjie_tools/cjpm/doc/developer_guide_zh.md#L136)）。

### 4.2 一次交叉编译实际依赖什么（以 OHOS 为例）

集成构建脚本 [build_ohos_aarch64.sh](file:///workspace/cangjie/cangjie_compiler/integration_build/scripts/ohcangjie/build_ohos_aarch64.sh#L14-L39) 展示了完整依赖三件套：

```bash
--target ohos-aarch64
--target-toolchain ${OHOS_ROOT}/prebuilts/clang/ohos/.../llvm/bin   # 外部 clang/lld
--target-sysroot   ${OHOS_ROOT}/.../musl/sysroot                    # 外部 musl C 库与 CRT
--target-lib       .../cangjie_runtime/runtime/output               # 目标架构的仓颉运行时预编译品
```

驱动层的工具发现逻辑（[Gnu.cpp 第 127–149 行](file:///workspace/cangjie/cangjie_compiler/src/Driver/Toolchains/Gnu.cpp#L127-L149)）印证了这一点：

- 交叉时按 `<triple>-ar`、`<triple>-ld` 的 GCC 惯例去 PATH / `-B` 路径找**用户安装的外部工具**；
- 只有开启 LTO 或 HWASan 时才改用 SDK 自带的 lld；**普通 Linux 编译默认调用系统 ld**，找不到就报错让用户加 `-B`。

### 4.3 目标库的目录布局：多目标 SDK 的雏形已存在

运行时库按 `<os>_<env>_<arch>_cjnative` 隔离存放（[Option.cpp 第 1295–1309 行](file:///workspace/cangjie/cangjie_compiler/src/Option/Option.cpp#L1295-L1309)），例如 `linux_aarch64_cjnative/`、`linux_ohos_aarch64_cjnative/`、`windows_x86_64_cjnative/`。打包脚本 [package_native.sh](file:///workspace/cangjie/cangjie_compiler/integration_build/scripts/cjnative/package_native.sh#L31-L51) 显示**一个 SDK 包目前只装一个目标目录**，android/ios 目标要下载独立 SDK 包。这是"每目标一个 SDK"的传统分发模型，与 Go 单 SDK 内嵌全部 `pkg/GOOS_GOARCH` 的模型形成鲜明对比，但目录设计本身并不排斥未来打成"fat SDK"。

### 4.4 原生编译都离不开系统 C 工具链

即便不交叉，官方也要求宿主机安装 binutils、glibc-devel、libstdc++-devel、gcc、OpenSSL 3（[linux_toolchain_install.md](file:///workspace/cangjie/cangjie_docs/docs/dev-guide/source_zh_cn/Appendix/linux_toolchain_install.md#L16-L66)）。运行时 README 说明 **OpenSSL 是动态链接系统库、不带源码**（[cangjie_runtime/README_zh.md](file:///workspace/cangjie/cangjie_runtime/README_zh.md) 开头依赖说明），PCRE2/flatbuffers/libboundscheck 才是源码内嵌。这决定了仓颉工具链在基因上是"寄生"于系统 C/C++ 生态的。

---

## 五、单文件二进制与静态链接现状

### 5.1 Linux 默认链接方式：动态 PIE

[Linux_CJNATIVE.cpp](file:///workspace/cangjie/cangjie_compiler/src/Driver/Toolchains/CJNATIVE/Linux_CJNATIVE.cpp) 的链接作业构造显示：

- 可执行文件固定加 `-pie`、`-dynamic-linker`（第 56–57、92–97 行），并从系统 C 库目录取 `Scrt1.o / crti.o / crtn.o`；
- 默认链接 `libcangjie-runtime.so`（第 133 行），再链 `-lboundscheck -lm -lc`（[BackendOptions.inc 第 23–27 行](file:///workspace/cangjie/cangjie_compiler/src/Driver/Toolchains/BackendOptions.inc#L23-L27)）。

所以普通仓颉程序虽然产物是一个文件，但运行时依赖：动态加载器、glibc、libstdc++/libgcc_s、仓颉运行时动态库（或 rpath 指向 SDK 目录），**拷到另一台机器不一定能跑**。

### 5.2 `--static` 不是 Go 意义上的全静态

`--static` 的实际行为（[Linux_CJNATIVE.cpp 第 117–135 行](file:///workspace/cangjie/cangjie_compiler/src/Driver/Toolchains/CJNATIVE/Linux_CJNATIVE.cpp#L117-L135)）只是把仓颉自家三个库换成归档：`libcangjie-runtime.a`、`libcangjie-thread.a`、`libboundscheck-static.a`，随后仍然追加 `-lstdc++ -lpthread -ldl -lm -lc`（[BackendOptions.inc 第 29–35 行](file:///workspace/cangjie/cangjie_compiler/src/Driver/Toolchains/BackendOptions.inc#L29-L35)），**全程没有 `-static/-Bstatic`，PIE 和解释器照设**。同文件第 39 行注释直说：

> `Static crt files are for 'ld -static' but it is not supported currently.`

平台限制也写在 [DriverOptions.cpp 第 312–338 行](file:///workspace/cangjie/cangjie_compiler/src/Driver/DriverOptions.cpp#L312-L338)：OHOS 上 `--static` 会被静默关闭并告警；文档的静态矩阵里 OpenHarmony 不支持 static-std。

### 5.3 唯一接近"自包含"的是 Windows/mingw 路线

[MinGW_CJNATIVE.cpp 第 183–212 行](file:///workspace/cangjie/cangjie_compiler/src/Driver/Toolchains/CJNATIVE/MinGW_CJNATIVE.cpp#L183-L212) 显示：Windows 路线统一使用 **SDK 自带的 lld/llvm-ar 和 `third_party/mingw` 下的 CRT 静态库**，静态模式连 libc++、unwind 一起归档。这套"捆绑 CRT + 自带链接器"的组合，本质上就是 Go/Rust-musl 模式的原型，证明在仓颉现有架构内实现自包含是可行的，只是 Linux 路线没有照搬。

### 5.4 标准库的 C 成分

stdlib 共 33 个模块、495 个仓颉源文件，另有 **38 个 C FFI 源文件**（如 core 的字符串/SIMD、net、fs、posix、process），它们在 SDK 构建期用目标 C 编译器编进各模块的 FFI 静态库（链接选项里成对出现的 `libcangjie-std-*.a` 与 `libcangjie-std-*FFI.a`，见 [BackendOptions.inc 第 66–85 行](file:///workspace/cangjie/cangjie_compiler/src/Driver/Toolchains/BackendOptions.inc#L66-L85)）。cjc 自身不编译 C 源码，cjpm 的 `ffi.c` 配置只接收**预编译好的 C 库路径**——这意味着含 C 依赖的第三方包做交叉编译时，必须有人先产出目标架构二进制，cjpm 因此设计了 `bin-dependencies` 机制来兜底。

---

## 六、与 Go 机制的逐项对比

| 维度 | Go | 仓颉现状 | 差距判断 |
|---|---|---|---|
| 后端 | 自研 SSA，内置多目标 codegen | fork LLVM，多目标能力现成 | 持平，LLVM 甚至更强 |
| 汇编器/链接器 | 自带（internal link/asm），无外部依赖 | lld 已随 SDK 捆绑，但 Linux 默认仍调系统 ld；ar 依赖外部 | 小改可补齐 |
| 运行时语言 | 纯 Go（含 GC、调度器） | C++17 + 80 个汇编文件，依赖 libstdc++/compiler-rt | 结构性差距 |
| 对 libc 的依赖 | 默认 cgo 关闭，零 libc，syscall 自封装 | glibc CRT（Scrt1.o 等）+ 动态加载器硬编码；net/posix 经 libc FFI | **最大障碍** |
| 标准库形态 | 纯 Go，按 GOOS/GOARCH 预编译于单一 SDK 内 | 仓颉 + 38 个 C 文件 + 动态 OpenSSL/PCRE2 | 需 musl/静态化改造 |
| 静态链接 | 默认全静态单文件 | `--static` 仅静态仓颉库，glibc 仍动态；全静态明确不支持 | 需专门开发 |
| 交叉命令 | `GOOS= GOARCH= go build`，零配置 | `cjc --target ... --sysroot ... -B...`，需自备工具链和目标 SDK | 体验差距大 |
| SDK 分发 | 一个包含全部目标 | 每目标独立 SDK 包（linux/android/ios 分开下载） | 打包/CI 工程 |
| 架构数量 | 10+ 架构（含 riscv64/loong64/wasm） | x86_64/aarch64/arm32 | 新架构移植成本高 |
| 第三方包生态 | 源码包即可交叉（纯 Go 前提下） | 含 C 的包需按目标发布二进制（bin-dependencies） | 生态流程待建 |

一句话概括：**Go 的自包含来自"运行时和标准库完全用自己语言写、对操作系统只做裸 syscall"；仓颉的运行时是托管型 C++ 运行时，深度嵌入 C/C++ 生态，这是两条路线所有差异的根源。**

---

## 七、要达到目标，具体缺什么（差距清单）

把"一个架构的 SDK 直接构建其他架构的单文件可执行二进制"拆成 6 项工程缺口：

1. **多目标合一的 fat SDK 打包体系**
   现状目录布局已支持隔离（`lib/<target>_cjnative/`），但发布流程每目标出包。需要改造 [package_native.sh](file:///workspace/cangjie/cangjie_compiler/integration_build/scripts/cjnative/package_native.sh) 同类脚本、增加多目标运行时/stdlib 的聚合编译与体积治理、建设矩阵 CI。

2. **内置 sysroot 与 CRT，去掉外部工具链硬依赖**
   Linux 路线需要引入可自由再分发的 **musl sysroot**（OHOS 路线已有 musl 实践和 [ohos 工具链 cmake](file:///workspace/cangjie/cangjie_compiler/cmake/ohos_aarch64_clang_toolchain.cmake) 可复用），并把 Linux 默认链接器从系统 ld 切换到捆绑 lld（MinGW/OHOS 已验证可行，改动集中在 [Gnu.cpp PrepareDependencyPath](file:///workspace/cangjie/cangjie_compiler/src/Driver/Toolchains/Gnu.cpp#L127-L149)）。

3. **真正的全静态链接（`ld -static` 等价物）**
   需要新增静态 CRT 选择路径（crt1.o/crtbeginT.o 体系）、静态 libstdc++ 替代（clang_rt + libc++ 静态归档，mingw 路线已有先例）、去掉写死的 `-dynamic-linker`/PIE 假设，并解决静态 glibc 的 NSS/DNS/dlopen 顽疾——务实路线是 musl 静态，而非 glibc 静态。

4. **OpenSSL 与 stdlib C FFI 的目标预制**
   OpenSSL 现为系统动态依赖；要么随 SDK 分发各目标静态 OpenSSL（ License 友好，Apache-2.0 兼容），要么长期用纯仓颉替代。38 个 C FFI 文件需要纳入多目标预制流水线。

5. **运行时的新架构移植（若要超出 x86/arm 三架构）**
   每个新架构要写约 11 个汇编桩（[runtime/src/arch 现有 8 组](file:///workspace/cangjie/cangjie_runtime/runtime/src/arch)，涵盖 C2N/I2N/N2C 跳转、栈增长、安全点、异常上下文恢复），并改动约 25 个含架构 ifdef 的 C++ 文件（ObjectModel、StackMap、Mutator、UnwindStack、Sync、Signal 等 GC 核心），再加编译器枚举、Triple 解析、TargetCPU 表和 LLVM target 注册验证。**这是新人月黑洞，属于资深运行时工程师领域。**

6. **cjpm 与包生态的多目标制品流程**
   cjpm 的 target 隔离、bin-dependencies、构建脚本 target 透传机制已具备雏形，需要补齐：自动从 fat SDK 定位目标库（免去 `--sysroot/-B`）、中心仓多目标制品发布规范、纯源码包的零配置交叉验证。

---

## 八、可行性评估

**总体判断：技术可行，无原理性阻断，但属于"生态级工程"而非"特性开发"。**

有利条件（占六成胜算）：

- LLVM 后端、lld、llvm-ar、compiler-rt 都是现成的交叉工具，且已在 SDK 内；
- Driver 的三元组/sysroot/工具链抽象、目标库隔离目录、cjpm 的 target 构建图都已就位；
- OHOS（musl 交叉）和 MinGW（捆绑 CRT + lld 自包含）两条路线已经分别验证了方案的两个半边；
- 运行时平台层划分清晰：OS 层仅 12 个文件、每架构汇编桩约 11 个，已有 8 组实现可参照，移植范围可控；
- 有 Rust 的成熟路线图可抄作业：`rustup target add` + musl + 自带 lld + 每目标 std 归档。

主要风险：

- **glibc 静态化是行业公认坑**（getaddrinfo、nsswitch、dlopen），Go 靠纯 Go net 解析器绕开，仓颉 net/posix 走 libc FFI，短期只能选 musl 路线，与 gnu 目标形成双 ABI；
- 全并发整理 GC 的栈映射、安全点、异常展开对新架构的正确性要求极高，测试调试周期长；
- 动态加载、反射、热重载等特性依赖动态链接设施，全静态化需要逐项回归；
- 路线图资源明显向 OpenHarmony 倾斜（README 的平台计划均围绕 OHOS），通用 Linux 自包含目标的优先级存在不确定性。

---

## 九、工作量估算

假设团队为熟悉 LLVM/运行时的资深工程师，基于上述代码模块的实际规模估算：

| 里程碑 | 内容 | 估算工作量 | 交付效果 |
|---|---|---|---|
| M1：多目标 SDK 与 lld 内化 | fat SDK 打包、CI 矩阵、Linux 默认切捆绑 lld、官方支持 linux gnu 跨架构（仍需用户提供 sysroot） | **2–3 人月** | 交叉编译"可用但要配置"，对齐当前 Rust target 的早期形态 |
| M2：musl 自包含 + 全静态 | 内置 musl sysroot、静态 CRT 路径、OpenSSL/FFI 静态预制、`--static` 升级为真全静态、测试矩阵 | **4–8 人月** | x64/arm64 Linux 产出零外部依赖单文件，**达成 Go 式核心体验** |
| M3：零配置体验与生态 | cjpm 自动目标库发现、中心仓多目标制品规范、文档与开发者体验、体积/兼容性治理 | **6–12 人月** | `--target` 一行命令完成交叉，生态包平滑跟随 |
| M4：新架构（每项，如 riscv64） | 运行时汇编桩+25 处 C++ 移植、编译器枚举/Triple、全量测试与 QEMU CI | **6–12 人月/架构** | 架构覆盖面追平 LLVM 能力 |
| **合计** | 现有 3 架构达到实用 Go 式体验（M1–M3） | **约 12–24 人月** | — |
| | 含 1 个新架构与生态成熟期（M1–M4） | **约 2–3 人年** | 全面对标 |

说明：M2 是技术风险最集中的阶段（GC/异常在静态 musl 下的行为、静态 OpenSSL、PIE 模型改造）；若接受"动态链接自带 musl"而非全静态，可压缩 2–3 人月，但产物严格说不算 Go 式单文件。

---

## 十、建议的演进路径

1. **短期（低成本高收益）**：在 M1 内先把 linux-aarch64/gnu 交叉组合官方化（cmake 工具链文件已存在），并让非 LTO 模式也默认使用 SDK 自带 lld，消除对系统 binutils 的硬依赖；
2. **中期**：复刻 OHOS/mingw 经验做通用 linux-musl 目标，SDK 内置 musl sysroot，推出真 `--static`，这是对标 Go 的决定性一步；
3. **长期**：fat SDK + cjpm 多目标制品中心仓一体化，再按社区呼声排期 riscv64 等新架构；
4. 对**使用者当下的务实建议**：追求单文件可执行文件时，Linux 上用 `cjc --static` 并配合固定 glibc 版本的容器构建，或直接评估 OpenHarmony/musl 目标与 Windows/mingw 目标；跨架构发布目前应按"每目标一套 SDK + 一套外部工具链"的传统模式规划 CI，不要预期 Go 式零配置。

---

## 附：关键证据索引

| 主题 | 文件位置 |
|---|---|
| 清单与子仓定义 | [cangjie.xml](file:///workspace/cangjie/.repo/manifests/cangjie/cangjie.xml) |
| 编译器架构与交叉编译自述 | [cangjie_compiler/README_zh.md](file:///workspace/cangjie/cangjie_compiler/README_zh.md#L37-L49) |
| SDK 构建目标字典 | [build.py#L57-L75](file:///workspace/cangjie/cangjie_compiler/build.py#L57-L75) |
| 架构/OS/环境枚举 | [Option.h#L104-L132](file:///workspace/cangjie/cangjie_compiler/include/cangjie/Option/Option.h#L104-L132) |
| cjc 交叉/静态选项 | [Options.inc#L310-L548](file:///workspace/cangjie/cangjie_compiler/include/cangjie/Option/Options.inc#L534-L548) |
| 交叉判定与 mtriple | [Option.h#L953](file:///workspace/cangjie/cangjie_compiler/include/cangjie/Option/Option.h#L953-L956)、[ToolOptions.cpp#L48-L52](file:///workspace/cangjie/cangjie_compiler/src/Driver/ToolOptions.cpp#L48-L52) |
| 外部工具/系统 ld 发现 | [Gnu.cpp#L127-L149](file:///workspace/cangjie/cangjie_compiler/src/Driver/Toolchains/Gnu.cpp#L127-L149) |
| Linux 动态 PIE 与伪静态 | [Linux_CJNATIVE.cpp#L39-L135](file:///workspace/cangjie/cangjie_compiler/src/Driver/Toolchains/CJNATIVE/Linux_CJNATIVE.cpp#L39-L135) |
| 静态链接选项内容 | [BackendOptions.inc#L29-L35](file:///workspace/cangjie/cangjie_compiler/src/Driver/Toolchains/BackendOptions.inc#L29-L35) |
| 静态能力平台限制 | [DriverOptions.cpp#L312-L338](file:///workspace/cangjie/cangjie_compiler/src/Driver/DriverOptions.cpp#L312-L338) |
| OHOS musl 交叉链接 | [Ohos_CJNATIVE.cpp](file:///workspace/cangjie/cangjie_compiler/src/Driver/Toolchains/CJNATIVE/Ohos_CJNATIVE.cpp#L40-L111) |
| Windows 自包含链接 | [MinGW_CJNATIVE.cpp#L183-L212](file:///workspace/cangjie/cangjie_compiler/src/Driver/Toolchains/CJNATIVE/MinGW_CJNATIVE.cpp#L183-L212) |
| 运行时架构移植层 | [runtime/src/arch](file:///workspace/cangjie/cangjie_runtime/runtime/src/arch)、[runtime/src/os](file:///workspace/cangjie/cangjie_runtime/runtime/src/os) |
| 标准库 C FFI | [stdlib/libs/std](file:///workspace/cangjie/cangjie_runtime/stdlib/libs/std) |
| 官方交叉支持矩阵 | [compile_options.md#L689-L704](file:///workspace/cangjie/cangjie_docs/docs/dev-guide/source_zh_cn/Appendix/compile_options.md#L689-L704) |
| 主机 C 工具链依赖 | [linux_toolchain_install.md](file:///workspace/cangjie/cangjie_docs/docs/dev-guide/source_zh_cn/Appendix/linux_toolchain_install.md#L16-L66) |
| cjpm 交叉目标校验 | [common.cj#L140-L178](file:///workspace/cangjie/cangjie_tools/cjpm/src/command/common.cj#L140-L178) |
| OHOS 交叉构建三件套 | [build_ohos_aarch64.sh](file:///workspace/cangjie/cangjie_compiler/integration_build/scripts/ohcangjie/build_ohos_aarch64.sh#L14-L39) |
| SDK 单目标打包 | [package_native.sh](file:///workspace/cangjie/cangjie_compiler/integration_build/scripts/cjnative/package_native.sh#L31-L51) |
