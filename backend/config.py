import os
from pathlib import Path

from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
BROWSERS_DIR = DATA_DIR / "browsers"
SCREENSHOTS_DIR = DATA_DIR / "screenshots"
DB_PATH = DATA_DIR / "dashboard.db"


class Settings(BaseSettings):
    gemini_api_key: str = ""
    gcp_project_id: str = "nyayanidhi-zero"
    gcp_region: str = "us-east5"
    database_url: str = f"sqlite+aiosqlite:///{DB_PATH}"
    display_width: int = 1280
    display_height: int = 800
    computer_use_model: str = "gemini-2.5-flash"
    content_model: str = "gemini-2.5-flash"
    thread_model: str = "gemini-2.5-flash"
    max_computer_use_iterations: int = 15

    behavior_tweets_min: int = 2
    behavior_tweets_max: int = 4
    behavior_likes_min: int = 8
    behavior_likes_max: int = 15
    behavior_retweets_min: int = 2
    behavior_retweets_max: int = 5
    behavior_replies_min: int = 1
    behavior_replies_max: int = 3
    behavior_follows_min: int = 0
    behavior_follows_max: int = 1
    behavior_min_action_gap: int = 180
    behavior_weekend_modifier: float = 0.6

    follow_campaign_daily_min: int = 15
    follow_campaign_daily_max: int = 25
    follow_campaign_gap_min: int = 180
    follow_campaign_gap_max: int = 480

    dashboard_username: str = "admin"
    dashboard_password: str = ""
    jwt_secret: str = "change-me-in-production"
    allowed_origins: str = "http://localhost:5173,http://localhost:4173"

    # Public status broadcast (read-only snapshot pushed to a public GitHub repo file).
    # Leave github_token / status_repo empty to disable publishing entirely.
    github_token: str = ""
    status_repo: str = ""  # "owner/repo"
    status_branch: str = "main"
    status_path: str = "status.json"
    publish_interval_minutes: int = 30

    model_config = {"env_file": str(BASE_DIR / ".env"), "extra": "ignore"}


settings = Settings()

for d in [DATA_DIR, BROWSERS_DIR, SCREENSHOTS_DIR]:
    d.mkdir(parents=True, exist_ok=True)
