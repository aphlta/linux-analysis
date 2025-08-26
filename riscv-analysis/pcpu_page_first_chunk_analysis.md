# Linux内核 PCPU Page First Chunk Allocator 机制分析

## 概述

Per-CPU (PCPU) Page First Chunk Allocator 是Linux内核中用于管理每CPU变量内存分配的重要机制。本文档基于Linux内核源码，重点分析了该机制在RISC-V架构下的实现原理和代码流程。

## 1. 核心数据结构

### 1.1 pcpu_chunk 结构体

```c
struct pcpu_chunk {
    struct list_head    list;           /* 链表节点 */
    int                 free_bytes;     /* 空闲字节数 */
    struct pcpu_block_md *md_blocks;    /* 元数据块数组 */
    void               *base_addr;      /* 基地址 */
    unsigned long      *alloc_map;      /* 分配位图 */
    unsigned long      *bound_map;      /* 边界位图 */
    struct pcpu_block_md first_block;   /* 第一个块的元数据 */
    int                 nr_pages;       /* 总页数 */
    int                 nr_populated;   /* 已填充页数 */
    int                 nr_empty_pop_pages; /* 空的已填充页数 */
    unsigned long       populated[];    /* 已填充页位图 */
};
```

### 1.2 pcpu_alloc_info 结构体

```c
struct pcpu_alloc_info {
    size_t              static_size;    /* 静态区域大小 */
    size_t              reserved_size;  /* 保留区域大小 */
    size_t              dyn_size;       /* 动态区域大小 */
    size_t              unit_size;      /* 单元大小 */
    size_t              atom_size;      /* 原子大小 */
    size_t              alloc_size;     /* 分配大小 */
    size_t              __ai_size;      /* 结构体总大小 */
    int                 nr_groups;      /* 组数 */
    struct pcpu_group_info groups[];    /* 组信息数组 */
};
```

### 1.3 关键全局变量

```c
static void *pcpu_base_addr;                    /* percpu区域基地址 */
static struct pcpu_chunk *pcpu_first_chunk;     /* 第一个chunk */
static struct pcpu_chunk *pcpu_reserved_chunk;  /* 保留chunk */
static int pcpu_unit_pages;                     /* 每单元页数 */
static int pcpu_unit_size;                      /* 每单元大小 */
static int pcpu_nr_units;                       /* 单元总数 */
static int pcpu_atom_size;                      /* 原子大小 */
static int pcpu_nr_slots;                       /* slot总数 */
static struct list_head *pcpu_chunk_lists;      /* chunk链表数组 */
```

## 2. pcpu_setup_first_chunk 函数分析

### 2.1 函数原型

```c
void __init pcpu_setup_first_chunk(const struct pcpu_alloc_info *ai, void *base_addr);
```

### 2.2 主要功能

1. **参数验证**: 检查传入的分配信息和基地址的有效性
2. **内存布局计算**: 根据分配信息计算各个区域的偏移和大小
3. **全局变量初始化**: 设置percpu分配器的全局状态
4. **chunk链表初始化**: 创建并初始化chunk管理链表
5. **第一个chunk创建**: 分别创建reserved chunk和dynamic chunk

### 2.3 代码流程

