import os
import logging
from dataclasses import dataclass, field
from typing import Literal
from dotenv import load_dotenv

load_dotenv(override=True)


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
class RcloneConfig:
    upload_path: str = ""  # e.g., "dropbox:/Obsidian/Transcripts"
    enabled_chat_ids: list[int] = field(default_factory=list)

    @property
    def is_enabled(self) -> bool:
        return bool(self.upload_path)


@dataclass
class AppConfig:
    telegram: TelegramConfig
    transcriber: TranscriberConfig
    editor: EditorConfig
    rclone: RcloneConfig = field(default_factory=RcloneConfig)
    temp_dir: str = "/tmp/omni_transcriber"
    log_level: str = "INFO"


DEFAULT_EDITOR_SYSTEM_PROMPT = """You are a professional meeting-minutes generation assistant. Upon receiving the user's raw transcript, output a structured Markdown document according to the following requirements.

## Language Rules
- **Title, Summary and Key Points**: Always output in **Chinese**, regardless of the transcript's language
- **Transcript**: Preserve the **original language** of the speech (do not translate)

## Format

Start with a level-1 heading (title), then divide into three sections with level-2 headings:

### Title (h1, 中文)
- Generate a concise, descriptive title (5-15 Chinese characters) that captures the main topic
- Use only Chinese characters, numbers, and basic punctuation (no special symbols or emojis)
- This title will be used as the filename, so keep it clean and filesystem-safe

### 1. Summary (中文)
- No more than 300 Chinese characters
- Capture the main purpose, key decisions, and outcomes

### 2. Key Points (中文)
- Up to 20 concise bullet points
- Focus on actionable items, decisions, and important information

### 3. Transcript (保持原文语言)
- **CRITICAL: Output the COMPLETE transcript** - Do NOT truncate, summarize, or omit any content. Every sentence from the original must appear in the output.
- **Correct mistranscriptions**: Fix only obvious speech-to-text errors (homophones, garbled words). NEVER change proper nouns, product names, version numbers, or technical terms — even if they seem incorrect
- **Clean up**: Remove all fillers ("um," "uh," "嗯," "那个"), stammers, repetitions, and meaningless padding
- **Paragraph breaks**: Split by speaker change or natural topic shifts (not by rigid word/sentence counts)

## Content Requirements
- Do **not** add new information or commentary—only refine what's in the original
- Preserve full semantic integrity; do **not** alter facts

## Output Requirements
- Start with `# ` followed by the title (no emoji in title)
- Then `## 📝 Summary`, `## ✨ Key Points`, `## 📄 Transcript`
- Output only the structured Markdown—no explanations, acknowledgments, or dialogue

## Example Structure
```markdown
# 产品需求评审会议记录

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


def _validate_thinking_level(value: str, field_name: str) -> Literal["low", "high"]:
    """Validate thinking_level value."""
    if value not in ("low", "high"):
        raise ValueError(
            f"Invalid {field_name}: '{value}'. Must be 'low' or 'high'."
        )
    return value  # type: ignore


def load_config() -> AppConfig:
    """Load configuration from environment variables."""
    # Validate required environment variables
    gemini_api_key = os.getenv("GEMINI_API_KEY", "")
    if not gemini_api_key:
        raise ValueError(
            "GEMINI_API_KEY environment variable is required. "
            "Please set it in your .env file."
        )

    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not bot_token:
        raise ValueError(
            "TELEGRAM_BOT_TOKEN environment variable is required. "
            "Please set it in your .env file."
        )

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
        bot_token=bot_token,
        allowed_chat_ids=allowed_chat_ids,
    )

    # Validate thinking levels
    transcriber_thinking = _validate_thinking_level(
        os.getenv("TRANSCRIBER_THINKING_LEVEL", "low"),
        "TRANSCRIBER_THINKING_LEVEL",
    )
    editor_thinking = _validate_thinking_level(
        os.getenv("EDITOR_THINKING_LEVEL", "high"),
        "EDITOR_THINKING_LEVEL",
    )

    transcriber = TranscriberConfig(
        api_key=gemini_api_key,
        model=os.getenv("TRANSCRIBER_MODEL", "gemini-2.5-flash"),
        temperature=float(os.getenv("TRANSCRIBER_TEMPERATURE", "1.0")),
        thinking_level=transcriber_thinking,
    )

    editor = EditorConfig(
        api_key=gemini_api_key,
        model=os.getenv("EDITOR_MODEL", "gemini-2.5-pro"),
        temperature=float(os.getenv("EDITOR_TEMPERATURE", "1.0")),
        thinking_level=editor_thinking,
    )

    # Parse rclone enabled chat IDs
    rclone_chat_ids_str = os.getenv("RCLONE_ENABLED_CHAT_IDS", "")
    rclone_enabled_chat_ids = []
    if rclone_chat_ids_str:
        for id_str in rclone_chat_ids_str.split(","):
            id_str = id_str.strip()
            if id_str:
                try:
                    rclone_enabled_chat_ids.append(int(id_str))
                except ValueError:
                    logging.warning(f"Invalid rclone chat ID: {id_str}")

    rclone = RcloneConfig(
        upload_path=os.getenv("RCLONE_UPLOAD_PATH", ""),
        enabled_chat_ids=rclone_enabled_chat_ids,
    )

    return AppConfig(
        telegram=telegram,
        transcriber=transcriber,
        editor=editor,
        rclone=rclone,
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
    # Suppress verbose fontTools logs during PDF font subsetting
    logging.getLogger("fontTools").setLevel(logging.WARNING)
