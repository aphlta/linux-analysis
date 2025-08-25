# RISC-V Kernel Mode Vector Support Patch Analysis

## Commit Information

**Commit ID**: ecd2ada8a5e0b464dab54f71d4ba7bbf5708711f
**Author**: Greentime Hu <greentime.hu@sifive.com>
**Date**: Mon Jan 15 05:59:20 2024 +0000
**Subject**: riscv: Add support for kernel mode vector

**Co-developed-by**: Vincent Chen <vincent.chen@sifive.com>
**Signed-off-by**: Vincent Chen <vincent.chen@sifive.com>
**Signed-off-by**: Greentime Hu <greentime.hu@sifive.com>
**Signed-off-by**: Andy Chiu <andy.chiu@sifive.com>
**Reviewed-by**: Eric Biggers <ebiggers@google.com>
**Tested-by**: Björn Töpel <bjorn@rivosinc.com>
**Tested-by**: Lad Prabhakar <prabhakar.mahadev-lad.rj@bp.renesas.com>

## Patch概述

这个patch为RISC-V架构添加了内核模式Vector支持，引入了`kernel_vector_begin()`和`kernel_vector_end()`函数，允许内核代码安全地使用Vector指令。这是RISC-V Vector扩展在内核空间使用的基础设施。

## 修改文件列表

1. `arch/riscv/include/asm/processor.h` - 添加Vector标志位定义和thread结构修改
2. `arch/riscv/include/asm/simd.h` - 新增SIMD相关接口定义
3. `arch/riscv/include/asm/vector.h` - 添加Vector函数声明
4. `arch/riscv/kernel/Makefile` - 添加kernel_mode_vector.c编译
5. `arch/riscv/kernel/kernel_mode_vector.c` - 新增内核模式Vector实现
6. `arch/riscv/kernel/process.c` - 初始化Vector标志位

## 详细代码修改分析

### 1. processor.h 修改

#### 新增Vector标志位定义
```c
/*
 * We use a flag to track in-kernel Vector context. Currently the flag has the
 * following meaning:
 *
 *  - bit 0: indicates whether the in-kernel Vector context is active. The
 *    activation of this state disables the preemption.
 */
#define RISCV_KERNEL_MODE_V    0x1
```

#### thread_struct结构修改
```c
struct thread_struct {
    // ... 其他字段
-   unsigned long vstate_ctrl;
+   u32 riscv_v_flags;        // 新增Vector标志位
+   u32 vstate_ctrl;          // 类型从unsigned long改为u32
    struct __riscv_v_ext_state vstate;
    // ...
};
```

**设计原理**:
- `riscv_v_flags`用于跟踪内核Vector上下文状态
- bit 0 (RISCV_KERNEL_MODE_V)表示内核Vector上下文是否激活
- 激活状态会禁用抢占，确保Vector状态的一致性

### 2. simd.h 新增文件

这个文件定义了SIMD相关的接口，主要包含`may_use_simd()`函数，用于检查当前上下文是否可以使用Vector指令。

```c
static __must_check inline bool may_use_simd(void)
{
    if (in_hardirq() || in_nmi())
        return false;
    // ... 其他检查逻辑
}
```

**设计原理**:
- 硬中断和NMI上下文中不允许使用Vector
- 确保Vector使用的安全性和上下文正确性

### 3. kernel_mode_vector.c 核心实现

#### 核心数据结构和函数

##### Vector标志位操作函数
```c
static inline void riscv_v_flags_set(u32 flags)
{
    current->thread.riscv_v_flags = flags;
}

static inline void riscv_v_start(u32 flags)
{
    int orig = riscv_v_flags();
    BUG_ON((orig & flags) != 0);  // 确保标志位未被设置
    riscv_v_flags_set(orig | flags);
}

static inline void riscv_v_stop(u32 flags)
{
    int orig = riscv_v_flags();
    BUG_ON((orig & flags) == 0);  // 确保标志位已被设置
    riscv_v_flags_set(orig & ~flags);
}
```

##### CPU Vector上下文管理
```c
void get_cpu_vector_context(void)
{
    preempt_disable();                    // 禁用抢占
    riscv_v_start(RISCV_KERNEL_MODE_V);  // 设置内核Vector模式标志
}

void put_cpu_vector_context(void)
{
    riscv_v_stop(RISCV_KERNEL_MODE_V);   // 清除内核Vector模式标志
    preempt_enable();                     // 重新启用抢占
}
```

