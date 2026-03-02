import pytest
import sys
from datetime import date
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

sys.path.insert(0, "/home/ubuntu/Timmy-time-dashboard/src")
from src.dashboard.app import app
from src.dashboard.models.database import Base, get_db
from src.dashboard.models.calm import Task, JournalEntry, TaskState, TaskCertainty


@pytest.fixture(name="test_db_engine")
def test_db_engine_fixture():
    # Create a new in-memory SQLite database for each test
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)  # Create tables
    yield engine
    Base.metadata.drop_all(bind=engine)  # Drop tables after test


@pytest.fixture(name="db_session")
def db_session_fixture(test_db_engine):
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_db_engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(name="client")
def client_fixture(db_session: Session):
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def test_create_task(client: TestClient, db_session: Session):
    response = client.post(
        "/calm/tasks",
        data={
            "title": "Test Task",
            "description": "This is a test description",
            "is_mit": False,
            "certainty": TaskCertainty.SOFT.value,
        },
    )
    assert response.status_code == 200
    assert "later_count-container" in response.text

    task = db_session.query(Task).filter(Task.title == "Test Task").first()
    assert task is not None
    assert task.state == TaskState.LATER
    assert task.description == "This is a test description"


def test_morning_ritual_creates_tasks_and_journal_entry(client: TestClient, db_session: Session):
    response = client.post(
        "/calm/ritual/morning",
        data={
            "mit1_title": "MIT Task 1",
            "mit2_title": "MIT Task 2",
            "other_tasks": "Other Task 1\nOther Task 2",
        },
    )
    assert response.status_code == 200
    assert "Timmy Calm" in response.text

    journal_entry = db_session.query(JournalEntry).first()
    assert journal_entry is not None
    assert len(journal_entry.mit_task_ids) == 2

    tasks = db_session.query(Task).all()
    assert len(tasks) == 4

    mit_tasks = db_session.query(Task).filter(Task.is_mit == True).all()
    assert len(mit_tasks) == 2

    now_task = db_session.query(Task).filter(Task.state == TaskState.NOW).first()
    next_task = db_session.query(Task).filter(Task.state == TaskState.NEXT).first()
    later_tasks = db_session.query(Task).filter(Task.state == TaskState.LATER).all()

    assert now_task is not None
    assert next_task is not None
    assert len(later_tasks) == 2


def test_complete_now_task_promotes_next_and_later(client: TestClient, db_session: Session):
    task_now = Task(title="Task NOW", state=TaskState.NOW, is_mit=True, sort_order=0)
    task_next = Task(title="Task NEXT", state=TaskState.NEXT, is_mit=False, sort_order=0)
    task_later1 = Task(title="Task LATER 1", state=TaskState.LATER, is_mit=True, sort_order=0)
    task_later2 = Task(title="Task LATER 2", state=TaskState.LATER, is_mit=False, sort_order=1)
    db_session.add_all([task_now, task_next, task_later1, task_later2])
    db_session.commit()
    db_session.refresh(task_now)
    db_session.refresh(task_next)
    db_session.refresh(task_later1)
    db_session.refresh(task_later2)

    response = client.post(f"/calm/tasks/{task_now.id}/complete")
    assert response.status_code == 200

    assert db_session.query(Task).filter(Task.id == task_now.id).first().state == TaskState.DONE
    assert db_session.query(Task).filter(Task.id == task_next.id).first().state == TaskState.NOW
    assert db_session.query(Task).filter(Task.id == task_later1.id).first().state == TaskState.NEXT
    assert db_session.query(Task).filter(Task.id == task_later2.id).first().state == TaskState.LATER


def test_defer_now_task_promotes_next_and_later(client: TestClient, db_session: Session):
    task_now = Task(title="Task NOW", state=TaskState.NOW, is_mit=True, sort_order=0)
    task_next = Task(title="Task NEXT", state=TaskState.NEXT, is_mit=False, sort_order=0)
    task_later1 = Task(title="Task LATER 1", state=TaskState.LATER, is_mit=True, sort_order=0)
    task_later2 = Task(title="Task LATER 2", state=TaskState.LATER, is_mit=False, sort_order=1)
    db_session.add_all([task_now, task_next, task_later1, task_later2])
    db_session.commit()
    db_session.refresh(task_now)
    db_session.refresh(task_next)
    db_session.refresh(task_later1)
    db_session.refresh(task_later2)

    response = client.post(f"/calm/tasks/{task_now.id}/defer")
    assert response.status_code == 200

    assert db_session.query(Task).filter(Task.id == task_now.id).first().state == TaskState.DEFERRED
    assert db_session.query(Task).filter(Task.id == task_next.id).first().state == TaskState.NOW
    assert db_session.query(Task).filter(Task.id == task_later1.id).first().state == TaskState.NEXT
    assert db_session.query(Task).filter(Task.id == task_later2.id).first().state == TaskState.LATER


