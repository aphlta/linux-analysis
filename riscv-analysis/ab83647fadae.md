# RISC-V qspinlock支持实现分析 - Commit ab83647fadae

## 基本信息

**Commit ID**: ab83647fadae2f1f723119dc066b39a461d6d288  
**作者**: Alexandre Ghiti <alexghiti@rivosinc.com>  
**提交者**: Palmer Dabbelt <palmer@rivosinc.com>  
**作者日期**: 2024年11月3日 15:51:53 +0100  
**提交日期**: 2024年11月11日 07:33:20 -0800  
**标题**: riscv: Add qspinlock support  

## Patch概述

这个patch为RISC-V架构添加了队列自旋锁(qspinlock)支持，引入了一个新的配置选项`CONFIG_COMBO_SPINLOCKS`，允许在运行时根据硬件扩展的可用性在qspinlock和ticket spinlock之间进行选择。这是一个重要的性能优化，特别是在多核系统中能够显著提升锁的性能。

## 详细修改内容

### 1. 文档更新

**文件**: `Documentation/features/locking/queued-spinlocks/arch-support.txt`

```diff
-    |       riscv: | TODO |
+    |       riscv: |  ok  |
```

- 将RISC-V架构的qspinlock支持状态从"TODO"更新为"ok"
- 标志着RISC-V正式支持队列自旋锁特性

### 2. Kconfig配置系统修改

**文件**: `arch/riscv/Kconfig`

#### 2.1 添加ARCH_WEAK_RELEASE_ACQUIRE支持

```diff
+       select ARCH_WEAK_RELEASE_ACQUIRE if ARCH_USE_QUEUED_SPINLOCKS
```

- 当使用队列自旋锁时启用弱内存序支持
- 这对于RISC-V的弱内存模型是必要的

#### 2.2 新增spinlock类型选择配置

```c
choice
       prompt "RISC-V spinlock type"
       default RISCV_COMBO_SPINLOCKS

config RISCV_TICKET_SPINLOCKS
       bool "Using ticket spinlock"

config RISCV_QUEUED_SPINLOCKS
       bool "Using queued spinlock"
       depends on SMP && MMU && NONPORTABLE
       select ARCH_USE_QUEUED_SPINLOCKS
       help
         The queued spinlock implementation requires the forward progress
         guarantee of cmpxchg()/xchg() atomic operations: CAS with Zabha or
         LR/SC with Ziccrse provide such guarantee.

config RISCV_COMBO_SPINLOCKS
       bool "Using combo spinlock"
       depends on SMP && MMU
       select ARCH_USE_QUEUED_SPINLOCKS
       help
         Embed both queued spinlock and ticket lock so that the spinlock
         implementation can be chosen at runtime.
endchoice
```

**配置选项分析**:

1. **RISCV_TICKET_SPINLOCKS**: 传统的ticket spinlock实现
2. **RISCV_QUEUED_SPINLOCKS**: 纯qspinlock实现，需要硬件扩展支持
3. **RISCV_COMBO_SPINLOCKS**: 组合实现，运行时选择（默认选项）

### 3. 构建系统修改

**文件**: `arch/riscv/include/asm/Kbuild`

```diff
-generic-y += spinlock.h
-generic-y += spinlock_types.h
+generic-y += qspinlock.h
+generic-y += qspinlock_types.h
+generic-y += ticket_spinlock.h
```

- 移除通用spinlock头文件的使用
- 添加qspinlock和ticket_spinlock的特定头文件支持

### 4. 核心spinlock实现

**文件**: `arch/riscv/include/asm/spinlock.h`

这是一个全新的文件，实现了RISC-V特定的spinlock逻辑：

#### 4.1 配置相关定义

```c
#ifdef CONFIG_QUEUED_SPINLOCKS
#define _Q_PENDING_LOOPS	(1 << 9)
#endif
```

- 定义qspinlock的pending循环次数
- 针对RISC-V架构进行了优化

#### 4.2 组合spinlock实现

