#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
txt2md.py — 将纯文本(.txt)转换为 Markdown(.md)文档

支持两种模式：
1. 批量模式（默认）：遍历配置的源文件夹，将所有 .txt 转换为 .md 输出到目标文件夹
2. 单文件模式：python3 txt2md.py 输入.txt [-o 输出.md]

功能特性：
- 自动识别常见中文编码（UTF-8 / GBK / GB18030 / UTF-16 等）
- 标题识别：Markdown 式 # 标题、第X章/第X节、一、二、三、（一）（二）、1.1 等
- 列表识别：- * + 转无序列表；数字. / （1） 等转有序列表
- 网址/邮箱不会被误判为列表；连续短行自动合并为段落
"""

import argparse
import os
import re
import sys
from pathlib import Path

# ============================================================
#                       配置区（按需修改）
# ============================================================
# 待转换的 txt 所在文件夹（支持 Windows / Linux 路径写法）
SOURCE_DIR = r"D:\my_wiki\data\2"

# 转换后的 md 输出文件夹
OUTPUT_DIR = r"D:\my_wiki\raw\untracked"

# 是否递归遍历子文件夹（True 会保留子目录结构）
RECURSIVE = True

# 已存在同名 .md 时是否覆盖（False 则跳过）
OVERWRITE = True
# ============================================================


# ---------------- 编码检测 ----------------

def detect_encoding(path):
    """按优先级尝试常见编码，返回能成功解码的编码名。"""
    candidates = ["utf-8-sig", "utf-8", "gb18030", "gbk", "utf-16", "latin-1"]
    with open(path, "rb") as f:
        raw = f.read()
    for enc in candidates:
        try:
            raw.decode(enc)
            return enc
        except (UnicodeDecodeError, LookupError):
            continue
    return "utf-8"  # 兜底，交给 open 报错


# ---------------- 行类型判断 ----------------

# Markdown 标题：# ~ ######
MD_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")

# 中文章节标题（独立成行才生效）
CN_HEADING_RE = re.compile(
    r"^(第\s*[0-9一二三四五六七八九十百千零两]+\s*[章节卷部篇讲回])"
    r"|^(?:[一二三四五六七八九十]+、)"
    r"|^(?:（[一二三四五六七八九十]+）)"
    r"|^(?:\([一二三四五六七八九十]+\))"
    r"|^(\d+\.\d+(?:\.\d+)?\s*[\u4e00-\u9fa5])"   # 形如 1.1 / 1.1.2 开头的编号
)

# 无序列表行
ULIST_RE = re.compile(r"^[-*+]\s+")

# 有序列表行：1. / 1、 / （1） / (1)
OLIST_RE = re.compile(r"^(\d+[\.、]|[（(]\d+[）)])\s*")

# 纯空白行
BLANK_RE = re.compile(r"^\s*$")


def is_md_heading(line):
    m = MD_HEADING_RE.match(line)
    return (m, m.group(1).count("#") if m else None)


def is_cn_heading(line):
    return CN_HEADING_RE.match(line) is not None


def is_list_line(line):
    stripped = line.strip()
    if not stripped:
        return False
    # 网址或邮箱（如 http://...）不应被误判为无序列表
    if re.match(r"^(https?://|www\.|[\w.+-]+@[\w.-]+\.\w+)", stripped, re.I):
        return False
    if ULIST_RE.match(stripped):
        return "ul"
    if OLIST_RE.match(stripped):
        return "ol"
    return False


def detect_heading_level(line):
    """根据中文编号形式推断层级：第X章->1，X、->2，（X）->3，X.X->2"""
    s = line.strip()
    if re.match(r"^第\s*[0-9一二三四五六七八九十百千零两]+\s*[章节卷部篇讲回]", s):
        return 1
    if re.match(r"^[一二三四五六七八九十]+、", s):
        return 2
    if re.match(r"^（[一二三四五六七八九十]+）|^\([一二三四五六七八九十]+\)", s):
        return 3
    if re.match(r"^\d+\.\d+", s):
        return 2
    return 2


# ---------------- 主转换 ----------------

def convert_txt_to_md(text):
    """将文本内容转换为 Markdown，返回 Markdown 字符串。"""
    lines = text.splitlines()
    out = []
    para = []          # 正在积累的段落行
    prev_was_list = False
    list_kind = None   # 当前列表类型 ul / ol / None

    def flush_paragraph():
        nonlocal para
        if para:
            out.append(" ".join(p.strip() for p in para))
            para = []

    def flush_list_gap():
        """列表与相邻内容之间留空行，保证 Markdown 渲染正确"""
        nonlocal prev_was_list
        if out and out[-1] != "" and prev_was_list:
            out.append("")
        prev_was_list = False

    for raw in lines:
        line = raw.rstrip()

        if BLANK_RE.match(line):
            flush_paragraph()
            if out and out[-1] != "":
                out.append("")
            prev_was_list = False
            continue

        # 1) Markdown 式标题
        m, level = is_md_heading(line)
        if m:
            flush_paragraph()
            flush_list_gap()
            if out and out[-1] != "":
                out.append("")
            out.append(f"{'#' * level} {m.group(2).strip()}")
            list_kind = None
            continue

        # 2) 中文章节标题
        if is_cn_heading(line):
            flush_paragraph()
            flush_list_gap()
            if out and out[-1] != "":
                out.append("")
            level = detect_heading_level(line)
            out.append(f"{'#' * level} {line.strip()}")
            list_kind = None
            continue

        # 3) 列表行
        kind = is_list_line(line)
        if kind:
            flush_paragraph()
            if list_kind != kind:
                flush_list_gap()
                list_kind = kind
            stripped = line.strip()
            if kind == "ul":
                out.append(f"- {ULIST_RE.sub('', stripped).strip()}")
            else:
                # 统一转为 "1. " 形式的有序列表（仅保留编号数字）
                m = OLIST_RE.match(stripped)
                num = re.sub(r"[^\d]", "", m.group(1))
                rest = OLIST_RE.sub("", stripped).strip()
                out.append(f"{num}. {rest}")
            prev_was_list = True
            continue

        # 4) 普通文本：作为段落积累
        prev_was_list = False
        para.append(line)

    flush_paragraph()

    # 收尾：去掉多余空行，保证文件以单个换行结束
    while out and out[-1] == "":
        out.pop()
    return "\n".join(out) + "\n"


# ---------------- 批量转换 ----------------

def find_txt_files(source_dir, recursive):
    """遍历源文件夹，返回所有 .txt 文件路径列表"""
    pattern = "**/*.txt" if recursive else "*.txt"
    return sorted(Path(source_dir).glob(pattern))


def convert_one_file(src_path, out_path):
    """转换单个文件，返回 (是否成功, 提示信息)"""
    encoding = detect_encoding(src_path)
    try:
        with open(src_path, "r", encoding=encoding) as f:
            text = f.read()
    except UnicodeDecodeError:
        return False, f"无法用 {encoding} 解码，已跳过"
    except OSError as e:
        return False, f"读取失败：{e}"

    md_text = convert_txt_to_md(text)
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(md_text)
    except OSError as e:
        return False, f"写入失败：{e}"
    return True, f"完成（输入编码：{encoding}）"


def batch_convert(source_dir, output_dir, recursive, overwrite):
    """遍历文件夹批量转换，返回统计信息"""
    src_root = Path(source_dir)
    dst_root = Path(output_dir)

    if not src_root.is_dir():
        print(f"错误：源文件夹不存在：{src_root}", file=sys.stderr)
        return None

    txt_files = find_txt_files(src_root, recursive)
    if not txt_files:
        print(f"提示：{src_root} 下未找到任何 .txt 文件")
        return {"total": 0, "ok": 0, "skipped": 0, "failed": []}

    stats = {"total": 0, "ok": 0, "skipped": 0, "failed": []}
    for src in txt_files:
        stats["total"] += 1
        # 在输出目录中保留相对子目录结构，避免同名文件互相覆盖
        rel = src.relative_to(src_root)
        out = dst_root / rel.with_suffix(".md")

        if out.exists() and not overwrite:
            stats["skipped"] += 1
            print(f"[跳过] {rel} -> {out}（已存在，OVERWRITE=False）")
            continue

        ok, msg = convert_one_file(src, out)
        if ok:
            stats["ok"] += 1
            print(f"[成功] {rel} -> {out}  {msg}")
        else:
            stats["failed"].append(str(rel))
            print(f"[失败] {rel}  {msg}", file=sys.stderr)
    return stats


def print_summary(stats, output_dir):
    if stats is None:
        return
    print("-" * 50)
    print(f"批量转换完成：共 {stats['total']} 个文件，"
          f"成功 {stats['ok']}，跳过 {stats['skipped']}，失败 {len(stats['failed'])}")
    if stats["failed"]:
        print("失败文件：")
        for f in stats["failed"]:
            print(f"  - {f}")
    print(f"输出目录：{Path(output_dir).resolve()}")


# ---------------- 命令行入口 ----------------

def main():
    parser = argparse.ArgumentParser(
        description="将纯文本(.txt)转换为 Markdown(.md)文档：批量遍历文件夹 或 转换单个文件",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("input", nargs="?", help="单个 txt 文件路径（不填则使用配置区的 SOURCE_DIR 批量转换）")
    parser.add_argument("--source", help="批量模式：待转换的文件夹（默认取配置区 SOURCE_DIR）")
    parser.add_argument("--output-dir", help="批量模式：输出文件夹（默认取配置区 OUTPUT_DIR）")
    parser.add_argument("-o", "--output", help="单文件模式：输出的 md 文件路径（默认同名同目录）")
    parser.add_argument("--encoding", help="单文件模式：指定输入编码（默认自动检测）")
    parser.add_argument("--no-recursive", action="store_true", help="批量模式：不递归子文件夹")
    parser.add_argument("--no-overwrite", action="store_true", help="批量模式：已存在的 .md 不覆盖")
    args = parser.parse_args()

    # ---------- 单文件模式 ----------
    if args.input:
        src = Path(args.input)
        if not src.is_file():
            print(f"错误：找不到输入文件 {src}", file=sys.stderr)
            sys.exit(1)
        if args.output:
            out = Path(args.output)
        else:
            out = src.with_suffix(".md")
        ok, msg = convert_one_file(src, out)
        if not ok:
            print(f"错误：{msg}", file=sys.stderr)
            sys.exit(1)
        print(f"转换完成：{src} -> {out}（{msg}）")
        return

    # ---------- 批量模式 ----------
    source_dir = args.source or SOURCE_DIR
    output_dir = args.output_dir or OUTPUT_DIR
    recursive = not args.no_recursive
    overwrite = not args.no_overwrite

    print(f"源文件夹：{Path(source_dir).resolve()}")
    print(f"输出文件夹：{Path(output_dir).resolve()}")
    stats = batch_convert(source_dir, output_dir, recursive, overwrite)
    if stats is None:
        sys.exit(1)
    print_summary(stats, output_dir)


if __name__ == "__main__":
    main()