```c
void __init pcpu_setup_first_chunk(const struct pcpu_alloc_info *ai, void *base_addr)
{
    // 1. 参数验证
    PCPU_SETUP_BUG_ON(ai->nr_groups <= 0);
    PCPU_SETUP_BUG_ON(!base_addr);
    PCPU_SETUP_BUG_ON(ai->unit_size < size_sum);
    
    // 2. 分配临时数组
    group_offsets = memblock_alloc_or_panic(alloc_size, SMP_CACHE_BYTES);
    group_sizes = memblock_alloc_or_panic(alloc_size, SMP_CACHE_BYTES);
    unit_map = memblock_alloc_or_panic(alloc_size, SMP_CACHE_BYTES);
    unit_off = memblock_alloc_or_panic(alloc_size, SMP_CACHE_BYTES);
    
    // 3. 构建CPU到单元的映射
    for (group = 0, unit = 0; group < ai->nr_groups; group++, unit += i) {
        const struct pcpu_group_info *gi = &ai->groups[group];
        for (i = 0; i < gi->nr_units; i++) {
            cpu = gi->cpu_map[i];
            if (cpu == NR_CPUS) continue;
            unit_map[cpu] = unit + i;
            unit_off[cpu] = gi->base_offset + i * ai->unit_size;
        }
    }
    
    // 4. 初始化全局变量
    pcpu_unit_pages = ai->unit_size >> PAGE_SHIFT;
    pcpu_unit_size = pcpu_unit_pages << PAGE_SHIFT;
    pcpu_atom_size = ai->atom_size;
    
    // 5. 分配chunk链表
    pcpu_chunk_lists = memblock_alloc_or_panic(pcpu_nr_slots * sizeof(pcpu_chunk_lists[0]), SMP_CACHE_BYTES);
    
    // 6. 创建第一个chunk
    static_size = ALIGN(ai->static_size, PCPU_MIN_ALLOC_SIZE);
    dyn_size = ai->dyn_size - (static_size - ai->static_size);
    
    tmp_addr = (unsigned long)base_addr + static_size;
    if (ai->reserved_size)
        pcpu_reserved_chunk = pcpu_alloc_first_chunk(tmp_addr, ai->reserved_size);
    
    tmp_addr = (unsigned long)base_addr + static_size + ai->reserved_size;
    pcpu_first_chunk = pcpu_alloc_first_chunk(tmp_addr, dyn_size);
    
    // 7. 设置基地址
    pcpu_base_addr = base_addr;
}
```

## 3. pcpu_page_first_chunk 函数分析

### 3.1 函数原型

```c
int __init pcpu_page_first_chunk(size_t reserved_size, pcpu_fc_cpu_to_node_fn_t cpu_to_nd_fn);
```

### 3.2 主要功能

pcpu_page_first_chunk是page-based的第一个chunk分配器，主要用于将percpu区域映射到vmalloc空间中。

### 3.3 实现步骤

1. **构建分配信息**: 调用pcpu_build_alloc_info构建分配信息
2. **分配页面数组**: 为每个CPU单元分配页面
3. **逐页分配内存**: 使用pcpu_fc_alloc为每个页面分配物理内存
4. **注册VM区域**: 在vmalloc空间中注册虚拟内存区域
5. **建立页表映射**: 调用pcpu_populate_pte建立页表
6. **映射页面**: 使用__pcpu_map_pages建立虚拟地址到物理页面的映射
7. **复制静态数据**: 将静态percpu数据复制到每个CPU单元
8. **调用pcpu_setup_first_chunk**: 完成第一个chunk的设置

### 3.4 关键代码片段

```c
int __init pcpu_page_first_chunk(size_t reserved_size, pcpu_fc_cpu_to_node_fn_t cpu_to_nd_fn)
{
    // 1. 构建分配信息
    ai = pcpu_build_alloc_info(reserved_size, 0, PAGE_SIZE, NULL);
    if (IS_ERR(ai)) return PTR_ERR(ai);
    
    // 2. 分配页面数组
    unit_pages = ai->unit_size >> PAGE_SHIFT;
    pages_size = PFN_ALIGN(unit_pages * num_possible_cpus() * sizeof(pages[0]));
    pages = memblock_alloc_or_panic(pages_size, SMP_CACHE_BYTES);
    
    // 3. 逐页分配内存
    j = 0;
    for (unit = 0; unit < num_possible_cpus(); unit++) {
        unsigned int cpu = ai->groups[0].cpu_map[unit];
        for (i = 0; i < unit_pages; i++) {
            void *ptr = pcpu_fc_alloc(cpu, PAGE_SIZE, PAGE_SIZE, cpu_to_nd_fn);
            if (!ptr) goto enomem;
            kmemleak_ignore_phys(__pa(ptr));
            pages[j++] = virt_to_page(ptr);
        }
    }
    
    // 4. 注册VM区域
    vm.flags = VM_ALLOC;
    vm.size = num_possible_cpus() * ai->unit_size;
    vm_area_register_early(&vm, PAGE_SIZE);
    
    // 5. 建立映射并复制数据
    for (unit = 0; unit < num_possible_cpus(); unit++) {
        unsigned long unit_addr = (unsigned long)vm.addr + unit * ai->unit_size;
        
        // 建立页表
        for (i = 0; i < unit_pages; i++)
            pcpu_populate_pte(unit_addr + (i << PAGE_SHIFT));
        
        // 映射页面
        rc = __pcpu_map_pages(unit_addr, &pages[unit * unit_pages], unit_pages);
        if (rc < 0) panic("failed to map percpu area, err=%d\n", rc);
        
        // 复制静态数据
        memcpy((void *)unit_addr, __per_cpu_start, ai->static_size);
    }
    
    // 6. 完成设置
    pcpu_setup_first_chunk(ai, vm.addr);
    return 0;
}
```

