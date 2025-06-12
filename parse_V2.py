#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
#  项目名称：Sage Thief (圣人盗) – 离线文件跨机传输工具
#  文件名称：parse_V2.py
#  脚本功能：智能取景 + 透视校正 + QR 解码 + 块重组 + 校验 & 自动解压
#  版    本：v2.0.0
#  作    者：Fred YUAN
#  首次创建：2024-06-12
#  仓库地址：https://github.com/FredyHKU/sage_thief
#
#  项目目的：
#      在无法联网或网络受限的环境中，通过二维码实现文件/代码包的
#      无介质搬运；无需 U 盘、蓝牙或网络连接即可将数据安全带出。
#      本文件部署于个人电脑， 与 compress_V2.py 配合使用，自动解析手机/截图中的二维码，
#      重建原始文件并进行完整性校验，实现离线安全传输。
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
import json
import base64
import hashlib
import zipfile
from pathlib import Path
from typing import Dict, Optional

import cv2
import numpy as np
from PIL import Image
from pyzbar.pyzbar import decode as pyzbar_decode
try:
    from tqdm import tqdm
except ImportError:
    def tqdm(x, *a, **k): return x   # 无 tqdm 也能跑


###############################################################
########### 请修改这里的参数，否则无法运行后果自负！！！###########
###############################################################

QR_FOLDER  = "./photo_get"         # 拍摄/截图放这里
OUTPUT_DIR = "./reconstructed_out" # 输出目录
DEBUG_DIR  = "./debug_crop"        # 保存自动裁剪结果（可选）
os.makedirs(DEBUG_DIR, exist_ok=True)

###############################################################
# 以下为正是代码，非必要请勿修改，有必要请自行修改，自行判断！！！##
###############################################################