def test_start_task_demotes_current_now_and_promotes_to_now(client: TestClient, db_session: Session):
    task_now = Task(title="Task NOW", state=TaskState.NOW, is_mit=True, sort_order=0)
    task_next = Task(title="Task NEXT", state=TaskState.NEXT, is_mit=False, sort_order=0)
    task_later1 = Task(title="Task LATER 1", state=TaskState.LATER, is_mit=True, sort_order=0)
    db_session.add_all([task_now, task_next, task_later1])
    db_session.commit()
    db_session.refresh(task_now)
    db_session.refresh(task_next)
    db_session.refresh(task_later1)

    response = client.post(f"/calm/tasks/{task_later1.id}/start")
    assert response.status_code == 200

    assert db_session.query(Task).filter(Task.id == task_later1.id).first().state == TaskState.NOW
    assert db_session.query(Task).filter(Task.id == task_now.id).first().state == TaskState.NEXT
    assert db_session.query(Task).filter(Task.id == task_next.id).first().state == TaskState.LATER


def test_evening_ritual_archives_active_tasks(client: TestClient, db_session: Session):
    journal_entry = JournalEntry(entry_date=date.today())
    db_session.add(journal_entry)
    db_session.commit()
    db_session.refresh(journal_entry)

    task_now = Task(title="Task NOW", state=TaskState.NOW)
    task_next = Task(title="Task NEXT", state=TaskState.NEXT)
    task_later = Task(title="Task LATER", state=TaskState.LATER)
    task_done = Task(title="Task DONE", state=TaskState.DONE)
    db_session.add_all([task_now, task_next, task_later, task_done])
    db_session.commit()

    response = client.post(
        "/calm/ritual/evening",
        data={
            "evening_reflection": "Reflected well",
            "gratitude": "Grateful for everything",
            "energy_level": 8,
        },
    )
    assert response.status_code == 200
    assert "Evening Ritual Complete" in response.text

    assert db_session.query(Task).filter(Task.id == task_now.id).first().state == TaskState.DEFERRED
    assert db_session.query(Task).filter(Task.id == task_next.id).first().state == TaskState.DEFERRED
    assert db_session.query(Task).filter(Task.id == task_later.id).first().state == TaskState.DEFERRED
    assert db_session.query(Task).filter(Task.id == task_done.id).first().state == TaskState.DONE

    updated_journal = db_session.query(JournalEntry).filter(JournalEntry.id == journal_entry.id).first()
    assert updated_journal.evening_reflection == "Reflected well"
    assert updated_journal.gratitude == "Grateful for everything"
    assert updated_journal.energy_level == 8


def test_reorder_later_tasks(client: TestClient, db_session: Session):
    task_later1 = Task(title="Task LATER 1", state=TaskState.LATER, sort_order=0)
    task_later2 = Task(title="Task LATER 2", state=TaskState.LATER, sort_order=1)
    task_later3 = Task(title="Task LATER 3", state=TaskState.LATER, sort_order=2)
    db_session.add_all([task_later1, task_later2, task_later3])
    db_session.commit()
    db_session.refresh(task_later1)
    db_session.refresh(task_later2)
    db_session.refresh(task_later3)

    response = client.post(
        "/calm/tasks/reorder",
        data={
            "later_task_ids": f"{task_later3.id},{task_later1.id},{task_later2.id}"
        },
    )
    assert response.status_code == 200

    assert db_session.query(Task).filter(Task.id == task_later3.id).first().sort_order == 0
    assert db_session.query(Task).filter(Task.id == task_later1.id).first().sort_order == 1
    assert db_session.query(Task).filter(Task.id == task_later2.id).first().sort_order == 2


def test_reorder_promote_later_to_next(client: TestClient, db_session: Session):
    task_now = Task(title="Task NOW", state=TaskState.NOW, is_mit=True, sort_order=0)
    task_later1 = Task(title="Task LATER 1", state=TaskState.LATER, is_mit=False, sort_order=0)
    task_later2 = Task(title="Task LATER 2", state=TaskState.LATER, is_mit=False, sort_order=1)
    db_session.add_all([task_now, task_later1, task_later2])
    db_session.commit()
    db_session.refresh(task_now)
    db_session.refresh(task_later1)
    db_session.refresh(task_later2)

    response = client.post(
        "/calm/tasks/reorder",
        data={
            "next_task_id": task_later1.id
        },
    )
    assert response.status_code == 200

    assert db_session.query(Task).filter(Task.id == task_now.id).first().state == TaskState.NOW
    assert db_session.query(Task).filter(Task.id == task_later1.id).first().state == TaskState.NEXT
    assert db_session.query(Task).filter(Task.id == task_later2.id).first().state == TaskState.LATER