## 4. RISC-V架构下的Per-CPU区域设置

### 4.1 架构特性

通过分析RISC-V架构的相关代码，发现：

1. **无架构特定实现**: RISC-V架构没有定义`CONFIG_HAVE_SETUP_PER_CPU_AREA`，因此使用通用的SMP percpu区域设置
2. **使用embed方式**: 默认使用`pcpu_embed_first_chunk`进行第一个chunk的分配
3. **内存布局**: 遵循标准的Linux percpu内存布局

### 4.2 setup_per_cpu_areas实现

在RISC-V架构下，使用通用的setup_per_cpu_areas实现：

```c
void __init setup_per_cpu_areas(void)
{
    unsigned long delta;
    unsigned int cpu;
    int rc;
    
    // 总是为模块percpu变量保留区域
    rc = pcpu_embed_first_chunk(PERCPU_MODULE_RESERVE, PERCPU_DYNAMIC_RESERVE,
                                PAGE_SIZE, NULL, NULL);
    if (rc < 0)
        panic("Failed to initialize percpu areas.");
    
    // 计算每个CPU的偏移
    delta = (unsigned long)pcpu_base_addr - (unsigned long)__per_cpu_start;
    for_each_possible_cpu(cpu)
        __per_cpu_offset[cpu] = delta + pcpu_unit_offsets[cpu];
}
```

## 5. 内存布局和管理机制

### 5.1 Percpu内存布局

```
第一个Chunk的内存布局:
+------------------+------------------+------------------+
|   Static Area    | Reserved Area    |  Dynamic Area    |
|  (静态percpu变量) | (模块percpu变量)  | (动态分配区域)    |
+------------------+------------------+------------------+
^                  ^                  ^
|                  |                  |
__per_cpu_start   static_size        static_size + reserved_size
                                     
总大小: unit_size (通常对齐到页边界)
```

### 5.2 Chunk管理

1. **Chunk分类**:
   - `pcpu_first_chunk`: 第一个chunk，包含动态分配区域
   - `pcpu_reserved_chunk`: 保留chunk，用于模块percpu变量
   - 其他chunk: 后续动态创建的chunk

2. **Chunk状态管理**:
   - 使用链表数组`pcpu_chunk_lists`管理不同状态的chunk
   - 根据空闲空间大小将chunk分类到不同的slot中
   - 支持chunk的隔离、回收和重新整合

### 5.3 分配算法

1. **First-fit算法**: 在chunk中查找第一个满足大小要求的空闲区域
2. **Bitmap管理**: 使用位图跟踪已分配和空闲区域
3. **Block元数据**: 使用`pcpu_block_md`结构体优化查找性能

## 6. 关键配置选项

### 6.1 编译时配置

```c
// 支持embed方式的第一个chunk
#ifdef CONFIG_NEED_PER_CPU_EMBED_FIRST_CHUNK
#define BUILD_EMBED_FIRST_CHUNK 1
#else
#define BUILD_EMBED_FIRST_CHUNK 0
#endif

// 支持page方式的第一个chunk
#ifdef CONFIG_NEED_PER_CPU_PAGE_FIRST_CHUNK
#define BUILD_PAGE_FIRST_CHUNK 1
#else
#define BUILD_PAGE_FIRST_CHUNK 0
#endif
```

### 6.2 运行时选择