# ---------- 核心：智能解码 ----------
def smart_qr_decode(img_path: str, debug_save=True) -> Optional[str]:
    """
    读取一张照片 → 尝试自动定位/拉正 → 返回文本或 None
    1) 直接用 cv2.QRCodeDetector
    2) 自动找最大四边形 → 透视拉正
    3) 对拉正后的图像做多路预处理，逐一尝试 cv2 / pyzbar
    """
    img_bgr = cv2.imdecode(np.fromfile(img_path, np.uint8), cv2.IMREAD_COLOR)
    if img_bgr is None:
        print(f"❌ 读取失败: {img_path}")
        return None

    qr_det = cv2.QRCodeDetector()

    # ========= ① 原图直接尝试 =========
    val, _, _ = qr_det.detectAndDecode(img_bgr)
    if val:
        return val

    # ========= ② 自动取景（跟原来一样） =========
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    gray_blur = cv2.bilateralFilter(gray, 9, 75, 75)
    _, th = cv2.threshold(gray_blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    cnts, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    best = None; best_area = 0
    for c in cnts:
        area = cv2.contourArea(c)
        if area < 10_000:
            continue
        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.02 * peri, True)
        if len(approx) == 4 and area > best_area:
            best_area, best = area, approx.reshape(4, 2)

    if best is None:
        return None

    def order(pts):
        rect = np.zeros((4, 2), dtype="float32")
        s = pts.sum(1); diff = np.diff(pts, 1)
        rect[0] = pts[np.argmin(s)]      # 左上
        rect[2] = pts[np.argmax(s)]      # 右下
        rect[1] = pts[np.argmin(diff)]   # 右上
        rect[3] = pts[np.argmax(diff)]   # 左下
        return rect

    src = order(best)
    side = int(max(
        np.linalg.norm(src[0]-src[1]),
        np.linalg.norm(src[1]-src[2]),
        np.linalg.norm(src[2]-src[3]),
        np.linalg.norm(src[3]-src[0])
    ))
    side = np.clip(side, 400, 1600)
    dst = np.array([[0, 0], [side, 0], [side, side], [0, side]], dtype="float32")
    M = cv2.getPerspectiveTransform(src, dst)
    warp = cv2.warpPerspective(img_bgr, M, (side, side))

    if debug_save:
        dbg_name = os.path.join(DEBUG_DIR, Path(img_path).stem + "_crop.png")
        cv2.imwrite(dbg_name, warp)

    # ========= ③ 多路预处理 & 多次解码 =========
    gray = cv2.cvtColor(warp, cv2.COLOR_BGR2GRAY)

    def gen_variants(g):
        v = [g]                                   # 原始灰度
        # 3.1 CLAHE
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(g)
        v.append(clahe)
        # 3.2 自适应阈值
        adap = cv2.adaptiveThreshold(clahe, 255,
                                     cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                     cv2.THRESH_BINARY, 25, 10)
        v.append(adap)
        # 3.3 Otsu
        _, otsu = cv2.threshold(clahe, 0, 255,
                                cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        v.append(otsu)
        # 3.4 闭运算 + 锐化
        kernel = np.ones((3, 3), np.uint8)
        close = cv2.morphologyEx(adap, cv2.MORPH_CLOSE, kernel, 1)
        # 简易锐化
        sharp = cv2.addWeighted(close, 1.5, cv2.GaussianBlur(close, (0, 0), 3), -0.5, 0)
        v.append(sharp)
        # 3.5 ×2 放大
        big = cv2.resize(g, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        v.append(big)
        return v

    for g in gen_variants(gray):
        # cv2.QRCodeDetector 需要 3 通道
        attempt = cv2.cvtColor(g, cv2.COLOR_GRAY2BGR) if g.ndim == 2 else g
        val, _, _ = qr_det.detectAndDecode(attempt)
        if val:
            return val
        # pyzbar
        pil_img = Image.fromarray(g) if g.ndim == 2 else \
                  Image.fromarray(cv2.cvtColor(attempt, cv2.COLOR_BGR2RGB))
        res = pyzbar_decode(pil_img)
        if res:
            return res[0].data.decode('utf-8')

    return None
# -----------------------------------

def parse_qr_content(content: str,
                     data_chunks: Dict[int, str],
                     meta_holder: Dict[str, dict]) -> None:
    """按照新协议拆分"""
    if content.startswith("META|"):
        try:
            meta_holder["meta"] = json.loads(content[5:])
            # print("🗂  META OK")
        except json.JSONDecodeError:
            print("⚠️  META JSON 解析失败")
        return
    if "|" in content:                       # 多块
        seq, chunk = content.split("|",1)
        try:
            idx = int(seq.lstrip("0") or "0")
            data_chunks[idx] = chunk
            # print(f"📦  收到块 {idx}")
        except ValueError:
            print("⚠️  序号解析失败")
    else:                                    # 单块
        data_chunks[1] = content
        print("📦  收到单块")

def rebuild_file(meta: Optional[dict],
                 data_chunks: Dict[int, str]) -> bool:
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    if meta:
        total = meta["total_chunks"]
        if len(data_chunks) != total:
            miss = sorted(set(range(1,total+1))-data_chunks.keys())
            print(f"❌ 缺失块 {miss}")
            return False
        ordered = [data_chunks[i] for i in range(1,total+1)]
        fname, sha_expect = meta["original_filename"], meta["sha256_checksum"]
    else:
        if len(data_chunks)!=1:
            print("❌ 无 META 且多块，无法重组")
            return False
        ordered = [data_chunks[1]]
        fname, sha_expect = "recovered_file", None

    raw = base64.b64decode("".join(ordered))
    sha = hashlib.sha256(raw).hexdigest()
    if sha_expect and sha!=sha_expect:
        print("❌ SHA256 校验失败")
        return False

    out_path = os.path.join(OUTPUT_DIR,fname)
    with open(out_path,"wb") as f: f.write(raw)
    print(f"\n🎉 文件已写出 → {out_path}")

    # 自动解压 zip
    if out_path.lower().endswith(".zip"):
        with zipfile.ZipFile(out_path) as z:
            z.extractall(os.path.join(OUTPUT_DIR,Path(fname).stem))
        print("📦 ZIP 已解压")

    return True

def main():
    qr_dir = Path(QR_FOLDER)
    if not qr_dir.is_dir():
        print("❌ QR_FOLDER 不存在"); return

    data_chunks: Dict[int,str] = {}
    meta_holder: Dict[str,dict] = {}

    print("🚀 开始扫描二维码...")
    for img in tqdm(sorted(qr_dir.iterdir())):
        if img.suffix.lower() not in (".png",".jpg",".jpeg"):
            continue
        txt = smart_qr_decode(str(img))
        if txt:
            parse_qr_content(txt,data_chunks,meta_holder)
        else:
            print(f"⚠️  解析失败: {img.name}")

    if rebuild_file(meta_holder.get("meta"), data_chunks):
        print("\n🎊 完成！")
    else:
        print("\n😞 失败，请检查缺失块")

if __name__ == "__main__":
    main()