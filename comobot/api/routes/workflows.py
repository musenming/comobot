"""Workflow CRUD and execution endpoints."""

from __future__ import annotations

import json
import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from comobot.api.deps import get_current_user, get_db
from comobot.db.connection import Database

router = APIRouter(prefix="/api/workflows")


class WorkflowCreate(BaseModel):
    name: str
    description: str = ""
    template: str | None = None
    definition: dict
    trigger_rules: dict | None = None


class WorkflowUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    definition: dict | None = None
    enabled: bool | None = None
    trigger_rules: dict | None = None


class WorkflowFromTemplate(BaseModel):
    template_id: str
    name: str
    params: dict = {}
    trigger_rules: dict | None = None


@router.get("")
async def list_workflows(
    db: Database = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    rows = await db.fetchall(
        "SELECT id, name, description, template, enabled, trigger_rules, "
        "created_at, updated_at FROM workflows ORDER BY updated_at DESC"
    )
    results = []
    for row in rows or []:
        item = dict(row)
        run_stats = await db.fetchone(
            "SELECT COUNT(*) as total, MAX(started_at) as last_run_at "
            "FROM workflow_runs WHERE workflow_id = ?",
            (row["id"],),
        )
        item["total_runs"] = run_stats["total"] if run_stats else 0
        item["last_run_at"] = run_stats["last_run_at"] if run_stats else None
        results.append(item)
    return results


@router.post("/{workflow_id}/duplicate")
async def duplicate_workflow(
    workflow_id: int,
    db: Database = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    row = await db.fetchone("SELECT * FROM workflows WHERE id = ?", (workflow_id,))
    if not row:
        raise HTTPException(status_code=404, detail="Workflow not found")
    copy_name = f"{row['name']} (copy)"
    try:
        cursor = await db.execute(
            "INSERT INTO workflows (name, description, template, definition, trigger_rules) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                copy_name,
                row["description"],
                row["template"],
                row["definition"],
                row["trigger_rules"],
            ),
        )
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail=f"Workflow '{copy_name}' already exists")
    return {"id": cursor.lastrowid, "name": copy_name}


@router.post("/{workflow_id}/run")
async def manual_run(
    workflow_id: int,
    db: Database = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    from comobot.orchestrator.engine import WorkflowEngine

    engine = WorkflowEngine(db)
    result = await engine.execute(
        workflow_id,
        {"message": "Manual trigger", "channel": "web", "chat_id": "admin"},
    )
    return result


@router.get("/templates")
async def list_templates(_user: str = Depends(get_current_user)):
    from comobot.orchestrator.templates import list_templates

    return list_templates()


@router.post("/from-template")
async def create_from_template(
    body: WorkflowFromTemplate,
    db: Database = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    from comobot.orchestrator.templates import build_from_template

    definition = build_from_template(body.template_id, body.params)
    try:
        cursor = await db.execute(
            "INSERT INTO workflows (name, template, definition, trigger_rules) VALUES (?, ?, ?, ?)",
            (
                body.name,
                body.template_id,
                json.dumps(definition),
                json.dumps(body.trigger_rules) if body.trigger_rules else None,
            ),
        )
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail=f"Workflow '{body.name}' already exists")
    return {"id": cursor.lastrowid, "name": body.name}


@router.get("/{workflow_id}")
async def get_workflow(
    workflow_id: int,
    db: Database = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    row = await db.fetchone("SELECT * FROM workflows WHERE id = ?", (workflow_id,))
    if not row:
        raise HTTPException(status_code=404, detail="Workflow not found")
    result = dict(row)
    result["definition"] = json.loads(result["definition"]) if result["definition"] else {}
    result["trigger_rules"] = json.loads(result["trigger_rules"]) if result["trigger_rules"] else {}
    return result


@router.post("")
async def create_workflow(
    body: WorkflowCreate,
    db: Database = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    try:
        cursor = await db.execute(
            "INSERT INTO workflows (name, description, template, definition, trigger_rules) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                body.name,
                body.description,
                body.template,
                json.dumps(body.definition),
                json.dumps(body.trigger_rules) if body.trigger_rules else None,
            ),
        )
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail=f"Workflow '{body.name}' already exists")
    return {"id": cursor.lastrowid, "name": body.name}


@router.put("/{workflow_id}")
async def update_workflow(
    workflow_id: int,
    body: WorkflowUpdate,
    db: Database = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    updates = []
    params = []
    if body.name is not None:
        updates.append("name = ?")
        params.append(body.name)
    if body.description is not None:
        updates.append("description = ?")
        params.append(body.description)
    if body.definition is not None:
        updates.append("definition = ?")
        params.append(json.dumps(body.definition))
    if body.enabled is not None:
        updates.append("enabled = ?")
        params.append(1 if body.enabled else 0)
    if body.trigger_rules is not None:
        updates.append("trigger_rules = ?")
        params.append(json.dumps(body.trigger_rules))

    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    updates.append("updated_at = datetime('now')")
    params.append(workflow_id)
    await db.execute(f"UPDATE workflows SET {', '.join(updates)} WHERE id = ?", tuple(params))
    return {"id": workflow_id, "updated": True}


@router.delete("/{workflow_id}")
async def delete_workflow(
    workflow_id: int,
    db: Database = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    await db.execute("DELETE FROM workflows WHERE id = ?", (workflow_id,))
    return {"deleted": True}


@router.post("/{workflow_id}/execute")
async def execute_workflow(
    workflow_id: int,
    db: Database = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    from comobot.orchestrator.engine import WorkflowEngine

    engine = WorkflowEngine(db)
    result = await engine.execute(
        workflow_id, {"message": "Manual trigger", "channel": "web", "chat_id": "admin"}
    )
    return result


@router.get("/{workflow_id}/runs")
async def get_runs(
    workflow_id: int,
    db: Database = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    return await db.fetchall(
        "SELECT * FROM workflow_runs WHERE workflow_id = ? ORDER BY started_at DESC LIMIT 50",
        (workflow_id,),
    )
