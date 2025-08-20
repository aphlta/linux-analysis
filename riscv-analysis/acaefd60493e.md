# SiFive Bullet 0x07版本PMU事件支持 - Patch分析报告

## Commit信息

**Commit ID:** acaefd60493e265f1aefbc1b79d92367df6f676a  
**作者:** Eric Lin <eric.lin@sifive.com>  
**日期:** Wed Feb 12 17:21:37 2025 -0800  
**标题:** perf vendor events riscv: Add SiFive Bullet version 0x07 events

**Co-developed-by:** Samuel Holland <samuel.holland@sifive.com>  
**Reviewed-by:** Ian Rogers <irogers@google.com>  
**Tested-by:** Ian Rogers <irogers@google.com>, Atish Patra <atishp@rivosinc.com>  
**Signed-off-by:** Namhyung Kim <namhyung@kernel.org>

## 修改概述

本patch为SiFive Bullet微架构的0x07版本添加了新的PMU（Performance Monitoring Unit）事件支持。这些新事件主要用于支持调试、跟踪和计数器采样过滤功能（Sscofpmf扩展）。

### 修改统计
- **修改文件数:** 7个文件
- **新增行数:** 120行
- **删除行数:** 0行

### 修改的文件列表
1. `tools/perf/pmu-events/arch/riscv/mapfile.csv` - 添加版本匹配规则
2. `tools/perf/pmu-events/arch/riscv/sifive/bullet-07/cycle-and-instruction-count.json` - 周期和指令计数事件
3. `tools/perf/pmu-events/arch/riscv/sifive/bullet-07/firmware.json` - 固件事件
4. `tools/perf/pmu-events/arch/riscv/sifive/bullet-07/instruction.json` - 指令事件
5. `tools/perf/pmu-events/arch/riscv/sifive/bullet-07/memory.json` - 内存事件
6. `tools/perf/pmu-events/arch/riscv/sifive/bullet-07/microarch.json` - 微架构事件
7. `tools/perf/pmu-events/arch/riscv/sifive/bullet-07/watchpoint.json` - 观察点事件

## 详细技术分析

### 1. 微架构版本识别机制

在`mapfile.csv`中新增的匹配规则：
```
0x489-0x8000000000000[1-9a-e]07-0x[78ac][[:xdigit:]]+,v1,sifive/bullet-07,core
```

**解析:**
- `0x489`: SiFive的MVENDORID（厂商ID）
- `0x8000000000000[1-9a-e]07`: MARCHID模式，支持多种Bullet架构变体的0x07版本
- `0x[78ac][[:xdigit:]]+`: MIMPID模式，匹配特定的实现版本

### 2. 新增PMU事件分类分析

#### 2.1 微架构性能事件 (microarch.json)

**流水线互锁事件:**
- `ADDRESSGEN_INTERLOCK` (0x101): 地址生成互锁周期
- `LONGLATENCY_INTERLOCK` (0x201): 长延迟互锁周期
- `CSR_INTERLOCK` (0x401): CSR访问互锁周期
- `INTEGER_MUL_DIV_INTERLOCK` (0x20001): 整数乘除法互锁周期
- `FP_INTERLOCK` (0x40001): 浮点运算互锁周期

**缓存和内存事件:**
- `ICACHE_BLOCKED` (0x801): 指令缓存阻塞周期
- `DCACHE_BLOCKED` (0x1001): 数据缓存阻塞周期

**分支预测事件:**
- `BRANCH_DIRECTION_MISPREDICTION` (0x2001): 条件分支方向预测错误
- `BRANCH_TARGET_MISPREDICTION` (0x4001): 分支目标预测错误

**流水线控制事件:**
- `PIPELINE_FLUSH` (0x8001): 流水线刷新（fence.i、CSR访问等）
- `REPLAY` (0x10001): 指令重放
- `TRACE_STALL` (0x80001): 跟踪编码器反压导致的停顿

#### 2.2 观察点事件 (watchpoint.json)

