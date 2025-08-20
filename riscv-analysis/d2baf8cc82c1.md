# Patch Analysis: d2baf8cc82c1

## Commit Information
- **Commit ID**: d2baf8cc82c17459fca019a12348efcf86bfec29
- **Author**: Ard Biesheuvel <ardb@kernel.org>
- **Date**: Tue Jan 16 14:52:27 2024 +0100
- **Subject**: riscv/efistub: Tighten ELF relocation check

## 修改内容概述

这个patch修改了RISC-V架构下EFI stub的Makefile，加强了ELF重定位检查。具体修改是在`drivers/firmware/efi/libstub/Makefile`文件中，将RISC-V的重定位检查表达式从单一的`R_RISCV_HI20`扩展为更全面的检查模式。

### 修改前后对比

**修改前**:
```makefile
STUBCOPY_RELOC-$(CONFIG_RISCV) := R_RISCV_HI20
```

**修改后**:
```makefile
STUBCOPY_RELOC-$(CONFIG_RISCV) := -E R_RISCV_HI20\|R_RISCV_$(BITS)\|R_RISCV_RELAX
```

## 技术原理分析

### 1. EFI Stub的作用

EFI stub是Linux内核的一个组件，它允许内核作为EFI应用程序直接从UEFI固件启动，而无需传统的bootloader。EFI stub必须是位置无关的代码，因为它在运行时的加载地址是不确定的。

### 2. 重定位检查的必要性

EFI stub的Makefile包含逻辑来确保构成stub的目标文件不包含需要运行时修复的重定位（通常是为了适应可执行文件的运行时加载地址）。这些检查通过以下命令实现：

```bash
if $(OBJDUMP) -r $@ | grep $(STUBCOPY_RELOC-y); then \
    echo "$@: absolute symbol references not allowed in the EFI stub" >&2; \
    /bin/false; \
fi;
```

### 3. RISC-V特定的重定位类型

#### R_RISCV_HI20
- 这是RISC-V架构中的高20位重定位类型
- 用于加载32位常量的高20位到寄存器
- 通常与R_RISCV_LO12配对使用

#### R_RISCV_$(BITS)
- 这是一个动态变量，根据架构位数（32或64）展开
- 对于64位RISC-V，展开为R_RISCV_64
- 对于32位RISC-V，展开为R_RISCV_32
- 这些是绝对地址重定位，在EFI stub中是不允许的

#### R_RISCV_RELAX
- 这是RISC-V特有的链接时优化重定位类型
- 允许链接器在链接时进行指令序列优化
- 可能会改变代码的布局和地址计算方式

### 4. GP（Global Pointer）相关问题

如commit消息所述，RISC-V还要避免基于GP的重定位，因为它们要求在启动代码中为GP分配正确的基址，而这在EFI stub中没有实现。GP是RISC-V架构中的一个特殊寄存器，用于优化全局变量的访问。

## 相关提交分析

### 前置提交: afb2a4fb8455

在这个patch之前，有一个相关的提交`afb2a4fb8455`（"riscv/efistub: Ensure GP-relative addressing is not used"），该提交：

1. **问题背景**: RISC-V efistub的cflags缺少`-mno-relax`，存在编译器使用GP相对寻址的风险
2. **具体问题**: 在binutils-2.41和kernel 6.1中，`_edata`符号发生了这种情况，导致`handle_kernel_image`中的`kernel_size`无效，重定位失败
3. **解决方案**: 在RISC-V的编译标志中添加`-mno-relax`

```makefile
# 修改前
cflags-$(CONFIG_RISCV) += -fpic -DNO_ALTERNATIVE
# 修改后  
cflags-$(CONFIG_RISCV) += -fpic -DNO_ALTERNATIVE -mno-relax
```

### 问题的完整解决方案

这两个提交形成了一个完整的解决方案：

1. **afb2a4fb8455**: 在编译时通过`-mno-relax`防止生成relaxation重定位
2. **d2baf8cc82c1**: 在链接检查时确保检测到任何遗漏的problematic重定位

## 修改的技术细节

### grep表达式的变化

修改后的表达式使用了扩展正则表达式（`-E`标志）和管道符（`|`）来匹配多种重定位类型：

```bash
# 修改前：只检查R_RISCV_HI20
grep R_RISCV_HI20

# 修改后：检查多种重定位类型
grep -E "R_RISCV_HI20|R_RISCV_$(BITS)|R_RISCV_RELAX"
```

### 动态位数处理

`R_RISCV_$(BITS)`的使用允许Makefile根据目标架构自动选择正确的重定位类型：
- 在64位RISC-V上：检查`R_RISCV_64`
- 在32位RISC-V上：检查`R_RISCV_32`

## 影响和意义

### 1. 提高了构建时检查的完整性
- 原来只检查`R_RISCV_HI20`一种重定位类型
- 现在检查包括绝对地址重定位和relaxation重定位在内的多种类型

### 2. 防止运行时错误
- 在构建时就能发现problematic重定位
- 避免EFI stub在运行时因为无效重定位而失败

### 3. 架构特定的优化
- 考虑了RISC-V架构的特殊性（GP寄存器、relaxation等）
- 为不同位数的RISC-V提供了统一的解决方案

## 相关邮件链接

该patch引用了LKML邮件：https://lkml.kernel.org/r/42c63cb9-87d0-49db-9af8-95771b186684%40siemens.com

这个邮件链接表明这个修改是响应社区报告的具体问题，很可能是Siemens的工程师发现并报告的问题。

## 总结

这个patch是RISC-V EFI支持完善过程中的重要一步，它与前一个commit（afb2a4fb8455）一起，形成了对RISC-V EFI stub重定位问题的完整解决方案。通过在编译时禁用relaxation和在链接时加强检查，确保了EFI stub的正确性和可靠性。这种双重保护机制体现了内核开发中"defense in depth"的思想，即在多个层面设置保护措施来防止问题的发生。