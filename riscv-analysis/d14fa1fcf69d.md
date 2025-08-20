# RISC-V Kernel GP Register Leakage Fix Analysis

## Commit Information
- **Commit ID**: d14fa1fcf69d
- **Title**: riscv: process: Fix kernel gp leakage
- **Author**: Stefan O'Rear <sorear@fastmail.com>
- **Reviewer**: Alexandre Ghiti <alexghiti@rivosinc.com>
- **Maintainer**: Palmer Dabbelt <palmer@rivosinc.com>
- **Fixes**: 7db91e57a0ac ("RISC-V: Task implementation")
- **Cc**: stable@vger.kernel.org

## 漏洞描述

这个patch修复了RISC-V架构中一个严重的安全漏洞：内核全局指针(gp)寄存器值泄露到用户空间。该漏洞存在于kernel thread创建过程中，会将内核的`__global_pointer$`地址暴露给用户空间进程。

### 漏洞成因

在原始的`copy_thread()`函数实现中，当创建kernel thread时，代码会执行以下操作：

```c
register unsigned long gp_in_global __asm__("gp");

if (unlikely(args->fn)) {
    /* Kernel thread */
    memset(childregs, 0, sizeof(struct pt_regs));
    childregs->gp = gp_in_global;  // 问题所在：将内核gp值设置到用户寄存器上下文
    childregs->status = SR_PP | SR_PIE;
    // ...
}
```

这里的问题是`childregs`指向的是**用户空间寄存器上下文**(`pt_regs`)，而不是内核上下文。即使是kernel thread，这个上下文在某些情况下也会被用户空间观察到。

## 安全影响

该漏洞允许用户空间通过多种方式获取内核地址信息，破坏KASLR(Kernel Address Space Layout Randomization)保护：

### 1. kernel_execve路径泄露
`kernel_execve`当前不清理整数寄存器，导致PID 1和其他由内核启动的用户进程的初始寄存器状态包含：
- `sp` = 用户栈地址
- `gp` = 内核`__global_pointer$`地址
- 其他整数寄存器被memset清零

### 2. ptrace接口泄露
通过`ptrace(PTRACE_GETREGSET)`可以在user_mode_helper线程exec完成前attach并读取寄存器状态。虽然需要SIGSTOP信号传递，但这只能在用户/内核边界发生。

### 3. /proc接口泄露
`/proc/*/task/*/syscall`接口可以在exec完成前读取user_mode_helpers的pt_regs，虽然gp不在返回的寄存器列表中，但存在潜在风险。

### 4. PERF_SAMPLE_REGS_USER泄露
这是最严重的影响：
- `LOCKDOWN_PERF`通常阻止通过`PERF_SAMPLE_REGS_INTR`访问内核地址
- 但由于此漏洞，内核地址也通过`PERF_SAMPLE_REGS_USER`暴露
- `PERF_SAMPLE_REGS_USER`在`LOCKDOWN_PERF`下是被允许的
- 这为编写exploit代码提供了可能

### 5. 追踪基础设施泄露
大部分追踪基础设施允许访问用户寄存器，需要进一步确定哪些追踪形式在不允许访问内核寄存器的情况下允许访问用户寄存器。

## 代码修改分析

### 修改内容

```diff
-register unsigned long gp_in_global __asm__("gp");
-
 if (unlikely(args->fn)) {
     /* Kernel thread */
     memset(childregs, 0, sizeof(struct pt_regs));
-    childregs->gp = gp_in_global;
     /* Supervisor/Machine, irqs on: */
     childregs->status = SR_PP | SR_PIE;
```

### 修改原理

1. **删除全局变量声明**：移除了`register unsigned long gp_in_global __asm__("gp")`声明，这个变量用于获取当前gp寄存器值。

2. **移除gp寄存器设置**：在kernel thread创建时，不再设置`childregs->gp = gp_in_global`。

3. **保持memset清零**：`memset(childregs, 0, sizeof(struct pt_regs))`确保包括gp在内的所有用户寄存器都被清零。

### 为什么这样修改是安全的

1. **Kernel thread不需要用户gp**：Kernel thread运行在内核空间，不需要用户空间的全局指针。

2. **内核有独立的gp管理**：内核在上下文切换时会正确管理自己的gp寄存器，不依赖于pt_regs中的值。

3. **用户进程会正确初始化**：当kernel thread最终exec成为用户进程时，`start_thread()`会正确设置用户空间的寄存器状态。

## 历史背景

### 原始实现 (7db91e57a0ac)

在最初的RISC-V任务实现中，代码是这样的：

```c
if (unlikely(p->flags & PF_KTHREAD)) {
    /* Kernel thread */
    const register unsigned long gp __asm__ ("gp");
    memset(childregs, 0, sizeof(struct pt_regs));
    childregs->gp = gp;  // 设置内核gp到用户上下文
    childregs->sstatus = SR_PS | SR_PIE;
    // ...
}
```

这个实现的问题在于混淆了内核上下文和用户上下文的边界。

### 演进过程

1. **初始实现**：直接将内核gp设置到用户寄存器上下文
2. **中间演进**：代码结构有所调整，但核心问题依然存在
3. **当前修复**：完全移除了这个不必要且危险的设置

## 相关提交分析

### Fixes标签指向的commit
- **7db91e57a0ac**: "RISC-V: Task implementation"
- 这是RISC-V架构最初的任务管理实现
- 引入了gp寄存器泄露问题

### 修复的必要性
- 标记为`Cc: stable@vger.kernel.org`，表明需要backport到稳定版本
- 这是一个安全修复，影响所有使用RISC-V架构的系统

## 技术细节

### RISC-V gp寄存器
- `gp`(Global Pointer)是RISC-V架构中的一个特殊寄存器
- 用于优化全局变量和静态变量的访问
- 在内核中指向`__global_pointer$`符号
- 泄露这个值可以帮助攻击者绕过KASLR保护

### pt_regs结构
- 保存用户空间寄存器状态的结构
- 在系统调用、异常、中断时保存/恢复用户寄存器
- 可以通过多种内核接口被用户空间观察到

### 内核线程特点
- 运行在内核空间，没有用户空间内存映射
- 可能通过`kernel_execve`转换为用户进程
- 在转换过程中，pt_regs会成为新用户进程的初始寄存器状态

## 影响范围

### 受影响的系统
- 所有运行RISC-V架构的Linux系统
- 特别是启用了性能监控、追踪或调试功能的系统

### 攻击场景
1. **本地权限提升**：本地用户可能利用泄露的内核地址进行进一步攻击
2. **KASLR绕过**：攻击者可以计算出内核基址，为ROP/JOP攻击做准备
3. **信息泄露**：即使不能直接利用，也为其他攻击提供了有价值的信息

## 修复验证

修复后的代码确保：
1. Kernel thread的用户寄存器上下文完全清零
2. 不会泄露任何内核地址信息到用户空间
3. 不影响正常的内核线程功能
4. 与现有的用户进程创建流程兼容

## 总结

这个patch修复了一个存在已久的安全漏洞，该漏洞允许用户空间获取内核地址信息，破坏系统的安全边界。修复方案简洁有效：移除不必要的内核gp寄存器设置，确保用户寄存器上下文的清洁性。这个修复对于维护RISC-V系统的安全性至关重要，特别是在面对日益复杂的攻击手段时。