"""
Prompt 集中化管理
- 所有 LLM prompt 写成 markdown 文件，便于 review / diff / Skill 共享
- 支持 {{include: rules/xxx.md}} 复用规则片段
- 支持 {var} 变量替换（Python str.format）
- 版本号保存在 VERSION 文件，写入 JSON 便于后续增量重跑

用法：
    from prompts import load_prompt, PROMPT_VERSION
    sys_prompt = load_prompt("words/system.md")
    user_prompt = load_prompt("words/user.md", title="...", paragraph="...", sentences_block="...")
"""

import re
from pathlib import Path

PROMPTS_DIR = Path(__file__).parent
VERSION_FILE = PROMPTS_DIR / "VERSION"
PROMPT_VERSION = VERSION_FILE.read_text("utf-8").strip() if VERSION_FILE.exists() else "v0"

_INCLUDE_RE = re.compile(r"\{\{include:\s*(\S+?)\s*\}\}")


def _resolve_includes(text: str, depth: int = 0) -> str:
    """递归展开 {{include: path}} 指令"""
    if depth > 5:
        raise RuntimeError("include 嵌套过深，疑似循环引用")

    def _replace(m: re.Match) -> str:
        path = m.group(1).strip()
        target = PROMPTS_DIR / path
        if not target.exists():
            raise FileNotFoundError(f"prompt include 未找到: {path}")
        return _resolve_includes(target.read_text("utf-8"), depth + 1)

    return _INCLUDE_RE.sub(_replace, text)


def load_prompt(name: str, **kwargs) -> str:
    """加载 prompt 文件，展开 include，填充变量"""
    path = PROMPTS_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"prompt 未找到: {name}")
    text = _resolve_includes(path.read_text("utf-8"))
    # 变量替换仅在有 kwargs 时进行（避免示例里的 {} 被误伤）
    if kwargs:
        # 转义所有 {} 成 {{}}，再把 {var_name} 恢复
        # 简化策略：仅替换用户传入的变量名，其余 {} 保持原状
        for k, v in kwargs.items():
            text = text.replace("{" + k + "}", str(v))
    return text
