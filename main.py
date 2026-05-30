"""
MiMo TTS Proxy Server
基于小米 MiMo 官方 API 文档实现。
https://platform.xiaomimimo.com/static/docs/usage-guide/speech-synthesis-v2.5.md
"""

import os
import json
import base64
import threading
from pathlib import Path
from typing import Optional

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response, HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# ── 配置 ──────────────────────────────────────────────

CONFIG_DIR = Path(__file__).parent / "data"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_CONFIG = {
    "api_host": "https://api.xiaomimimo.com",
    "api_key": "",
    "model": "mimo-v2.5-tts",
    "voice": "冰糖",
    "audio_format": "wav",
    "listen_lan": False,
    "port": 5120,
}

# ── 内置音色（官方文档）───────────────────────────────

BUILTIN_VOICES = [
    {"name": "冰糖", "id": "冰糖", "lang": "zh-CN", "gender": "female"},
    {"name": "茉莉", "id": "茉莉", "lang": "zh-CN", "gender": "female"},
    {"name": "苏打", "id": "苏打", "lang": "zh-CN", "gender": "male"},
    {"name": "白桦", "id": "白桦", "lang": "zh-CN", "gender": "male"},
    {"name": "Mia", "id": "Mia", "lang": "en-US", "gender": "female"},
    {"name": "Chloe", "id": "Chloe", "lang": "en-US", "gender": "female"},
    {"name": "Milo", "id": "Milo", "lang": "en-US", "gender": "male"},
    {"name": "Dean", "id": "Dean", "lang": "en-US", "gender": "male"},
]

# ── 模型列表（官方文档）───────────────────────────────

MODELS = [
    {"id": "mimo-v2.5-tts", "name": "内置音色 TTS", "desc": "使用高质量内置音色合成语音，支持唱歌、风格控制", "supports_voice_design": False},
    {"id": "mimo-v2.5-tts-voicedesign", "name": "语音设计 TTS", "desc": "通过文字描述自定义声音，无需预设或音频样本", "supports_voice_design": True},
]

# ── 风格标签预设（官方文档支持的标签）──────────────────

STYLE_PRESETS = [
    {"name": "开心", "tag": "开心", "category": "基础情感"},
    {"name": "悲伤", "tag": "悲伤", "category": "基础情感"},
    {"name": "愤怒", "tag": "愤怒", "category": "基础情感"},
    {"name": "温柔", "tag": "温柔", "category": "整体基调"},
    {"name": "冷酷", "tag": "冷酷", "category": "整体基调"},
    {"name": "活泼", "tag": "活泼", "category": "整体基调"},
    {"name": "磁性", "tag": "磁性", "category": "音色定位"},
    {"name": "甜美", "tag": "甜美", "category": "音色定位"},
    {"name": "撒娇", "tag": "撒娇", "category": "角色声线"},
    {"name": "叹气", "tag": "叹气", "category": "语音特征"},
    {"name": "微笑", "tag": "微笑", "category": "笑哭语气"},
    {"name": "唱歌", "tag": "唱歌", "category": "特殊"},
]

# ── App ───────────────────────────────────────────────

app = FastAPI(title="MiMo TTS Proxy", version="2.0.0")

STATIC_DIR = Path(__file__).parent / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

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

    model: str = "mimo-v2.5-tts"
    voice: str = "冰糖"
    input: str = ""
    response_format: str = "wav"
    speed: float = 1.0


class PreviewRequest(BaseModel):
    """预览请求"""

    text: str = "你好，这是一段测试语音。"
    voice: str = "冰糖"
    model: str = "mimo-v2.5-tts"
    style_tags: list[str] = []
    style_instruction: str = ""
    voice_design_description: str = ""


class ConfigUpdate(BaseModel):
    """配置更新"""

    api_host: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None
    voice: Optional[str] = None
    audio_format: Optional[str] = None
    listen_lan: Optional[bool] = None
    port: Optional[int] = None


# ── MiMo API 调用 ────────────────────────────────────

# 官方音色名 → ID 映射（有些音色名就是 ID）
VOICE_NAME_MAP = {v["name"]: v["id"] for v in BUILTIN_VOICES}


