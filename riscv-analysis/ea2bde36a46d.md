# RISC-V CONFIG_RELOCATABLE riscv32支持分析

## 1. Commit基本信息

**Commit ID:** ea2bde36a46d5724c1b44d80cc9fafbd73c2ecf9  
**作者:** Samuel Holland <samuel.holland@sifive.com>  
**提交日期:** Sat Oct 26 10:13:57 2024 -0700  
**标题:** riscv: Support CONFIG_RELOCATABLE on riscv32  
**邮件列表链接:** https://lore.kernel.org/r/20241026171441.3047904-6-samuel.holland@sifive.com  
**维护者:** Palmer Dabbelt <palmer@rivosinc.com>  

## 2. 修改内容详细分析

### 2.1 修改的文件

1. **arch/riscv/Kconfig** - 配置选项修改
2. **arch/riscv/mm/init.c** - 内核重定位代码修改

### 2.2 具体修改内容

#### Kconfig修改
```diff
 config RELOCATABLE
        bool "Build a relocatable kernel"
-       depends on 64BIT && !XIP_KERNEL
+       depends on !XIP_KERNEL
        select MODULE_SECTIONS if MODULES
        help
           This builds a kernel as a Position Independent Executable (PIE),
```

**修改说明:**
- 移除了对64位架构的依赖限制
- 现在32位RISC-V架构也可以启用CONFIG_RELOCATABLE选项
- 保留了对XIP_KERNEL的排斥条件

#### mm/init.c修改

**1. 头文件包含修改**
```diff
 #include <linux/execmem.h>
 
 #include <asm/fixmap.h>
 #include <asm/io.h>
 #include <asm/kasan.h>
+#include <asm/module.h>
 #include <asm/numa.h>
 #include <asm/pgtable.h>
 #include <asm/sections.h>
```

**2. ELF类型定义修改**
```diff
 static void __init relocate_kernel(void)
 {
-       Elf64_Rela *rela = (Elf64_Rela *)&__rela_dyn_start;
+       Elf_Rela *rela = (Elf_Rela *)&__rela_dyn_start;
        /*
         * This holds the offset between the linked virtual address and the
         * relocated virtual address.
         */
        uintptr_t va_kernel_link_pa_offset = KERNEL_LINK_ADDR - kernel_map.phys_addr;
 
-       for ( ; rela < (Elf64_Rela *)&__rela_dyn_end; rela++) {
-               Elf64_Addr addr = (rela->r_offset - va_kernel_link_pa_offset);
-               Elf64_Addr relocated_addr = rela->r_addend;
+       for ( ; rela < (Elf_Rela *)&__rela_dyn_end; rela++) {
+               Elf_Addr addr = (rela->r_offset - va_kernel_link_pa_offset);
+               Elf_Addr relocated_addr = rela->r_addend;
 
                if (rela->r_info != R_RISCV_RELATIVE)
                        continue;
 
-               *(Elf64_Addr *)addr = relocated_addr;
+               *(Elf_Addr *)addr = relocated_addr;
        }
```

**3. 页表边界检查修改**
```diff
-       BUG_ON(PUD_SIZE - (kernel_map.virt_addr & (PUD_SIZE - 1)) < kernel_map.size);
+       if (IS_ENABLED(CONFIG_64BIT))
+               BUG_ON(PUD_SIZE - (kernel_map.virt_addr & (PUD_SIZE - 1)) < kernel_map.size);
        relocate_kernel();
```

## 3. 代码修改原理分析

### 3.1 ELF类型抽象化

#### 问题背景
原始代码硬编码使用64位ELF类型（`Elf64_Rela`, `Elf64_Addr`），这限制了代码只能在64位架构上工作。

#### 解决方案
使用架构无关的ELF类型定义：
- `Elf_Rela` - 根据架构自动选择`Elf32_Rela`或`Elf64_Rela`
- `Elf_Addr` - 根据架构自动选择`Elf32_Addr`或`Elf64_Addr`

#### 类型定义机制
在`include/asm-generic/module.h`中定义：
```c
#ifdef CONFIG_64BIT
#define Elf_Rela    Elf64_Rela
#define Elf_Addr    Elf64_Addr
#else
#define Elf_Rela    Elf32_Rela
#define Elf_Addr    Elf32_Addr
#endif
```

### 3.2 内核重定位机制

