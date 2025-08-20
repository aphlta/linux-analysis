# RISC-V Perf Guest vs Host 区分支持 Patch 分析

## 1. Commit 基本信息

- **Commit ID**: 5bb5ccb3e8d8dba29941cd78d5c1bcd27b227b4a
- **标题**: riscv: perf: add guest vs host distinction
- **作者**: Quan Zhou <zhouquan@iscas.ac.cn>
- **提交日期**: 2024年10月15日
- **审核者**: Andrew Jones <ajones@ventanamicro.com>
- **维护者**: Anup Patel <anup@brainfault.org>
- **合并日期**: 2024年10月28日

## 2. Patch 概述

本patch为RISC-V架构引入了基本的guest支持，使perf能够区分PMU中断是来自host还是guest，并收集基础信息。这是RISC-V虚拟化支持的重要组成部分。

## 3. 修改内容详细分析

### 3.1 文件修改统计

```
 arch/riscv/include/asm/perf_event.h |  6 ++++++
 arch/riscv/kernel/perf_callchain.c  | 38 ++++++++++++++++++++++++++++++++++++++
 2 files changed, 44 insertions(+)
```

### 3.2 arch/riscv/include/asm/perf_event.h 修改

#### 3.2.1 新增函数声明

```c
#ifdef CONFIG_PERF_EVENTS
#include <linux/perf_event.h>

// 新增的函数声明
unsigned long perf_instruction_pointer(struct pt_regs *regs);
unsigned long perf_misc_flags(struct pt_regs *regs);

#define perf_arch_bpf_user_pt_regs(regs) (struct user_regs_struct *)regs

#define perf_arch_fetch_caller_regs(regs, __ip) { \
	(regs)->epc = (__ip); \
	(regs)->s0 = (unsigned long) __builtin_frame_address(0); \
	(regs)->sp = current_stack_pointer; \
	(regs)->status = SR_PP; \
}
#endif
```

**分析**:
- 新增了两个关键函数的声明：`perf_instruction_pointer` 和 `perf_misc_flags`
- 这两个函数是perf框架中用于区分guest/host上下文的标准接口
- 通过条件编译确保只在启用PERF_EVENTS时包含

### 3.3 arch/riscv/kernel/perf_callchain.c 修改

#### 3.3.1 现有函数的guest检查

```c
void perf_callchain_user(struct perf_callchain_entry_ctx *entry,
			 struct pt_regs *regs)
{
	if (perf_guest_state()) {
		/* TODO: We don't support guest os callchain now */
		return;
	}

	arch_stack_walk_user(fill_callchain, entry, regs);
}

void perf_callchain_kernel(struct perf_callchain_entry_ctx *entry,
			   struct pt_regs *regs)
{
	if (perf_guest_state()) {
		/* TODO: We don't support guest os callchain now */
		return;
	}

	walk_stackframe(NULL, regs, fill_callchain, entry);
}
```

**分析**:
- 在用户态和内核态callchain函数中添加了guest状态检查
- 当检测到guest状态时，直接返回，暂不支持guest OS的callchain
- 这是一个渐进式的实现，为未来完整的guest callchain支持预留了空间

#### 3.3.2 新增核心函数

##### perf_instruction_pointer 函数

```c
unsigned long perf_instruction_pointer(struct pt_regs *regs)
{
	if (perf_guest_state())
		return perf_guest_get_ip();

	return instruction_pointer(regs);
}
```

**功能分析**:
- 根据当前执行上下文返回正确的指令指针
- 如果在guest模式下，调用`perf_guest_get_ip()`获取guest的IP
- 否则返回host的指令指针
- 这是perf采样时获取准确PC值的关键函数

##### perf_misc_flags 函数

```c
unsigned long perf_misc_flags(struct pt_regs *regs)
{
	unsigned int guest_state = perf_guest_state();
	unsigned long misc = 0;

	if (guest_state) {
		if (guest_state & PERF_GUEST_USER)
			misc |= PERF_RECORD_MISC_GUEST_USER;
		else
			misc |= PERF_RECORD_MISC_GUEST_KERNEL;
	} else {
		if (user_mode(regs))
			misc |= PERF_RECORD_MISC_USER;
		else
			misc |= PERF_RECORD_MISC_KERNEL;
	}

	return misc;
}
```

