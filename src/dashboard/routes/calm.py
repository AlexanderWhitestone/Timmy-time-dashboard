
import logging
from datetime import date, datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from dashboard.models.calm import JournalEntry, Task, TaskCertainty, TaskState
from dashboard.models.database import SessionLocal, engine, get_db, create_tables
from dashboard.templating import templates

# Ensure CALM tables exist (safe to call multiple times)
create_tables()

logger = logging.getLogger(__name__)

router = APIRouter(tags=["calm"])


# Helper functions for state machine logic
def get_now_task(db: Session) -> Optional[Task]:
    return db.query(Task).filter(Task.state == TaskState.NOW).first()

def get_next_task(db: Session) -> Optional[Task]:
    return db.query(Task).filter(Task.state == TaskState.NEXT).first()

def get_later_tasks(db: Session) -> List[Task]:
    return db.query(Task).filter(Task.state == TaskState.LATER).order_by(Task.is_mit.desc(), Task.sort_order).all()

def promote_tasks(db: Session):
    # Ensure only one NOW task exists. If multiple, demote extras to NEXT.
    now_tasks = db.query(Task).filter(Task.state == TaskState.NOW).all()
    if len(now_tasks) > 1:
        # Keep the one with highest priority/sort_order, demote others to NEXT
        now_tasks.sort(key=lambda t: (t.is_mit, t.sort_order), reverse=True)
        for task_to_demote in now_tasks[1:]:
            task_to_demote.state = TaskState.NEXT
            db.add(task_to_demote)
        db.flush() # Make changes visible

    # If no NOW task, promote NEXT to NOW
    current_now = db.query(Task).filter(Task.state == TaskState.NOW).first()
    if not current_now:
        next_task = db.query(Task).filter(Task.state == TaskState.NEXT).first()
        if next_task:
            next_task.state = TaskState.NOW
            db.add(next_task)
            db.flush() # Make changes visible

    # If no NEXT task, promote highest priority LATER to NEXT
    current_next = db.query(Task).filter(Task.state == TaskState.NEXT).first()
    if not current_next:
        later_tasks = db.query(Task).filter(Task.state == TaskState.LATER).order_by(Task.is_mit.desc(), Task.sort_order).all()
        if later_tasks:
            later_tasks[0].state = TaskState.NEXT
            db.add(later_tasks[0])

    db.commit()



# Endpoints
@router.get("/calm", response_class=HTMLResponse)
async def get_calm_view(request: Request, db: Session = Depends(get_db)):
    now_task = get_now_task(db)
    next_task = get_next_task(db)
    later_tasks_count = len(get_later_tasks(db))
    return templates.TemplateResponse(request, "calm/calm_view.html", {"now_task": now_task,
            "next_task": next_task,
            "later_tasks_count": later_tasks_count,
        },
    )


@router.get("/calm/ritual/morning", response_class=HTMLResponse)
async def get_morning_ritual_form(request: Request):
    return templates.TemplateResponse(request, "calm/morning_ritual_form.html", {})


