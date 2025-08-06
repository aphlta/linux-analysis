#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自动比较大于指定版本的相邻Git版本脚本

该脚本会：
1. 获取所有大于指定版本的Git标签
2. 按版本号排序
3. 对每两个相邻版本调用generate_patch_analysis.py进行比较
"""

import subprocess
import re
import sys
import os
from packaging import version
import argparse
from datetime import datetime

def run_git_command(cmd):
    """执行Git命令并返回结果"""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, check=True)
        return result.stdout.strip().split('\n') if result.stdout.strip() else []
    except subprocess.CalledProcessError as e:
        print(f"❌ Git命令执行失败: {cmd}")
        print(f"错误信息: {e.stderr}")
        return []

def get_all_tags():
    """获取所有Git标签"""
    print("🔍 获取所有Git标签...")
    tags = run_git_command("git tag -l")
    return [tag for tag in tags if tag.strip()]

def parse_version_tag(tag):
    """解析版本标签，返回可比较的版本对象"""
    # 匹配常见的版本格式：v6.6.8, v6.6.8-rc1, v6.6.8.1等
    version_pattern = r'^v?(\d+\.\d+\.\d+(?:\.\d+)?(?:-\w+\d*)?(?:\.\w+\d*)?)$'
    match = re.match(version_pattern, tag)
    if match:
        version_str = match.group(1)
        try:
            # 处理rc版本
            if '-rc' in version_str:
                base_version, rc_part = version_str.split('-rc')
                # 将rc版本转换为预发布版本格式
                version_str = f"{base_version}rc{rc_part}"
            return version.parse(version_str)
        except Exception:
            return None
    return None

def filter_versions_greater_than(tags, min_version_str):
    """过滤出大于指定版本的标签"""
    print(f"🔍 过滤大于 {min_version_str} 的版本...")

    try:
        min_version = version.parse(min_version_str.lstrip('v'))
    except Exception as e:
        print(f"❌ 无法解析最小版本 {min_version_str}: {e}")
        return []

    valid_versions = []
    for tag in tags:
        parsed_version = parse_version_tag(tag)
        if parsed_version and parsed_version > min_version:
            valid_versions.append((tag, parsed_version))

    # 按版本号排序
    valid_versions.sort(key=lambda x: x[1])

    sorted_tags = [tag for tag, _ in valid_versions]
    print(f"✅ 找到 {len(sorted_tags)} 个符合条件的版本")

    return sorted_tags

def check_analysis_script_exists():
    """检查generate_patch_analysis.py脚本是否存在"""
    script_path = "generate_patch_analysis.py"
    if not os.path.exists(script_path):
        print(f"❌ 错误: 找不到 {script_path} 脚本")
        print("请确保该脚本在当前目录中")
        return False
    return True

def run_patch_analysis(source_version, target_version, output_dir="version_comparisons"):
    """运行补丁分析脚本"""
    # 确保输出目录存在
    os.makedirs(output_dir, exist_ok=True)

    # 生成输出文件名
    safe_source = re.sub(r'[^\w\-_.]', '_', source_version)
    safe_target = re.sub(r'[^\w\-_.]', '_', target_version)
    output_file = os.path.join(output_dir, f"{safe_target}-to-{safe_source}-diff.xlsx")

    print(f"\n🔄 分析版本差异: {target_version} -> {source_version}")
    print(f"📁 输出文件: {output_file}")

    # 构建命令
    cmd = f"python3 generate_patch_analysis.py {source_version} {target_version} --output '{output_file}'"

    try:
        result = subprocess.run(cmd, shell=True, check=True)
        print(f"✅ 分析完成: {output_file}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ 分析失败: {target_version} -> {source_version}")
        print(f"错误代码: {e.returncode}")
        return False

def main():
    parser = argparse.ArgumentParser(
        description='自动比较大于指定版本的相邻Git版本',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""使用示例:
  %(prog)s --min-version v6.6.8
  %(prog)s --min-version v6.6.8 --output-dir my_comparisons
  %(prog)s --min-version v6.6.8 --max-comparisons 5
        """
    )

    parser.add_argument('--min-version', default='v6.6.8',
                       help='最小版本（默认: v6.6.8）')
    parser.add_argument('--output-dir', default='version_comparisons',
                       help='输出目录（默认: version_comparisons）')
    parser.add_argument('--max-comparisons', type=int,
                       help='最大比较次数（可选，用于限制比较数量）')
    parser.add_argument('--dry-run', action='store_true',
                       help='仅显示将要比较的版本对，不实际执行')

    args = parser.parse_args()

    print(f"🚀 开始版本比较分析")
    print(f"📋 最小版本: {args.min_version}")
    print(f"📁 输出目录: {args.output_dir}")

    # 检查分析脚本是否存在
    if not args.dry_run and not check_analysis_script_exists():
        sys.exit(1)

    # 获取所有标签
    all_tags = get_all_tags()
    if not all_tags:
        print("❌ 没有找到任何Git标签")
        sys.exit(1)

    # 过滤和排序版本
    filtered_versions = filter_versions_greater_than(all_tags, args.min_version)
    if len(filtered_versions) < 2:
        print(f"❌ 找到的版本数量不足（需要至少2个版本进行比较）")
        print(f"找到的版本: {filtered_versions}")
        sys.exit(1)

    # 生成相邻版本对
    version_pairs = []
    for i in range(len(filtered_versions) - 1):
        target_version = filtered_versions[i]      # 较旧的版本
        source_version = filtered_versions[i + 1]  # 较新的版本
        version_pairs.append((source_version, target_version))

    # 应用最大比较次数限制
    if args.max_comparisons and len(version_pairs) > args.max_comparisons:
        version_pairs = version_pairs[:args.max_comparisons]
        print(f"⚠️  限制比较次数为 {args.max_comparisons} 对")

    print(f"\n📊 将要进行 {len(version_pairs)} 次版本比较:")
    for i, (source, target) in enumerate(version_pairs, 1):
        print(f"  {i}. {target} -> {source}")

    if args.dry_run:
        print("\n🔍 这是试运行模式，实际不会执行分析")
        return

    # 执行分析
    print(f"\n🔄 开始执行分析...")
    successful_analyses = 0
    failed_analyses = 0

    start_time = datetime.now()

    for i, (source_version, target_version) in enumerate(version_pairs, 1):
        print(f"\n{'='*60}")
        print(f"📈 进度: {i}/{len(version_pairs)}")

        if run_patch_analysis(source_version, target_version, args.output_dir):
            successful_analyses += 1
        else:
            failed_analyses += 1

    end_time = datetime.now()
    duration = end_time - start_time

    # 输出总结
    print(f"\n{'='*60}")
    print(f"📊 分析完成总结:")
    print(f"✅ 成功: {successful_analyses} 次")
    print(f"❌ 失败: {failed_analyses} 次")
    print(f"⏱️  总耗时: {duration}")
    print(f"📁 输出目录: {os.path.abspath(args.output_dir)}")

    if successful_analyses > 0:
        print(f"\n🎉 所有分析结果已保存到 {args.output_dir} 目录中")

if __name__ == "__main__":
    main()