**功能分析**:
- 根据当前执行上下文设置perf记录的misc标志
- 支持四种状态：
  - `PERF_RECORD_MISC_GUEST_USER`: Guest用户态
  - `PERF_RECORD_MISC_GUEST_KERNEL`: Guest内核态  
  - `PERF_RECORD_MISC_USER`: Host用户态
  - `PERF_RECORD_MISC_KERNEL`: Host内核态
- 这些标志帮助perf工具正确分析和显示采样数据

## 4. 技术原理分析

### 4.1 Guest/Host 检测机制

#### 4.1.1 perf_guest_state() 函数

```c
// 在 include/linux/perf_event.h 中定义
#ifdef CONFIG_GUEST_PERF_EVENTS
static inline unsigned int perf_guest_state(void)
{
	return static_call(__perf_guest_state)();
}
#else
static inline unsigned int perf_guest_state(void) { return 0; }
#endif
```

**原理**:
- 使用Linux的static call机制实现高效的间接调用
- 虚拟化层（如KVM）注册回调函数来报告当前状态
- 返回值包含`PERF_GUEST_ACTIVE`和`PERF_GUEST_USER`标志

#### 4.1.2 Guest状态标志

```c
#define PERF_GUEST_ACTIVE	0x01  // 当前在guest模式
#define PERF_GUEST_USER		0x02  // guest用户态
```

### 4.2 RISC-V虚拟化上下文

在RISC-V虚拟化环境中：
- Hypervisor通过H扩展管理guest
- PMU中断可能来自guest或host
- 需要正确识别中断源以提供准确的性能分析

### 4.3 Perf框架集成

这个patch实现了perf框架要求的标准接口：
- `perf_instruction_pointer()`: 获取正确的指令指针
- `perf_misc_flags()`: 设置采样记录的上下文标志

## 5. 相关提交分析

### 5.1 依赖的基础设施

本patch依赖于以下已有的基础设施：

1. **CONFIG_GUEST_PERF_EVENTS**: 内核配置选项
2. **perf_guest_info_callbacks**: Guest信息回调结构
3. **static call机制**: 高效的间接函数调用
4. **RISC-V H扩展支持**: 硬件虚拟化支持

### 5.2 后续相关提交

预期的后续工作可能包括：

1. **Guest callchain支持**: 完善guest OS的调用栈追踪
2. **KVM集成**: 在RISC-V KVM中注册guest回调
3. **PMU虚拟化**: 完整的guest PMU支持

## 6. 影响和意义

### 6.1 功能影响

1. **性能分析准确性**: 能够正确区分guest和host的性能事件
2. **虚拟化支持**: 为RISC-V虚拟化环境提供基础的perf支持
3. **工具兼容性**: 使现有的perf工具能够在RISC-V虚拟化环境中工作

### 6.2 架构意义

1. **标准化**: 遵循了Linux perf框架的标准接口
2. **可扩展性**: 为未来更完整的guest支持奠定基础
3. **跨架构一致性**: 与x86、ARM64等架构保持一致的实现模式

## 7. 测试和验证

### 7.1 测试场景

1. **Host环境测试**: 确保不影响现有的host perf功能
2. **Guest环境测试**: 验证guest状态的正确检测
3. **混合负载测试**: 同时运行host和guest负载时的正确性

### 7.2 验证方法

```bash
# 在host上运行perf
perf record -e cycles ./test_program
perf report

# 检查采样记录的misc标志
perf script -F comm,pid,tid,cpu,time,event,ip,sym,misc
```

## 8. 潜在问题和限制

### 8.1 当前限制

1. **Guest callchain缺失**: 暂不支持guest OS的调用栈追踪
2. **依赖虚拟化层**: 需要hypervisor提供正确的guest状态信息
3. **性能开销**: 每次采样都需要检查guest状态

### 8.2 未来改进方向

1. **完整的guest支持**: 实现guest callchain和符号解析
2. **性能优化**: 减少guest状态检查的开销
3. **更多PMU事件**: 支持更多类型的性能事件

## 9. 总结

这个patch为RISC-V架构引入了基本但重要的guest/host区分功能，是RISC-V虚拟化支持的重要里程碑。虽然当前实现相对简单，但它建立了正确的架构基础，为未来更完整的虚拟化性能分析支持铺平了道路。

该实现遵循了Linux内核的最佳实践，与其他架构保持一致，并为RISC-V生态系统的虚拟化发展做出了重要贡献。