@router.post("/calm/ritual/morning", response_class=HTMLResponse)
async def post_morning_ritual(
    request: Request,
    db: Session = Depends(get_db),
    mit1_title: str = Form(None),
    mit2_title: str = Form(None),
    mit3_title: str = Form(None),
    other_tasks: str = Form(""),
):
    # Create Journal Entry
    mit_task_ids = []
    journal_entry = JournalEntry(entry_date=date.today())
    db.add(journal_entry)
    db.commit()
    db.refresh(journal_entry)

    # Create MIT tasks
    for mit_title in [mit1_title, mit2_title, mit3_title]:
        if mit_title:
            task = Task(
                title=mit_title,
                is_mit=True,
                state=TaskState.LATER, # Initially LATER, will be promoted
                certainty=TaskCertainty.SOFT,
            )
            db.add(task)
            db.commit()
            db.refresh(task)
            mit_task_ids.append(task.id)

    journal_entry.mit_task_ids = mit_task_ids
    db.add(journal_entry)

    # Create other tasks
    for task_title in other_tasks.split('\n'):
        task_title = task_title.strip()
        if task_title:
            task = Task(
                title=task_title,
                state=TaskState.LATER,
                certainty=TaskCertainty.FUZZY,
            )
            db.add(task)

    db.commit()

    # Set initial NOW/NEXT states
    # Set initial NOW/NEXT states after all tasks are created
    if not get_now_task(db) and not get_next_task(db):
        later_tasks = db.query(Task).filter(Task.state == TaskState.LATER).order_by(Task.is_mit.desc(), Task.sort_order).all()
        if later_tasks:
            # Set the highest priority LATER task to NOW
            later_tasks[0].state = TaskState.NOW
            db.add(later_tasks[0])
            db.flush() # Flush to make the change visible for the next query

            # Set the next highest priority LATER task to NEXT
            if len(later_tasks) > 1:
                later_tasks[1].state = TaskState.NEXT
                db.add(later_tasks[1])
    db.commit() # Commit changes after initial NOW/NEXT setup

    return templates.TemplateResponse(request, "calm/calm_view.html", {"now_task": get_now_task(db),
            "next_task": get_next_task(db),
            "later_tasks_count": len(get_later_tasks(db)),
        },
    )


@router.get("/calm/ritual/evening", response_class=HTMLResponse)
async def get_evening_ritual_form(request: Request, db: Session = Depends(get_db)):
    journal_entry = db.query(JournalEntry).filter(JournalEntry.entry_date == date.today()).first()
    if not journal_entry:
        raise HTTPException(status_code=404, detail="No journal entry for today")
    return templates.TemplateResponse(
        "calm/evening_ritual_form.html", {"request": request, "journal_entry": journal_entry})


@router.post("/calm/ritual/evening", response_class=HTMLResponse)
async def post_evening_ritual(
    request: Request,
    db: Session = Depends(get_db),
    evening_reflection: str = Form(None),
    gratitude: str = Form(None),
    energy_level: int = Form(None),
):
    journal_entry = db.query(JournalEntry).filter(JournalEntry.entry_date == date.today()).first()
    if not journal_entry:
        raise HTTPException(status_code=404, detail="No journal entry for today")

    journal_entry.evening_reflection = evening_reflection
    journal_entry.gratitude = gratitude
    journal_entry.energy_level = energy_level
    db.add(journal_entry)

    # Archive any remaining active tasks
    active_tasks = db.query(Task).filter(Task.state.in_([TaskState.NOW, TaskState.NEXT, TaskState.LATER])).all()
    for task in active_tasks:
        task.state = TaskState.DEFERRED # Or DONE, depending on desired archiving logic
        task.deferred_at = datetime.utcnow()
        db.add(task)

    db.commit()

    return templates.TemplateResponse(request, "calm/evening_ritual_complete.html", {})


