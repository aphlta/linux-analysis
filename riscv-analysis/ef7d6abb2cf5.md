# RISC-V hwprobe which-cpus 测试功能分析

## 1. Commit 信息

**Commit ID:** ef7d6abb2cf57a18d34b332f0865c4d03bd810a3  
**作者:** Andrew Jones <ajones@ventanamicro.com>  
**日期:** Wed Nov 22 17:47:05 2023 +0100  
**标题:** RISC-V: selftests: Add which-cpus hwprobe test  

## 2. Patch 修改内容详细分析

### 2.1 修改的文件

1. **tools/testing/selftests/riscv/hwprobe/Makefile**
   - 在 `TEST_GEN_PROGS` 中添加了 `which-cpus` 测试程序
   - 添加了编译规则：`$(OUTPUT)/which-cpus: which-cpus.c sys_hwprobe.S`

2. **tools/testing/selftests/riscv/hwprobe/which-cpus.c** (新文件)
   - 完整的测试程序，共154行代码
   - 实现了对 `RISCV_HWPROBE_WHICH_CPUS` 标志的全面测试

### 2.2 核心功能实现

#### 2.2.1 测试程序结构

```c
// 主要包含的头文件
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sched.h>
#include <unistd.h>
#include <assert.h>
#include "hwprobe.h"
#include "../../kselftest.h"
```

#### 2.2.2 关键函数分析

**1. help() 函数**
- 提供命令行帮助信息
- 说明程序的两种使用模式：
  - 无参数：运行测试套件
  - 有参数：查询特定hwprobe对的CPU列表

**2. print_cpulist() 函数**
- 格式化输出CPU列表
- 支持连续CPU范围的压缩显示（如：1-4,7,9-12）
- 处理空CPU集合的情况

**3. do_which_cpus() 函数**
- 解析命令行参数中的key=value对
- 调用 `riscv_hwprobe()` 系统调用
- 输出匹配条件的CPU列表

**4. main() 函数**
- 实现7个测试用例，验证 `RISCV_HWPROBE_WHICH_CPUS` 功能

### 2.3 测试用例详细分析

#### 测试用例1：参数验证 - cpusetsize为0
```c
rc = riscv_hwprobe(pairs, 1, 0, (unsigned long *)&cpus, RISCV_HWPROBE_WHICH_CPUS);
ksft_test_result(rc == -EINVAL, "no cpusetsize\n");
```
- **目的：** 验证当cpusetsize为0时返回-EINVAL错误
- **预期结果：** 系统调用应该失败并返回-EINVAL

#### 测试用例2：参数验证 - cpus为NULL
```c
rc = riscv_hwprobe(pairs, 1, sizeof(cpu_set_t), NULL, RISCV_HWPROBE_WHICH_CPUS);
ksft_test_result(rc == -EINVAL, "NULL cpus\n");
```
- **目的：** 验证当cpus指针为NULL时的错误处理
- **预期结果：** 系统调用应该失败并返回-EINVAL

#### 测试用例3：未知key处理
```c
pairs[0] = (struct riscv_hwprobe){ .key = 0xbadc0de, };
rc = riscv_hwprobe(pairs, 1, sizeof(cpu_set_t), (unsigned long *)&cpus, RISCV_HWPROBE_WHICH_CPUS);
ksft_test_result(rc == 0 && CPU_COUNT(&cpus) == 0, "unknown key\n");
```
- **目的：** 验证对未知key的处理
- **预期结果：** 调用成功但CPU集合为空

#### 测试用例4：重复key处理
```c
pairs[0] = (struct riscv_hwprobe){ .key = RISCV_HWPROBE_KEY_BASE_BEHAVIOR, .value = RISCV_HWPROBE_BASE_BEHAVIOR_IMA, };
pairs[1] = (struct riscv_hwprobe){ .key = RISCV_HWPROBE_KEY_BASE_BEHAVIOR, .value = RISCV_HWPROBE_BASE_BEHAVIOR_IMA, };
```
- **目的：** 验证重复key的处理
- **预期结果：** 调用应该成功

#### 测试用例5：设置所有CPU
```c
pairs[0] = (struct riscv_hwprobe){ .key = RISCV_HWPROBE_KEY_BASE_BEHAVIOR, .value = RISCV_HWPROBE_BASE_BEHAVIOR_IMA, };
pairs[1] = (struct riscv_hwprobe){ .key = RISCV_HWPROBE_KEY_IMA_EXT_0, .value = ext0_all, };
```
- **目的：** 验证当所有CPU都支持指定特性时的行为
- **预期结果：** 返回的CPU数量应该等于系统在线CPU总数

