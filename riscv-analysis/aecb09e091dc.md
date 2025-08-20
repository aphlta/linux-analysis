# RISC-V Unaligned Access Speed Test Parameter Patch 分析

## Commit 信息

- **Commit ID**: aecb09e091dc143345a9e4b282d0444554445f4b
- **作者**: Andrew Jones <ajones@ventanamicro.com>
- **提交者**: Alexandre Ghiti <alexghiti@rivosinc.com>
- **提交日期**: 2025年3月19日
- **标题**: riscv: Add parameter for skipping access speed tests

## Patch 概述

这个patch为RISC-V架构添加了跳过标量(scalar)和向量(vector)非对齐访问速度测试的命令行参数功能。主要目的是:

1. 允许测试替代代码路径
2. 在测试运行过慢的环境中跳过测试
3. 要求所有CPU必须具有相同的非对齐访问速度

## 详细修改内容

### 1. 新增命令行参数

#### 标量非对齐访问速度参数
```c
static long unaligned_scalar_speed_param = RISCV_HWPROBE_MISALIGNED_SCALAR_UNKNOWN;

static int __init set_unaligned_scalar_speed_param(char *str)
{
    if (!strcmp(str, speed_str[RISCV_HWPROBE_MISALIGNED_SCALAR_SLOW]))
        unaligned_scalar_speed_param = RISCV_HWPROBE_MISALIGNED_SCALAR_SLOW;
    else if (!strcmp(str, speed_str[RISCV_HWPROBE_MISALIGNED_SCALAR_FAST]))
        unaligned_scalar_speed_param = RISCV_HWPROBE_MISALIGNED_SCALAR_FAST;
    else if (!strcmp(str, speed_str[RISCV_HWPROBE_MISALIGNED_SCALAR_UNSUPPORTED]))
        unaligned_scalar_speed_param = RISCV_HWPROBE_MISALIGNED_SCALAR_UNSUPPORTED;
    else
        return -EINVAL;
    return 1;
}
__setup("unaligned_scalar_speed=", set_unaligned_scalar_speed_param);
```

#### 向量非对齐访问速度参数
```c
static long unaligned_vector_speed_param = RISCV_HWPROBE_MISALIGNED_VECTOR_UNKNOWN;

static int __init set_unaligned_vector_speed_param(char *str)
{
    if (!strcmp(str, speed_str[RISCV_HWPROBE_MISALIGNED_VECTOR_SLOW]))
        unaligned_vector_speed_param = RISCV_HWPROBE_MISALIGNED_VECTOR_SLOW;
    else if (!strcmp(str, speed_str[RISCV_HWPROBE_MISALIGNED_VECTOR_FAST]))
        unaligned_vector_speed_param = RISCV_HWPROBE_MISALIGNED_VECTOR_FAST;
    else if (!strcmp(str, speed_str[RISCV_HWPROBE_MISALIGNED_VECTOR_UNSUPPORTED]))
        unaligned_vector_speed_param = RISCV_HWPROBE_MISALIGNED_VECTOR_UNSUPPORTED;
    else
        return -EINVAL;
    return 1;
}
__setup("unaligned_vector_speed=", set_unaligned_vector_speed_param);
```

### 2. 修改初始化逻辑

#### 标量非对齐访问处理
原来的逻辑:
```c
if (unaligned_scalar_speed_param == RISCV_HWPROBE_MISALIGNED_SCALAR_UNKNOWN &&
    !check_unaligned_access_emulated_all_cpus()) {
    check_unaligned_access_speed_all_cpus();
```

修改后的逻辑:
```c
if (unaligned_scalar_speed_param != RISCV_HWPROBE_MISALIGNED_SCALAR_UNKNOWN) {
    pr_info("scalar unaligned access speed set to '%s' (%lu) by command line\n",
            speed_str[unaligned_scalar_speed_param], unaligned_scalar_speed_param);
    for_each_online_cpu(cpu)
        per_cpu(misaligned_access_speed, cpu) = unaligned_scalar_speed_param;
} else if (!check_unaligned_access_emulated_all_cpus()) {
    check_unaligned_access_speed_all_cpus();
}
```

#### 向量非对齐访问处理
原来的逻辑:
```c
if (!has_vector()) {
    for_each_online_cpu(cpu)
        per_cpu(vector_misaligned_access, cpu) = RISCV_HWPROBE_MISALIGNED_VECTOR_UNSUPPORTED;
} else if (!check_vector_unaligned_access_emulated_all_cpus() &&
           IS_ENABLED(CONFIG_RISCV_PROBE_VECTOR_UNALIGNED_ACCESS)) {
    kthread_run(vec_check_unaligned_access_speed_all_cpus,
                NULL, "vec_check_unaligned_access_speed_all_cpus");
}
```

