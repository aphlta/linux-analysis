# RISC-V MODULE_SECTIONS 优化 Patch 分析报告

## Commit 信息

- **Commit ID**: 2aff5f955bbae311ca4b66e1dbd934e8f346d1f1
- **作者**: Qingfang Deng <qingfang.deng@siflower.com.cn>
- **提交日期**: Sat May 11 09:57:25 2024 +0800
- **标题**: riscv: do not select MODULE_SECTIONS by default
- **审核者**: Charlie Jenkins <charlie@rivosinc.com>
- **链接**: https://lore.kernel.org/r/20240511015725.1162-1-dqfext@gmail.com
- **签署者**: Palmer Dabbelt <palmer@rivosinc.com>

## 1. Patch 修改内容详细分析

### 1.1 修改概述

这个patch对RISC-V架构的内核配置进行了优化，主要修改了MODULE_SECTIONS配置选项的选择逻辑。

### 1.2 具体修改内容

**修改文件**: `arch/riscv/Kconfig`

**修改前**:
```kconfig
config RISCV
    # ... 其他配置 ...
    select MODULES_USE_ELF_RELA if MODULES
    select MODULE_SECTIONS if MODULES
    # ... 其他配置 ...
```

**修改后**:
```kconfig
config RISCV
    # ... 其他配置 ...
    select MODULES_USE_ELF_RELA if MODULES
    # 移除了 select MODULE_SECTIONS if MODULES
    # ... 其他配置 ...

config RELOCATABLE
    bool "Build a relocatable kernel"
    depends on MMU && 64BIT && !XIP_KERNEL
    select MODULE_SECTIONS if MODULES  # 新增
    help
      This builds a kernel as a Position Independent Executable (PIE),
      which retains all relocation metadata required to relocate the
      kernel binary to a different virtual address than it was linked at.
```

## 2. 技术原理分析

### 2.1 MODULE_SECTIONS 配置选项的作用

MODULE_SECTIONS是Linux内核中的一个配置选项，用于控制内核模块的节(section)处理机制：

1. **PLT/GOT支持**: 启用时，内核会为模块创建PLT(Procedure Linkage Table)和GOT(Global Offset Table)
2. **重定位处理**: 支持复杂的重定位类型，如R_RISCV_GOT_HI20和R_RISCV_CALL_PLT
3. **内存开销**: 会增加额外的内存开销来存储这些表

### 2.2 RISC-V模块编译模型的演进

#### 历史背景 - commit aad15bc85c18的影响

在commit aad15bc85c18 ("riscv: Change code model of module to medany to improve data accessing")中，RISC-V架构做了重要改变：

**修改前** (使用-fPIC):
```makefile
KBUILD_AFLAGS_MODULE += -fPIC
KBUILD_CFLAGS_MODULE += -fPIC
```

**修改后** (使用medany代码模型):
```makefile
ifeq ($(CONFIG_64BIT)$(CONFIG_CMODEL_MEDLOW),yy)
KBUILD_CFLAGS_MODULE += -mcmodel=medany
endif
```

#### 代码模型对比分析

1. **-fPIC模型**:
   - 生成位置无关代码
   - 依赖GOT/PLT进行符号访问
   - 产生R_RISCV_GOT_HI20和R_RISCV_CALL_PLT重定位
   - 需要MODULE_SECTIONS支持

2. **medany模型**:
   - RISC-V特有的代码模型
   - 使用PC相对寻址
   - 不依赖GOT/PLT
   - 不产生GOT/PLT相关重定位
   - 不需要MODULE_SECTIONS支持

### 2.3 重定位类型分析

#### R_RISCV_GOT_HI20重定位

在`arch/riscv/kernel/module.c`中的处理:
```c
static int apply_r_riscv_got_hi20_rela(struct module *me, void *location,
                                       Elf_Addr v)
{
    ptrdiff_t offset = (void *)v - location;
    
    /* Always emit the got entry */
    if (IS_ENABLED(CONFIG_MODULE_SECTIONS)) {
        offset = (void *)module_emit_got_entry(me, v) - location;
    } else {
        pr_err(
          "%s: can not generate the GOT entry for symbol = %016llx from PC = %p\n",
          me->name, (long long)v, location);
        return -EINVAL;
    }
    
    return riscv_insn_rmw(location, 0xfff, (offset + 0x800) & 0xfffff000);
}
```

#### R_RISCV_CALL_PLT重定位

