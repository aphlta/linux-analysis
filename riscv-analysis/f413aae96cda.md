# Patch Analysis: f413aae96cda

## 基本信息

**Commit ID**: f413aae96cda059635910c462ede0a8f0385897c  
**作者**: Charlie Jenkins <charlie@rivosinc.com>  
**提交日期**: 2024年3月8日  
**标题**: riscv: Set unaligned access speed at compile time  

## 修改概述

这个patch引入了Kconfig选项来在编译时设置内核的未对齐访问支持，提供了运行时未对齐访问探测的非便携式替代方案。主要将未对齐访问探测代码移动到独立文件中，并通过新的`RISCV_PROBE_UNALIGNED_ACCESS_SUPPORT`选项进行控制。

## 修改的文件

1. **arch/riscv/Kconfig** - 重构Kconfig配置选项
2. **arch/riscv/include/asm/cpufeature.h** - 更新头文件声明
3. **arch/riscv/kernel/Makefile** - 调整编译规则
4. **arch/riscv/kernel/cpufeature.c** - 移除未对齐访问相关代码
5. **arch/riscv/kernel/sys_hwprobe.c** - 更新hwprobe系统调用
6. **arch/riscv/kernel/traps_misaligned.c** - 添加条件编译
7. **arch/riscv/kernel/unaligned_access_speed.c** - 新增文件，包含未对齐访问检测代码

## 详细修改分析

### 1. Kconfig配置重构

#### 原有配置
```kconfig
config RISCV_MISALIGNED
    bool "Support misaligned load/store traps for kernel and userspace"
    select SYSCTL_ARCH_UNALIGN_ALLOW
    default y
```

#### 新配置结构
```kconfig
config RISCV_MISALIGNED
    bool
    select SYSCTL_ARCH_UNALIGN_ALLOW
    help
      Embed support for emulating misaligned loads and stores.

choice
    prompt "Unaligned Accesses Support"
    default RISCV_PROBE_UNALIGNED_ACCESS
```

**新增的选择项**:
- `RISCV_PROBE_UNALIGNED_ACCESS`: 运行时探测硬件未对齐访问支持
- `RISCV_EMULATED_UNALIGNED_ACCESS`: 在系统不支持时模拟未对齐访问
- `RISCV_SLOW_UNALIGNED_ACCESS`: 假设系统支持慢速未对齐访问
- `RISCV_EFFICIENT_UNALIGNED_ACCESS`: 假设系统支持快速未对齐访问

### 2. 代码重构

#### cpufeature.h头文件变化

**移除的声明**:
```c
DECLARE_PER_CPU(long, misaligned_access_speed);
```

**新增的条件编译**:
```c
#if defined(CONFIG_RISCV_MISALIGNED)
bool check_unaligned_access_emulated_all_cpus(void);
void unaligned_emulation_finish(void);
bool unaligned_ctl_available(void);
DECLARE_PER_CPU(long, misaligned_access_speed);
#endif

#if defined(CONFIG_RISCV_PROBE_UNALIGNED_ACCESS)
DECLARE_STATIC_KEY_FALSE(fast_unaligned_access_speed_key);

static __always_inline bool has_fast_unaligned_accesses(void)
{
    return static_branch_likely(&fast_unaligned_access_speed_key);
}
#else
static __always_inline bool has_fast_unaligned_accesses(void)
{
    if (IS_ENABLED(CONFIG_HAVE_EFFICIENT_UNALIGNED_ACCESS))
        return true;
    else
        return false;
}
#endif
```

#### 新文件: unaligned_access_speed.c

这个新文件包含了从`cpufeature.c`移动过来的所有未对齐访问检测相关代码：

**主要函数**:
1. `check_unaligned_access()` - 单CPU未对齐访问性能测试
2. `check_unaligned_access_speed_all_cpus()` - 所有CPU的性能测试
3. `riscv_online_cpu()` / `riscv_offline_cpu()` - CPU热插拔回调
4. `set_unaligned_access_static_branches()` - 设置静态分支