修改后的逻辑:
```c
if (!has_vector())
    unaligned_vector_speed_param = RISCV_HWPROBE_MISALIGNED_VECTOR_UNSUPPORTED;

if (unaligned_vector_speed_param == RISCV_HWPROBE_MISALIGNED_VECTOR_UNKNOWN &&
    !check_vector_unaligned_access_emulated_all_cpus() &&
    IS_ENABLED(CONFIG_RISCV_PROBE_VECTOR_UNALIGNED_ACCESS)) {
    kthread_run(vec_check_unaligned_access_speed_all_cpus,
                NULL, "vec_check_unaligned_access_speed_all_cpus");
} else {
    pr_info("vector unaligned access speed set to '%s' by command line\n",
            speed_str[unaligned_vector_speed_param]);
    for_each_online_cpu(cpu)
        per_cpu(vector_misaligned_access, cpu) = unaligned_vector_speed_param;
}
```

### 3. 代码重构

#### CPU热插拔回调设置
移除了条件编译保护:
```c
// 原来的代码
#ifdef CONFIG_RISCV_PROBE_UNALIGNED_ACCESS
cpuhp_setup_state_nocalls(CPUHP_AP_ONLINE_DYN, "riscv:online",
                          riscv_online_cpu, riscv_offline_cpu);
#endif

// 修改后的代码
cpuhp_setup_state_nocalls(CPUHP_AP_ONLINE_DYN, "riscv:online",
                          riscv_online_cpu, riscv_offline_cpu);
```

这是因为现在标量CPU热插拔回调需要始终运行，所以需要将其及其支持函数从CONFIG_RISCV_PROBE_UNALIGNED_ACCESS条件编译中移出。

## 技术原理分析

### 1. 非对齐访问速度检测机制

RISC-V架构的非对齐访问速度检测通过以下方式工作:

- **标量非对齐访问**: 通过测量非对齐内存访问与对齐访问的性能差异来确定速度
- **向量非对齐访问**: 类似地测量向量指令的非对齐访问性能
- **速度分类**: 分为fast(快速)、slow(慢速)、unsupported(不支持)三种

### 2. 参数处理机制

使用Linux内核的`__setup()`宏来注册命令行参数处理函数:
- `unaligned_scalar_speed=`: 设置标量非对齐访问速度
- `unaligned_vector_speed=`: 设置向量非对齐访问速度

参数值可以是: "slow", "fast", "unsupported"

### 3. Per-CPU变量管理

使用`DEFINE_PER_CPU()`定义的per-CPU变量:
- `misaligned_access_speed`: 存储每个CPU的标量非对齐访问速度
- `vector_misaligned_access`: 存储每个CPU的向量非对齐访问速度

当通过命令行参数设置速度时，会为所有在线CPU设置相同的值。

## 相关提交分析

这个patch是一个修复和改进系列的一部分:

1. **2744ec472de3**: "riscv: Fix set up of vector cpu hotplug callback" - 修复向量CPU热插拔回调设置
2. **05ee21f0fcb8**: "riscv: Fix set up of cpu hotplug callbacks" - 修复CPU热插拔回调设置
3. **813d39baee32**: "riscv: Change check_unaligned_access_speed_all_cpus to void" - 将函数返回类型改为void

这些提交解决了非对齐访问速度检测中的一系列问题，特别是CPU热插拔处理和函数接口的改进。

## 影响和意义

### 1. 测试灵活性
- 允许开发者和测试人员跳过耗时的速度测试
- 支持在已知硬件特性的环境中直接设置速度参数
- 便于测试不同代码路径

### 2. 性能优化
- 在某些环境中，速度测试可能非常耗时
- 通过命令行参数可以避免不必要的测试开销
- 提高系统启动速度

### 3. 调试支持
- 为内核开发者提供了更多的调试选项
- 可以强制设置特定的访问速度来测试相关代码路径
- 有助于验证不同速度设置下的系统行为

## 总结

这个patch通过添加命令行参数支持，显著提高了RISC-V非对齐访问速度检测机制的灵活性和可控性。它不仅解决了在某些环境中测试运行过慢的问题，还为开发者提供了更好的测试和调试工具。代码重构部分确保了CPU热插拔回调的正确设置，这对于多核系统的稳定性至关重要。