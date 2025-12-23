import os
import logging
from dataclasses import dataclass, field
from typing import Literal
from dotenv import load_dotenv

load_dotenv()


@dataclass
class TranscriberConfig:
    api_key: str
    model: str = "gemini-2.5-flash"
    temperature: float = 1.0
    thinking_level: Literal["low", "high"] = "low"


@dataclass
class EditorConfig:
    api_key: str
    model: str = "gemini-2.5-pro"
    temperature: float = 1.0
    thinking_level: Literal["low", "high"] = "high"
    system_prompt: str = field(default="")

    def __post_init__(self):
        if not self.system_prompt:
            self.system_prompt = DEFAULT_EDITOR_SYSTEM_PROMPT


@dataclass
class TelegramConfig:
    bot_token: str
    allowed_chat_ids: list[int] = field(default_factory=list)


@dataclass
class AppConfig:
    telegram: TelegramConfig
    transcriber: TranscriberConfig
    editor: EditorConfig
    temp_dir: str = "/tmp/omni_transcriber"
    log_level: str = "INFO"


DEFAULT_EDITOR_SYSTEM_PROMPT = """You are a professional meeting-minutes generation assistant. Upon receiving the user's raw transcript, output a structured Markdown document according to the following requirements.

## Language Rules
- **Summary and Key Points**: Always output in **Chinese**, regardless of the transcript's language
- **Transcript**: Preserve the **original language** of the speech (do not translate)

## Format

Divide into three sections with level-2 headings:

### 1. Summary (中文)
- No more than 300 Chinese characters
- Capture the main purpose, key decisions, and outcomes

### 2. Key Points (中文)
- Up to 20 concise bullet points
- Focus on actionable items, decisions, and important information

### 3. Transcript (保持原文语言)
- **Correct mistranscriptions**: Fix any clearly erroneous words or phrases based on context (output only the corrected version, do not show original errors)
- **Clean up**: Remove all fillers ("um," "uh," "嗯," "那个"), stammers, repetitions, and meaningless padding
- **Paragraph breaks**: Split by speaker change or natural topic shifts (not by rigid word/sentence counts)

## Content Requirements
- Do **not** add new information or commentary—only refine what's in the original
- Preserve full semantic integrity; do **not** alter facts

## Output Requirements
- Start directly with `## 📝 Summary`
- Output only the structured Markdown—no explanations, acknowledgments, or dialogue

## Example Structure
```markdown
## 📝 Summary
（用中文总结核心结论，不超过300字）

## ✨ Key Points
- 要点一（中文）
- 要点二（中文）
...

---

## 📄 Transcript
第一段内容，按照说话人或话题自然分段。已经修正了错误转录，去除了口头禅和重复。

第二段内容，保持原文语言输出。如果原文是英文，这里就是英文。

...
```"""


def load_config() -> AppConfig:
    """Load configuration from environment variables."""
    gemini_api_key = os.getenv("GEMINI_API_KEY", "")

    # Parse allowed chat IDs
    chat_ids_str = os.getenv("TELEGRAM_ALLOWED_CHAT_IDS", "")
    allowed_chat_ids = []
    if chat_ids_str:
        for id_str in chat_ids_str.split(","):
            id_str = id_str.strip()
            if id_str:
                try:
                    allowed_chat_ids.append(int(id_str))
                except ValueError:
                    logging.warning(f"Invalid chat ID: {id_str}")

    telegram = TelegramConfig(
        bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
        allowed_chat_ids=allowed_chat_ids,
    )

    transcriber = TranscriberConfig(
        api_key=gemini_api_key,
        model=os.getenv("TRANSCRIBER_MODEL", "gemini-2.5-flash"),
        temperature=float(os.getenv("TRANSCRIBER_TEMPERATURE", "1.0")),
        thinking_level=os.getenv("TRANSCRIBER_THINKING_LEVEL", "low"),  # type: ignore
    )

    editor = EditorConfig(
        api_key=gemini_api_key,
        model=os.getenv("EDITOR_MODEL", "gemini-2.5-pro"),
        temperature=float(os.getenv("EDITOR_TEMPERATURE", "1.0")),
        thinking_level=os.getenv("EDITOR_THINKING_LEVEL", "high"),  # type: ignore
    )

    return AppConfig(
        telegram=telegram,
        transcriber=transcriber,
        editor=editor,
        temp_dir=os.getenv("TEMP_DIR", "/tmp/omni_transcriber"),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
    )


# Global config instance
config = load_config()


def setup_logging():
    """Configure logging based on config."""
    logging.basicConfig(
        level=getattr(logging, config.log_level.upper(), logging.INFO),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
