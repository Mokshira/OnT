# OCR 与翻译助手

一个面向 Windows 的 PyQt6 桌面工具，用于对屏幕框选区域或剪贴板图片执行 OCR 识别与翻译。应用将 OCR 与翻译拆分为两套独立的 API 配置，可分别启用、关闭和选择模型，并支持并行调用兼容 OpenAI Chat Completions 格式的多模态 API。

## 主要功能

- **屏幕框选识别**：在屏幕上拖拽框选任意区域，自动截图并提交处理。
- **框选区域复用**：保留上一次框选区域，支持右键刷新、拖动调整位置，以及通过全局快捷键刷新。
- **剪贴板图片处理**：开启监听后，检测到新的剪贴板图片会自动执行 OCR / 翻译。
- **OCR 与翻译独立执行**：OCR 和翻译可分别开启或关闭，并使用各自独立的 API Profile。
- **多套 API Profile**：OCR 与翻译配置页均支持新增、更新、删除和切换多套 API 配置。
- **模型列表拉取**：可从兼容服务的 `/v1/models` 接口拉取模型名称并填入下拉框。
- **流式结果显示**：兼容普通 JSON 响应和 SSE 流式响应；流式增量在工作线程内按时间片（默认 80ms）合并后以增量（delta）形式发送，处理中以纯文本增量追加显示，完成后再做一次完整 Markdown 渲染，整页长文输出时界面依然流畅。
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

## 安装与启动

### 开发环境

在项目根目录执行：

```bash
python -m venv .venv
.venv\Scripts\pip.exe install -r requirements.txt
```

可选：从示例配置生成本地配置（推荐，避免手写字段）：

```bash
copy config.example.json config.json
```

然后用编辑器或应用左侧导航的「API 服务」页填写真实的 `api_key`、`base_url`、`model_name`。

启动：

```bash
.venv\Scripts\python.exe main.py
```

项目使用根目录的 `.venv` 作为开发与测试虚拟环境。

### 打包版本

解压 `Releases` 中的文件后直接运行可执行文件。首次运行会在 exe 同目录生成 `config.json`；也可事先将 `config.example.json` 复制为 `config.json` 再填写密钥。

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
│   ├── main_window.py      # 主窗口（侧边栏导航 + 全部页面）
│   ├── settings_pages.py   # 窗口内设置页（API 服务 / 提示词 / 快捷键 / 关于）
│   ├── ui_widgets.py       # 通用控件（导航项、开关、分段控件、标签）
│   ├── theme.py            # 统一主题与样式
│   ├── screenshot_tool.py  # 屏幕框选与截图
│   ├── stream_utils.py     # 流式增量合并与起始门控（纯 Python，无 Qt 依赖）
│   └── ...
├── assets/                 # 图标等静态资源
├── design/                 # 新前端 UI 设计稿（React 原型，仅作界面基准）
├── tests/                  # 单元测试
├── config.example.json     # 配置示例（可提交到仓库）
├── config.json             # 本地配置（含密钥，已被 .gitignore 忽略）
├── requirements.txt
└── .venv/                  # 项目虚拟环境
```

## 快速开始

1. 按上文完成安装，并准备好 `config.json`（可从 `config.example.json` 复制）。
2. 启动应用。
3. 在左侧导航中点击「API 服务」。
4. 在「API 服务」中选择 OCR 识别，填写：
   - API Key
   - API Base URL
   - 模型名称
5. 切换到「提示词」，按需编辑 OCR 提示词；再在「API 服务」切到翻译并填写：
   - API Key
   - API Base URL
   - 模型名称
   - 目标语言
   - 翻译提示词
6. 点击「保存设置」。
7. 回到「概览」页，点击「开始框选」，拖拽选择需要识别或翻译的屏幕区域。
8. OCR 结果可在「识别结果」页查看，翻译结果会显示在悬浮翻译展示区中。

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

### 主窗口

- 左侧导航：**概览** / **识别结果** / **API 服务** / **提示词** / **快捷键** / **关于**，所有页面都在主窗口内切换，不再弹出独立设置窗口。
- 侧边栏右上角的圆形按钮可 **收起 / 展开侧边栏**；收起后仅显示图标，悬停可看到页面名称。
- **开始框选**：在概览页开始屏幕区域截图。
- **剪贴板自动处理**：开启或关闭剪贴板图片监听。
- **OCR / 翻译 / 悬浮字幕** 开关：分别控制服务启用与悬浮窗显示。
- **复制结果**：在识别结果页复制当前 OCR 输出到剪贴板。

### 设置页

- **保存设置**：每个设置页底部都有保存按钮，保存 API、Prompt、快捷键和悬浮展示区样式。
- **拉取模型**：从当前配置的 API 服务拉取可用模型。
- **新增 / 更新 / 删除**：管理当前 OCR 或翻译角色下的 API Profile。

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

| 文件 | 用途 | 是否入库 |
| --- | --- | --- |
| `config.example.json` | 字段齐全的示例配置，密钥为空 | 是 |
| `config.json` | 本地真实配置（含 API Key） | 否（`.gitignore` 已忽略） |

### 配置位置

- **开发环境**：项目根目录下的 `config.json`。
- **打包环境**：exe 所在目录下的 `config.json`。

首次启动且不存在配置文件时，应用会使用内置默认值；之后在界面中保存会写出 `config.json`。

### 安全说明

- **不要**将填有真实 `api_key` 的 `config.json` 提交到 Git 或分享给他人。
- 请以 `config.example.json` 为模板创建本地配置，只在本机填写密钥。
- 若密钥曾意外泄露，请立即在服务商控制台轮换 / 作废。

### 主要字段

| 字段 | 说明 |
| --- | --- |
| `ocr_api_configs` / `translation_api_configs` | OCR / 翻译的 API Profile 列表 |
| `selected_ocr_api_config_id` / `selected_translation_api_config_id` | 当前选中的 Profile ID |
| `ocr_enabled` / `translation_enabled` | 是否执行 OCR / 翻译 |
| `target_language` | 翻译目标语言（替换 Prompt 中的 `[目标语言]`） |
| `ocr_prompt_template` / `translation_prompt_template` | OCR / 翻译提示词 |
| `refresh_shortcut` | 刷新框选区域的全局快捷键 |
| `subtitle_font_size` / `subtitle_font_color` | 悬浮窗字号与文字颜色 |
| `subtitle_background_color` / `subtitle_background_opacity` | 悬浮窗背景色与透明度（0–100） |

单个 API Profile 字段：

| 字段 | 说明 |
| --- | --- |
| `profile_id` | 配置唯一 ID |
| `profile_name` | 显示名称 |
| `api_key` | API 密钥（可为空，用于部分本地服务） |
| `base_url` | 服务地址（见上方规范化规则） |
| `model_name` | 模型名称 |

完整示例见仓库根目录的 [`config.example.json`](./config.example.json)。

## 测试

在项目根目录、已安装依赖的环境下：

```bash
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

部分界面相关测试会使用 Qt offscreen 平台，适合在无显示器的 CI 中运行。
