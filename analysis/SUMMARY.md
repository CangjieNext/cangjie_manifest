# 本地多仓分析汇总（2026-11-08）

## 仓库与版本
- cangjie_runtime @ e927f24 (GitHub CangjieNext 镜像 = GitCode Cangjie 官方) — std 源码位于 stdlib/libs/std
- cangjie_stdx @ 49d2f1e — 扩展库 stdx
- go @ master 浅克隆 (golang/go, src/)
- rust @ master 浅克隆 (rust-lang/rust, library/)
- swift @ main 浅克隆 (apple/swift, stdlib/public) + swift-corelibs-foundation/xctest/libdispatch 浅克隆
- kotlin @ master 浅克隆 (JetBrains/kotlin, libraries/)

## 规模统计（统一口径：用户可见顶层公开声明 + 类型内公开成员；平台变体全计）
| 范围 | 包/模块 | 文件 | LOC | 顶层公开 | 公开成员 |
|---|---|---|---|---|---|
| 仓颉 std | 40 包(33顶级目录) | 495 | 143,715 | 1,224 (class374/struct117/enum43/interface112/type8/func466/const103/var1) | 5,107 |
| 仓颉 stdx | 38 包 | 273 | 98,759 | 453 | 2,809 |
| 仓颉 std+stdx | 78 | 768 | 242,474 | 1,677 | 7,916 |
| Go std(全) | 316 包 | 2,395 | 799,809 | 74,065 (const 63,228, 其中 syscall 包 62,498) | 19,282 |
| Go std 剔除 syscall | 315 | 2,141 | 639,395 | 6,556 | 18,961 |
| Rust library(分发crate) | 23 crate | 1,443 | 957,695 | 28,495 (stdarch intrinsic 21,986) | 9,348 |
| Rust 剔除 stdarch | — | 1,230 | 433,669 | 6,509 | 8,719 |
| Rust 明细: std 655文件/155,924LOC/top4,989(fn879)/mem5,086; core 294/178,210/1,181/2,490; alloc 97/70,007/155/815; proc_macro 17/5,086/51/96; test 31/7,458/49/56; portable-simd 80/10,777/58/118; stdarch 213/524,026/21,986(fn18,140)/629 |
| Swift stdlib/public | 14 模块 | 474 | 206,403 | 1,379 (struct227/protocol164/func569/typealias166...) | 5,073 |
| Swift corelibs Foundation | 4 | 175 | 71,330 | 466 | 2,710 |
| Swift corelibs XCTest | 1 | 34 | 5,030 | 50 | 63 |
| Swift 合计 | 18 | 683 | 282,763 | 1,895 | 7,846 (+libdispatch C 49,892 LOC) |
| Kotlin stdlib 全源集 | — | 962 | 140,283 | 8,501 (fun 6,833) | 20,635 |
| Kotlin stdlib 仅公共源集 src/kotlin | — | 168 | 19,244 | 939 | 1,990 |
| Kotlin 明细: common(生成) 34文件 top3,773; js 204/top1,591; jvm 168/top1,149; wasm 186/top551; native-wasm 109/top85; kotlin.test 9文件 top23 |

## Swift stdlib/public 模块: core(258文件/143,296LOC/top790) Concurrency(79/20,675/111) RuntimeModule Cxx Differentiation Distributed Observation Platform Synchronization(21/4,110/20) EmbeddedPlatform SwiftOnoneSupport Volatile Windows libexec StringProcessing RegexBuilder RegexParser（注：StringProcessing/RegexBuilder/RegexParser 未在 14 模块中显示? —— 实际 pkg_count=14，列表如上）

## Go 顶层包(53): archive arena bufio builtin bytes cmp compress container context crypto database debug embed encoding errors expvar flag fmt go hash html image index io iter log maps math mime net os path plugin reflect regexp runtime simd slices sort strconv strings structs sync syscall testdata testing text time unicode unique unsafe uuid weak
（新包: arena/simd/uuid/weak/structs/unique/iter/maps/slices/cmp —— 2023-2026 新增）