##### 内核Vector接口函数
```c
void kernel_vector_begin(void)
{
    if (WARN_ON(!has_vector()))
        return;
    
    BUG_ON(!may_use_simd());              // 检查是否可以使用SIMD
    
    get_cpu_vector_context();             // 获取CPU Vector上下文
    
    riscv_v_vstate_save(current, task_pt_regs(current));  // 保存当前Vector状态
    
    riscv_v_enable();                     // 启用Vector
}

void kernel_vector_end(void)
{
    if (WARN_ON(!has_vector()))
        return;
    
    riscv_v_vstate_restore(current, task_pt_regs(current)); // 恢复Vector状态
    
    riscv_v_disable();                    // 禁用Vector
    
    put_cpu_vector_context();             // 释放CPU Vector上下文
}
```

### 4. process.c 修改

在`copy_thread()`函数中初始化新进程的Vector标志位:
```c
int copy_thread(struct task_struct *p, const struct kernel_clone_args *args)
{
    // ... 其他初始化代码
+   p->thread.riscv_v_flags = 0;  // 初始化Vector标志位为0
    p->thread.ra = (unsigned long)ret_from_fork;
    // ...
}
```

## 技术原理分析

### 1. Vector状态管理机制

#### 状态保存和恢复流程
```
kernel_vector_begin():
1. 检查Vector硬件支持
2. 检查当前上下文是否允许使用SIMD
3. 禁用抢占(get_cpu_vector_context)
4. 保存当前任务的Vector状态到内存
5. 启用Vector硬件

kernel_vector_end():
1. 从内存恢复当前任务的Vector状态
2. 禁用Vector硬件
3. 重新启用抢占(put_cpu_vector_context)
```

#### 抢占控制机制
- 在Vector使用期间禁用抢占，防止上下文切换导致的状态混乱
- 使用`RISCV_KERNEL_MODE_V`标志位跟踪内核Vector使用状态
- 确保Vector状态的原子性操作

### 2. 安全性保障

#### 上下文检查
- `may_use_simd()`确保只在安全的上下文中使用Vector
- 硬中断和NMI中禁止使用Vector
- 检查抢占状态和软中断状态

#### 错误检测
- 使用`BUG_ON()`检测非法的标志位状态
- `WARN_ON()`检测硬件支持情况
- 确保`kernel_vector_begin()`和`kernel_vector_end()`成对调用

### 3. 性能优化考虑

#### 延迟状态保存
- 只在实际需要时保存/恢复Vector状态
- 避免不必要的寄存器操作
- 最小化上下文切换开销

#### 抢占控制优化
- 精确控制抢占禁用的时间窗口
- 只在Vector使用期间禁用抢占
- 平衡性能和响应性

## 相关提交分析

这个patch是RISC-V Vector内核支持系列的基础patch，后续相关提交包括:

1. **956895b9d8f7**: "riscv: vector: make Vector always available for softirq context"
   - 使Vector在软中断上下文中可用

2. **7df56cbc27e4**: "riscv: sched: defer restoring Vector context for user"
   - 延迟用户空间Vector上下文恢复，优化调度性能

3. **c2a658d41924**: "riscv: lib: vectorize copy_to_user/copy_from_user"
   - 使用Vector指令优化内存拷贝函数

4. **2080ff949307**: "riscv: vector: allow kernel-mode Vector with preemption"
   - 允许在可抢占的内核模式中使用Vector

## 影响和意义

### 1. 功能影响
- 为RISC-V内核提供了安全使用Vector指令的基础设施
- 支持内核中的高性能计算和优化算法
- 为后续的Vector优化(如加密、内存拷贝等)奠定基础

### 2. 性能影响
- 启用了内核中Vector指令的使用，可以显著提升特定算法性能
- 通过精确的状态管理，最小化了Vector使用的开销
- 为系统调用和内核函数的Vector优化创造了条件

### 3. 架构影响
- 完善了RISC-V Vector扩展的内核支持
- 提供了与ARM NEON类似的内核Vector使用模式
- 为RISC-V生态系统的高性能计算应用提供了支持

## 总结

这个patch是RISC-V Vector扩展内核支持的重要里程碑，它:

1. **建立了完整的内核Vector使用框架**，包括状态管理、上下文控制和安全检查
2. **提供了简洁的API接口**，使内核开发者可以安全地使用Vector指令
3. **实现了高效的状态管理机制**，最小化了Vector使用的性能开销
4. **为后续的Vector优化奠定了基础**，支持加密、内存操作等高性能算法的实现

该patch的设计充分考虑了安全性、性能和可维护性，为RISC-V架构在高性能计算领域的应用提供了重要支持。