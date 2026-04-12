"""
LLM API 调用客户端
- 支持速率限制 (RPM)
- 自动重试 (JSON 解析失败时)
- 结构化 JSON 输出
"""

import json
import time
import re
import requests
from typing import Any

API_URL = "https://api.xiaomimimo.com/v1/chat/completions"
API_KEY = "sk-c4906zis2rmob8pz4jwz0osfzwjofibknn88teohttcckvzm"
MODEL = "mimo-v2-pro"
RPM = 90  # 留 10 的余量

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
    """调用 LLM API，返回原始文本响应"""
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

    for attempt in range(3):
        try:
            resp = requests.post(API_URL, headers=headers, json=payload, timeout=180)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except requests.exceptions.RequestException as e:
            print(f"    ⚠ API 请求失败 (尝试 {attempt + 1}/3): {e}")
            if attempt < 2:
                time.sleep(5 * (attempt + 1))
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
