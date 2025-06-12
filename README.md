# Sage Thief 离线文件跨机传输工具  

利用二维码完成文件/代码包的离线搬运  
（`compress_V2.py` - 生成二维码；`parse_V2.py` - 解码并还原）

---

## 一、项目简介
在无法联网或网络受限的办公电脑上，将目标文件夹快速压缩并“切片”成一组**大容量二维码**；再通过手机拍照方式把图片拷贝到另一台可联网的个人电脑上完成**自动解码、完整性校验、自动解压**。  
整个过程无需 U 盘、蓝牙或任何网络连接。

```
┌── 受限电脑 ──┐                     ┌── 私人电脑 ──┐
│ compress_V2  │  →  拍照 / 发送原图  →  │ parse_V2     │
└──────────────┘                     └──────────────┘
```

---

## 二、快速开始

### 1. 克隆/下载代码
```
project/
├─ compress_V2.py   # 码片生成端
├─ parse_V2.py      # 码片解析端
```

### 2. 安装依赖  
代码在 **Python == 3.10.11** 测试通过，其他版本请自行debug，两台电脑分别创建虚拟环境后执行：

<details>
<summary>办公电脑（只需 qrcode / pyzbar）</summary>

```bash
# 推荐清华镜像，规避受限源限制
pip install "qrcode[pil]" pyzbar \
    -i http://pypi.tuna.tsinghua.edu.cn/simple \
    --trusted-host pypi.tuna.tsinghua.edu.cn
```
</details>

<details>
<summary>私人电脑（需要完整解析链）</summary>

```bash
pip install "qrcode[pil]" pyzbar opencv-python tqdm pillow numpy
```
</details>

亦可直接使用以下 `requirements.txt`（办公端只装前两行即可）：

```txt
qrcode[pil]
pyzbar
opencv-python
tqdm
numpy
Pillow
```

---

## 三、使用说明

### 3.1 生成端：`compress_V2.py`

1. **参数配置**  
   打开脚本顶部区域，按需修改：
   
   * `TARGET_FOLDER`   要打包的根目录  
   * `CODE_EXTENSION`   自定义需打包的文件类型  
   * `TARGET_CHUNK_SIZE` 建议 800-2000（字符），越大图片越少但越难扫

2. **运行脚本**
   ```bash
   python compress_V2.py
   ```
   主要流程  
   * 将 `TARGET_FOLDER` 递归打包为 ZIP（仅包含指定扩展名）  
   * Base64 编码后按最优大小自动切片  
   * 每片生成带序号的二维码 PNG，外加一张 `meta.png`（包含校验信息）  
   * 结果全部写入 `qrcode_output/`

3. **传输文件**  
   在显示器上依次打开生成的 PNG（或 PowerPoint 轮播），**使用手机相机拍“原图”**发送到个人电脑（微信文件传输需要勾选 *发送原图*）。

### 3.2 解析端：`parse_V2.py`

1. 将手机收到的所有二维码图片放入 `./photo_get/`（可新建）  
   * 支持 `.png/.jpg/.jpeg`  
   * 不要求命名顺序

2. **运行脚本**
   ```bash
   python parse_V2.py
   ```
   脚本会：
   * 智能取景、透视矫正、多重预处理 → 自动解码  
   * 按序重组，校验 SHA-256  
   * 写出原 ZIP 至 `./reconstructed_out/`，并自动解压

3. 若缺块 / 校验失败，终端会给出缺失序号，重新补拍即可。

---

## 四、目录与文件说明

```
photo_get/            # 放置需要解析的二维码照片
debug_crop/           # （解析端）存放自动裁剪后的中间图
qrcode_output/        # （生成端）输出的二维码文件
reconstructed_out/    # （解析端）最终恢复的文件及解压目录
```

---

## 五、常见问题

1. **扫码失败 / 块缺失**  
   - 增大 `TARGET_CHUNK_SIZE` 后请务必保持相机对焦清晰。  
   - 使用白底黑码；避免屏幕低亮度、摩尔纹。  
   - `parse_V2.py` 的 `DEBUG_DIR` 中会保存矫正后的方图，方便人工检查。

2. **字体缺失导致生成错误**  
   `compress_V2.py` 会自动在 `arial.ttf / simhei.ttf / DejaVuSans.ttf` 中择一；如仍报错，请将任意 TTF 放到脚本同级目录或自行修改代码。

3. **极大文件**  
   单个二维码极限容量约 4200 字符（L 级纠错，version 40）。建议保持在 2 k 字符左右，以提升扫码成功率。

拍照样例：
![6d7328929332effb80a503766c10186](https://github.com/user-attachments/assets/f521415a-5d9a-448e-9a3a-5bf2f73616ca)

---

## 六、脚本工作流程（协议简述）

```
┌──────────┐
│  Base64  │
└────┬─────┘
     │  按 n 字符切片
┌────▼─────┐
│ 序号|数据 │  (01|xxxxx)
└────┬─────┘
     │  + META|{...}  (总片数 / 校验 / 原文件名)
┌────▼─────┐
│  QRCode  │
└──────────┘
```

解析端按 `META.total_chunks` 校验所有块是否齐全 → `base64 → zip → 解压`。

---

> 至此，离线环境中的文件即可通过二维码安全、可靠地搬运到联网设备上。祝使用顺利！
> 本项目主要用于紧急情况下解决传输困境，使用者请务必遵循相关法律法规！