```c
#ifdef CONFIG_RISCV_COMBO_SPINLOCKS

#define __no_arch_spinlock_redefine
#include <asm/ticket_spinlock.h>
#include <asm/qspinlock.h>
#include <asm/jump_label.h>

DECLARE_STATIC_KEY_TRUE(qspinlock_key);

#define SPINLOCK_BASE_DECLARE(op, type, type_lock)			\
static __always_inline type arch_spin_##op(type_lock lock)		\
{										\
	if (static_branch_unlikely(&qspinlock_key))			\
		return queued_spin_##op(lock);				\
	return ticket_spin_##op(lock);					\
}

SPINLOCK_BASE_DECLARE(lock, void, arch_spinlock_t *)
SPINLOCK_BASE_DECLARE(unlock, void, arch_spinlock_t *)
SPINLOCK_BASE_DECLARE(is_locked, int, arch_spinlock_t *)
SPINLOCK_BASE_DECLARE(is_contended, int, arch_spinlock_t *)
SPINLOCK_BASE_DECLARE(trylock, bool, arch_spinlock_t *)
SPINLOCK_BASE_DECLARE(value_unlocked, int, arch_spinlock_t)
```

**实现原理**:
- 使用静态分支(static branch)技术进行运行时选择
- `qspinlock_key`默认为true，表示优先使用qspinlock
- 通过`static_branch_unlikely`实现零开销的运行时切换
- 为所有spinlock操作生成包装函数

### 5. 运行时初始化

**文件**: `arch/riscv/kernel/setup.c`

#### 5.1 静态key定义

```c
#if defined(CONFIG_RISCV_COMBO_SPINLOCKS)
DEFINE_STATIC_KEY_TRUE(qspinlock_key);
EXPORT_SYMBOL(qspinlock_key);
#endif
```

#### 5.2 spinlock初始化函数

```c
static void __init riscv_spinlock_init(void)
{
	char *using_ext = NULL;

	if (IS_ENABLED(CONFIG_RISCV_TICKET_SPINLOCKS)) {
		pr_info("Ticket spinlock: enabled\n");
		return;
	}

	if (IS_ENABLED(CONFIG_RISCV_ISA_ZABHA) &&
	    IS_ENABLED(CONFIG_RISCV_ISA_ZACAS) &&
	    riscv_isa_extension_available(NULL, ZABHA) &&
	    riscv_isa_extension_available(NULL, ZACAS)) {
		using_ext = "using Zabha";
	} else if (riscv_isa_extension_available(NULL, ZICCRSE)) {
		using_ext = "using Ziccrse";
	}
#if defined(CONFIG_RISCV_COMBO_SPINLOCKS)
	else {
		static_branch_disable(&qspinlock_key);
		pr_info("Ticket spinlock: enabled\n");
		return;
	}
#endif

	if (!using_ext)
		pr_err("Queued spinlock without Zabha or Ziccrse");
	else
		pr_info("Queued spinlock %s: enabled\n", using_ext);
}
```

**初始化逻辑**:
1. 检查是否强制使用ticket spinlock
2. 检测硬件扩展支持：
   - 优先检查Zabha + Zacas扩展组合
   - 其次检查Ziccrse扩展
3. 根据硬件支持情况决定使用哪种spinlock
4. 在combo模式下，如果硬件不支持则回退到ticket spinlock

#### 5.3 初始化调用

```c
void __init setup_arch(char **cmdline_p)
{
	// ... 其他初始化代码 ...
	riscv_user_isa_enable();
	riscv_spinlock_init();
}
```

- 在系统架构初始化的最后阶段调用
- 确保ISA扩展检测已经完成

### 6. 通用头文件修改

#### 6.1 qspinlock.h修改

**文件**: `include/asm-generic/qspinlock.h`

```diff
+#ifndef __no_arch_spinlock_redefine
 /*
  * Remapping spinlock architecture specific functions to the corresponding
  * queued spinlock functions.
  */
 #define arch_spin_is_locked(l)		queued_spin_is_locked(l)
 #define arch_spin_is_contended(l)	queued_spin_is_contended(l)
 #define arch_spin_value_unlocked(l)	queued_spin_value_unlocked(l)
 #define arch_spin_lock(l)		queued_spin_lock(l)
 #define arch_spin_trylock(l)		queued_spin_trylock(l)
 #define arch_spin_unlock(l)		queued_spin_unlock(l)
+#endif
```