### 3. 编译系统变化

**Makefile修改**:
```makefile
# 移除
obj-y += copy-unaligned.o

# 新增
obj-$(CONFIG_RISCV_MISALIGNED) += unaligned_access_speed.o
obj-$(CONFIG_RISCV_PROBE_UNALIGNED_ACCESS) += copy-unaligned.o
```

### 4. hwprobe系统调用更新

**新增条件编译的hwprobe_misaligned函数**:
```c
#if defined(CONFIG_RISCV_PROBE_UNALIGNED_ACCESS)
static u64 hwprobe_misaligned(const struct cpumask *cpus)
{
    // 原有的运行时检测逻辑
}
#else
static u64 hwprobe_misaligned(const struct cpumask *cpus)
{
    if (IS_ENABLED(CONFIG_RISCV_EFFICIENT_UNALIGNED_ACCESS))
        return RISCV_HWPROBE_MISALIGNED_FAST;

    if (IS_ENABLED(CONFIG_RISCV_EMULATED_UNALIGNED_ACCESS) && unaligned_ctl_available())
        return RISCV_HWPROBE_MISALIGNED_EMULATED;

    return RISCV_HWPROBE_MISALIGNED_SLOW;
}
#endif
```

## 技术原理分析

### 1. 编译时配置的优势

**性能优化**:
- 避免运行时探测的开销
- 允许编译器进行更好的优化
- 减少内核启动时间

**确定性**:
- 在已知硬件平台上提供确定的行为
- 避免运行时探测可能的不准确性

### 2. 静态分支优化

使用Linux内核的静态分支机制(`static_branch_likely`):
```c
static __always_inline bool has_fast_unaligned_accesses(void)
{
    return static_branch_likely(&fast_unaligned_access_speed_key);
}
```

**优势**:
- 零运行时开销的条件分支
- 基于运行时信息动态修改代码路径
- 提高热路径性能

### 3. 模块化设计

**代码分离**:
- 将探测代码移到独立文件`unaligned_access_speed.c`
- 通过Kconfig控制编译包含
- 保持接口一致性

## 相关提交分析

这个patch是一个系列修改的一部分：

1. **313130c62cf1**: "riscv: Only check online cpus for emulated accesses"
   - 修复了CPU状态检查的bug
   - 为本patch奠定了基础

2. **6e5ce7f2eae3**: "riscv: Decouple emulated unaligned accesses from access speed"
   - 解耦了模拟访问和访问速度的概念
   - 为配置选项重构做准备

3. **f413aae96cda**: 本patch，引入编译时配置

## 影响和意义

### 1. 性能影响

**正面影响**:
- 减少内核启动时间
- 消除运行时探测开销
- 允许更好的编译时优化

**潜在风险**:
- 错误配置可能导致性能下降或功能异常
- 失去运行时适应性

### 2. 可移植性

**非便携式选项**:
- `RISCV_SLOW_UNALIGNED_ACCESS`和`RISCV_EFFICIENT_UNALIGNED_ACCESS`标记为`depends on NONPORTABLE`
- 明确警告用户这些选项的限制

### 3. 向后兼容性

**保持兼容**:
- 默认仍使用运行时探测(`RISCV_PROBE_UNALIGNED_ACCESS`)
- hwprobe系统调用接口保持不变
- 现有用户空间程序无需修改

## 总结

这个patch是RISC-V架构未对齐访问处理的重要改进，通过引入编译时配置选项，为不同使用场景提供了灵活性：

1. **运行时探测** - 适用于通用发行版，保持最大兼容性
2. **编译时配置** - 适用于特定硬件平台，优化性能
3. **模拟支持** - 确保在不支持硬件上的功能正确性

这种设计平衡了性能、兼容性和灵活性的需求，是内核配置系统设计的良好实践。