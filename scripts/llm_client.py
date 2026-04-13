"""
LLM API 调用客户端
- 凭证从 .env / 环境变量读取（禁止硬编码）
- 支持速率限制 (RPM)
- 自动重试 (JSON 解析失败时)
- 结构化 JSON 输出
"""

import json
import os
import re
import time
from pathlib import Path
from typing import Any

import requests


def _load_dotenv() -> None:
    """轻量 .env 加载器（无 python-dotenv 依赖）。仓库根目录的 .env 生效。"""
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text("utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        # 环境变量优先级高于 .env
        os.environ.setdefault(key, value)


_load_dotenv()

API_URL = os.environ.get("MIMO_API_URL", "https://api.xiaomimimo.com/v1/chat/completions")
API_KEY = os.environ.get("MIMO_API_KEY", "")
MODEL = os.environ.get("MIMO_MODEL", "mimo-v2-pro")
RPM = int(os.environ.get("MIMO_RPM", "90"))  # mimo 官方 100，冒险可上 150-200

if not API_KEY:
    raise RuntimeError(
        "MIMO_API_KEY 未设置。请复制 .env.example 为 .env 并填入真实 key，"
        "或导出环境变量 MIMO_API_KEY=..."
    )

_last_call_times: list[float] = []


def _rate_limit():
    """简单的滑动窗口 RPM 限流"""
    global _last_call_times
    now = time.time()
    # 清除 60s 之前的记录
    _last_call_times = [t for t in _last_call_times if now - t < 60]
    if len(_last_call_times) >= RPM:
        sleep_time = 60 - (now - _last_call_times[0]) + 0.1
        if sleep_time > 0:
            print(f"    ⏳ 速率限制，等待 {sleep_time:.1f}s...")
            time.sleep(sleep_time)
    _last_call_times.append(time.time())


def call_llm(system_prompt: str, user_prompt: str, temperature: float = 0.3) -> str:
    """调用 LLM API，返回原始文本响应。对 429 做长退避，最多 6 次重试。"""
    _rate_limit()

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
    }

    max_attempts = 6
    for attempt in range(max_attempts):
        try:
            resp = requests.post(API_URL, headers=headers, json=payload, timeout=180)
            # 针对 429 特殊处理：更长退避
            if resp.status_code == 429:
                # 尊重服务端 Retry-After（如果有）
                retry_after = resp.headers.get("Retry-After")
                if retry_after:
                    try:
                        wait = float(retry_after)
                    except ValueError:
                        wait = 30.0
                else:
                    # 指数退避 30/45/60/75/90 秒
                    wait = 30 + attempt * 15
                if attempt < max_attempts - 1:
                    time.sleep(wait)
                    continue
                else:
                    raise requests.exceptions.HTTPError(f"429 after {max_attempts} retries")
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except requests.exceptions.RequestException as e:
            if attempt < max_attempts - 1:
                # 普通错误：短退避
                time.sleep(3 + attempt * 2)
            else:
                raise


def call_llm_json(system_prompt: str, user_prompt: str, temperature: float = 0.3,
                  **kwargs) -> dict | list:
    """调用 LLM 并解析为 JSON，自动修复常见格式问题"""
    raw = call_llm(system_prompt, user_prompt, temperature)
    return parse_json_response(raw)


def parse_json_response(raw: str) -> Any:
    """从 LLM 响应中提取并解析 JSON，支持截断修复"""
    text = raw.strip()

    # 去掉 markdown 代码块标记
    text = re.sub(r'^```(?:json)?\s*\n?', '', text)
    text = re.sub(r'\n?```\s*$', '', text)
    text = text.strip()

    # 尝试直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 尝试找到第一个 { 或 [ 开头的 JSON
    for start_char, end_char in [('{', '}'), ('[', ']')]:
        start = text.find(start_char)
        if start == -1:
            continue
        end = text.rfind(end_char)
        if end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                continue

    # 尝试修复截断的 JSON（逐步补全闭合符号）
    for start_char, end_char in [('{', '}'), ('[', ']')]:
        start = text.find(start_char)
        if start == -1:
            continue
        fragment = text[start:]
        # 尝试补全
        for suffix in [
            ']}]}',
            '"]}]}',
            '"}]}]}',
            '"]}}',
            '"}]}',
            '"}]}'
        ]:
            try:
                return json.loads(fragment + suffix)
            except json.JSONDecodeError:
                continue

    raise ValueError(f"无法解析 JSON 响应:\n{raw[:500]}")