#### 6.2 ticket_spinlock.h修改

**文件**: `include/asm-generic/ticket_spinlock.h`

```diff
+#ifndef __no_arch_spinlock_redefine
 /*
  * Remapping spinlock architecture specific functions to the corresponding
  * ticket spinlock functions.
  */
 #define arch_spin_is_locked(l)		ticket_spin_is_locked(l)
 #define arch_spin_is_contended(l)	ticket_spin_is_contended(l)
 #define arch_spin_value_unlocked(l)	ticket_spin_value_unlocked(l)
 #define arch_spin_lock(l)		ticket_spin_lock(l)
 #define arch_spin_trylock(l)		ticket_spin_trylock(l)
 #define arch_spin_unlock(l)		ticket_spin_unlock(l)
+#endif
```

**修改目的**:
- 添加`__no_arch_spinlock_redefine`保护
- 允许架构特定代码重新定义spinlock函数
- 避免与RISC-V的组合实现冲突

## 技术原理分析

### 1. qspinlock vs ticket spinlock

#### 1.1 ticket spinlock特点

- **FIFO公平性**: 严格按照请求顺序获取锁
- **简单实现**: 基于fetch-and-add操作
- **缓存友好**: 在低竞争情况下性能良好
- **扩展性限制**: 在高竞争情况下性能下降明显

#### 1.2 qspinlock特点

- **更好的扩展性**: 在高竞争情况下性能更优
- **MCS锁算法**: 基于队列的锁实现
- **减少缓存抖动**: 等待者在本地变量上自旋
- **复杂实现**: 需要更复杂的原子操作支持

### 2. RISC-V硬件扩展要求

#### 2.1 Zabha扩展 (Atomic Byte and Halfword)

- 提供8位和16位的原子操作
- 包括原子比较交换操作
- 与Zacas配合使用效果更佳

#### 2.2 Zacas扩展 (Atomic Compare-and-Swap)

- 提供原子比较交换指令
- 支持32位、64位和128位操作
- 为qspinlock提供高效的原子操作基础

#### 2.3 Ziccrse扩展 (Load-Reserved/Store-Conditional)

- 提供LR/SC指令序列
- 保证前向进展(forward progress)
- 是qspinlock的最低硬件要求

### 3. 静态分支技术

#### 3.1 实现原理

```c
static_branch_unlikely(&qspinlock_key)
```

- 使用jump label技术实现零开销的条件分支
- 在运行时修改指令流，避免分支预测开销
- 初始状态为true，优先使用qspinlock

#### 3.2 性能优势

- **零运行时开销**: 编译时确定的分支不产生额外开销
- **动态切换**: 可以在运行时改变行为
- **缓存友好**: 避免了条件分支的缓存污染

### 4. 内存序考虑

#### 4.1 ARCH_WEAK_RELEASE_ACQUIRE

- RISC-V采用弱内存模型
- qspinlock需要特殊的内存序处理
- 确保锁的获取和释放语义正确

#### 4.2 内存屏障优化

- 利用RISC-V的acquire/release语义
- 减少不必要的内存屏障指令
- 提高整体性能

## 相关提交分析

这个patch是RISC-V原子操作和锁优化系列的重要组成部分：

### 1. 前置依赖提交

1. **f7bd2be7663c**: "riscv: Implement arch_cmpxchg128() using Zacas"
   - 实现了128位原子比较交换
   - 为qspinlock提供了必要的原子操作支持

2. **38acdee32d23**: "riscv: Implement cmpxchg32/64() using Zacas"
   - 实现了32位和64位的Zacas支持
   - 建立了Zacas扩展的基础框架

3. **679e132c0ae2**: "RISC-V: KVM: Allow Zabha extension for Guest/VM"
   - 在虚拟化环境中支持Zabha扩展
   - 确保虚拟机也能使用优化的原子操作

### 2. 相关配置提交

1. **51624ddcf59d**: "dt-bindings: riscv: Add Zabha ISA extension description"
   - 添加了Zabha扩展的设备树绑定
   - 支持硬件扩展的自动检测

