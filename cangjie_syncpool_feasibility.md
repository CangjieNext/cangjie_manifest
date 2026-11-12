# 仓颉引入类 Go `sync.Pool` 机制：可行性与工作量评估

> 分析对象：CangjieNext 官方多仓代码库（经 `repo` 工具实际同步到本地 `/workspace/cj`）
> 涉及仓库：`cangjie_runtime`（C++ 运行时 + 仓颉标准库）、`cangjie_compiler`（LLVM 后端编译器）、`cangjie_stdx`（扩展库）

---

## 一、结论速览

| 维度 | 结论 |
|---|---|
| **总体可行性** | **可行**。但"完全复刻 Go `sync.Pool` 语义"不可行，需按仓颉的 GC/线程模型做语义裁剪 |
| **推荐落点** | **标准库层（`std.sync` / `std.objectpool` 复活）**，不改运行时与编译器 |
| **最小可行版本（MVP）工作量** | **纯仓颉代码，1 人 × 3~5 天**（含测试与 benchmark） |
| **完整对齐 Go 语义（含 per-P 无锁 + GC 联动）** | **1 人 × 3~5 周**，需动运行时 C++（新增 ~3 个导出符号） |
| **最大风险** | 仓颉**没有 GC 回调钩子**（Go 的 `poolCleanup` 无对应物），导致"GC 后清理池"只能退化为轮询/弱引用近似——但 `WeakRef(DEFERRED)` 的官方"内存不足回收"语义可兜底防 OOM，风险等级由高降为中 |

---

## 二、代码库实测结论（关键事实）

### 2.1 仓颉已经有 Go 式调度器 —— 这是最重要的有利条件

仓颉**不是**裸 OS 线程模型，而是与 Go 高度同构的 **CJThread（协程）+ Processor（P）** 架构：

