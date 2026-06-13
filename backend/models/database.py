import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text, event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from backend.config import settings


def _generate_id():
    return str(uuid.uuid4())


def _now():
    return datetime.utcnow()


engine = create_async_engine(settings.database_url, echo=False)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Account(Base):
    __tablename__ = "accounts"

    id = Column(String, primary_key=True, default=_generate_id)
    username = Column(String, unique=True, nullable=False)
    display_name = Column(String, default="")
    persona_id = Column(String, nullable=True)
    browser_context_dir = Column(String, default="")
    is_logged_in = Column(Boolean, default=False)
    last_session_check = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)
    behavior_enabled = Column(Boolean, default=False)
    campaign_enabled = Column(Boolean, default=False)
    created_at = Column(DateTime, default=_now)


class Persona(Base):
    __tablename__ = "personas"

    id = Column(String, primary_key=True, default=_generate_id)
    name = Column(String, nullable=False)
    tone = Column(String, default="")
    topics = Column(Text, default="[]")
    style_guide = Column(Text, default="")
    posting_frequency = Column(String, default="3-5 per day")
    example_tweets = Column(Text, default="[]")
    system_prompt = Column(Text, default="")
    created_at = Column(DateTime, default=_now)


class ContentItem(Base):
    __tablename__ = "content_items"

    id = Column(String, primary_key=True, default=_generate_id)
    account_id = Column(String, nullable=False)
    content_type = Column(String, default="tweet")
    status = Column(String, default="draft")
    body = Column(Text, default="")
    thread_items = Column(Text, nullable=True)
    target_tweet_url = Column(String, nullable=True)
    ai_meta = Column(Text, nullable=True)
    scheduled_for = Column(DateTime, nullable=True)
    posted_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    screenshot_path = Column(String, nullable=True)
    created_at = Column(DateTime, default=_now)


class AnalyticsSnapshot(Base):
    __tablename__ = "analytics_snapshots"

    id = Column(String, primary_key=True, default=_generate_id)
    account_id = Column(String, nullable=False)
    snapshot_date = Column(String, nullable=False)
    followers_count = Column(Integer, default=0)
    following_count = Column(Integer, default=0)
    tweet_count = Column(Integer, default=0)


class FollowCandidate(Base):
    __tablename__ = "follow_candidates"

    id = Column(String, primary_key=True, default=_generate_id)
    account_id = Column(String, nullable=False)
    target_username = Column(String, nullable=False)
    display_name = Column(String, default="")
    bio = Column(Text, default="")
    source_seed = Column(String, default="")
    times_seen = Column(Integer, default=1)
    status = Column(String, default="discovered")
    followed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=_now)


class BehaviorLog(Base):
    __tablename__ = "behavior_log"

    id = Column(String, primary_key=True, default=_generate_id)
    account_id = Column(String, nullable=False)
    action_type = Column(String, nullable=False)
    category = Column(String, nullable=True)
    target_url = Column(String, nullable=True)
    content_id = Column(String, nullable=True)
    status = Column(String, default="pending")
    scheduled_time = Column(DateTime, nullable=False)
    executed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_now)


class EngagementTarget(Base):
    __tablename__ = "engagement_targets"

    id = Column(String, primary_key=True, default=_generate_id)
    account_id = Column(String, nullable=False)
    target_username = Column(String, nullable=False)
    category = Column(String, default="ai")
    priority = Column(Integer, default=5)
    last_engaged = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=_now)


class ComputerUseLog(Base):
    __tablename__ = "computer_use_log"

    id = Column(String, primary_key=True, default=_generate_id)
    account_id = Column(String, nullable=True)
    task = Column(String, default="")
    actions_count = Column(Integer, default=0)
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    cost_cents = Column(Float, default=0.0)
    success = Column(Boolean, default=False)
    duration_ms = Column(Integer, default=0)
    created_at = Column(DateTime, default=_now)


@event.listens_for(engine.sync_engine, "connect")
def _set_sqlite_pragma(dbapi_connection, _connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db():
    async with async_session() as session:
        yield session
