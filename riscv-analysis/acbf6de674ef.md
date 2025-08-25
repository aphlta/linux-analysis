# StarFive Dubhe-80 PMU事件支持补丁分析

## 基本信息

**Commit ID:** acbf6de674ef7b1b5870b25e7b3c695bf84273d0  
**作者:** Ji Sheng Teoh <jisheng.teoh@starfivetech.com>  
**提交日期:** 2023年11月3日  
**标题:** perf vendor events riscv: Add StarFive Dubhe-80 JSON file  

## 补丁概述

这个补丁为RISC-V架构的perf工具添加了StarFive Dubhe-80处理器的PMU（Performance Monitoring Unit）事件支持。该补丁通过添加JSON配置文件，使perf工具能够识别和监控Dubhe-80处理器的性能事件。

## 修改内容详细分析

### 1. 文件修改列表

补丁修改了以下3个文件：
- `tools/perf/pmu-events/arch/riscv/mapfile.csv` (新增1行)
- `tools/perf/pmu-events/arch/riscv/starfive/dubhe-80/common.json` (新增172行)
- `tools/perf/pmu-events/arch/riscv/starfive/dubhe-80/firmware.json` (新增68行)

### 2. mapfile.csv修改

在mapfile.csv中新增了一行映射规则：
```csv
0x67e-0x80000000db000080-0x[[:xdigit:]]+,v1,starfive/dubhe-80,core
```

**技术解析：**
- `0x67e`: StarFive的JEDEC厂商ID (MVENDORID)
- `0x80000000db000080`: Dubhe-80的微架构ID (MARCHID)
- `0x[[:xdigit:]]+`: 实现版本ID的正则表达式匹配 (MIMPID)
- `v1`: JSON文件版本
- `starfive/dubhe-80`: JSON文件路径
- `core`: 事件类型（核心事件）

### 3. common.json - 核心性能事件

该文件定义了34个核心性能事件（EventCode 0x1-0x22），涵盖了处理器的各个关键组件：

#### 内存管理单元(MMU)事件：
- `ACCESS_MMU_STLB` (0x1): 访问MMU STLB
- `MISS_MMU_STLB` (0x2): MMU STLB缺失
- `ACCESS_MMU_PTE_C` (0x3): 访问MMU PTE缓存
- `MISS_MMU_PTE_C` (0x4): MMU PTE缓存缺失

#### 分支预测和控制流事件：
- `ROB_FLUSH` (0x5): ROB刷新（所有类型异常）
- `BTB_PREDICTION_MISS` (0x6): BTB预测缺失
- `BPU_BR_RETIRE` (0xA): 条件分支指令退休
- `BPU_BR_MISS` (0xB): 条件分支指令缺失
- `RET_INS_RETIRE` (0xC): 返回指令退休
- `RET_INS_MISS` (0xD): 返回指令缺失
- `INDIRECT_JR_MISS` (0xE): 间接跳转指令缺失

#### 指令缓存和TLB事件：
- `ITLB_MISS` (0x7): 指令TLB缺失
- `ICACHE_MISS` (0x9): 指令缓存缺失
- `SYNC_DEL_FETCH_G` (0x8): SYNC交付取指组

#### 流水线和调度事件：
- `IBUF_VAL_ID_NORDY` (0xF): IBUF有效而ID未就绪
- `IBUF_NOVAL_ID_RDY` (0x10): IBUF无效而ID就绪
- `REN_INT_PHY_REG_NORDY` (0x11): 重命名整数物理寄存器文件未就绪
- `REN_FP_PHY_REG_NORDY` (0x12): 重命名浮点物理寄存器文件未就绪
- `REN_CP_NORDY` (0x13): 重命名检查点未就绪
- `DEC_VAL_ROB_NORDY` (0x14): 解码有效且ROB未就绪
- `OOD_FLUSH_LS_DEP` (0x15): 由于加载/存储依赖的乱序刷新

#### 数据缓存和内存事件：
- `ACCESS_DTLB` (0x17): 访问数据TLB
- `MISS_DTLB` (0x18): 数据TLB缺失
- `LOAD_INS_DCACHE` (0x19): 加载指令访问数据缓存
- `LOAD_INS_MISS_DCACHE` (0x1A): 加载指令数据缓存缺失
- `STORE_INS_DCACHE` (0x1B): 存储/原子指令访问数据缓存
- `STORE_INS_MISS_DCACHE` (0x1C): 存储/原子指令数据缓存缺失

#### 二级缓存事件：
- `LOAD_SCACHE` (0x1D): 加载访问二级缓存
- `STORE_SCACHE` (0x1E): 存储访问二级缓存
- `LOAD_MISS_SCACHE` (0x1F): 加载二级缓存缺失
- `STORE_MISS_SCACHE` (0x20): 存储二级缓存缺失
- `L2C_PF_REQ` (0x21): L2缓存数据预取请求
- `L2C_PF_HIT` (0x22): L2缓存数据预取命中

### 4. firmware.json - 固件事件

该文件定义了22个标准RISC-V固件事件，这些事件遵循RISC-V SBI规范：