2. **6116e22ef33a**: "riscv: Improve zacas fully-ordered cmpxchg()"
   - 优化了全序Zacas操作
   - 提高了原子操作的性能

### 3. 后续优化提交

预期会有更多的性能优化和bug修复提交，特别是：
- 针对特定工作负载的调优
- 与其他子系统的集成优化
- 虚拟化环境下的性能优化

## 性能影响分析

### 1. 多核扩展性提升

#### 1.1 高竞争场景

- **qspinlock优势**: 在高竞争情况下，qspinlock的队列机制避免了thundering herd问题
- **缓存效率**: 等待者在本地变量上自旋，减少缓存行的来回传输
- **公平性**: 虽然不是严格FIFO，但在高负载下提供更好的整体吞吐量

#### 1.2 低竞争场景

- **快速路径**: qspinlock在无竞争时的性能与ticket spinlock相当
- **内存开销**: qspinlock需要额外的队列节点，但在低竞争时影响较小

### 2. 系统级性能影响

#### 2.1 内核热路径优化

- **调度器**: 改善多核调度的性能
- **内存管理**: 提升页面分配和释放的并发性
- **文件系统**: 减少文件系统锁的竞争

#### 2.2 应用程序性能

- **多线程应用**: 受益于更好的内核锁性能
- **数据库系统**: 在高并发访问时性能提升明显
- **Web服务器**: 改善高连接数场景下的性能

### 3. 硬件要求和兼容性

#### 3.1 硬件支持检测

```c
if (IS_ENABLED(CONFIG_RISCV_ISA_ZABHA) &&
    IS_ENABLED(CONFIG_RISCV_ISA_ZACAS) &&
    riscv_isa_extension_available(NULL, ZABHA) &&
    riscv_isa_extension_available(NULL, ZACAS)) {
    // 使用Zabha优化的qspinlock
} else if (riscv_isa_extension_available(NULL, ZICCRSE)) {
    // 使用Ziccrse的qspinlock
} else {
    // 回退到ticket spinlock
}
```

#### 3.2 向后兼容性

- **自动回退**: 在不支持的硬件上自动使用ticket spinlock
- **运行时检测**: 无需重新编译内核即可适应不同硬件
- **性能保证**: 即使在旧硬件上也不会有性能退化

## 潜在问题和注意事项

### 1. 硬件依赖性

#### 1.1 扩展支持要求

- **Zabha/Zacas**: 最佳性能需要这些扩展
- **Ziccrse**: 最低要求，保证前向进展
- **检测准确性**: 依赖于正确的硬件特性检测

#### 1.2 工具链要求

- **编译器支持**: 需要支持相关扩展的编译器
- **汇编器支持**: 必须能够正确处理新的原子指令
- **调试工具**: 调试器需要理解新的指令序列

### 2. 内存模型复杂性

#### 2.1 弱内存序挑战

- **正确性验证**: 需要仔细验证内存序的正确性
- **性能调优**: 在正确性和性能之间找到平衡
- **测试覆盖**: 需要全面的并发测试

#### 2.2 调试复杂性

- **竞态条件**: qspinlock的复杂性可能引入新的竞态条件
- **死锁检测**: 需要更复杂的死锁检测机制
- **性能分析**: 需要新的工具来分析qspinlock的性能

### 3. 配置和部署考虑

#### 3.1 配置选择

- **COMBO_SPINLOCKS**: 推荐的默认选择，提供最大兼容性
- **QUEUED_SPINLOCKS**: 仅在确定硬件支持时使用
- **TICKET_SPINLOCKS**: 保守选择，适用于所有硬件

#### 3.2 性能调优

- **工作负载特性**: 不同工作负载可能有不同的最优选择
- **硬件特性**: 需要根据具体硬件特性进行调优
- **监控和测量**: 需要持续监控性能指标

## 测试和验证

### 1. 功能测试

#### 1.1 基本功能验证

- **锁的正确性**: 验证锁的互斥性和公平性
- **原子操作**: 测试各种原子操作的正确性
- **内存序**: 验证内存序语义的正确实现