#### 重定位的必要性
1. **位置无关执行**: 内核可以在任意物理地址加载和运行
2. **KASLR支持**: 为内核地址空间布局随机化提供基础
3. **NOMMU支持**: 在没有MMU的系统上提供灵活的内存布局

#### 重定位过程
1. **解析重定位表**: 遍历`__rela_dyn_start`到`__rela_dyn_end`之间的重定位条目
2. **处理R_RISCV_RELATIVE类型**: 这是相对重定位，需要根据加载地址调整
3. **更新内存内容**: 将计算出的新地址写入目标位置

#### 32位与64位的差异
- **地址宽度**: 32位使用32位地址，64位使用64位地址
- **重定位条目大小**: `Elf32_Rela`和`Elf64_Rela`结构体大小不同
- **页表结构**: 32位和64位的页表层级不同

### 3.3 页表边界检查优化

#### 原始问题
```c
BUG_ON(PUD_SIZE - (kernel_map.virt_addr & (PUD_SIZE - 1)) < kernel_map.size);
```
这个检查假设内核映射不能跨越PUD边界，但这个限制只适用于64位架构。

#### 32位架构的差异
- **Sv32页表**: 只有两级页表（PGD和PTE），没有PUD级别
- **早期映射**: 使用PGD条目直接映射，不存在跨越中间页表边界的问题
- **PUD_SIZE**: 在32位架构上可能未定义或定义不当

#### 解决方案
```c
if (IS_ENABLED(CONFIG_64BIT))
    BUG_ON(PUD_SIZE - (kernel_map.virt_addr & (PUD_SIZE - 1)) < kernel_map.size);
```
只在64位架构上执行这个检查。

## 4. 相关提交分析

### 4.1 Patch系列背景

这个commit是一个更大的patch系列的一部分，该系列旨在改进RISC-V的内核重定位支持：

1. **d073a571e68f**: "asm-generic: Always define Elf_Rel and Elf_Rela"
   - 确保ELF类型定义在所有架构上都可用
   - 为本patch提供了必要的类型定义基础

2. **51b766c79a3d**: "riscv: Support CONFIG_RELOCATABLE on NOMMU"
   - 在NOMMU系统上启用重定位支持
   - 重构了`relocate_kernel()`函数的调用位置

3. **2c0391b29b27**: "riscv: Allow NOMMU kernels to access all of RAM"
   - 允许NOMMU内核访问所有RAM
   - 为重定位功能提供了更灵活的内存布局

### 4.2 技术演进路径

1. **第一阶段**: 基础架构改进（通用ELF类型定义）
2. **第二阶段**: NOMMU支持（内存访问和重定位机制）
3. **第三阶段**: 32位支持（本patch，类型抽象化）

## 5. 技术影响分析

### 5.1 功能增强

1. **32位RISC-V支持**: 扩展了CONFIG_RELOCATABLE到32位架构
2. **NOMMU兼容性**: 特别适用于没有MMU的嵌入式系统
3. **代码统一**: 32位和64位使用相同的重定位代码路径

### 5.2 性能影响

1. **运行时开销**: 重定位过程只在启动时执行一次
2. **内存占用**: 重定位表占用少量额外空间
3. **启动时间**: 重定位处理增加微量启动时间

### 5.3 安全性考虑

1. **KASLR基础**: 为未来的32位KASLR支持提供基础
2. **地址泄露防护**: 使内核地址更难预测
3. **代码完整性**: 重定位过程确保代码正确性

## 6. 应用场景

### 6.1 主要用途

1. **嵌入式系统**: 32位RISC-V嵌入式设备
2. **NOMMU系统**: 没有内存管理单元的简单系统
3. **灵活部署**: 内核可以加载到不同的物理地址

### 6.2 限制条件

1. **XIP排斥**: 不能与XIP_KERNEL同时使用
2. **KASLR未支持**: 32位架构上KASLR尚未实现
3. **内存要求**: 需要足够的连续内存空间

## 7. 总结

这个patch通过以下关键技术实现了32位RISC-V的CONFIG_RELOCATABLE支持：

1. **类型抽象化**: 使用架构无关的ELF类型定义
2. **条件编译**: 针对不同架构采用不同的检查逻辑
3. **代码重用**: 最大化32位和64位代码的共享

该修改为32位RISC-V系统提供了更灵活的内核部署选项，特别适用于嵌入式和NOMMU环境，同时为未来的安全特性（如KASLR）奠定了基础。修改保持了向后兼容性，不影响现有的64位系统功能。