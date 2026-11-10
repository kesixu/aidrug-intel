"""集中配置。secrets 只从 .env / 环境变量读取，绝不硬编码。"""
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    # 统一 AIDRUG_ 前缀，避免 TZ/DB_PATH 这类字段名撞上系统环境变量
    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", extra="ignore", env_prefix="AIDRUG_")

    # DeepSeek（保持无前缀的惯用环境变量名）
    deepseek_api_key: str = Field(default="", validation_alias="DEEPSEEK_API_KEY")
    deepseek_base_url: str = Field(default="https://api.deepseek.com", validation_alias="DEEPSEEK_BASE_URL")
    deepseek_model_pro: str = Field(default="deepseek-flash", validation_alias="DEEPSEEK_MODEL_PRO")      # 对话/晨报/进化（2026-10-17 起与 flash 同为 V4.1 Flash）
    deepseek_model_flash: str = Field(default="deepseek-flash", validation_alias="DEEPSEEK_MODEL_FLASH")  # 批量条目分析
    # 单价（元 / 百万 token），仅用于费用估算展示，可在 .env 覆盖
    price_flash_in: float = 0.5
    price_flash_out: float = 2.0
    price_pro_in: float = 4.0
    price_pro_out: float = 16.0

    # 存储与日志
    db_path: Path = BASE_DIR / "data" / "aidrug.db"
    log_dir: Path = BASE_DIR / "workspace" / "logs"
    sources_file: Path = BASE_DIR / "config" / "sources.yml"

    # 运行行为
    tz: str = "Asia/Shanghai"
    scheduler_enabled: bool = True
    fetch_timeout: float = 20.0
    fetch_max_per_source: int = 30    # 单源单轮最多入库条数（防改版后误灌）
    analyze_batch_limit: int = 40     # 单轮 LLM 分析条数上限（防成本失控）
    content_max_chars: int = 4000     # 送入 LLM 的正文截断
    brief_hour: int = 7               # 晨报时间（北京时间）
    brief_minute: int = 30


settings = Settings()
