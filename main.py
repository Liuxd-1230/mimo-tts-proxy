"""
MiMo TTS Proxy Server
独立的 TTS API 中转服务，提供 WebUI 管理界面和 OpenAI 兼容 API 端点。
"""

import os
import json
import base64
import asyncio
from pathlib import Path
from typing import Optional

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# ── 配置 ──────────────────────────────────────────────

CONFIG_DIR = Path(__file__).parent / "data"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_CONFIG = {
    "api_host": "https://api.xiaomimimo.com",
    "api_key": "",
    "model": "mimo-v2.5-tts",
    "default_voice": "冰糖",
    "voice_design_mode": "",
    "voice_design_instruction": "",
    "listen_lan": False,
    "port": 5120,
}

# ── 内置音色 ──────────────────────────────────────────

BUILTIN_VOICES = [
    {"name": "冰糖", "id": "bingtang", "lang": "zh-CN"},
    {"name": "茉莉", "id": "moli", "lang": "zh-CN"},
    {"name": "知性的姐姐", "id": "zhixing", "lang": "zh-CN"},
    {"name": "甜心少女", "id": "tianxin", "lang": "zh-CN"},
    {"name": "阳光青年", "id": "yangguang", "lang": "zh-CN"},
    {"name": "活泼小女", "id": "huopo", "lang": "zh-CN"},
    {"name": "御姐", "id": "yujie", "lang": "zh-CN"},
    {"name": "温柔小姨", "id": "wenrou", "lang": "zh-CN"},
    {"name": "儿语姐姐", "id": "eryu", "lang": "zh-CN"},
    {"name": "酷拽学姐", "id": "kuzhuai", "lang": "zh-CN"},
]

VOICE_DESIGN_PRESETS = [
    {"name": "动画配音", "instruction": "声音夸张活泼，情绪饱满，有动漫角色的表演感"},
    {"name": "播客讲述", "instruction": "自然轻松，语速适中，像朋友聊天一样娓娓道来"},
    {"name": "温柔安抚", "instruction": "声音轻柔温暖，语速偏慢，像在哄人入睡"},
    {"name": "阳光开朗", "instruction": "声音明亮有活力，带着微笑的语气"},
    {"name": "新闻播报", "instruction": "字正腔圆，语速均匀，严肃正式的播音腔"},
    {"name": "恐怖故事", "instruction": "低沉压抑，偶尔压低声音制造悬念感"},
]

# ── App ───────────────────────────────────────────────

app = FastAPI(title="MiMo TTS Proxy", version="1.0.0")

# 静态文件
STATIC_DIR = Path(__file__).parent / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/favicon.ico")
async def favicon():
    from fastapi.responses import FileResponse
    icon = STATIC_DIR / "favicon.ico"
    if icon.exists():
        return FileResponse(icon)
    return Response(status_code=204)

# 全局配置
config: dict = {}


def load_config():
    global config
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            saved = json.load(f)
        config = {**DEFAULT_CONFIG, **saved}
    else:
        config = DEFAULT_CONFIG.copy()
    save_config()


def save_config():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


# ── Pydantic Models ──────────────────────────────────


class TTSRequest(BaseModel):
    """OpenAI 兼容的 TTS 请求体"""

    model: str = "mimo-tts-01"
    voice: str = "冰糖"
    input: str = ""
    response_format: str = "wav"
    speed: float = 1.0


class VoiceDesignRequest(BaseModel):
    """语音设计请求"""

    text: str = "你好，这是一段测试语音。"
    voice: str = "冰糖"
    instruction: str = ""


class ConfigUpdate(BaseModel):
    """配置更新"""

    api_host: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None
    default_voice: Optional[str] = None
    voice_design_mode: Optional[str] = None
    voice_design_instruction: Optional[str] = None
    listen_lan: Optional[bool] = None
    port: Optional[int] = None


# ── MiMo API 调用 ────────────────────────────────────


async def call_mimo_tts(
    text: str,
    voice: str = "冰糖",
    instruction: str = "",
    model: str = "mimo-tts-01",
    api_host: str = "",
    api_key: str = "",
) -> bytes:
    """调用 MiMo TTS API，返回音频 bytes"""
    host = api_host or config.get("api_host", "https://api.xiaomimimo.com")
    key = api_key or config.get("api_key", "")
    mdl = model or config.get("model", "mimo-tts-01")

    if not key:
        raise HTTPException(status_code=400, detail="未配置 API Key")

    # 构建消息
    system_content = f"Voice Name: {voice}"
    if instruction:
        system_content += f"\n{instruction}"

    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": text},
    ]

    url = f"{host.rstrip('/')}/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "api-key": key,
        "Authorization": f"Bearer {key}",
    }
    payload = {"model": mdl, "messages": messages}

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(url, json=payload, headers=headers)

    if resp.status_code != 200:
        raise HTTPException(
            status_code=resp.status_code,
            detail=f"MiMo API 错误: {resp.text[:500]}",
        )

    data = resp.json()
    try:
        audio_b64 = data["choices"][0]["message"]["audio"]["data"]
    except (KeyError, IndexError):
        raise HTTPException(status_code=500, detail=f"响应格式异常: {json.dumps(data, ensure_ascii=False)[:500]}")

    return base64.b64decode(audio_b64)


