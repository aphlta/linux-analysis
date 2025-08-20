# RISC-V RISCV_ALTERNATIVE_EARLY 修复分析 - Commit 1ff95eb2bebd

## 基本信息

- **Commit ID**: 1ff95eb2bebda50c4c5406caaf201e0fcb24cc8f
- **作者**: Alexandre Ghiti <alexghiti@rivosinc.com>
- **提交日期**: 2024年8月29日 18:50:48 +0200
- **标题**: riscv: Fix RISCV_ALTERNATIVE_EARLY
- **修复的问题**: 1745cfafebdf ("riscv: don't use global static vars to store alternative data")
- **邮件列表链接**: https://lore.kernel.org/r/20240829165048.49756-1-alexghiti@rivosinc.com
- **维护者**: Palmer Dabbelt <palmer@rivosinc.com>

## 问题描述

### 核心问题

`RISCV_ALTERNATIVE_EARLY` 会在启动过程的非常早期阶段调用 `sbi_ecall()`，此时第一个内存映射尚未建立，因此不能有任何instrumentation发生。

此外，当内核是可重定位的时候，我们也不能在这么早的阶段进行任何重定位，因为它们只会被虚拟地打补丁。

### 问题根源

1. **早期启动阶段限制**: 在内存映射建立之前，不能使用任何instrumentation
2. **可重定位内核问题**: 早期阶段的重定位只会被虚拟地打补丁，无法正确工作
3. **全局变量依赖**: 之前的实现依赖全局静态变量，在早期阶段访问存在问题

### 报告的问题

- **报告者1**: Conor Dooley <conor.dooley@microchip.com>
- **链接**: https://lore.kernel.org/linux-riscv/20240813-pony-truck-3e7a83e9759e@spud/
- **报告者2**: syzbot+cfbcb82adf6d7279fd35@syzkaller.appspotmail.com
- **链接**: https://lore.kernel.org/linux-riscv/00000000000065062c061fcec37b@google.com/

## 代码修改分析

### 修改的文件

1. **arch/riscv/include/asm/sbi.h** - SBI头文件修改
2. **arch/riscv/kernel/Makefile** - 编译配置修改
3. **arch/riscv/kernel/sbi.c** - 移除函数实现
4. **arch/riscv/kernel/sbi_ecall.c** - 新增文件

### 具体修改内容

#### 1. sbi.h 头文件修改

**移除的函数声明**:
```c
// 从 sbi.h 中移除了以下函数的实现
struct sbiret __sbi_ecall(unsigned long arg0, unsigned long arg1,
                         unsigned long arg2, unsigned long arg3,
                         unsigned long arg4, unsigned long arg5,
                         int fid, int ext);

long __sbi_base_ecall(int fid);
```

**新增的内联函数**:
```c
// 在 sbi.h 中新增了内联包装函数
static inline struct sbiret sbi_ecall(int ext, int fid, unsigned long arg0,
                                     unsigned long arg1, unsigned long arg2,
                                     unsigned long arg3, unsigned long arg4,
                                     unsigned long arg5)
{
    return __sbi_ecall(arg0, arg1, arg2, arg3, arg4, arg5, fid, ext);
}
```

#### 2. Makefile 修改

**新增的编译选项**:
```makefile
# 为新的 sbi_ecall.c 文件添加特殊编译选项
CFLAGS_sbi_ecall.o := -mcmodel=medany

# 移除 FTRACE 支持
CFLAGS_REMOVE_sbi_ecall.o = $(CC_FLAGS_FTRACE)

# 对于可重定位内核，禁用 PIE
CFLAGS_sbi_ecall.o += -fno-pie

# 禁用 KASAN instrumentation
KASAN_SANITIZE_sbi_ecall.o := n

# 添加到构建目标
obj-$(CONFIG_RISCV_SBI) += sbi.o sbi_ecall.o
```

#### 3. 新增 sbi_ecall.c 文件

