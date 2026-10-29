#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量清洗110章格式硬伤：
1. ASCII直引号 " → 中文弯引号 “”（成对替换）
2. --- 分隔线 → 删除
3. 阿拉伯数字 → 汉字数字
"""

import os
import re

def convert_quotes(text):
    """成对替换ASCII直引号为中文弯引号"""
    # 双引号成对替换
    result = []
    in_quote = False
    for ch in text:
        if ch == '"':
            if not in_quote:
                result.append('\u201c')  # 左双引号 "
                in_quote = True
            else:
                result.append('\u201d')  # 右双引号 "
                in_quote = False
        else:
            result.append(ch)
    return ''.join(result)

def remove_separators(text):
    """删除---分隔线"""
    text = re.sub(r'^---\s*$', '', text, flags=re.MULTILINE)
    text = text.replace('---', '')
    return text

def convert_digits(text):
    """阿拉伯数字转汉字数字"""
    digit_map = {
        '0': '零', '1': '一', '2': '二', '3': '三', '4': '四',
        '5': '五', '6': '六', '7': '七', '8': '八', '9': '九'
    }
    for d, c in digit_map.items():
        text = text.replace(d, c)
    return text

def clean_file(filepath):
    """清洗单个文件"""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original = content
    
    # 1. 替换引号
    content = convert_quotes(content)
    
    # 2. 删除分隔线
    content = remove_separators(content)
    
    # 3. 转换数字
    content = convert_digits(content)
    
    if content != original:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    return False

def main():
    dir_path = r"F:\F05_Projects_Hub\穿越之我是杨广\正文_精修版\卷一_龙潜于渊"
    
    files = sorted([f for f in os.listdir(dir_path) if f.endswith('.md')])
    print(f"共 {len(files)} 个文件待清洗")
    
    changed = 0
    for fname in files:
        fpath = os.path.join(dir_path, fname)
        try:
            if clean_file(fpath):
                changed += 1
        except Exception as e:
            print(f"  [错误] {fname}: {e}")
    
    print(f"\n清洗完成: {changed}/{len(files)} 个文件被修改")

if __name__ == '__main__':
    main()
