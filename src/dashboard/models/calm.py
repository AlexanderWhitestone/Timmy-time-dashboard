
from datetime import datetime, date
from enum import Enum as PyEnum
from sqlalchemy import (
    Column, Integer, String, DateTime, Boolean, Enum as SQLEnum,
    Date, ForeignKey, Index, JSON
)
from sqlalchemy.orm import relationship
from .database import Base  # Assuming a shared Base in models/database.py

class TaskState(str, PyEnum):
    LATER = "LATER"
    NEXT = "NEXT"
    NOW = "NOW"
    DONE = "DONE"
    DEFERRED = "DEFERRED" # Task pushed to tomorrow

class TaskCertainty(str, PyEnum):
    FUZZY = "FUZZY" # An intention without a time
    SOFT = "SOFT"   # A flexible task with a time
    HARD = "HARD"   # A fixed meeting/appointment

class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    description = Column(String(1000), nullable=True)

    state = Column(SQLEnum(TaskState), default=TaskState.LATER, nullable=False, index=True)
    certainty = Column(SQLEnum(TaskCertainty), default=TaskCertainty.SOFT, nullable=False)
    is_mit = Column(Boolean, default=False, nullable=False) # 1-3 per day

    sort_order = Column(Integer, default=0, nullable=False)

    # Time tracking
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    deferred_at = Column(DateTime, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (Index('ix_task_state_order', 'state', 'sort_order'),)

class JournalEntry(Base):
    __tablename__ = "journal_entries"

    id = Column(Integer, primary_key=True, index=True)
    entry_date = Column(Date, unique=True, nullable=False, index=True, default=date.today)

    # Relationships to the 1-3 MITs for the day
    mit_task_ids = Column(JSON, nullable=True)

    evening_reflection = Column(String(2000), nullable=True)
    gratitude = Column(String(500), nullable=True)
    energy_level = Column(Integer, nullable=True)  # User-reported, 1-10

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