**核心函数实现**:
```c
// SPDX-License-Identifier: GPL-2.0
/* Copyright (c) 2024 Rivos Inc. */

#include <asm/sbi.h>
#define CREATE_TRACE_POINTS
#include <asm/trace.h>

long __sbi_base_ecall(int fid)
{
    struct sbiret ret;

    ret = sbi_ecall(SBI_EXT_BASE, fid, 0, 0, 0, 0, 0, 0);
    if (!ret.error)
        return ret.value;
    else
        return sbi_err_map_linux_errno(ret.error);
}
EXPORT_SYMBOL(__sbi_base_ecall);

struct sbiret __sbi_ecall(unsigned long arg0, unsigned long arg1,
                         unsigned long arg2, unsigned long arg3,
                         unsigned long arg4, unsigned long arg5,
                         int fid, int ext)
{
    struct sbiret ret;

    trace_sbi_call(ext, fid);

    register uintptr_t a0 asm ("a0") = (uintptr_t)(arg0);
    register uintptr_t a1 asm ("a1") = (uintptr_t)(arg1);
    register uintptr_t a2 asm ("a2") = (uintptr_t)(arg2);
    register uintptr_t a3 asm ("a3") = (uintptr_t)(arg3);
    register uintptr_t a4 asm ("a4") = (uintptr_t)(arg4);
    register uintptr_t a5 asm ("a5") = (uintptr_t)(arg5);
    register uintptr_t a6 asm ("a6") = (uintptr_t)(fid);
    register uintptr_t a7 asm ("a7") = (uintptr_t)(ext);
    asm volatile ("ecall"
                  : "+r" (a0), "+r" (a1)
                  : "r" (a2), "r" (a3), "r" (a4), "r" (a5), "r" (a6), "r" (a7)
                  : "memory");
    ret.error = a0;
    ret.value = a1;

    trace_sbi_return(ext, ret.error, ret.value);

    return ret;
}
EXPORT_SYMBOL(__sbi_ecall);
```

## 技术原理分析

### 1. RISCV_ALTERNATIVE_EARLY 机制

**Alternative 机制的作用**:
- 允许在运行时根据CPU特性动态替换代码段
- 在启动早期阶段检测CPU特性并应用相应的优化
- 支持不同厂商的CPU扩展和errata修复

**早期阶段的特殊要求**:
- 不能依赖虚拟内存映射
- 不能使用全局变量（可能未正确重定位）
- 不能有任何instrumentation（KASAN、FTRACE等）
- 必须使用位置无关代码

### 2. SBI (Supervisor Binary Interface) 调用

**SBI的作用**:
- RISC-V架构中Supervisor模式与Machine模式之间的标准接口
- 提供系统服务，如CPU管理、时钟、IPI等
- 在早期启动阶段用于获取硬件信息

**ecall指令**:
```assembly
ecall  # 执行环境调用，从S模式陷入M模式
```

**寄存器约定**:
- a0-a5: 参数寄存器
- a6: 功能ID (fid)
- a7: 扩展ID (ext)
- 返回值: a0(error), a1(value)

### 3. Trace 机制集成

**新增的trace点**:
```c
// arch/riscv/include/asm/trace.h
TRACE_EVENT_CONDITION(sbi_call,
    TP_PROTO(int ext, int fid),
    TP_ARGS(ext, fid),
    TP_CONDITION(ext != SBI_EXT_HSM),  // 排除HSM扩展
    // ...
);

TRACE_EVENT_CONDITION(sbi_return,
    TP_PROTO(int ext, long error, long value),
    TP_ARGS(ext, error, value),
    TP_CONDITION(ext != SBI_EXT_HSM),
    // ...
);
```

**trace的作用**:
- 调试SBI调用的执行情况
- 性能分析和优化
- 排除HSM(Hart State Management)扩展以避免过多的trace输出

### 4. 编译选项详解

**-mcmodel=medany**:
- 使用medium any代码模型
- 允许代码和数据在任意位置
- 适合早期启动代码

**-fno-pie**:
- 禁用位置无关可执行文件
- 避免早期阶段的重定位问题
- 确保代码能在物理地址空间正确执行

**禁用instrumentation**:
- `CFLAGS_REMOVE_sbi_ecall.o = $(CC_FLAGS_FTRACE)`: 禁用函数跟踪
- `KASAN_SANITIZE_sbi_ecall.o := n`: 禁用KASAN地址检查

## 修复前后对比

### 修复前的问题