提供8个硬件观察点的计数支持：
- `WATCHPOINT_0` 到 `WATCHPOINT_7` (0x164, 0x264, 0x464, 0x864, 0x1064, 0x2064, 0x4064, 0x8064)
- 所有观察点都配置为action=8模式

**编码规律分析:**
观察点事件编码采用位移模式：
- 基础编码: 0x64
- 观察点0-7分别对应位移: 0x100, 0x200, 0x400, 0x800, 0x1000, 0x2000, 0x4000, 0x8000

#### 2.3 周期和指令计数事件 (cycle-and-instruction-count.json)

- `CORE_CLOCK_CYCLES` (0x165): 核心时钟周期计数
- `INSTRUCTIONS_RETIRED` (0x265): 退休指令计数

#### 2.4 指令分类事件 (instruction.json)

**基础指令类型:**
- `EXCEPTION_TAKEN` (0x100): 异常处理
- `INTEGER_LOAD_RETIRED` (0x200): 整数加载指令
- `INTEGER_STORE_RETIRED` (0x400): 整数存储指令
- `ATOMIC_MEMORY_RETIRED` (0x800): 原子内存指令
- `SYSTEM_INSTRUCTION_RETIRED` (0x1000): 系统指令（CSR、WFI、MRET等）

**算术和控制流指令:**
- `INTEGER_ARITHMETIC_RETIRED` (0x2000): 整数算术指令
- `CONDITIONAL_BRANCH_RETIRED` (0x4000): 条件分支指令
- `JAL_INSTRUCTION_RETIRED` (0x8000): 跳转链接指令
- `JALR_INSTRUCTION_RETIRED` (0x10000): 间接跳转指令
- `INTEGER_MULTIPLICATION_RETIRED` (0x20000): 整数乘法指令
- `INTEGER_DIVISION_RETIRED` (0x40000): 整数除法指令

**浮点指令:**
- `FP_LOAD_RETIRED` (0x80000): 浮点加载指令
- `FP_STORE_RETIRED` (0x100000): 浮点存储指令
- `FP_ADD_RETIRED` (0x200000): 浮点加法指令
- `FP_MUL_RETIRED` (0x400000): 浮点乘法指令
- `FP_MULADD_RETIRED` (0x800000): 浮点融合乘加指令
- `FP_DIV_SQRT_RETIRED` (0x1000000): 浮点除法/平方根指令
- `OTHER_FP_RETIRED` (0x2000000): 其他浮点指令

#### 2.5 内存系统事件 (memory.json)

**缓存事件:**
- `ICACHE_MISS` (0x102): 指令缓存缺失
- `DCACHE_MISS` (0x202): 数据缓存缺失
- `DCACHE_RELEASE` (0x402): 数据缓存写回请求

**TLB事件:**
- `ITLB_MISS` (0x802): 指令TLB缺失
- `DTLB_MISS` (0x1002): 数据TLB缺失
- `UTLB_MISS` (0x2002): 统一TLB缺失

#### 2.6 固件事件 (firmware.json)

支持22个标准的RISC-V SBI固件事件，包括：
- 内存访问异常事件（FW_MISALIGNED_LOAD/STORE, FW_ACCESS_LOAD/STORE）
- 系统管理事件（FW_SET_TIMER, FW_IPI_SENT/RECEIVED）
- 内存管理事件（FW_FENCE_I, FW_SFENCE_VMA, FW_HFENCE_GVMA等）

### 3. 技术原理分析

#### 3.1 Sscofpmf扩展支持

Sscofpmf（Supervisor-mode Counter Overflow and Privilege Mode Filtering）是RISC-V的性能监控扩展，提供：
- **计数器溢出处理**: 支持计数器溢出中断
- **特权模式过滤**: 可以按特权模式（M/S/U）过滤事件
- **采样支持**: 支持基于事件的性能采样

#### 3.2 事件编码设计原理

**位域编码策略:**
- 使用不同的位模式来区分事件类别
- 高位用于事件分组，低位用于具体事件
- 保持与早期Bullet版本的兼容性

