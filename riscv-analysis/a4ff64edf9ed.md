# RISC-V THEAD CMO Errata Patch 分析报告

## Commit 信息
- **Commit ID**: a4ff64edf9edc8f05e2183610dc8306d3279c6ac
- **作者**: Jisheng Zhang <jszhang@kernel.org>
- **日期**: 2023年11月14日
- **标题**: riscv: errata: thead: use riscv_nonstd_cache_ops for CMO

## 修改概述

这个patch将THEAD C906/C910处理器的Cache Management Operations (CMO)从使用alternative机制动态补丁改为使用`riscv_nonstd_cache_ops`非标准缓存操作接口。

## 详细修改内容

### 1. 配置文件修改 (arch/riscv/Kconfig.errata)

```diff
+       select RISCV_NONSTANDARD_CACHE_OPS
```

在`ERRATA_THEAD_CMO`配置项中添加了对`RISCV_NONSTANDARD_CACHE_OPS`的依赖，启用非标准缓存操作支持。

### 2. THEAD Errata实现修改 (arch/riscv/errata/thead/errata.c)

#### 新增THEAD CMO操作函数

```c
// 新增的THEAD CMO指令定义
#define THEAD_INVAL_A0	".long 0x02a5000b"
#define THEAD_CLEAN_A0	".long 0x0255000b"
#define THEAD_FLUSH_A0	".long 0x02b5000b"
#define THEAD_SYNC_S	".long 0x0190000b"

// 新增的THEAD CMO操作宏
#define THEAD_CMO_OP(_op, _start, _size, _cachesize)			\
asm volatile("mv a0, %1\n\t"							\
	     "j 2f\n\t"								\
	     "3:\n\t"								\
	     THEAD_##_op##_A0 "\n\t"					\
	     "add a0, a0, %0\n\t"						\
	     "2:\n\t"								\
	     "bltu a0, %2, 3b\n\t"						\
	     THEAD_SYNC_S							\
	     : : "r"(_cachesize),						\
		 "r"((unsigned long)(_start) & ~((_cachesize) - 1UL)),	\
		 "r"((unsigned long)(_start) + (_size))			\
	     : "a0")

// 新增的缓存操作函数
static void thead_errata_cache_inv(phys_addr_t paddr, size_t size)
{
	THEAD_CMO_OP(INVAL, paddr, size, riscv_cbom_block_size);
}

static void thead_errata_cache_wback(phys_addr_t paddr, size_t size)
{
	THEAD_CMO_OP(CLEAN, paddr, size, riscv_cbom_block_size);
}

static void thead_errata_cache_wback_inv(phys_addr_t paddr, size_t size)
{
	THEAD_CMO_OP(FLUSH, paddr, size, riscv_cbom_block_size);
}

// 新增的非标准缓存操作结构体
static const struct riscv_nonstd_cache_ops thead_errata_cmo_ops = {
	.wback = &thead_errata_cache_wback,
	.inv = &thead_errata_cache_inv,
	.wback_inv = &thead_errata_cache_wback_inv,
};
```

#### 修改errata_probe_cmo函数

在`errata_probe_cmo`函数中添加了对非标准缓存操作的注册：

```c
if (stage == RISCV_ALTERNATIVES_BOOT) {
	riscv_cbom_block_size = L1_CACHE_BYTES;
	riscv_noncoherent_supported();
	riscv_noncoherent_register_cache_ops(&thead_errata_cmo_ops);
}
```

### 3. ALT_CMO_OP宏简化 (arch/riscv/include/asm/errata_list.h)

原来的`ALT_CMO_OP`宏从`ALTERNATIVE_2`简化为`ALTERNATIVE`：

```diff
-asm volatile(ALTERNATIVE_2(
-	__nops(6),
+asm volatile(ALTERNATIVE(
+	__nops(5),
	"mv a0, %1\n\t"
	"j 2f\n\t"
	"3:\n\t"
	CBO_##_op(a0)
	"add a0, a0, %0\n\t"
	"2:\n\t"
-	"bltu a0, %2, 3b\n\t"
-	"nop", 0, RISCV_ISA_EXT_ZICBOM, CONFIG_RISCV_ISA_ZICBOM,
-	"mv a0, %1\n\t"
-	"j 2f\n\t"
-	"3:\n\t"
-	THEAD_##_op##_A0 "\n\t"
-	"add a0, a0, %0\n\t"
-	"2:\n\t"
-	"bltu a0, %2, 3b\n\t"
-	THEAD_SYNC_S, THEAD_VENDOR_ID,
-			ERRATA_THEAD_CMO, CONFIG_ERRATA_THEAD_CMO)
+	"bltu a0, %2, 3b\n\t",
+	0, RISCV_ISA_EXT_ZICBOM, CONFIG_RISCV_ISA_ZICBOM)
```