#### 异常和陷阱事件：
- `FW_MISALIGNED_LOAD`: 未对齐加载陷阱
- `FW_MISALIGNED_STORE`: 未对齐存储陷阱
- `FW_ACCESS_LOAD`: 加载访问陷阱
- `FW_ACCESS_STORE`: 存储访问陷阱
- `FW_ILLEGAL_INSN`: 非法指令陷阱

#### 系统调用事件：
- `FW_SET_TIMER`: 设置定时器事件
- `FW_IPI_SENT`: 发送IPI到其他HART
- `FW_IPI_RECEIVED`: 从其他HART接收IPI

#### 内存屏障事件：
- `FW_FENCE_I_SENT/RECEIVED`: FENCE.I请求发送/接收
- `FW_SFENCE_VMA_SENT/RECEIVED`: SFENCE.VMA请求发送/接收
- `FW_SFENCE_VMA_ASID_SENT/RECEIVED`: 带ASID的SFENCE.VMA请求
- `FW_HFENCE_GVMA_SENT/RECEIVED`: HFENCE.GVMA请求（虚拟化）
- `FW_HFENCE_GVMA_VMID_SENT/RECEIVED`: 带VMID的HFENCE.GVMA请求
- `FW_HFENCE_VVMA_SENT/RECEIVED`: HFENCE.VVMA请求
- `FW_HFENCE_VVMA_ASID_SENT/RECEIVED`: 带ASID的HFENCE.VVMA请求

## 技术原理分析

### 1. RISC-V PMU架构

RISC-V PMU基于以下寄存器：
- `mhpmcounter[3-31]`: 硬件性能监控计数器
- `mhpmevent[3-31]`: 性能事件选择寄存器
- `mcountinhibit`: 计数器禁用控制

### 2. 事件映射机制

perf工具通过以下步骤识别和使用PMU事件：

1. **硬件识别**: 读取CSR寄存器获取MVENDORID、MARCHID、MIMPID
2. **映射查找**: 在mapfile.csv中查找匹配的映射规则
3. **事件加载**: 加载对应的JSON文件定义的事件
4. **事件配置**: 将事件代码写入mhpmevent寄存器
5. **计数监控**: 通过mhpmcounter寄存器读取计数值

### 3. 设备树配置

补丁提供了PMU设备树节点的配置示例：

```dts
pmu {
    compatible = "riscv,pmu";
    riscv,raw-event-to-mhpmcounters =
        /* Event ID 1-31 */
        <0x00 0x00 0xFFFFFFFF 0xFFFFFFE0 0x00007FF8>,
        /* Event ID 32-33 */
        <0x00 0x20 0xFFFFFFFF 0xFFFFFFFE 0x00007FF8>,
        /* Event ID 34 */
        <0x00 0x22 0xFFFFFFFF 0xFFFFFF22 0x00007FF8>;
};
```

这个配置定义了原始事件ID到硬件计数器的映射关系。

## 相关提交分析

通过git历史分析，发现相关的提交包括：

1. **5ebe2f4bf0a8**: "perf vendor events riscv: Add StarFive Dubhe-90 JSON file" - 同系列处理器的后续支持
2. **0d5701dc9cd6**: "soc: sifive: ccache: Add StarFive JH7100 support" - StarFive其他芯片的支持
3. **3d70b9853b44**: "dt-bindings: cache: sifive,ccache0: Add StarFive JH7100 compatible" - 设备树绑定支持

这些提交表明StarFive正在逐步完善其RISC-V处理器在Linux内核中的支持。

## 补丁影响和意义

### 1. 功能增强
- 为StarFive Dubhe-80处理器提供了完整的性能监控支持
- 支持34个核心性能事件和22个固件事件
- 使开发者能够深入分析处理器性能特征

### 2. 生态系统完善
- 完善了RISC-V生态系统中的性能分析工具链
- 为StarFive处理器的性能优化提供了基础设施
- 促进了RISC-V在高性能计算领域的应用

### 3. 标准化贡献
- 遵循了RISC-V PMU标准和SBI固件事件规范
- 为其他RISC-V厂商提供了参考实现
- 推动了RISC-V性能监控标准的统一

## 使用示例

补丁提供了详细的使用示例，展示了如何使用perf工具监控各种性能事件：

```bash
perf stat -a \
    -e access_mmu_stlb \
    -e miss_mmu_stlb \
    -e access_mmu_pte_c \
    -e rob_flush \
    -e btb_prediction_miss \
    -e itlb_miss \
    -e sync_del_fetch_g \
    -e icache_miss \
    -e bpu_br_retire \
    -e bpu_br_miss \
    -e ret_ins_retire \
    -e ret_ins_miss \
    -- openssl speed rsa2048
```

这个示例展示了如何同时监控多个性能事件，为性能分析提供了全面的数据。

## 总结

这个补丁是一个高质量的硬件支持补丁，它：

1. **完整性**: 提供了全面的PMU事件支持，涵盖了处理器的各个关键组件
2. **标准化**: 严格遵循RISC-V规范和Linux内核的代码规范
3. **实用性**: 提供了详细的使用示例和配置说明
4. **可维护性**: 代码结构清晰，文档完善
5. **前瞻性**: 为StarFive处理器的未来发展奠定了基础

该补丁的成功合并标志着StarFive Dubhe-80处理器在Linux生态系统中获得了官方支持，为基于该处理器的系统开发和性能优化提供了重要工具。