#### 1.2 并发测试

- **高竞争场景**: 测试多个CPU同时竞争锁的情况
- **混合工作负载**: 测试不同类型的并发访问模式
- **长时间运行**: 验证长时间运行的稳定性

### 2. 性能测试

#### 2.1 微基准测试

- **锁获取延迟**: 测量锁获取的平均延迟
- **吞吐量**: 测量单位时间内的锁操作次数
- **扩展性**: 测试随CPU数量增加的性能变化

#### 2.2 宏基准测试

- **内核编译**: 测试内核编译时间的变化
- **数据库性能**: 测试数据库工作负载的性能
- **Web服务器**: 测试高并发Web服务的性能

### 3. 回归测试

#### 3.1 兼容性测试

- **不同硬件**: 在支持和不支持扩展的硬件上测试
- **不同配置**: 测试各种内核配置组合
- **虚拟化环境**: 在虚拟机中测试功能和性能

#### 3.2 稳定性测试

- **压力测试**: 长时间高负载测试
- **故障注入**: 测试异常情况下的行为
- **内存压力**: 在内存不足情况下的测试

## 未来发展方向

### 1. 硬件扩展支持

#### 1.1 新扩展集成

- **更多原子操作**: 支持更多类型的原子操作
- **向量原子操作**: 集成向量扩展的原子操作
- **条件原子操作**: 支持更复杂的条件原子操作

#### 1.2 性能优化

- **指令调度**: 优化原子指令的调度
- **缓存优化**: 进一步减少缓存一致性开销
- **功耗优化**: 在保持性能的同时降低功耗

### 2. 软件生态完善

#### 2.1 工具链改进

- **编译器优化**: 更好的代码生成和优化
- **调试支持**: 改进的调试和分析工具
- **性能分析**: 专门的性能分析工具

#### 2.2 标准化工作

- **RISC-V标准**: 参与RISC-V标准的制定
- **Linux内核**: 推动相关特性进入主线内核
- **生态系统**: 与其他RISC-V项目的协作

### 3. 应用场景扩展

#### 3.1 高性能计算

- **科学计算**: 支持大规模并行科学计算
- **机器学习**: 优化机器学习工作负载
- **图计算**: 支持大规模图计算应用

#### 3.2 嵌入式系统

- **实时系统**: 支持实时系统的严格时序要求
- **低功耗**: 在嵌入式系统中的功耗优化
- **安全性**: 增强嵌入式系统的安全性

## 总结

### 1. 技术成就

这个patch代表了RISC-V生态系统在并发性能优化方面的重要里程碑：

- **架构完整性**: 为RISC-V提供了完整的spinlock解决方案
- **性能优化**: 在多核系统中提供了显著的性能提升
- **硬件利用**: 充分利用了RISC-V的硬件扩展特性
- **向后兼容**: 保持了与现有系统的完全兼容性

### 2. 工程价值

- **模块化设计**: 清晰的模块化设计便于维护和扩展
- **运行时适应**: 智能的运行时硬件检测和适应
- **零开销抽象**: 使用静态分支实现零开销的抽象
- **测试覆盖**: 全面的测试确保了代码质量

### 3. 生态意义

- **标准推进**: 推动了RISC-V锁机制的标准化
- **性能基准**: 为RISC-V系统建立了新的性能基准
- **社区贡献**: 为开源社区提供了高质量的实现
- **产业影响**: 为RISC-V在服务器和高性能计算领域的应用奠定了基础

### 4. 技术启示

这个patch展示了几个重要的技术原则：

- **硬件软件协同**: 软件设计充分考虑硬件特性
- **性能与兼容性平衡**: 在追求性能的同时保持兼容性
- **渐进式优化**: 通过渐进式的改进实现最终目标
- **社区协作**: 通过社区协作实现复杂的技术目标

这个patch不仅解决了RISC-V架构的具体技术问题，更为整个RISC-V生态系统的发展提供了重要的技术基础和发展方向。它体现了开源社区在推动硬件架构发展方面的重要作用，也展示了RISC-V架构在现代计算系统中的巨大潜力。