```c
enum pcpu_fc {
    PCPU_FC_AUTO,   // 自动选择
    PCPU_FC_EMBED,  // embed方式
    PCPU_FC_PAGE,   // page方式
    PCPU_FC_NR,
};

// 通过内核参数percpu_alloc=选择分配方式
static int __init percpu_alloc_setup(char *str)
{
    if (!strcmp(str, "embed"))
        pcpu_chosen_fc = PCPU_FC_EMBED;
    else if (!strcmp(str, "page"))
        pcpu_chosen_fc = PCPU_FC_PAGE;
    return 0;
}
```

## 7. NUMA环境下的Per-CPU内存分配策略

### 7.1 NUMA感知的核心机制

在NUMA环境下，percpu分配器通过以下机制确保内存分配的局部性：

#### 7.1.1 CPU到NUMA节点映射

```c
// 核心函数指针类型定义
typedef int (*pcpu_fc_cpu_to_node_fn_t)(int cpu);

// 通用的CPU到节点映射函数
static inline int cpu_to_node(int cpu)
{
    return per_cpu(numa_node, cpu);
}

// 设置CPU的NUMA节点
static inline void set_cpu_numa_node(int cpu, int node)
{
    per_cpu(numa_node, cpu) = node;
}
```

#### 7.1.2 NUMA感知的内存分配

`pcpu_fc_alloc`函数是NUMA感知分配的核心实现：

```c
static void * __init pcpu_fc_alloc(unsigned int cpu, size_t size, size_t align,
                                   pcpu_fc_cpu_to_node_fn_t cpu_to_nd_fn)
{
    const unsigned long goal = __pa(MAX_DMA_ADDRESS);
#ifdef CONFIG_NUMA
    int node = NUMA_NO_NODE;
    void *ptr;

    // 1. 获取CPU对应的NUMA节点
    if (cpu_to_nd_fn)
        node = cpu_to_nd_fn(cpu);

    // 2. 检查节点有效性
    if (node == NUMA_NO_NODE || !node_online(node) || !NODE_DATA(node)) {
        // 回退到通用分配
        ptr = memblock_alloc_from(size, align, goal);
        pr_info("cpu %d has no node %d or node-local memory\n", cpu, node);
    } else {
        // 3. 在指定NUMA节点分配内存
        ptr = memblock_alloc_try_nid(size, align, goal,
                                     MEMBLOCK_ALLOC_ACCESSIBLE, node);
        pr_debug("per cpu data for cpu%d %zu bytes on node%d at 0x%llx\n",
                 cpu, size, node, (u64)__pa(ptr));
    }
    return ptr;
#else
    // 非NUMA环境直接分配
    return memblock_alloc_from(size, align, goal);
#endif
}
```

### 7.2 CPU分组和距离计算

#### 7.2.1 pcpu_build_alloc_info中的NUMA处理

```c
struct pcpu_alloc_info * __init pcpu_build_alloc_info(
    size_t reserved_size, size_t dyn_size, size_t atom_size,
    pcpu_fc_cpu_distance_fn_t cpu_distance_fn)
{
    // 1. 计算CPU间距离，进行分组
    for_each_possible_cpu(cpu) {
        for_each_possible_cpu(tcpu) {
            if (cpu == tcpu)
                break;
            if (group_map[cpu] == group_map[tcpu])
                continue;
            if (cpu_distance_fn &&
                cpu_distance_fn(cpu, tcpu) > LOCAL_DISTANCE)
                continue;
            // 将距离近的CPU分到同一组
            group_map[tcpu] = group_map[cpu];
        }
    }
    
    // 2. 根据分组结果构建分配信息
    // ...
}
```

#### 7.2.2 NUMA距离定义

```c
// include/linux/topology.h
#define LOCAL_DISTANCE      10  // 本地节点距离
#define REMOTE_DISTANCE     20  // 远程节点距离

// 节点间距离函数
#ifndef node_distance
#define node_distance(from, to) ((from) == (to) ? LOCAL_DISTANCE : REMOTE_DISTANCE)
#endif
```

### 7.3 RISC-V架构下的NUMA支持现状

#### 7.3.1 当前状态分析

通过代码分析发现，RISC-V架构目前的NUMA支持情况：