#### 测试用例6：设置亲和性CPU
```c
memcpy(&cpus, &cpus_aff, sizeof(cpu_set_t));
rc = riscv_hwprobe(pairs, 2, sizeof(cpu_set_t), (unsigned long *)&cpus, RISCV_HWPROBE_WHICH_CPUS);
ksft_test_result(rc == 0 && CPU_EQUAL(&cpus, &cpus_aff), "set all affinity cpus\n");
```
- **目的：** 验证在进程CPU亲和性范围内的CPU筛选
- **预期结果：** 返回的CPU集合应该与进程亲和性CPU集合相等

#### 测试用例7：清空所有CPU
```c
pairs[1] = (struct riscv_hwprobe){ .key = RISCV_HWPROBE_KEY_IMA_EXT_0, .value = ~ext0_all, };
```
- **目的：** 验证当没有CPU支持指定特性时的行为
- **预期结果：** 返回的CPU集合应该为空

## 3. 代码修改原理分析

### 3.1 hwprobe系统调用机制

`riscv_hwprobe` 是RISC-V架构特有的系统调用，用于查询硬件特性。该系统调用有两种工作模式：

1. **传统模式（flags=0）：** 给定CPU集合，查询这些CPU支持的硬件特性
2. **which-cpus模式（flags=RISCV_HWPROBE_WHICH_CPUS）：** 给定硬件特性要求，返回支持这些特性的CPU集合

### 3.2 RISCV_HWPROBE_WHICH_CPUS 标志的工作原理

当设置了 `RISCV_HWPROBE_WHICH_CPUS` 标志时，系统调用的行为发生反转：

1. **输入：** 
   - `pairs`：包含期望的key-value对
   - `cpus`：初始CPU集合（通常设置为全部CPU或进程亲和性CPU）

2. **处理过程：**
   - 遍历每个CPU，检查是否支持所有指定的硬件特性
   - 如果CPU不支持某个特性，将其从CPU集合中移除
   - 对于未知的key，清空整个CPU集合

3. **输出：**
   - `cpus`：修改后的CPU集合，只包含支持所有指定特性的CPU

### 3.3 关键数据结构

```c
struct riscv_hwprobe {
    __s64 key;    // 硬件特性标识符
    __u64 value;  // 特性值或期望值
};
```

常用的key包括：
- `RISCV_HWPROBE_KEY_BASE_BEHAVIOR`：基础行为特性
- `RISCV_HWPROBE_KEY_IMA_EXT_0`：IMA扩展特性

## 4. 相关提交分析

### 4.1 提交序列

这个patch是一个功能完整实现的最后一环：

1. **53b2b22850e1** - "RISC-V: Move the hwprobe syscall to its own file"
   - 将hwprobe系统调用移到独立文件
   - 为后续功能扩展做准备

2. **36d842d654be** - "RISC-V: hwprobe: Clarify cpus size parameter"
   - 澄清cpus参数的大小语义
   - 改进参数验证

3. **e178bf146e4b** - "RISC-V: hwprobe: Introduce which-cpus flag"
   - 引入RISCV_HWPROBE_WHICH_CPUS标志
   - 实现核心功能逻辑
   - 添加VDSO支持

4. **ef7d6abb2cf5** - "RISC-V: selftests: Add which-cpus hwprobe test" (当前patch)
   - 添加完整的测试套件
   - 验证功能正确性

### 4.2 功能演进

这个功能的引入是为了解决以下问题：

1. **CPU异构性处理：** 在异构RISC-V系统中，不同CPU可能支持不同的扩展指令集
2. **任务调度优化：** 应用程序可以查询支持特定指令集的CPU，进行针对性的任务调度
3. **性能优化：** 允许应用程序根据CPU能力选择最优的代码路径

## 5. 技术意义和影响

### 5.1 对RISC-V生态的意义

1. **标准化硬件查询接口：** 提供了统一的硬件特性查询机制
2. **支持异构计算：** 为RISC-V异构系统提供了基础设施
3. **性能优化基础：** 为高性能计算和优化库提供了硬件感知能力

### 5.2 测试覆盖范围

这个测试程序覆盖了以下关键场景：

1. **参数验证：** 确保系统调用正确处理无效参数
2. **边界条件：** 测试空CPU集合、未知key等边界情况
3. **功能正确性：** 验证CPU筛选逻辑的正确性
4. **兼容性：** 确保与现有CPU亲和性机制的兼容

### 5.3 实际应用场景

1. **编译器优化：** JIT编译器可以查询CPU特性，生成优化代码
2. **数学库优化：** BLAS、FFT等库可以选择最优实现
3. **容器调度：** 容器编排系统可以根据硬件特性调度任务
4. **性能分析：** 性能分析工具可以了解硬件能力分布

## 6. 总结

这个patch为RISC-V的hwprobe系统调用添加了完整的测试覆盖，验证了which-cpus功能的正确性。该功能是RISC-V架构支持异构计算的重要基础设施，为应用程序提供了硬件感知能力，有助于性能优化和资源调度。测试程序设计全面，覆盖了各种边界条件和实际使用场景，确保了功能的可靠性和稳定性。