移除了原来内嵌的THEAD CMO指令，现在只保留标准的ZICBOM指令路径。

## 技术原理分析

### 1. 架构设计变更

#### 原有设计
- 使用`ALTERNATIVE_2`机制在运行时动态选择指令
- 直接在`ALT_CMO_OP`宏中内嵌THEAD特定的CMO指令
- 编译时生成多个代码路径，运行时根据CPU特性选择

#### 新设计
- 使用`riscv_nonstd_cache_ops`函数指针接口
- THEAD CMO操作独立实现为专门的函数
- 通过间接调用实现非标准缓存操作

### 2. 缓存操作流程

#### 标准ZICBOM流程
```
DMA操作 -> arch_dma_cache_xxx() -> ALT_CMO_OP -> CBO指令
```

#### THEAD CMO流程
```
DMA操作 -> arch_dma_cache_xxx() -> noncoherent_cache_ops.xxx() -> THEAD_CMO_OP -> THEAD指令
```

### 3. THEAD CMO指令解析

根据代码中的注释，THEAD CMO指令格式如下：

```
th.dcache.ipa rs1 (invalidate, physical address)
| 31 - 25 | 24 - 20 | 19 - 15 | 14 - 12 | 11 - 7 | 6 - 0 |
  0000001    01010      rs1       000      00000  0001011

th.dcache.cpa rs1 (clean, physical address)
| 31 - 25 | 24 - 20 | 19 - 15 | 14 - 12 | 11 - 7 | 6 - 0 |
  0000001    01001      rs1       000      00000  0001011

th.dcache.cipa rs1 (clean then invalidate, physical address)
| 31 - 25 | 24 - 20 | 19 - 15 | 14 - 12 | 11 - 7 | 6 - 0 |
  0000001    01011      rs1       000      00000  0001011

th.sync.s (make sure all cache operations finished)
| 31 - 25 | 24 - 20 | 19 - 15 | 14 - 12 | 11 - 7 | 6 - 0 |
  0000000    11001     00000      000      00000  0001011
```

对应的机器码：
- `THEAD_INVAL_A0`: 0x02a5000b (th.dcache.ipa a0)
- `THEAD_CLEAN_A0`: 0x0295000b (th.dcache.cpa a0)
- `THEAD_FLUSH_A0`: 0x02b5000b (th.dcache.cipa a0)
- `THEAD_SYNC_S`: 0x0190000b (th.sync.s)

### 4. 性能影响分析

#### 间接调用开销
- 原来：直接内联汇编，零开销
- 现在：函数指针调用，有轻微的间接调用开销

#### 作者的性能测试结果
根据commit message，作者在Sipeed Lichee Pi 4A开发板上测试GMAC和EMMC，发现没有性能差异。这证实了Arnd的观点："访问失效缓存行的成本可能远高于间接分支的成本"。

## 修改动机和背景

### 1. 代码简化
- 移除复杂的`ALTERNATIVE_2`机制
- 统一非标准缓存操作的处理方式
- 提高代码可读性和可维护性

### 2. 架构统一
正如Arnd所建议的："将THEAD操作与所有非标准操作放在同一级别是有意义的，但我仍然会将CMO作为避免间接分支的显式快速路径。这对于可读性和间接分支有明显开销的平台来说都是正确的做法。"

### 3. 扩展性考虑
- 为其他厂商的非标准CMO操作提供统一接口
- 便于添加新的非标准缓存操作支持

## 相关提交分析

这个patch是一个重构性质的修改，主要目的是：

1. **简化代码结构**：移除复杂的alternative机制，使用更清晰的函数指针接口
2. **统一非标准操作**：为所有非标准缓存操作提供统一的处理框架
3. **保持性能**：虽然引入了间接调用，但实际测试显示性能无差异
4. **提高可维护性**：代码更容易理解和维护

## 影响范围

### 正面影响
- 代码更简洁易懂
- 为其他非标准CMO操作提供了框架
- 减少了alternative机制的复杂性

### 潜在风险
- 间接调用可能在某些场景下有轻微性能影响
- 增加了运行时的函数指针解引用

## 总结

这个patch是一个成功的代码重构，在保持功能不变的前提下，显著简化了THEAD CMO的实现方式。通过引入`riscv_nonstd_cache_ops`接口，不仅解决了当前的问题，还为未来支持更多非标准缓存操作奠定了基础。虽然理论上存在间接调用的性能开销，但实际测试证明这种开销在实际应用中是可以忽略的。