@router.post("/calm/tasks", response_class=HTMLResponse)
async def create_new_task(
    request: Request,
    db: Session = Depends(get_db),
    title: str = Form(...),
    description: Optional[str] = Form(None),
    is_mit: bool = Form(False),
    certainty: TaskCertainty = Form(TaskCertainty.SOFT),
):
    task = Task(
        title=title,
        description=description,
        is_mit=is_mit,
        certainty=certainty,
        state=TaskState.LATER,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    # After creating a new task, we might need to re-evaluate NOW/NEXT/LATER, but for simplicity
    # and given the spec, new tasks go to LATER. Promotion happens on completion/deferral.
    return templates.TemplateResponse(
        "calm/partials/later_count.html",
        {"request": request, "later_tasks_count": len(get_later_tasks(db))},
    )


@router.post("/calm/tasks/{task_id}/start", response_class=HTMLResponse)
async def start_task(
    request: Request,
    task_id: int,
    db: Session = Depends(get_db),
):
    current_now_task = get_now_task(db)
    if current_now_task and current_now_task.id != task_id:
        current_now_task.state = TaskState.NEXT # Demote current NOW to NEXT
        db.add(current_now_task)

    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    task.state = TaskState.NOW
    task.started_at = datetime.utcnow()
    db.add(task)
    db.commit()

    # Re-evaluate NEXT from LATER if needed
    promote_tasks(db)

    return templates.TemplateResponse(
        "calm/partials/now_next_later.html",
        {
            "request": request,
            "now_task": get_now_task(db),
            "next_task": get_next_task(db),
            "later_tasks_count": len(get_later_tasks(db)),
        },
    )


@router.post("/calm/tasks/{task_id}/complete", response_class=HTMLResponse)
async def complete_task(
    request: Request,
    task_id: int,
    db: Session = Depends(get_db),
):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    task.state = TaskState.DONE
    task.completed_at = datetime.utcnow()
    db.add(task)
    db.commit()

    promote_tasks(db)

    return templates.TemplateResponse(
        "calm/partials/now_next_later.html",
        {
            "request": request,
            "now_task": get_now_task(db),
            "next_task": get_next_task(db),
            "later_tasks_count": len(get_later_tasks(db)),
        },
    )


@router.post("/calm/tasks/{task_id}/defer", response_class=HTMLResponse)
async def defer_task(
    request: Request,
    task_id: int,
    db: Session = Depends(get_db),
):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    task.state = TaskState.DEFERRED
    task.deferred_at = datetime.utcnow()
    db.add(task)
    db.commit()

    promote_tasks(db)

    return templates.TemplateResponse(
        "calm/partials/now_next_later.html",
        {
            "request": request,
            "now_task": get_now_task(db),
            "next_task": get_next_task(db),
            "later_tasks_count": len(get_later_tasks(db)),
        },
    )


@router.get("/calm/partials/later_tasks_list", response_class=HTMLResponse)
async def get_later_tasks_list(request: Request, db: Session = Depends(get_db)):
    later_tasks = get_later_tasks(db)
    return templates.TemplateResponse(
        "calm/partials/later_tasks_list.html",
        {"request": request, "later_tasks": later_tasks},
    )


@router.post("/calm/tasks/reorder", response_class=HTMLResponse)
async def reorder_tasks(
    request: Request,
    db: Session = Depends(get_db),
    # Expecting a comma-separated string of task IDs in new order
    later_task_ids: str = Form(""),
    next_task_id: Optional[int] = Form(None),
):
    # Reorder LATER tasks
    if later_task_ids:
        ids_in_order = [int(x.strip()) for x in later_task_ids.split(',') if x.strip()]
        for index, task_id in enumerate(ids_in_order):
            task = db.query(Task).filter(Task.id == task_id).first()
            if task and task.state == TaskState.LATER:
                task.sort_order = index
                db.add(task)

    # Handle NEXT task if it's part of the reorder (e.g., moved from LATER to NEXT explicitly)
    if next_task_id:
        task = db.query(Task).filter(Task.id == next_task_id).first()
        if task and task.state == TaskState.LATER: # Only if it was a LATER task being promoted manually
            # Demote current NEXT to LATER
            current_next = get_next_task(db)
            if current_next:
                current_next.state = TaskState.LATER
                current_next.sort_order = len(get_later_tasks(db)) # Add to end of later
                db.add(current_next)

            task.state = TaskState.NEXT
            task.sort_order = 0 # NEXT tasks don't really need sort_order, but for consistency
            db.add(task)

    db.commit()

    # Re-render the relevant parts of the UI
    return templates.TemplateResponse(
        "calm/partials/now_next_later.html",
        {
            "request": request,
            "now_task": get_now_task(db),
            "next_task": get_next_task(db),
            "later_tasks_count": len(get_later_tasks(db)),
        },
    )


# Include this router in the main FastAPI app
# Already registered in src/dashboard/app.py as calm_router.