1. **全局变量依赖**: `__sbi_ecall()` 和 `__sbi_base_ecall()` 在 `sbi.c` 中实现，可能依赖全局状态
2. **Instrumentation干扰**: 整个 `sbi.c` 文件需要禁用instrumentation
3. **重定位问题**: 在可重定位内核中，早期调用可能访问错误的地址
4. **编译复杂性**: 需要为整个文件设置特殊编译选项

### 修复后的改进

1. **隔离关键函数**: 将关键的SBI调用函数移到独立文件
2. **精确控制**: 只对必要的函数禁用instrumentation
3. **清晰的职责分离**: `sbi.c` 处理高级SBI功能，`sbi_ecall.c` 处理底层调用
4. **更好的可维护性**: 减少了编译选项的复杂性

## 相关提交分析

### 被修复的提交: 1745cfafebdf

**标题**: "riscv: don't use global static vars to store alternative data"

**主要修改**:
- 移除了全局静态变量 `cpu_mfr_info` 和 `vendor_patch_func`
- 改为在每次调用时动态获取CPU制造商信息
- 避免了早期阶段对全局变量的依赖

**引入的问题**:
- 虽然解决了全局变量问题，但没有考虑到SBI调用的早期阶段限制
- `__sbi_ecall()` 仍然在可能有instrumentation的环境中执行

## 技术影响分析

### 1. 启动稳定性

**改进**:
- 消除了早期启动阶段的潜在崩溃
- 确保SBI调用在所有配置下都能正常工作
- 提高了可重定位内核的稳定性

### 2. 调试能力

**增强**:
- 新增的trace点提供了SBI调用的可见性
- 有助于调试启动问题和性能分析
- 排除HSM扩展避免了trace输出过多

### 3. 代码维护性

**提升**:
- 清晰的职责分离使代码更易理解
- 减少了编译选项的复杂性
- 为未来的SBI功能扩展提供了更好的基础

### 4. 性能影响

**最小化**:
- 函数调用开销基本不变
- trace机制只在启用时才有开销
- 编译优化确保了最佳性能

## Alternative机制在RISC-V中的重要性

### 1. CPU特性检测

**多样化的RISC-V实现**:
- 不同厂商的CPU有不同的扩展支持
- 需要在运行时检测并适配
- Alternative机制提供了统一的解决方案

### 2. Errata处理

**硬件问题缓解**:
- 不同CPU版本可能有不同的硬件问题
- Alternative机制允许动态应用修复
- 确保内核在各种硬件上的兼容性

### 3. 性能优化

**指令集扩展利用**:
- 根据CPU支持的扩展选择最优指令序列
- 在不支持扩展的CPU上回退到基础实现
- 实现了性能和兼容性的平衡

## 总结

### 技术价值

这个patch通过将关键的SBI调用函数隔离到独立文件，解决了以下关键问题：

1. **启动稳定性**: 消除了早期启动阶段的instrumentation干扰
2. **重定位兼容性**: 确保可重定位内核的正确工作
3. **代码清晰性**: 提供了更好的职责分离和可维护性
4. **调试能力**: 新增trace机制增强了调试和分析能力

### 实际意义

#### 对RISC-V生态的影响
- **稳定性提升**: 提高了RISC-V内核在各种配置下的稳定性
- **开发效率**: 更好的调试能力加速了问题定位和解决
- **兼容性保证**: 确保了不同RISC-V实现的兼容性

#### 对内核开发的贡献
- **最佳实践**: 为早期启动代码的编写提供了参考
- **架构设计**: 展示了如何正确处理早期阶段的特殊要求
- **问题解决**: 提供了instrumentation和重定位问题的解决方案

### 未来发展

这个patch为RISC-V的未来发展奠定了基础：

1. **扩展支持**: 为新的RISC-V扩展提供了稳定的基础
2. **厂商适配**: 简化了不同厂商CPU的适配工作
3. **调试工具**: trace机制为开发更强大的调试工具提供了基础
4. **性能优化**: 为基于CPU特性的性能优化提供了可靠平台

这个看似简单的重构实际上解决了RISC-V架构中一个基础而关键的问题，体现了对系统启动过程深入理解和精确控制的重要性。