async def call_mimo_tts(
    text: str,
    voice: str = "冰糖",
    model: str = "mimo-v2.5-tts",
    style_tags: list[str] = None,
    style_instruction: str = "",
    api_host: str = "",
    api_key: str = "",
    audio_format: str = "wav",
) -> bytes:
    """
    调用 MiMo TTS API。

    官方 API 格式：
    - user role: 风格指令（可选，内置音色时）/ 声音描述（必填，语音设计时）
    - assistant role: 要合成的文本
    - audio.voice: 音色 ID
    """
    host = api_host or config.get("api_host", "https://api.xiaomimimo.com")
    key = api_key or config.get("api_key", "")
    mdl = model or config.get("model", "mimo-v2.5-tts")

    if not key:
        raise HTTPException(status_code=400, detail="未配置 API Key")

    # 构建 assistant content（要合成的文本）
    assistant_content = text

    # 如果有风格标签，加到文本前面
    if style_tags:
        tags_str = " ".join(f"({t})" for t in style_tags)
        assistant_content = f"{tags_str}{text}"

    # 构建 messages
    messages = []

    # user message: 风格指令或语音设计描述
    is_voicedesign = "voicedesign" in mdl
    if is_voicedesign:
        # voicedesign 模型：user 消息是声音描述（必填）
        desc = style_instruction or "一个自然流畅的声音"
        messages.append({"role": "user", "content": desc})
    elif style_instruction:
        # 内置音色模型：user 消息是风格指令（可选）
        messages.append({"role": "user", "content": style_instruction})

    # assistant message: 要合成的文本（必填）
    messages.append({"role": "assistant", "content": assistant_content})

    # 音色 ID
    voice_id = VOICE_NAME_MAP.get(voice, voice)

    url = f"{host.rstrip('/')}/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "api-key": key,
        "Authorization": f"Bearer {key}",
    }
    payload = {
        "model": mdl,
        "messages": messages,
        "audio": {
            "format": audio_format,
            "voice": voice_id,
        },
    }

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
        raise HTTPException(
            status_code=500,
            detail=f"响应格式异常: {json.dumps(data, ensure_ascii=False)[:500]}",
        )

    return base64.b64decode(audio_b64)


# ── API 路由 ──────────────────────────────────────────


@app.get("/")
async def index():
    html_file = STATIC_DIR / "index.html"
    if html_file.exists():
        return HTMLResponse(html_file.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>MiMo TTS Proxy</h1>")


@app.get("/favicon.ico")
async def favicon():
    icon = STATIC_DIR / "favicon.ico"
    if icon.exists():
        return FileResponse(icon)
    return Response(status_code=204)


@app.get("/v1/models")
async def list_models():
    return {
        "object": "list",
        "data": [{"id": m["id"], "object": "model", "owned_by": "xiaomi"} for m in MODELS],
    }


@app.post("/v1/audio/speech")
async def openai_compatible_tts(req: TTSRequest):
    """OpenAI 兼容的 TTS 端点 — SillyTavern 用这个"""
    if not req.input:
        raise HTTPException(status_code=400, detail="input 不能为空")

    # 从配置读取风格设置
    style_tags = []
    style_instruction = ""

    audio_bytes = await call_mimo_tts(
        text=req.input,
        voice=req.voice,
        model=req.model,
        style_tags=style_tags,
        style_instruction=style_instruction,
        audio_format=req.response_format or config.get("audio_format", "wav"),
    )

    media_type = "audio/wav"
    if req.response_format == "mp3":
        media_type = "audio/mpeg"
    elif req.response_format == "pcm16":
        media_type = "audio/pcm"

    return Response(content=audio_bytes, media_type=media_type)


# ── WebUI API ─────────────────────────────────────────


@app.get("/api/config")
async def get_config():
    safe = config.copy()
    if safe.get("api_key"):
        key = safe["api_key"]
        safe["api_key_masked"] = key[:4] + "****" + key[-4:] if len(key) > 8 else "****"
    else:
        safe["api_key_masked"] = ""
    return safe


@app.post("/api/config")
async def update_config(update: ConfigUpdate):
    for field, value in update.model_dump(exclude_none=True).items():
        config[field] = value
    save_config()
    return {"ok": True}


@app.get("/api/voices")
async def list_voices():
    return {
        "voices": BUILTIN_VOICES,
        "models": MODELS,
        "style_presets": STYLE_PRESETS,
    }


@app.post("/api/preview")
async def preview_voice(req: PreviewRequest):
    """预览音色（返回音频流）"""
    audio_bytes = await call_mimo_tts(
        text=req.text,
        voice=req.voice,
        model=req.model,
        style_tags=req.style_tags,
        style_instruction=req.style_instruction,
    )
    return Response(content=audio_bytes, media_type="audio/wav")


@app.get("/api/test")
async def test_connection():
    if not config.get("api_key"):
        return {"ok": False, "error": "未配置 API Key"}
    try:
        audio = await call_mimo_tts(
            text="你好，我是小米的语音助手。",
            voice="冰糖",
            model="mimo-v2.5-tts",
        )
        return {"ok": True, "size": len(audio)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/api/restart")
async def restart_server():
    import sys
    save_config()

    def do_restart():
        import time
        time.sleep(0.5)
        os.execv(sys.executable, [sys.executable] + sys.argv)

    threading.Thread(target=do_restart, daemon=True).start()
    return {"ok": True, "message": "正在重启..."}


# ── 启动 ──────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="MiMo TTS Proxy Server")
    parser.add_argument("--port", type=int, default=None, help="监听端口")
    parser.add_argument("--lan", action="store_true", default=None, help="启用局域网监听")
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