## 仓颉 std 包清单(40): std core collection collection.concurrent concurrent console(deprecated) convert crypto crypto.cipher crypto.digest database database.sql env fs interop io math math.numeric net objectpool overflow posix process random ref reflect regex runtime sort sync time unicode unittest(+common/diff/mock/prop_test) argopt ast binary deriving(+api/builtins/impl/resolve)
## 仓颉 stdx 包清单(38): stdx actors(+macros) aspect_cj(+plugins) chir compress(tar/zlib) crypto(common/crypto/digest/keys/kit/x509) dynamicLoader effect encoding(base64/hex/json+stream/url) fuzz log logger net(http/tls) plugin serialization string_intern syntax unittest(data)

## 关键能力本地证据
- 仓颉 stdx.net.http: HTTP/1.1+2.0 client+server(http_server1_1/stream_server2_0/http_client1_1/http_client2_0), WebSocket, HPACK, cookie_jar, 连接池/协程池
- 仓颉 stdx.crypto: digest(md5,sha1/224/256/384/512,sm3,hmac) keys(rsa,ecdsa,sm2) sm4 secure_random x509(cert/csr/der/oid/signature) kit
- 仓颉 std.net: TCP(tcp/tcp_server) UDP Unix(unix/unix_datagram) Raw socket(socket_raw) DNS IPv4/IPv6 keepalive options
- 仓颉 std.unittest: assert/bench/fuzz/parameterized(mock,prop_test 属性测试,diff,xml reporter,tempdir)
- 仓颉 std.database.sql: driver/driver_manager/datasource/pool/transaction/query_result (接口层,同 Go database/sql 模式)
- 仓颉 stdx.compress: zlib/tar(v7,ustar,gnu,pax,posix 格式)/tar_gzip；无 zip
- 仓颉 std.core: Thread/ThreadLocal/Future/ThreadSnapshot; std.concurrent: ThreadGroup; std.sync: Atomic(I8-64,U*,Bool,Reference,OptionReference)/Barrier/Mutex/ReentrantMutex/ReadWriteLock/ReentrantReadWriteMutex/Monitor/MultiConditionMonitor/Condition/UniqueLock/Lock
- 仓颉 math.numeric: BigInt + Decimal
- 仓颉 std.time: DateTime/MonoTime/TimeZone/DateTimeFormat(Duration 在 core)
- 仓颉 stdx.encoding: base64/hex/url/json(+stream)
- 仓颉特色: std.ast(语法解析) stdx.syntax/chir stdx.deriving? (deriving 在 std) aspect_cj(AOP) effect(非局部控制) actors objectpool overflow argopt string_intern
- 仓颉 stdx third_party 目录为空(仅 CMakeLists)——native 依赖(如 openssl)经 pkg.cangjie-lang.cn registry 二进制分发,源码仓不含
- Rust std 模块: alloc ascii backtrace collections env error ffi fs hash io macros net num os panic path prelude process random(新) sync thread time view —— 无 calendar/uuid(社区)/http/crypto/json/regex/log
- Kotlin stdlib 包: collections coroutines(核心原语) time uuid ranges enums text io random concurrent(atomic) reflect properties annotation contracts comparisons util contextParameters
- Swift FoundationNetworking: URLSession 系 32 文件(仅客户端); FoundationXML; corelibs-libdispatch 为 C(49,892 LOC)

## 平台支持(仓颉 README): Linux(x86_64/aarch64) Windows(x86_64) macOS(x86_64/aarch64) OpenHarmony(aarch64/arm32/x86_64) HarmonyOS(aarch64) iOS(aarch64/x86_64) Android(aarch64/x86_64/arm32) —— 标准库不可在 Windows 原生构建(需 Linux 交叉编译)

## 方法论注意
1. 平台变体重复计数: Go syscall 最严重(全 GOOS 表叠加), 已单列剔除口径; Rust stdarch 为生成 intrinsic; Kotlin 多源集 actual 重复
2. 仓颉声明默认 internal, 显式 public 才计入(与 Go 大写导出/Rust pub/Swift public/Kotlin 默认 public 等价口径)
3. 成员统计为正则近似(indent public), 用于相对比较
4. Kotlin 应用完备度依赖 JDK; Rust 依赖 crates.io; Swift 依赖 Apple 平台闭源框架 —— 官方库对比仅计一手源码
