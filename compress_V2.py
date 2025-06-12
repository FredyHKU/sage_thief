#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
#  项目名称：Sage Thief (圣人盗) – 离线文件跨机传输工具
#  文件名称：compress_V2.py
#  脚本功能：将目标文件夹打包 → Base64 → 按块切片 → 生成大容量二维码
#  版    本：v2.0.0
#  作    者：Fred YUAN
#  首次创建：2024-06-12
#  仓库地址：https://github.com/FredyHKU/sage_thief
#
#  项目目的：
#      在无法联网或网络受限的环境中，通过二维码实现文件/代码包的
#      无介质搬运；无需 U 盘、蓝牙或网络连接即可将数据安全带出。
#
#  许可证：MIT License
#  ---------------------------------------------------------------------------
#  Copyright (c) 2024 Fred YUAN
#
#  Permission is hereby granted, free of charge, to any person obtaining a copy
#  of this software and associated documentation files (the “Software”), to deal
#  in the Software without restriction, including without limitation the rights
#  to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
#  copies of the Software, and to permit persons to whom the Software is
#  furnished to do so, subject to the following conditions:
#
#  The above copyright notice and this permission notice shall be included in
#  all copies or substantial portions of the Software.
#
#  THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
#  IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
#  AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
#  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
#  OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
#  THE SOFTWARE.
# =============================================================================

import os
import zipfile
import base64
import hashlib
import json
import qrcode
from pyzbar import pyzbar
from PIL import Image, ImageDraw, ImageFont


###############################################################
########### 请修改这里的参数，否则无法运行后果自负！！！###########
###############################################################

CODE_EXTENSION = ['.py', '.js', '.html', '.css', '.java', '.cpp', '.c', '.h', '.txt', '.md', '.json', '.xml', '.yml', '.yaml']
TARGET_FOLDER = r"D:\work\flair\1-8\deployment\pi_dev"
TARGET_CHUNK_SIZE = 2000  # QR码容量更大，推荐值：800-2000，根据需要调整，表示每个二维码中字符数量，数字越大图片数量越少但失败率越高

###############################################################
# 以下为正式代码，非必要请勿修改，有必要请自行修改，自行判断！！！##
###############################################################


def calculate_sha256(file_path):
    """计算文件SHA256校验值"""
    sha256_hash = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256_hash.update(chunk)
    return sha256_hash.hexdigest()

def create_code_archive(source_folder, output_dir="qrcode_output"):
    """简化版：小文件直接用少量大码解决"""
    
    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)
    
    # 1. 打包文件夹为ZIP
    zip_path = os.path.join(output_dir, "code_archive.zip")
    print("正在打包文件...")
    
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as zipf:
        file_count = 0
        for root, dirs, files in os.walk(source_folder):
            for file in files:
                file_path = os.path.join(root, file)
                if any(file.endswith(ext) for ext in CODE_EXTENSION):
                    arcname = os.path.relpath(file_path, source_folder)
                    zipf.write(file_path, arcname)
                    file_count += 1
                    print(f"  添加文件: {arcname}")
    
    zip_size = os.path.getsize(zip_path)
    print(f"打包完成，共 {file_count} 个文件，大小: {zip_size} 字节")
    
    # 2. 读取ZIP文件并编码
    with open(zip_path, 'rb') as f:
        zip_data = f.read()
    
    encoded_data = base64.b64encode(zip_data).decode('utf-8')
    print(f"Base64编码后: {len(encoded_data)} 字符")
    
    # 3. 智能分块 - 使用单一参数控制
    chunk_size = calculate_optimal_chunk_size(len(encoded_data), TARGET_CHUNK_SIZE)
    chunks = [encoded_data[i:i+chunk_size] for i in range(0, len(encoded_data), chunk_size)]
    
    print(f"目标块大小: {TARGET_CHUNK_SIZE} 字符")
    print(f"实际块大小: {chunk_size} 字符")
    print(f"分割为 {len(chunks)} 个块")
    
    # 显示每块的实际大小
    for i, chunk in enumerate(chunks):
        print(f"  块 {i+1}: {len(chunk)} 字符")
    
    # 4. 生成QR码
    qrcode_files = []
    
    for i, chunk in enumerate(chunks):
        if len(chunks) == 1:
            # 单块直接包含数据
            qr_content = chunk
            qr_filename = "single_data.png"
            qr_label = "QR Code"
        else:
            # 多块需要序号
            qr_content = f"{i+1:02d}|{chunk}"
            qr_filename = f"data_{i+1:02d}.png"
            qr_label = f"QR Code {i+1}/{len(chunks)}"
        
        qr_path = os.path.join(output_dir, qr_filename)
        success = create_qrcode_image(qr_content, qr_path, label=qr_label)
        if success:
            qrcode_files.append(qr_filename)
            print(f"  生成: {qr_filename} ({len(qr_content)} 字符)")
    
    # 5. 生成完整的元数据（如果有多块才需要）
    zip_checksum = calculate_sha256(zip_path)
    if len(chunks) > 1:        
        metadata = {
            "total_chunks": len(chunks),
            "original_filename": f"{os.path.basename(source_folder)}.zip",
            "original_size": zip_size,
            "sha256_checksum": zip_checksum,
            "chunk_size": chunk_size
        }
        
        meta_content = f"META|{json.dumps(metadata, separators=(',', ':'))}"
        meta_path = os.path.join(output_dir, "meta.png")
        if create_qrcode_image(meta_content, meta_path, label="Meta QR Code"):
            qrcode_files.append("meta.png")
            print(f"  生成: meta.png ({len(meta_content)} 字符)")
    
    print(f"\n生成完成！文件保存在: {output_dir}")
    print(f"总共只需要 {len(qrcode_files)} 个码！")
    
    # 测试解码
    test_decode_sample(output_dir, qrcode_files[:2])
    
    
