from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.memory import MemoryJobStore
from tzlocal import get_localzone

# The behavior engine and follow campaign schedule jobs using naive datetime.now()
# (local time), so the scheduler must run in the machine's local timezone for those
# run_dates to fire when intended. A hardcoded tz would misfire by the UTC offset.
scheduler = AsyncIOScheduler(
    jobstores={"default": MemoryJobStore()},
    job_defaults={"coalesce": True, "max_instances": 1},
    timezone=get_localzone(),
)
