import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = PROJECT_ROOT / ".env"

DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-v4-pro"


def load_env_file(env_path=ENV_FILE):
    """Load simple KEY=VALUE pairs from .env without overriding real env vars."""
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def ask_llm(prompt, sender_name, group_name):
    """Call DeepSeek through the OpenAI-compatible SDK."""
    load_env_file()

    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("未配置 DEEPSEEK_API_KEY，请在 .env 中填写")

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("未安装 openai，请先执行 python -m pip install openai") from exc

    client = OpenAI(
        api_key=api_key,
        base_url=os.environ.get("DEEPSEEK_BASE_URL", DEFAULT_BASE_URL),
    )

    response = client.chat.completions.create(
        model=os.environ.get("DEEPSEEK_MODEL", DEFAULT_MODEL),
        messages=[
            {
                "role": "system",
                "content": "你是群聊里的AI助手，请用中文简洁、清楚、友好地回答。",
            },
            {
                "role": "user",
                "content": f"群聊名称：{group_name}\n提问用户：{sender_name}\n问题：{prompt}",
            },
        ],
        stream=False,
        reasoning_effort=os.environ.get("DEEPSEEK_REASONING_EFFORT", "high"),
        extra_body={"thinking": {"type": "enabled"}},
    )

    return response.choices[0].message.content.strip()
