# RISC-V模块重定位越界访问修复分析

## Commit信息
- **Commit ID**: 0b4cce68efb93e31a8e51795d696df6e379cb41c
- **作者**: Samuel Holland <samuel.holland@sifive.com>
- **日期**: Wed Apr 9 10:14:49 2025 -0700
- **标题**: riscv: module: Fix out-of-bounds relocation access

## 问题描述

当前代码允许`rel[j]`访问重定位段末尾之外的一个元素，存在越界访问的风险。这个问题是在优化ELF重定位函数时引入的。

## 修改内容

### 核心修改

在`arch/riscv/kernel/module.c`文件的`apply_relocate_add`函数中：

```c
// 修改前
if (j > sechdrs[relsec].sh_size / sizeof(*rel))
    j = 0;

// 修改后  
if (j == num_relocations)
    j = 0;
```

### 修改位置
- **文件**: `arch/riscv/kernel/module.c`
- **函数**: `apply_relocate_add()`
- **行号**: 863行

## 技术原理分析

### 1. 重定位处理流程

在RISC-V架构中，处理`R_RISCV_PCREL_LO12_I`和`R_RISCV_PCREL_LO12_S`类型的重定位时，需要找到对应的HI20重定位条目：

```c
if (type == R_RISCV_PCREL_LO12_I || type == R_RISCV_PCREL_LO12_S) {
    unsigned int j = j_idx;
    bool found = false;
    
    do {
        // 查找对应的HI20重定位条目
        unsigned long hi20_loc = sechdrs[sechdrs[relsec].sh_info].sh_addr + rel[j].r_offset;
        u32 hi20_type = ELF_RISCV_R_TYPE(rel[j].r_info);
        
        if (hi20_loc == sym->st_value && 
            (hi20_type == R_RISCV_PCREL_HI20 || hi20_type == R_RISCV_GOT_HI20)) {
            // 找到匹配的HI20条目，计算lo12值
            // ...
            found = true;
            break;
        }
        
        j++;
        if (j == num_relocations)  // 修复后的边界检查
            j = 0;
            
    } while (j_idx != j);
}
```

### 2. 边界检查问题

#### 原始问题
```c
if (j > sechdrs[relsec].sh_size / sizeof(*rel))
```

这个条件允许`j`等于`sechdrs[relsec].sh_size / sizeof(*rel)`，即等于重定位条目的总数。由于数组索引从0开始，这会导致访问`rel[num_relocations]`，超出了有效范围`[0, num_relocations-1]`。

#### 修复方案
```c
if (j == num_relocations)
```

当`j`等于重定位条目总数时立即重置为0，确保始终在有效范围内访问数组。

### 3. 变量定义对比

```c
unsigned int num_relocations = sechdrs[relsec].sh_size / sizeof(*rel);
```

- `num_relocations`: 重定位条目的总数
- `sechdrs[relsec].sh_size / sizeof(*rel)`: 与`num_relocations`等价的表达式

修复使用了更简洁且语义更清晰的`num_relocations`变量。

## 相关提交分析

### 引入问题的提交
- **Commit ID**: 080c4324fa5e81ff3780206a138223abfb57a68e
- **作者**: Maxim Kochetkov <fido_max@inbox.ru>
- **日期**: Thu Dec 14 09:39:06 2023 +0300
- **标题**: riscv: optimize ELF relocation function in riscv

#### 优化目标
该提交旨在优化RISC-V ELF重定位函数的性能：
- **问题**: 安装包含多个符号表项的3MB+驱动需要180+秒
- **优化**: 通过修改第二个循环的起始位置，将安装时间缩短到2秒
- **方法**: 引入`j_idx`变量记录上次循环结束位置，避免重复搜索

#### 优化原理
原始代码每次都从头开始搜索HI20重定位条目：
```c
// 优化前
for (j = 0; j < sechdrs[relsec].sh_size / sizeof(*rel); j++) {
    // 搜索逻辑
}
```

优化后使用循环搜索，从上次结束位置继续：
```c
// 优化后
unsigned int j = j_idx;  // 从上次结束位置开始
do {
    // 搜索逻辑
    j++;
    if (j > sechdrs[relsec].sh_size / sizeof(*rel))  // 边界检查有误
        j = 0;
} while (j_idx != j);
j_idx = j;  // 记录结束位置
```

但在边界检查时引入了越界访问的bug。

## 安全影响

### 1. 内存安全风险
- **越界读取**: 可能读取重定位段之外的内存内容
- **数据损坏**: 在某些情况下可能导致不可预测的行为
- **系统稳定性**: 可能引起内核崩溃或模块加载失败

### 2. 影响范围
- **架构**: 仅影响RISC-V架构
- **场景**: 加载包含`R_RISCV_PCREL_LO12_I`或`R_RISCV_PCREL_LO12_S`重定位类型的内核模块
- **触发条件**: 当搜索循环到达重定位段末尾时

## 修复验证

### 1. 边界检查正确性
```c
// 有效索引范围: [0, num_relocations-1]
// 修复前: j 可能等于 num_relocations (越界)
// 修复后: j 在等于 num_relocations 时立即重置为 0
```

### 2. 功能等价性
- 修复保持了原有的循环搜索逻辑
- 性能优化效果不受影响
- 仅修复了边界检查的安全问题

## 总结

这是一个典型的性能优化引入安全问题的案例。虽然优化显著提升了模块加载性能（从180秒降到2秒），但在边界检查实现上存在细微错误，可能导致越界内存访问。

修复方案简洁有效：
1. 使用更清晰的变量名`num_relocations`
2. 修正边界检查逻辑，确保数组访问始终在有效范围内
3. 保持原有优化的性能收益

这个修复强调了在进行性能优化时，必须仔细验证边界条件和内存访问的安全性。