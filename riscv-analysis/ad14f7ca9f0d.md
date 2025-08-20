# Patch分析报告: ad14f7ca9f0d

## 1. 基本信息

**Commit ID**: ad14f7ca9f0d9fdf73d1fd61aaf8248d46ffc849  
**作者**: Vladimir Isaev <vladimir.isaev@syntacore.com>  
**日期**: Wed Mar 13 10:35:46 2024 +0300  
**标题**: riscv: hwprobe: do not produce frtace relocation  

## 2. 问题描述

### 2.1 核心问题

这个patch解决了RISC-V架构中hwprobe vDSO函数产生ftrace重定位的问题，该重定位会导致Android链接器崩溃。

### 2.2 问题表现

在启用`CONFIG_DYNAMIC_FTRACE`时，hwprobe vDSO函数会产生`R_RISCV_RELATIVE`类型的重定位，这会导致：
- Android链接器崩溃
- vDSO函数无法正常工作
- 系统稳定性问题

### 2.3 问题根源

问题源于`CONFIG_DYNAMIC_FTRACE`配置选项，它会在函数中插入ftrace调用点，从而产生不必要的重定位信息。在vDSO（Virtual Dynamic Shared Object）环境中，这种重定位是有害的。

## 3. 修改内容详细分析

### 3.1 修改的文件

**文件**: `arch/riscv/kernel/vdso/Makefile`

**修改内容**:
```makefile
# Disable -pg to prevent insert call site
CFLAGS_REMOVE_vgettimeofday.o = $(CC_FLAGS_FTRACE) $(CC_FLAGS_SCS)
+CFLAGS_REMOVE_hwprobe.o = $(CC_FLAGS_FTRACE) $(CC_FLAGS_SCS)
```

### 3.2 修改原理

1. **CFLAGS_REMOVE机制**: 使用Makefile的`CFLAGS_REMOVE_`前缀来移除特定文件的编译标志
2. **CC_FLAGS_FTRACE**: 移除ftrace相关的编译标志（如`-pg`），防止插入ftrace调用点
3. **CC_FLAGS_SCS**: 移除Shadow Call Stack相关标志，虽然RISC-V不支持SCS，但保持一致性

### 3.3 技术细节

#### 3.3.1 修改前的问题

```
readelf -rW arch/riscv/kernel/vdso/vdso.so:

Relocation section '.rela.dyn' at offset 0xd00 contains 1 entry:
    Offset             Info             Type
0000000000000d20  0000000000000003 R_RISCV_RELATIVE

objdump:
0000000000000c86 <__vdso_riscv_hwprobe@@LINUX_4.15>:
 c86:   0001                    nop
 c88:   0001                    nop
 c8a:   0001                    nop
 c8c:   0001                    nop
 c8e:   e211                    bnez    a2,c92 <__vdso_riscv_hwprobe...
```

#### 3.3.2 修改后的效果

```
readelf -rW arch/riscv/kernel/vdso/vdso.so:

There are no relocations in this file.

objdump:
0000000000000c86 <__vdso_riscv_hwprobe@@LINUX_4.15>:
 c86:   e211                    bnez    a2,c8a <__vdso_riscv_hwprobe...
 c88:   c6b9                    beqz    a3,cd6 <__vdso_riscv_hwprobe...
 c8a:   e739                    bnez    a4,cd8 <__vdso_riscv_hwprobe...
 c8c:   ffffd797                auipc   a5,0xffffd
```

**关键改进**:
- 消除了重定位表项
- 移除了函数开头的nop指令（ftrace占位符）
- 代码更加紧凑和高效

## 4. 相关提交分析

### 4.1 修复的原始提交

**Fixes**: aa5af0aa90ba ("RISC-V: Add hwprobe vDSO function and data")

这个提交引入了hwprobe vDSO功能，包括：
- 添加了`__vdso_riscv_hwprobe`函数
- 实现了硬件探测的vDSO接口
- 但没有考虑ftrace的影响

### 4.2 类似问题的先例

**参考**: e05d57dcb8c7 ("riscv: Fixup __vdso_gettimeofday broke dynamic ftrace")

这个更早的提交解决了类似的问题：
- 同样是vDSO函数的ftrace重定位问题
- 使用了相同的解决方案：`CFLAGS_REMOVE_vgettimeofday.o = $(CC_FLAGS_FTRACE) $(CC_FLAGS_SCS)`
- 为当前patch提供了解决方案的模板

## 5. 技术背景

### 5.1 vDSO机制

vDSO（Virtual Dynamic Shared Object）是一种特殊的共享库：
- 由内核提供，映射到用户空间
- 允许某些系统调用在用户空间直接执行
- 避免了用户态到内核态的切换开销
- 提高了系统调用性能

### 5.2 ftrace机制

ftrace是Linux内核的函数跟踪框架：
- `CONFIG_DYNAMIC_FTRACE`启用动态函数跟踪
- 在函数入口插入`-pg`标志生成的调用点
- 运行时可以动态启用/禁用函数跟踪
- 在vDSO中不应该存在，因为vDSO运行在用户空间

### 5.3 重定位问题

重定位在vDSO中的问题：
- vDSO需要在不同的虚拟地址加载
- 重定位信息增加了加载复杂性
- Android链接器对某些重定位类型处理不当
- 可能导致运行时崩溃

## 6. 影响分析

### 6.1 正面影响

1. **修复Android兼容性**: 解决了Android系统上的崩溃问题
2. **提升性能**: 移除了不必要的nop指令，代码更紧凑
3. **消除重定位**: 简化了vDSO的加载过程
4. **保持一致性**: 与vgettimeofday的处理方式保持一致

### 6.2 潜在风险

1. **调试困难**: 禁用ftrace后，hwprobe函数无法被ftrace跟踪
2. **性能分析限制**: 无法使用ftrace工具分析hwprobe性能

### 6.3 适用范围

- 影响所有使用hwprobe vDSO的RISC-V系统
- 特别重要对于Android和其他对重定位敏感的环境
- 对标准Linux发行版也有积极影响

## 7. 代码审查

### 7.1 审查者

- **Reviewed-by**: Alexandre Ghiti <alexghiti@rivosinc.com>
- **Reviewed-by**: Guo Ren <guoren@kernel.org>

### 7.2 审查质量

两位审查者都是RISC-V领域的专家：
- Alexandre Ghiti: RISC-V内存管理专家
- Guo Ren: RISC-V架构维护者，曾修复类似问题

## 8. 总结

这个patch是一个重要的修复，解决了RISC-V hwprobe vDSO函数的ftrace重定位问题。修改简单但有效，通过在Makefile中添加一行配置，禁用了hwprobe.o的ftrace和SCS标志。这个修复：

1. **解决了实际问题**: 修复了Android链接器崩溃
2. **方案成熟**: 基于已验证的解决方案（vgettimeofday的修复）
3. **影响最小**: 只影响编译标志，不改变代码逻辑
4. **向后兼容**: 不影响现有功能

这个patch展示了内核开发中如何处理工具链特性与特殊运行环境（如vDSO）之间的冲突，是一个典型的工程实践案例。