# ── API 路由 ──────────────────────────────────────────


@app.get("/")
async def index():
    """WebUI 主页"""
    html_file = STATIC_DIR / "index.html"
    if html_file.exists():
        return HTMLResponse(html_file.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>MiMo TTS Proxy</h1><p>static/index.html not found</p>")


@app.get("/v1/models")
async def list_models():
    """OpenAI 兼容：列出模型"""
    return {
        "object": "list",
        "data": [
            {"id": "mimo-v2.5-tts", "object": "model", "owned_by": "xiaomi"},
        ],
    }


@app.post("/v1/audio/speech")
async def openai_compatible_tts(req: TTSRequest):
    """OpenAI 兼容的 TTS 端点 — SillyTavern 用这个"""
    if not req.input:
        raise HTTPException(status_code=400, detail="input 不能为空")

    # 检查是否是语音设计模式的 voice
    voice = req.voice
    instruction = ""

    # 如果 voice 是预设名称，查找对应指令
    for preset in VOICE_DESIGN_PRESETS:
        if voice.startswith(preset["name"] + ":"):
            instruction = voice[len(preset["name"]) + 1 :].strip()
            voice = config.get("default_voice", "冰糖")
            break

    # 如果配置了全局语音设计
    if not instruction and config.get("voice_design_mode"):
        if config["voice_design_mode"] == "custom":
            instruction = config.get("voice_design_instruction", "")
        else:
            for preset in VOICE_DESIGN_PRESETS:
                if preset["name"] == config["voice_design_mode"]:
                    instruction = preset["instruction"]
                    break

    audio_bytes = await call_mimo_tts(
        text=req.input,
        voice=voice,
        instruction=instruction,
        model=req.model,
    )

    # 根据请求格式返回
    media_type = "audio/wav"
    if req.response_format == "mp3":
        media_type = "audio/mpeg"
    elif req.response_format == "opus":
        media_type = "audio/ogg"

    return Response(content=audio_bytes, media_type=media_type)


# ── WebUI API ─────────────────────────────────────────


@app.get("/api/config")
async def get_config():
    """获取当前配置（隐藏 API Key）"""
    safe = config.copy()
    if safe.get("api_key"):
        key = safe["api_key"]
        safe["api_key_masked"] = key[:4] + "****" + key[-4:] if len(key) > 8 else "****"
    else:
        safe["api_key_masked"] = ""
    return safe


@app.post("/api/config")
async def update_config(update: ConfigUpdate):
    """更新配置"""
    for field, value in update.model_dump(exclude_none=True).items():
        config[field] = value
    save_config()
    return {"ok": True}


@app.get("/api/voices")
async def list_voices():
    """列出所有音色"""
    return {"voices": BUILTIN_VOICES, "design_presets": VOICE_DESIGN_PRESETS}


@app.post("/api/preview")
async def preview_voice(req: VoiceDesignRequest):
    """预览音色（返回音频流）"""
    audio_bytes = await call_mimo_tts(
        text=req.text,
        voice=req.voice,
        instruction=req.instruction,
    )
    return Response(content=audio_bytes, media_type="audio/wav")


@app.get("/api/test")
async def test_connection():
    """测试 API 连接"""
    if not config.get("api_key"):
        return {"ok": False, "error": "未配置 API Key"}
    try:
        audio = await call_mimo_tts(text="测试连接", voice="冰糖")
        return {"ok": True, "size": len(audio)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/api/restart")
async def restart_server():
    """重启服务（通过重新执行当前进程）"""
    import sys
    import os

    save_config()
    # 延迟重启，让响应先返回
    def do_restart():
        import time
        time.sleep(0.5)
        os.execv(sys.executable, [sys.executable] + sys.argv)

    import threading
    threading.Thread(target=do_restart, daemon=True).start()
    return {"ok": True, "message": "正在重启..."}


# ── 启动 ──────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="MiMo TTS Proxy Server")
    parser.add_argument("--port", type=int, default=None, help="监听端口")
    parser.add_argument("--lan", action="store_true", default=None, help="启用局域网监听 (0.0.0.0)")
    parser.add_argument("--host", type=str, default=None, help="监听地址")
    args = parser.parse_args()

    load_config()

    port = args.port or config.get("port", 5120)
    if args.host:
        host = args.host
    elif args.lan or config.get("listen_lan"):
        host = "0.0.0.0"
    else:
        host = "127.0.0.1"

    print(f"\n🎙️  MiMo TTS Proxy Server")
    print(f"   地址: http://{host}:{port}")
    print(f"   WebUI: http://{host}:{port}/")
    print(f"   API:   http://{host}:{port}/v1/audio/speech")
    print(f"   局域网: {'✅ 已启用' if host == '0.0.0.0' else '❌ 仅本地'}\n")

    uvicorn.run(app, host=host, port=port, log_level="info")