- 调度器实现：[processor.cpp](file:///workspace/cj/cangjie_runtime/runtime/src/CJThread/src/runtime/schedule/src/processor.cpp)、[schedule_impl.h](file:///workspace/cj/cangjie_runtime/runtime/src/CJThread/src/runtime/schedule/include/inner/schedule_impl.h)
- `ProcessorGet()`（schedule_impl.h:269）可取到**当前 CJThread 绑定的 Processor**，即 Go 的 `getg().m.p` 的等价物
- 每个 Processor 持有 `pArray[PROCESSOR_PARRAY_NUM]`（processor.h），其中 `KEY_TIMER = 0` 已占用，**尚有空闲 slot 可用于承载 per-P 池**
- 工作窃取调度：`ProcessorSteal` / `ProcessorCJThreadSteal`（processor.cpp:219, 385），与 Go 的 `runqsteal` 一致

**含义**：Go `sync.Pool` 的核心设计——"每 P 一个本地池 + 全局共享兜底 + P 间窃取"——在仓颉里有**天然对应的承载点**，不需要新造线程抽象。

### 2.2 分配路径：已经是 bump-pointer + per-thread 缓冲

```
编译器 new → CJ_MCC_NewObject(TypeInfo*, size)
   → ObjectManager::NewObject
   → RegionSpace::Allocate(size, allocType)      [RegionSpace.cpp:65]
      → TryAllocateOnce                           [RegionSpace.cpp:20]
         → AllocBuffer::GetOrCreateAllocBuffer()  ← 每线程一份（ThreadLocal）
            → AllocBuffer::Allocate → tlRegion->Alloc()  ← bump 指针
```

- 编译器侧确认：`Allocate` CHIR 节点在 [AllocateImpl.cpp](file:///workspace/cj/cangjie_compiler/src/CodeGen/Base/AllocateImpl.cpp) 中被 lowering 成 `llvm::Intrinsic::cj_malloc_object`，**class 实例 100% 走堆分配，无逃逸分析、无栈分配**（`chir-ea` 选项在 `Option.cpp` 中被解析但**无任何 pass 消费**，是悬空开关）
- 对象头：`Allocator::HEADER_SIZE = 0`，`BaseObject` 仅含 1 个 8 字节 `StateWord`
- 关键点：**per-thread `AllocBuffer` 已经是"线程本地缓存"的现成范式**，池所需的 TLS 访问机制完全齐备

### 2.3 GC：默认是**复制式（对象会移动）**，且**没有 GC 回调钩子**

| 项目 | 仓颉现状 | 对池设计的影响 |
|---|---|---|
| 默认 GC | `WCollector`（继承 `CopyCollector`），`Heap::GetGCMode()` 可切 `GENERATIONAL`（`MixedCollector`） | **复制式 GC ⇒ 对象地址在 GC 后会变** |
| 写屏障 | 非分代用 SATB（`EnumBarrier.cpp`）；分代用 remembered-set（`RSetUpdateBarrier.cpp`） | 池中对象被 GC 搬移后，**池必须通过引用（而非裸指针）访问对象** |
| GC 回调 | 运行时内部有 `PreGarbageCollection` / `PostGarbageCollection` 虚函数（`TracingCollector.h`），但**未导出为 Cangjie 可调用符号**；标准库侧无任何注册接口 | **Go 的 `poolCleanup`（每次 GC 后清空 victim cache）无直接对应物** |
| GC 计数 | `g_gcCount++`（`CopyCollector.cpp:67`），经 `MCC_GetGCCount` 暴露；标准库 `std.runtime.getGCCount()` 可读（仅 `cjnative` 后端） | 可用作**轮询式**清理触发器 |
| 弱引用 | `std.ref.WeakRef<T>` + `CleanupPolicy.EAGER / DEFERRED`（[官方文档](file:///workspace/cj/cangjie_runtime/stdlib/libs/std/ref/weak_ref.cj)：DEFERRED 为"内存不足时才回收"的软引用语义，官方定位即"缓存、对象池"；EAGER 为"尽快回收"，适合监听器自动注销，**不适合池**） | **DEFERRED 提供空间维度的池收缩通道（防 OOM），无需 GC 回调也无需轮询** |

**这是本次评估的核心约束**：Go `sync.Pool` 依赖 `poolCleanup` 在每轮 GC 后把 `local` 池降级为 `victim` 池并在下一轮丢弃，从而保证池不无限增长、对象能最终被回收。仓颉运行时**内部有 GC 阶段钩子但未对外暴露**，标准库无法注册回调。

**缓解因素**：`std.ref.WeakRef(DEFERRED)` 官方语义（"内存不足时自动回收，避免 OOM"）为池提供了**空间驱动**的兜底收缩通道——GC 压力大时池中弱引用对象可被自动回收，最坏情况从"池膨胀占内存"降为"池暂不收缩但 GC 可自动放对象"。因此池设计变为**两条清理路线可选**：

| victim 层实现 | 清理时机 | 命中率 | 本质 |
|---|---|---|---|
| 强引用 victim + `getGCCount()` 轮询降级 | 确定性：每轮 GC 后惰性降级 | 高（Go 同级） | **时间驱动**清理（Go 语义） |
| `WeakRef(DEFERRED)` 做 victim | 不确定：内存压力驱动 | 波动大（GC 心情决定） | **空间驱动**清理（Java SoftReference 语义） |

注意：**local 层必须强引用**（"刚 Put 就 Get"的复用是池收益主体）；DEFERRED 解决"内存上限"但不解决"对象失效节奏"——对象带状态且 Reset 昂贵、或 benchmark 需要可复现行为时，仍需轮询降级。DEFERRED 的触发粒度（阈值、是否仅老年代 GC 触发）文档未写明，落地时需实测校准。

### 2.4 已有先例：仓颉其实**已经有一个被废弃的对象池**

`stdlib/libs/std/objectpool/objectpool.cj`（`std.objectpool.ObjectPool<T>`）：

- 标记了 **`@Deprecated`**，且 **`@When[backend == "cjnative"]`**（解释器后端不可用）
- 实现方式：`CJ_Gettid() % 50` 分 50 个分片，每片一个 `ConcurrentLinkedQueue`，**每次 get/put 都要抢锁**
- 有 `resetFunc` 回调（比 Go 更强）

即：**API 形态已有，但性能形态不合格**（分片锁竞争、非 per-P 无锁），且因 `@Deprecated` + 后端限定而事实上不可用。

### 2.5 `stdx` 里有两个更现代的池实现（可作为设计参考）

- **`ConcurrentRingPool<T>`**：[pool.cj](file:///workspace/cj/cangjie_stdx/src/stdx/net/http/pool.cj) —— 基于 `AtomicBool.compareAndSwap` 的无锁环形缓冲，`get` 走 CAS + `AtomicUInt64` 票据，`put` 用 CAS 抢位；支持 `newFn` / `resetFn` / `close()`。HTTP/2 的 `ArrayPool` 就是按 9/32/128/512/2048/4096/8192/16384 **分档**复用的。
- **`InternStringPool`**：基于 `CacheProxy` + LRU 驱逐。

两者都是 **"固定容量 + 有界 + 显式 close"** 风格，**不是** Go 那种"GC 驱动、无界、尽力而为"的语义。这恰好说明仓颉生态目前只落地了"有界池"这一种形态。

### 2.6 标准库并发原语齐备

`stdlib/libs/std/sync/`：`Mutex`、`ReentrantMutex`、`ReadWriteLock`、`Semaphore`、`Barrier`、`SyncCounter`、`Monitor`（含 Condition）、`AtomicInt64/AtomicUInt64/AtomicBool` 等；`stdlib/libs/std/collection/concurrent/non_blocking_queue.cj` 提供 `ConcurrentLinkedQueue`。

**`std.core.ThreadLocal<T>` 可用但不适合做池容器**：它把值 `Box<T>` 存入 `ThreadLocalMap` 的开放寻址哈希表（[thread_local.cj](file:///workspace/cj/cangjie_runtime/stdlib/libs/std/core/thread_local.cj)），每次 `get/set` 都有哈希探测 + 装箱开销，**不适合放在池的热路径上**。

---

## 三、与 Go `sync.Pool` 的机制差异对照

| Go `sync.Pool` 机制 | 仓颉可对应物 | 差距 |
|---|---|---|
| `poolLocal`（per-P 本地池） | `Processor.pArray` 空闲 slot / `ProcessorGet()` | 需在运行时导出 `CJ_MCC_GetCurrentProcessorId` 一类符号 |
| `procPin/procUnpin`（防止 G 在 P 间迁移） | CJThread 绑定的 Processor 会随调度迁移（`ProcessorSteal`） | **需新增 pin 机制，或改用 per-CJThread 语义** |
| 全局 `poolChain` 兜底 + 窃取 | `ConcurrentLinkedQueue` / `ConcurrentRingPool` | ✅ 无差距 |
| `poolCleanup`（GC 后降级 local→victim） | `PreGarbageCollection`/`PostGarbageCollection` 虚函数（内部） | **需导出为 C 符号**，否则退化 |
| `victim` 池二级缓存 | `WeakRef` + `CleanupPolicy.DEFERRED` | 可近似 |
| `Put` 时的类型擦除 `any` | 仓颉有泛型 `Pool<T>` | ✅ 仓颉**更强**（类型安全） |
| `New()` 工厂 + 用户 `Reset` | 仓颉 `objectpool` 已有 `resetFunc` | ✅ 仓颉**更强** |
| GC 移动对象 | 复制式 GC 会移动对象 | **池必须存引用而非裸地址**（Go 是非移动 GC） |

---

## 四、推荐方案与分级设计

### 方案 A：纯标准库实现（推荐，MVP）

在 `std.sync` 新增 `sync.Pool<T>`，完全用仓颉代码写，不动运行时：

```
Pool<T>
 ├─ per-CJThread 本地槽：ConcurrentRingPool<T>（每线程一个，CAS 无锁）
 ├─ 全局兜底：ConcurrentLinkedQueue<T>
 ├─ victim 缓存：WeakRef<T>(DEFERRED) 列表
 └─ 清理触发（二选一或组合）：
      a. 轮询 std.runtime.getGCCount()，计数变化时执行 local→victim 降级（时间驱动，确定性）
      b. victim 层用 WeakRef(DEFERRED)（空间驱动，内存压力下 GC 自动回收，防 OOM 兜底）
```

- **优势**：零运行时/编译器改动；只影响 `cjnative` 后端的性能路径，解释器后端可优雅降级
- **代价**：语义是 Go 的**近似**——GC 后清理是"惰性"的（下次访问时才降级），而非 Go 的"每轮 GC 立即清空"
- **注意**：per-CJThread 而非 per-P。CJThread 会迁移 Processor，但池是**按对象归属**而非按 CPU 亲和，跨 Processor 使用同一个 `ConcurrentRingPool` 仍安全（CAS 保护），只是失去了 Go per-P 的缓存亲和收益

### 方案 B：运行时增强（完整对齐 Go）

在运行时新增并导出：
1. `CJ_MCC_GetCurrentProcessorId()` —— 暴露 `ProcessorGet()->id`（processor.cpp:1123 已有 `ProcessorId()`）
2. `CJ_MCC_RegisterGCHook(cb)` —— 把 `TracingCollector::PreGarbageCollection`/`PostGarbageCollection` 导出，实现 Go 的 `poolCleanup` 精确语义
3. （可选）`CJ_MCC_ProcPin/ProcUnpin` —— 若坚持 per-P 无锁本地池

配套在 `std.sync` 实现 per-P 本地池 + 全局兜底 + victim 三级结构。

### 方案 C：复活 `std.objectpool`（兼容性路径）

把 `std.objectpool.ObjectPool<T>` 从 `@Deprecated` 中解放，**重写其内部实现**为方案 A 的形态，并去掉 `@When[backend == "cjnative"]` 限制（分后端提供降级实现）。对外 API 保持不变，减少用户迁移成本。

---

## 五、工作量评估

### 5.1 方案 A（MVP，纯标准库）

| 工作项 | 内容 | 人日 |
|---|---|---|
| `Pool<T>` 核心 API | `Get() : ?T`、`Put(T)`、`New` 工厂、`Reset` 回调 | 1.5 |
| 无锁本地容器 | 复用/裁剪 `ConcurrentRingPool`，泛型化为 `Pool<T>` | 1.0 |
| GC 降级逻辑 | `getGCCount()` 轮询 + local→victim 降级 + `WeakRef(DEFERRED)` 软引用兜底（若 MVP 选纯 DEFERRED 路线可省去轮询，进一步压缩至 ~4 人日） | 1.0 |
| 后端兼容 | 解释器后端降级为纯锁实现（`@When` 分支） | 0.5 |
| 单元测试 + 并发压测 | 正确性、GC 交互、竞态检测 | 1.0 |
| Benchmark | 分配速率 / 延迟对比（vs 无池） | 0.5 |
| **合计** | | **5.5 人日 ≈ 1 人 1~1.5 周** |

### 5.2 方案 B（完整对齐 Go）

在方案 A 基础上增加：

| 工作项 | 人日 |
|---|---|
| 运行时导出 `GetCurrentProcessorId` | 0.5 |
| 运行时 GC 钩子导出（`PreGarbageCollection` → C 回调） | 1.5 |
| per-P 本地池 + P 间窃取 | 2.0 |
| `procPin` 语义（防止 CJThread 迁移期间访问错池） | 2.0 |
| 运行时单测 + 编译器回归验证 | 1.5 |
| **增量合计** | **7.5 人日** |

**方案 B 总计 ≈ 13 人日 ≈ 1 人 3 周**（含方案 A）

### 5.3 方案 C（兼容性改造）

在方案 A 基础上增加：去掉 `@Deprecated`、多后端适配、API 文档与迁移说明 ≈ **+2 人日**。

---

## 六、风险与建议

### 风险清单

1. **【中·已下调】GC 回调缺失** —— 不做运行时改动就无法实现 Go 的精确 `poolCleanup` 语义。缓解：`WeakRef(DEFERRED)` 官方"内存不足回收"语义提供空间维度兜底（防 OOM）。建议 MVP 用 `WeakRef(DEFERRED)` 做 victim 层（免轮询、全后端可用），需要确定性失效节奏时再叠加 `getGCCount()` 轮询；DEFERRED 的实际触发粒度（阈值、是否仅老年代 GC）需落地时实测校准。运行时钩子导出作为方案 B 的后续增强。
2. **【中】复制式 GC 与对象移动** —— 池内对象在 GC 后地址改变，**池必须持有强引用（`Object`）而非裸指针**。若未来做"裸内存池"，必须额外处理移动问题。
3. **【中】解释器后端无 GC 计数** —— `std.runtime.getGCCount()` 是 `@When[backend == "cjnative"]`，解释器后端需另找降级路径（可用 `WeakRef` 单独兜底）。
4. **【中】`std.core.ThreadLocal` 不适合做池容器** —— 哈希探测 + `Box` 装箱开销会吃掉池的收益，必须用 `ConcurrentRingPool` 这类专用结构。
5. **【低】生态认知** —— `std.objectpool` 已被标记废弃，直接复活可能引起兼容性问题；建议**新增 `std.sync.Pool` 为主，复活 `objectpool` 为薄封装**。

### 建议推进顺序

1. **先做方案 A 的 MVP**（1~1.5 周），用 benchmark 验证实际收益 —— **仓颉目前 class 实例 100% 堆分配、无逃逸分析，池化收益理论上明确**（省掉 bump 指针分配 + GC 扫描/复制成本），值得先验证
2. 用 benchmark 数据决定是否投入方案 B 的运行时改造
3. 优先落地**有明确收益的场景**：`Array` / `ArrayList` / `StringBuilder` / `Map` 内部节点 等高频可复用对象（参考 `stdx` 的 `ArrayPool` 分档设计）

---

## 附录：本次分析的关键代码位置

| 主题 | 位置 |
|---|---|
| Processor 调度器 | `runtime/src/CJThread/src/runtime/schedule/src/processor.cpp` |
| per-P 存储 slot | `runtime/src/CJThread/src/runtime/schedule/include/inner/processor.h` (`pArray`, `KEY_TIMER`) |
| CJThread TLS 挂载 | `runtime/src/CJThread/src/runtime/schedule/include/inner/threadlocal.h` |
| 分配入口 | `runtime/src/Heap/Allocator/RegionSpace.cpp:20,65` |
| per-thread 分配缓冲 | `runtime/src/Heap/Allocator/AllocBuffer.h` |
| 对象模型 | `runtime/src/Common/BaseObject.h`, `runtime/src/Common/StateWord.h` |
| 复制式 GC | `runtime/src/Heap/Collector/CopyCollector.cpp:67` |
| 分代 GC | `runtime/src/Heap/GenerationalGC/MixedCollector.h` |
| GC 阶段钩子（内部） | `runtime/src/Heap/Collector/TracingCollector.h` (`PreGarbageCollection`/`PostGarbageCollection`) |
| 弱引用 | `stdlib/libs/std/ref/weak_ref.cj` |
| **已废弃的对象池** | `stdlib/libs/std/objectpool/objectpool.cj` |
| **无锁环池先例** | `cangjie_stdx/src/stdx/net/http/pool.cj` (`ConcurrentRingPool`) |
| 编译器分配 lowering | `cangjie_compiler/src/CodeGen/Base/AllocateImpl.cpp` |
| GC 计数标准库接口 | `stdlib/libs/std/runtime/runtime_gc.cj` |