1. **无专门NUMA配置**: RISC-V的Kconfig中没有定义`CONFIG_NUMA`相关选项
2. **使用通用实现**: 依赖于通用的NUMA拓扑管理机制
3. **默认单节点**: 在没有NUMA配置的情况下，所有CPU被视为在同一节点

#### 7.3.2 Per-CPU分配策略

在RISC-V架构下，percpu分配遵循以下策略：

```c
// arch/riscv下没有特定的setup_per_cpu_areas实现
// 使用通用版本：
void __init setup_per_cpu_areas(void)
{
    unsigned long delta;
    unsigned int cpu;
    int rc;
    
    // 使用embed方式分配第一个chunk
    rc = pcpu_embed_first_chunk(PERCPU_MODULE_RESERVE, 
                                PERCPU_DYNAMIC_RESERVE,
                                PAGE_SIZE, NULL, NULL);
    if (rc < 0)
        panic("Failed to initialize percpu areas.");
    
    // 计算每个CPU的偏移
    delta = (unsigned long)pcpu_base_addr - (unsigned long)__per_cpu_start;
    for_each_possible_cpu(cpu)
        __per_cpu_offset[cpu] = delta + pcpu_unit_offsets[cpu];
}
```

### 7.4 NUMA环境下的内存分配地址分析

#### 7.4.1 分配地址的NUMA属性

在NUMA环境下，percpu分配的地址具有以下特性：

1. **物理地址局部性**: 
   - 每个CPU的percpu数据尽量分配在其本地NUMA节点的物理内存中
   - 通过`memblock_alloc_try_nid()`确保物理内存的NUMA局部性

2. **虚拟地址映射**:
   - 对于page方式：使用vmalloc空间，虚拟地址连续但物理地址可能分散
   - 对于embed方式：直接使用线性映射区域，虚拟和物理地址都保持局部性

#### 7.4.2 内存访问性能优化

```c
// 示例：CPU访问其本地percpu数据的路径
static inline void *this_cpu_ptr(const void __percpu *ptr)
{
    // 1. 获取当前CPU编号
    int cpu = smp_processor_id();
    
    // 2. 计算该CPU的percpu偏移
    unsigned long offset = __per_cpu_offset[cpu];
    
    // 3. 返回该CPU专属的数据地址
    // 这个地址在NUMA环境下位于CPU的本地节点内存中
    return (void *)((unsigned long)ptr + offset);
}
```

### 7.5 性能优化机制

#### 7.5.1 内存预填充

- 维护一定数量的预填充页面(`PCPU_EMPTY_POP_PAGES_HIGH`)
- 支持原子分配的快速路径
- 异步回收和平衡机制

#### 7.5.2 TLB优化

- 批量TLB刷新减少开销
- 利用大页映射提高TLB效率
- 保持percpu区域的局部性

#### 7.5.3 NUMA拓扑感知优化

- CPU分组基于NUMA拓扑距离
- 优先本地节点内存分配
- 减少跨节点内存访问延迟

## 8. 总结

PCPU Page First Chunk Allocator是Linux内核中一个精心设计的内存管理机制，它通过以下特性实现了高效的per-CPU变量管理：

1. **灵活的分配策略**: 支持embed和page两种分配方式
2. **高效的内存管理**: 使用位图和元数据块优化分配性能
3. **NUMA感知**: 考虑NUMA拓扑进行内存分配
4. **架构无关**: 提供通用接口，支持各种架构
5. **动态扩展**: 支持运行时动态创建新的chunk

在RISC-V架构下，该机制使用标准的通用实现，默认采用embed方式进行第一个chunk的分配，为RISC-V系统提供了可靠的per-CPU变量支持。

## 参考文件

- <mcfile name="percpu.c" path="/ssdhome/maoweiming/alearn/linuxxxx/mm/percpu.c"></mcfile>
- <mcfile name="percpu-internal.h" path="/ssdhome/maoweiming/alearn/linuxxxx/mm/percpu-internal.h"></mcfile>
- <mcfile name="percpu.h" path="/ssdhome/maoweiming/alearn/linuxxxx/include/linux/percpu.h"></mcfile>
- <mcfile name="Kconfig" path="/ssdhome/maoweiming/alearn/linuxxxx/arch/riscv/Kconfig"></mcfile>