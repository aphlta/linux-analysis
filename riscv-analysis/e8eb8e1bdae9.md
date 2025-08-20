# Patch Analysis: e8eb8e1bdae9

## 基本信息

**Commit ID**: e8eb8e1bdae94b9e003f5909519fd311d0936890  
**作者**: Pu Lehui <pulehui@huawei.com>  
**提交日期**: Mon Mar 17 03:12:13 2025 +0000  
**标题**: riscv: fgraph: Select HAVE_FUNCTION_GRAPH_TRACER depends on HAVE_DYNAMIC_FTRACE_WITH_ARGS

## 问题描述

当前RISC-V架构上的function graph tracer (fgraph)依赖于DYNAMIC_FTRACE_WITH_ARGS基础设施。然而，DYNAMIC_FTRACE_WITH_ARGS可能在RISC-V上被关闭，这会导致已启用的fgraph功能异常。

## 修改内容

### 文件变更

**文件**: `arch/riscv/Kconfig`

```diff
-       select HAVE_FUNCTION_GRAPH_TRACER
+       select HAVE_FUNCTION_GRAPH_TRACER if HAVE_DYNAMIC_FTRACE_WITH_ARGS
```

### 修改原理

1. **依赖关系修正**: 原来RISC-V架构无条件选择`HAVE_FUNCTION_GRAPH_TRACER`，现在改为只有在`HAVE_DYNAMIC_FTRACE_WITH_ARGS`可用时才选择。

2. **配置逻辑**: 在RISC-V的Kconfig中，`HAVE_DYNAMIC_FTRACE_WITH_ARGS`的选择条件是：
   ```
   select HAVE_DYNAMIC_FTRACE_WITH_ARGS if HAVE_DYNAMIC_FTRACE
   ```
   而`HAVE_DYNAMIC_FTRACE`又依赖于：
   ```
   select HAVE_DYNAMIC_FTRACE if !XIP_KERNEL && MMU && (CLANG_SUPPORTS_DYNAMIC_FTRACE || GCC_SUPPORTS_DYNAMIC_FTRACE)
   ```

## 技术背景

### Function Graph Tracer架构变更

这个patch修复的问题源于commit `a3ed4157b7d8` ("fgraph: Replace fgraph_ret_regs with ftrace_regs")的变更：

1. **接口统一**: 该commit将function graph tracer的回调接口从`fgraph_ret_regs`改为`ftrace_regs`，简化了回调接口。

2. **配置选项变更**: `CONFIG_HAVE_FUNCTION_GRAPH_RETVAL`被`CONFIG_HAVE_FUNCTION_GRAPH_FREGS`替代。

3. **RISC-V实现**: 在RISC-V架构中，新的实现依赖于`DYNAMIC_FTRACE_WITH_ARGS`提供的基础设施。

### RISC-V Ftrace实现细节

从`arch/riscv/kernel/ftrace.c`可以看到：

```c
#ifdef CONFIG_DYNAMIC_FTRACE_WITH_ARGS
void ftrace_graph_func(unsigned long ip, unsigned long parent_ip,
                      struct ftrace_ops *op, struct ftrace_regs *fregs)
{
    unsigned long return_hooker = (unsigned long)&return_to_handler;
    unsigned long frame_pointer = arch_ftrace_regs(fregs)->s0;
    unsigned long *parent = &arch_ftrace_regs(fregs)->ra;
    // ...
}
#else
// 传统实现
#endif
```

新的function graph tracer实现完全依赖于`DYNAMIC_FTRACE_WITH_ARGS`提供的`ftrace_regs`结构。

## 问题根因分析

1. **配置不一致**: 在某些配置下，`DYNAMIC_FTRACE_WITH_ARGS`可能被禁用（例如XIP_KERNEL配置或编译器不支持），但`FUNCTION_GRAPH_TRACER`仍然被启用。

2. **编译错误**: 当`DYNAMIC_FTRACE_WITH_ARGS`未定义时，相关的`ftrace_regs`结构和函数不可用，导致编译失败。

3. **运行时异常**: 即使编译通过，运行时也可能因为缺少必要的基础设施而出现异常。

## 相关提交分析

### 被修复的提交

**Commit**: a3ed4157b7d8 ("fgraph: Replace fgraph_ret_regs with ftrace_regs")  
**作者**: Masami Hiramatsu (Google) <mhiramat@kernel.org>  
**日期**: Thu Dec 26 14:11:55 2024 +0900

这个提交的主要变更：
- 统一使用`ftrace_regs`替代`fgraph_ret_regs`
- 简化function graph tracer的回调接口
- 影响多个架构，包括ARM64、LoongArch、RISC-V、s390、x86等

### 报告来源

**报告者**: kernel test robot <lkp@intel.com>  
**链接**: https://lore.kernel.org/oe-kbuild-all/202503160820.dvqMpH0g-lkp@intel.com/

## 影响范围

### 受影响的配置

1. **XIP_KERNEL=y**: 在XIP (eXecute In Place)内核配置下，动态ftrace被禁用
2. **MMU=n**: 在无MMU配置下，动态ftrace不可用
3. **编译器不支持**: 当编译器不支持动态ftrace时

### 修复效果

1. **配置一致性**: 确保只有在支持`DYNAMIC_FTRACE_WITH_ARGS`时才启用function graph tracer
2. **编译稳定性**: 避免在不支持的配置下出现编译错误
3. **运行时稳定性**: 防止运行时因缺少基础设施而崩溃

## 测试验证

### 编译测试

可以通过以下配置组合验证修复效果：

1. **正常配置**: `CONFIG_DYNAMIC_FTRACE=y`, `CONFIG_FUNCTION_GRAPH_TRACER=y`
2. **XIP配置**: `CONFIG_XIP_KERNEL=y`, `CONFIG_FUNCTION_GRAPH_TRACER=n` (自动禁用)
3. **无MMU配置**: `CONFIG_MMU=n`, `CONFIG_FUNCTION_GRAPH_TRACER=n` (自动禁用)

### 功能测试

在支持的配置下，function graph tracer应该正常工作：
```bash
echo function_graph > /sys/kernel/debug/tracing/current_tracer
echo 1 > /sys/kernel/debug/tracing/tracing_on
```

## 总结

这个patch通过添加正确的依赖关系，修复了RISC-V架构上function graph tracer的配置问题。它确保了只有在具备必要基础设施（DYNAMIC_FTRACE_WITH_ARGS）时才启用function graph tracer，避免了编译错误和运行时异常。

这是一个典型的配置依赖修复patch，体现了内核配置系统中正确表达组件依赖关系的重要性。随着内核功能的演进和重构，这类依赖关系的维护是保证系统稳定性的关键。