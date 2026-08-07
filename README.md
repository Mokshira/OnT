# OCR 与翻译助手

一个面向 Windows 的 PyQt6 桌面工具，用于对屏幕框选区域或剪贴板图片执行 OCR 识别与翻译。应用将 OCR 与翻译拆分为两套独立的 API 配置，可分别启用、关闭和选择模型，并支持并行调用兼容 OpenAI Chat Completions 格式的多模态 API。

## 主要功能

- **屏幕框选识别**：在屏幕上拖拽框选任意区域，自动截图并提交处理。
- **框选区域复用**：保留上一次框选区域，支持右键刷新、拖动调整位置，以及通过全局快捷键刷新。
- **剪贴板图片处理**：开启监听后，检测到新的剪贴板图片会自动执行 OCR / 翻译。
- **OCR 与翻译独立执行**：OCR 和翻译可分别开启或关闭，并使用各自独立的 API Profile。
- **多套 API Profile**：OCR 与翻译配置页均支持新增、更新、删除和切换多套 API 配置。
- **模型列表拉取**：可从兼容服务的 `/v1/models` 接口拉取模型名称并填入下拉框。
- **流式结果显示**：兼容普通 JSON 响应和 SSE 流式响应，处理过程中可逐步更新显示内容。
- **悬浮翻译展示区**：翻译结果显示在桌面悬浮窗口中，支持拖拽、锁定、显示/隐藏和样式调整。
- **系统托盘**：关闭主窗口时可最小化到托盘，支持从托盘恢复、隐藏或退出。
- **本地配置持久化**：API、Prompt、快捷键和悬浮窗口样式会保存到本地 `config.json`。

## 运行环境

- Windows 10 或更高版本
- Python 3.11+
- 支持图片输入的多模态模型服务
- API 需兼容 OpenAI Chat Completions 风格接口

依赖项：

```txt
PyQt6>=6.7.0
requests>=2.32.0
Pillow>=10.3.0
```

## 启动

在项目根目录运行：

```bash
.venv\Scripts\python.exe main.py
```

项目使用根目录的 `.venv` 作为开发与测试虚拟环境。

或解压 `Releases` 的文件后直接运行。

## 项目结构

```text
OnT/
├── main.py                 # 应用启动入口
├── ocr_translator/         # 应用源码包
│   ├── app_controller.py   # 主流程与窗口协调
│   ├── api_worker.py       # API 调用与 SSE 解析
│   ├── api_utils.py        # API URL / 模型列表工具
│   ├── config_manager.py   # 配置数据与持久化
│   ├── floating_window.py  # 悬浮翻译窗口
│   ├── main_window.py      # 主窗口
│   ├── screenshot_tool.py  # 屏幕框选与截图
│   └── ...
├── assets/                 # 图标等静态资源
├── config.json             # 配置文件
├── requirements.txt
└── .venv/                  # 项目虚拟环境
```

## 快速开始

1. 启动应用。
2. 点击主窗口顶部的「展开设置」。
3. 在「识别配置」中填写 OCR API：
   - API Key
   - API Base URL
   - 模型名称
   - OCR 提示词
4. 切换到「翻译配置」，填写翻译 API：
   - API Key
   - API Base URL
   - 模型名称
   - 目标语言
   - 翻译提示词
5. 点击「保存配置」。
6. 点击「框选」，拖拽选择需要识别或翻译的屏幕区域。
7. OCR 结果会显示在主窗口中，翻译结果会显示在悬浮翻译展示区中。

## API 配置说明

应用期望服务兼容 OpenAI Chat Completions 接口。OCR 和翻译会各自向当前选中的 API Profile 发起请求。

### Base URL 规范化

保存或调用时，应用会自动规范化 Base URL：

| 用户输入 | 实际 Chat Completions URL |
| --- | --- |
| `https://example.com` | `https://example.com/v1/chat/completions` |
| `https://example.com/v1` | `https://example.com/v1/chat/completions` |
| `https://example.com/v1/chat/completions` | 保持不变 |

模型列表拉取会使用对应的 `/v1/models` 地址：

| 当前 Base URL | 模型列表 URL |
| --- | --- |
| `https://example.com` | `https://example.com/v1/models` |
| `https://example.com/v1` | `https://example.com/v1/models` |
| `https://example.com/v1/chat/completions` | `https://example.com/v1/models` |
| `https://example.com/v1/models` | 保持不变 |

### 默认配置

| 配置项 | 默认值 |
| --- | --- |
| 默认 API Profile 名称 | `默认配置` |
| 默认模型名 | `gpt-5.4` |
| 默认目标语言 | `简体中文` |
| 默认刷新快捷键 | `Ctrl+Shift+R` |
| 默认悬浮字幕字号 | `18` |
| 默认字幕颜色 | `#ffffff` |
| 默认字幕背景色 | `#000000` |
| 默认背景透明度 | `24` |

### Prompt 占位符

翻译 Prompt 支持以下占位符：

- `[目标语言]`：运行时替换为当前配置的目标语言。
- `[OCR结果]`：兼容旧版 Prompt 的占位符。当前流程会直接从图片识别并翻译，检测到该占位符时会替换为提示模型直接识别图片文本并翻译的说明。

默认 OCR Prompt：

```text
请完整提取图片中的所有文本内容。保持原有段落与换行结构。如果图片中包含数学公式，请尽量用清晰、可读的数学表达形式输出。只输出识别结果，不要添加解释。
```

默认翻译 Prompt：

```text
请完整提取图片中的所有文本内容。保持原有段落与换行结构。识别结果翻译为[目标语言]。只输出翻译后的纯文本结果，不要任何多余的解释或废话。
```

## 常用操作

### 主窗口按钮

- **框选**：开始屏幕区域截图。
- **复制 OCR 结果**：复制当前 OCR 输出到剪贴板。
- **保存配置**：保存 API、Prompt、快捷键和悬浮展示区样式。
- **OCR：开 / 关**：控制是否执行 OCR 请求。
- **翻译：开 / 关**：控制是否执行翻译请求。
- **剪贴板自动处理**：开启或关闭剪贴板图片监听。
- **翻译显示区**：显示或隐藏悬浮翻译展示区。
- **获取模型列表**：从当前配置的 API 服务拉取可用模型。
- **新增 / 更新 / 删除配置**：管理当前 OCR 或翻译配置页中的 API Profile。

### 框选区域

完成一次框选后，应用会显示可复用的区域边框：

- 拖动边框可移动框选区域。
- 右键选择「刷新」可重新截图并处理当前区域。
- 右键选择「关闭」可隐藏区域边框。
- 使用全局快捷键（默认 `Ctrl+Shift+R`）可刷新上一次框选区域。

### 剪贴板自动处理

开启「剪贴板自动处理」后：

1. 应用会立即尝试处理当前剪贴板图片。
2. 后续检测到新的剪贴板图片时，会自动执行已开启的 OCR / 翻译任务。
3. 应用会对图片内容做哈希去重，避免重复处理同一张剪贴板图片。

## 配置文件

默认配置文件名：

```text
config.json
```

配置保存位置：

- **开发环境**：项目根目录下的 `config.json`。
- **打包环境**：exe 所在目录下的 `config.json`。

配置内容包括：

- OCR API Profile 列表；
- 当前选中的 OCR API Profile；
- 翻译 API Profile 列表；
- 当前选中的翻译 API Profile；
- OCR / 翻译开关；
- 目标语言；
- OCR / 翻译 Prompt；
- 全局刷新快捷键；
- 悬浮翻译展示区样式。