**示例分析:**
```
指令事件: 0x100, 0x200, 0x400, 0x800... (2的幂次)
内存事件: 0x102, 0x202, 0x402, 0x802... (基础+0x02)
微架构事件: 0x101, 0x201, 0x401, 0x801... (基础+0x01)
```

#### 3.3 调试和跟踪功能增强

**观察点支持:**
- 8个硬件观察点，支持数据访问监控
- action=8配置，用于性能计数而非调试中断
- 可用于热点数据访问分析

**跟踪支持:**
- `TRACE_STALL`事件监控跟踪编码器的反压影响
- 支持处理器跟踪功能的性能分析

### 4. 与其他版本的对比分析

#### 4.1 版本演进路径

**基础Bullet版本 → 0x07版本 → 0x0d版本**

- **基础版本**: 基本的性能计数器支持
- **0x07版本**: 增加调试、跟踪和Sscofpmf支持
- **0x0d版本**: 在0x07基础上增加TLB miss stall计数器

#### 4.2 新增功能对比

**0x07版本新增:**
- 观察点事件支持（8个硬件观察点）
- 跟踪停顿事件（TRACE_STALL）
- 更详细的流水线互锁事件
- Sscofpmf扩展支持

**与0x0d版本的关系:**
- 0x0d版本继承0x07的所有功能
- 额外增加ITLB_MISS_STALL和DTLB_MISS_STALL事件

### 5. 相关提交分析

#### 5.1 提交时间线

1. **4f762cb4091b** (2025-02-12): "Update SiFive Bullet events" - 重新生成基础事件列表
2. **acaefd60493e** (2025-02-12): "Add SiFive Bullet version 0x07 events" - 本patch
3. **8866a3381550** (2025-02-12): "Add SiFive Bullet version 0x0d events" - 0x0d版本支持

#### 5.2 开发策略分析

**模块化设计:**
- 每个版本使用独立的目录结构
- 大部分事件文件可以在版本间复用
- 通过mapfile.csv进行版本匹配

**向后兼容:**
- 保持与早期Bullet版本的事件编码兼容
- 新版本只增加事件，不修改现有事件

### 6. 应用场景和意义

#### 6.1 性能分析应用

**系统级性能调优:**
- 流水线互锁分析，识别性能瓶颈
- 缓存和TLB性能监控
- 分支预测效率评估

**应用程序优化:**
- 指令级性能分析
- 内存访问模式优化
- 浮点运算性能调优

#### 6.2 调试和开发支持

**硬件调试:**
- 观察点支持数据访问监控
- 跟踪功能性能影响分析

**软件开发:**
- 编译器优化验证
- 算法性能评估
- 系统软件调优

### 7. 技术影响评估

#### 7.1 对Linux内核的影响

**perf工具增强:**
- 扩展了RISC-V平台的性能分析能力
- 提供了更细粒度的性能监控
- 支持现代处理器的高级调试功能

**生态系统完善:**
- 推动RISC-V性能分析工具链发展
- 为SiFive处理器提供完整的性能分析支持

#### 7.2 对开发者的价值

**性能优化:**
- 提供详细的微架构级性能数据
- 支持精确的性能瓶颈定位
- 帮助优化关键代码路径

**调试能力:**
- 硬件观察点支持
- 跟踪功能集成
- 系统级性能监控

## 总结

本patch为SiFive Bullet微架构的0x07版本添加了全面的PMU事件支持，主要特点包括：

1. **功能完整性**: 涵盖了微架构、内存、指令、固件等各个层面的性能事件
2. **技术先进性**: 支持Sscofpmf扩展，提供现代化的性能监控能力
3. **设计合理性**: 采用模块化设计，保持版本间的兼容性和可扩展性
4. **实用价值**: 为RISC-V平台的性能分析和调试提供了强大的工具支持

这个patch是RISC-V生态系统中性能分析工具链的重要组成部分，对于推动RISC-V在高性能计算领域的应用具有重要意义。