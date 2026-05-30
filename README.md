# MiMo TTS Proxy

独立的小米 MiMo TTS API 中转服务，带 WebUI 管理界面。

## 功能

- 🎙️ **MiMo TTS API 代理** — 转发到小米 MiMo API
- 🌐 **WebUI 管理界面** — 音色选择、语音设计、实时预览
- 🔌 **OpenAI 兼容 API** — `/v1/audio/speech` 端点，直接对接 SillyTavern
- 🏠 **局域网监听** — 一键开启，其他设备也能用
- 📦 **独立运行** — 不依赖任何第三方应用

## 快速开始

### Windows
1. 双击 `start.bat` 启动（仅本地）
2. 双击 `start-lan.bat` 启动（局域网模式）

### 命令行
```bash
pip install -r requirements.txt
python main.py           # 仅本地 (127.0.0.1:5120)
python main.py --lan     # 局域网 (0.0.0.0:5120)
python main.py --port 8080  # 自定义端口
```

## SillyTavern 对接

1. 启动本服务
2. 打开酒馆 → TTS 设置 → Provider 选择 **OpenAI Compatible**
3. 填写：
   - **Provider Endpoint:** `http://127.0.0.1:5120/v1/audio/speech`
   - **Model:** `mimo-v2.5-tts`
   - **Voice:** `冰糖`（或其他音色名）
   - **API Key:** 留空（由代理服务管理）

## 音色列表

| 音色 | ID |
|------|-----|
| 冰糖 | bingtang |
| 茉莉 | moli |
| 知性的姐姐 | zhixing |
| 甜心少女 | tianxin |
| 阳光青年 | yangguang |
| 活泼小女 | huopo |
| 御姐 | yujie |
| 温柔小姨 | wenrou |
| 儿语姐姐 | eryu |
| 酷拽学姐 | kuzhuai |

## 语音设计

WebUI 内置 6 个语音设计预设 + 自定义指令：

- 动画配音 / 播客讲述 / 温柔安抚 / 阳光开朗 / 新闻播报 / 恐怖故事

在 WebUI 中选择预设或输入自定义描述，应用于所有合成请求。

## API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/` | GET | WebUI |
| `/v1/audio/speech` | POST | OpenAI 兼容 TTS |
| `/v1/models` | GET | 模型列表 |
| `/api/config` | GET/POST | 配置管理 |
| `/api/voices` | GET | 音色列表 |
| `/api/preview` | POST | 预览试听 |
| `/api/test` | GET | 连接测试 |

## 技术栈

- **后端:** FastAPI + uvicorn
- **前端:** 原生 HTML/CSS/JS（Raycast 暗色风格）
- **依赖:** httpx, fastapi, uvicorn