```c
static int apply_r_riscv_call_plt_rela(struct module *me, void *location,
                                       Elf_Addr v)
{
    ptrdiff_t offset = (void *)v - location;
    u32 hi20, lo12;
    
    if (!riscv_insn_valid_32bit_offset(offset)) {
        /* Only emit the plt entry if offset over 32-bit range */
        if (IS_ENABLED(CONFIG_MODULE_SECTIONS)) {
            offset = (void *)module_emit_plt_entry(me, v) - location;
        } else {
            pr_err(
              "%s: target %016llx can not be addressed by the 32-bit offset from PC = %p\n",
              me->name, (long long)v, location);
            return -EINVAL;
        }
    }
    
    hi20 = (offset + 0x800) & 0xfffff000;
    lo12 = (offset - hi20) & 0xfff;
    riscv_insn_rmw(location, 0xfff, hi20);
    return riscv_insn_rmw(location + 4, 0xfffff, lo12 << 20);
}
```

### 2.4 RELOCATABLE配置的特殊需求

当启用CONFIG_RELOCATABLE时，内核被构建为位置无关可执行文件(PIE)：

1. **编译选项**: 模块使用-fPIE编译
2. **重定位需求**: 重新引入GOT/PLT相关重定位
3. **MODULE_SECTIONS需求**: 必须启用MODULE_SECTIONS来处理这些重定位

## 3. 修改原理和动机

### 3.1 问题分析

**修改前的问题**:
1. **不必要的开销**: 默认情况下所有RISC-V模块都启用MODULE_SECTIONS
2. **内存浪费**: medany模型下不需要PLT/GOT，但仍然分配相关内存
3. **性能影响**: 额外的间接跳转和内存访问

### 3.2 解决方案

**有条件选择MODULE_SECTIONS**:
- 默认情况下不选择MODULE_SECTIONS
- 仅在RELOCATABLE=y时选择MODULE_SECTIONS
- 保持向后兼容性

### 3.3 技术优势

1. **内存优化**: 减少不必要的PLT/GOT内存分配
2. **性能提升**: 避免间接跳转开销
3. **代码简化**: 减少重定位处理复杂度
4. **灵活性**: 根据实际需求选择功能

## 4. 相关提交分析

### 4.1 前置提交 - aad15bc85c18

**标题**: "riscv: Change code model of module to medany to improve data accessing"
**作者**: Vincent Chen <vincent.chen@sifive.com>
**日期**: Fri Feb 21 10:47:55 2020 +0800

**关键改变**:
- 将模块编译从-fPIC改为-mcmodel=medany
- 提升数据访问性能
- 为当前patch奠定基础

### 4.2 影响分析

这个改变使得:
1. 模块不再生成GOT/PLT相关重定位
2. MODULE_SECTIONS变得不必要
3. 为优化创造了条件

## 5. 代码影响范围

### 5.1 编译系统影响

1. **默认配置**: 大多数RISC-V系统不再默认启用MODULE_SECTIONS
2. **RELOCATABLE内核**: 自动启用MODULE_SECTIONS
3. **兼容性**: 不影响现有功能

### 5.2 运行时影响

1. **内存使用**: 减少模块内存占用
2. **加载性能**: 简化模块加载过程
3. **运行性能**: 减少间接跳转

### 5.3 开发者影响

1. **透明性**: 对大多数开发者透明
2. **调试**: 简化模块调试过程
3. **维护**: 减少维护复杂度

## 6. 测试和验证

### 6.1 功能验证

需要验证以下场景:
1. **普通模块加载**: 确保medany模型下模块正常工作
2. **RELOCATABLE内核**: 确保PIE模式下模块正常工作
3. **重定位处理**: 验证各种重定位类型正确处理

### 6.2 性能测试

1. **内存使用**: 对比MODULE_SECTIONS开启/关闭的内存差异
2. **加载时间**: 测量模块加载性能
3. **运行性能**: 测量模块执行性能

## 7. 潜在风险和注意事项

### 7.1 兼容性风险

1. **工具链依赖**: 需要支持medany模型的工具链
2. **第三方模块**: 可能影响使用特殊编译选项的第三方模块

### 7.2 调试影响

1. **符号解析**: 可能影响某些调试工具的符号解析
2. **性能分析**: 需要更新性能分析工具

## 8. 总结

### 8.1 主要贡献

1. **性能优化**: 减少不必要的内存和性能开销
2. **架构清理**: 简化RISC-V模块处理逻辑
3. **智能选择**: 根据实际需求选择功能
4. **向前兼容**: 为未来优化奠定基础

### 8.2 技术意义

这个patch体现了Linux内核在RISC-V架构上的持续优化：

1. **架构特化**: 充分利用RISC-V架构特性
2. **性能导向**: 以性能为目标的设计决策
3. **资源优化**: 合理使用系统资源
4. **工程实践**: 良好的软件工程实践

### 8.3 未来展望

1. **进一步优化**: 可能的进一步模块系统优化
2. **工具链改进**: 推动工具链的相应改进
3. **生态发展**: 促进RISC-V生态系统发展

这个patch虽然修改简单，但背后体现了对RISC-V架构深入理解和精心优化，是一个高质量的性能优化提交。它不仅解决了当前的资源浪费问题，还为未来的进一步优化奠定了基础。