def calculate_optimal_chunk_size(total_length, target_size):
    """
    计算最优块大小
    
    Args:
        total_length: 总数据长度
        target_size: 目标块大小
    
    Returns:
        优化后的块大小
    """
    if total_length <= target_size:
        # 数据很小，一个码就够
        return total_length
    
    # 计算理想的块数量
    ideal_chunks = (total_length + target_size - 1) // target_size
    
    # 重新计算块大小，确保块大小尽可能均匀
    optimized_chunk_size = (total_length + ideal_chunks - 1) // ideal_chunks
    
    # 确保不超过目标大小太多（允许10%的浮动）
    max_allowed = int(target_size * 1.1)
    if optimized_chunk_size > max_allowed:
        optimized_chunk_size = target_size
    
    # 确保不会太小（至少是目标的70%）
    min_allowed = int(target_size * 0.7)
    if optimized_chunk_size < min_allowed and total_length > min_allowed:
        optimized_chunk_size = target_size
    
    return optimized_chunk_size


def create_qrcode_image(content, output_path, label=""):
    """生成 QR 码图像，返回是否成功"""
    try:
        # 1) 生成二维码
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=16,
            border=8,
        )
        qr.add_data(content)
        qr.make(fit=True)

        # 强制转成 RGB，避免与背景模式不一致
        qr_img = qr.make_image(fill_color="black",
                               back_color="white").convert("RGB")

        # 2) 计算整体尺寸
        border = 30
        label_height = 100 if label else 0
        final_width  = qr_img.width  + 2 * border
        final_height = qr_img.height + 2 * border + label_height

        # 3) 创建白色背景（RGB）
        bordered_img = Image.new("RGB", (final_width, final_height), "white")

        # 4) 粘贴二维码
        bordered_img.paste(qr_img, (border, border))

        # 5) 文字标签
        if label:
            draw = ImageDraw.Draw(bordered_img)
            font_size = max(40, min(final_width // 12, 36))

            # 尝试若干常见字体
            font = None
            for fname in ("arial.ttf", "Arial.ttf", "simhei.ttf",
                          "DejaVuSans.ttf"):
                try:
                    font = ImageFont.truetype(fname, font_size)
                    break
                except OSError:
                    continue
            if font is None:
                font = ImageFont.load_default()

            # 居中绘制
            text_bbox   = draw.textbbox((0, 0), label, font=font)
            text_width  = text_bbox[2] - text_bbox[0]
            text_height = text_bbox[3] - text_bbox[1]
            text_x = (final_width - text_width) // 2
            text_y = qr_img.height + 2 * border + (label_height - text_height) // 2
            draw.text((text_x, text_y), label, fill="black", font=font)

        # 6) 保存
        bordered_img.save(output_path)
        print(f"QR 码尺寸: {qr_img.width}x{qr_img.height}, 版本: {qr.version}, 标签: {label}")
        return True

    except Exception as e:
        print(f"生成失败: {e}")
        return False

def test_decode_sample(output_dir, test_files):
    """测试解码"""
    print("\n验证解码...")
    for file in test_files:
        file_path = os.path.join(output_dir, file)
        if os.path.exists(file_path):
            try:
                img = Image.open(file_path)
                decoded = pyzbar.decode(img)
                if decoded:
                    content = decoded[0].data.decode('utf-8')
                    print(f"  {file}: ✓ 解码成功 ({len(content)} 字符)")
                    # 显示前50个字符作为预览
                    preview = content[:50] + "..." if len(content) > 50 else content
                    print(f"    内容预览: {preview}")
                else:
                    print(f"  {file}: ✗ 解码失败")
            except Exception as e:
                print(f"  {file}: ✗ 错误 - {e}")

if __name__ == "__main__":
    source_folder = TARGET_FOLDER
    if not os.path.exists(source_folder):
        print("文件夹不存在！")
        exit(1)
    
    create_code_archive(source_folder)
    