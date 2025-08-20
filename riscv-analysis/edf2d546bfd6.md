# RISC-V Patch Analysis: edf2d546bfd6

## Commit 信息

- **Commit ID**: edf2d546bfd6f5c4d143715cef1b1e7ce5718c4e
- **标题**: riscv: patch: Flush the icache right after patching to avoid illegal insns
- **作者**: Alexandre Ghiti <alexghiti@rivosinc.com>
- **提交日期**: 2024年6月26日
- **修复的问题**: Fixes: 6ca445d8af0e ("riscv: Fix early ftrace nop patching")

## 问题背景

### 原始问题

在RISC-V架构中，代码修补(code patching)机制存在一个严重的竞态条件问题：

1. **延迟的icache刷新**: 原来的实现在修补函数后延迟刷新指令缓存(icache)
2. **竞态条件**: 可能在icache刷新之前就调用了刚刚修补的函数
3. **非法指令异常**: CPU可能执行到部分修补的指令，导致非法指令陷阱

### 触发场景

- **早期ftrace修补**: 在系统启动早期，ftrace将编译器生成的2字节nop转换为4字节nop
- **多核环境**: 在多核系统中，某个核心可能在icache中有半修补的指令
- **硬件报告**: 在多个硬件平台上都出现了崩溃问题

## 修改内容详细分析

### 1. __patch_insn_set 函数修改

**位置**: `arch/riscv/kernel/patch.c:89-98`

```c
// 新增代码
/*
 * We could have just patched a function that is about to be
 * called so make sure we don't execute partially patched
 * instructions by flushing the icache as soon as possible.
 */
local_flush_icache_range((unsigned long)waddr,
                         (unsigned long)waddr + len);
```

**原理**:
- 在`memset(waddr, c, len)`之后立即刷新icache
- 确保修补的内存区域在CPU指令缓存中得到同步
- 使用`local_flush_icache_range()`进行本地CPU的icache刷新

### 2. __patch_insn_write 函数修改

**位置**: `arch/riscv/kernel/patch.c:135-144`

```c
// 新增代码
/*
 * We could have just patched a function that is about to be
 * called so make sure we don't execute partially patched
 * instructions by flushing the icache as soon as possible.
 */
local_flush_icache_range((unsigned long)waddr,
                         (unsigned long)waddr + len);
```

**原理**:
- 在`copy_to_kernel_nofault(waddr, insn, len)`之后立即刷新icache
- 确保复制的指令在指令缓存中是最新的
- 防止执行旧的缓存指令

### 3. patch_text_set_nosync 函数修改

**位置**: `arch/riscv/kernel/patch.c:205-208`

```c
// 删除的代码
-       if (!ret)
-               flush_icache_range((uintptr_t)tp, (uintptr_t)tp + len);
```

**原理**:
- 移除延迟的icache刷新
- 因为现在在`__patch_insn_set`中已经立即刷新了
- 避免重复刷新，提高效率

### 4. patch_text_nosync 函数修改

**位置**: `arch/riscv/kernel/patch.c:237-240`

```c
// 删除的代码
-       if (!ret)
-               flush_icache_range((uintptr_t) tp, (uintptr_t) tp + len);
```

**原理**:
- 同样移除延迟的icache刷新
- 依赖`__patch_insn_write`中的立即刷新
- 保持代码一致性

### 5. patch_text_cb 函数修改

**位置**: `arch/riscv/kernel/patch.c:253-263`

```c
// 修改前
} else {
    while (atomic_read(&patch->cpu_count) <= num_online_cpus())
        cpu_relax();
}

local_flush_icache_all();

// 修改后
} else {
    while (atomic_read(&patch->cpu_count) <= num_online_cpus())
        cpu_relax();

    local_flush_icache_all();
}
```

**原理**:
- 调整代码结构，将`local_flush_icache_all()`移到else分支内
- 确保只有等待的CPU执行icache刷新
- 保持多核同步的正确性

## 技术原理深入分析

### RISC-V指令缓存机制

1. **fence.i指令**: RISC-V使用`fence.i`指令刷新指令缓存
2. **本地刷新**: `local_flush_icache_range()`实际调用`local_flush_icache_all()`
3. **全局刷新**: `flush_icache_range()`会在所有CPU上执行刷新

### 代码修补流程

```
修补前流程:
1. 映射内存页面
2. 修改指令内容
3. 取消映射
4. 延迟刷新icache ← 问题所在

修补后流程:
1. 映射内存页面
2. 修改指令内容
3. 立即刷新icache ← 修复点
4. 取消映射
```

### 竞态条件分析

**问题场景**:
```
CPU A: 修补函数F
CPU B: 调用函数F (可能获取到部分修补的指令)
CPU A: 刷新icache
```

**修复后**:
```
CPU A: 修补函数F
CPU A: 立即刷新icache
CPU B: 调用函数F (获取到完整修补的指令)
```

## 性能影响分析

### 负面影响

1. **频繁刷新**: 每次修补都立即刷新icache，不再批量处理
2. **性能开销**: icache刷新是相对昂贵的操作
3. **延迟增加**: 修补操作的延迟会增加

### 正面影响

1. **系统稳定性**: 完全避免非法指令异常
2. **正确性保证**: 确保修补的原子性
3. **多核安全**: 在多核环境下更加安全

## 相关提交分析

### 修复的原始提交

- **Commit**: 6ca445d8af0e ("riscv: Fix early ftrace nop patching")
- **问题**: 早期ftrace修补时的icache刷新问题
- **解决方案**: 在ftrace_init_nop中添加本地icache刷新

### 更早的相关提交

- **Commit**: c97bf629963e ("riscv: Fix text patching when IPI are used")
- **背景**: 使用IPI进行文本修补时的问题

## 测试和验证

### 报告者

- **Conor Dooley**: 报告了多个硬件平台上的崩溃问题
- **测试验证**: 经过Conor Dooley和Björn Töpel的测试验证

### 审查者

- **Andy Chiu**: 代码审查
- **Palmer Dabbelt**: 维护者签名

## 总结

这个patch解决了RISC-V架构中一个关键的竞态条件问题，通过将icache刷新从延迟执行改为立即执行，确保了代码修补的原子性和正确性。虽然可能带来一定的性能开销，但这是为了系统稳定性必须付出的代价。

### 关键改进

1. **立即刷新**: 修补后立即刷新icache
2. **竞态消除**: 完全避免部分修补指令的执行
3. **多核安全**: 在多核环境下保证正确性
4. **向后兼容**: 不影响现有API接口

### 适用场景

- ftrace动态跟踪
- kprobes动态探测
- 热补丁(live patching)
- 任何需要运行时修改代码的场景