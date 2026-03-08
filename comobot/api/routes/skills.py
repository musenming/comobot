"""Skills management endpoints."""

from __future__ import annotations

import asyncio
import shutil
import zipfile
from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel

from comobot.agent.skills import SkillsLoader
from comobot.api.deps import get_current_user
from comobot.config.loader import load_config

router = APIRouter(prefix="/api/skills")


def _get_loader() -> SkillsLoader:
    config = load_config()
    workspace = config.workspace_path
    return SkillsLoader(workspace)


@router.get("")
async def list_skills(_user: str = Depends(get_current_user)):
    """List all available skills."""
    loader = _get_loader()
    skills = loader.list_skills(filter_unavailable=False)
    result = []
    for s in skills:
        meta = loader.get_skill_metadata(s["name"]) or {}
        result.append(
            {
                "name": s["name"],
                "source": s["source"],
                "path": s["path"],
                "description": meta.get("description", ""),
                "available": loader._check_requirements(loader._get_skill_meta(s["name"])),
            }
        )
    return result


@router.get("/search")
async def search_clawhub(q: str, limit: int = 10, _user: str = Depends(get_current_user)):
    """Search clawhub for skills."""
    if not q.strip():
        raise HTTPException(status_code=400, detail="Search query required")
    if not shutil.which("npx"):
        raise HTTPException(status_code=503, detail="npx not found — Node.js required for clawhub")

    try:
        proc = await asyncio.create_subprocess_exec(
            "npx",
            "--yes",
            "clawhub@latest",
            "search",
            q.strip(),
            "--limit",
            str(limit),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        output = stdout.decode().strip()
        if proc.returncode != 0:
            raise HTTPException(
                status_code=502, detail=stderr.decode().strip() or "clawhub search failed"
            )
        # Parse output lines into results
        results = []
        for line in output.split("\n"):
            line = line.strip()
            if line:
                results.append({"raw": line})
        return {"query": q, "results": results}
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="clawhub search timed out")


class InstallRequest(BaseModel):
    slug: str


@router.post("/install")
async def install_from_clawhub(body: InstallRequest, _user: str = Depends(get_current_user)):
    """Install a skill from clawhub."""
    if not body.slug.strip():
        raise HTTPException(status_code=400, detail="Skill slug required")
    if not shutil.which("npx"):
        raise HTTPException(status_code=503, detail="npx not found — Node.js required for clawhub")

    config = load_config()
    workspace = config.workspace_path

    try:
        proc = await asyncio.create_subprocess_exec(
            "npx",
            "--yes",
            "clawhub@latest",
            "install",
            body.slug.strip(),
            "--workdir",
            str(workspace),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
        if proc.returncode != 0:
            raise HTTPException(
                status_code=502,
                detail=stderr.decode().strip() or "clawhub install failed",
            )
        return {"installed": True, "slug": body.slug, "output": stdout.decode().strip()}
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="clawhub install timed out")


@router.post("/upload")
async def upload_skill(file: UploadFile, _user: str = Depends(get_current_user)):
    """Upload a custom skill (SKILL.md or zip containing SKILL.md)."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    config = load_config()
    workspace = config.workspace_path
    skills_dir = workspace / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)

    content = await file.read()

    if file.filename.endswith(".zip"):
        try:
            with zipfile.ZipFile(BytesIO(content)) as zf:
                # Find SKILL.md in the zip
                skill_files = [n for n in zf.namelist() if n.endswith("SKILL.md")]
                if not skill_files:
                    raise HTTPException(status_code=400, detail="No SKILL.md found in zip")
                # Use the first SKILL.md's parent dir as skill name
                skill_path = skill_files[0]
                parts = Path(skill_path).parts
                skill_name = parts[0] if len(parts) > 1 else Path(skill_path).stem
                target_dir = skills_dir / skill_name
                target_dir.mkdir(parents=True, exist_ok=True)
                # Extract all files from the skill directory
                for name in zf.namelist():
                    if name.startswith(parts[0] + "/") if len(parts) > 1 else True:
                        member_path = Path(name)
                        if len(parts) > 1:
                            rel = (
                                Path(*member_path.parts[1:]) if len(member_path.parts) > 1 else None
                            )
                        else:
                            rel = member_path
                        if rel and not str(rel).startswith(".."):
                            dest = target_dir / rel
                            if name.endswith("/"):
                                dest.mkdir(parents=True, exist_ok=True)
                            else:
                                dest.parent.mkdir(parents=True, exist_ok=True)
                                dest.write_bytes(zf.read(name))
        except zipfile.BadZipFile:
            raise HTTPException(status_code=400, detail="Invalid zip file")
        return {"uploaded": True, "name": skill_name}
    elif file.filename.endswith(".md"):
        # Single SKILL.md — use filename stem or ask for name
        skill_name = (
            file.filename.replace("SKILL.md", "").strip(".").strip("_").strip("-") or "custom"
        )
        target_dir = skills_dir / skill_name
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "SKILL.md").write_bytes(content)
        return {"uploaded": True, "name": skill_name}
    else:
        raise HTTPException(status_code=400, detail="Upload SKILL.md or a .zip containing SKILL.md")


@router.get("/{name}")
async def get_skill(name: str, _user: str = Depends(get_current_user)):
    """Get skill details and content."""
    loader = _get_loader()
    content = loader.load_skill(name)
    if content is None:
        raise HTTPException(status_code=404, detail="Skill not found")
    meta = loader.get_skill_metadata(name) or {}
    skills = loader.list_skills(filter_unavailable=False)
    source = "builtin"
    for s in skills:
        if s["name"] == name:
            source = s["source"]
            break
    return {
        "name": name,
        "source": source,
        "content": content,
        "metadata": meta,
        "available": loader._check_requirements(loader._get_skill_meta(name)),
    }


@router.delete("/{name}")
async def delete_skill(name: str, _user: str = Depends(get_current_user)):
    """Delete a workspace skill (builtin skills cannot be deleted)."""
    loader = _get_loader()
    skills = loader.list_skills(filter_unavailable=False)
    target = None
    for s in skills:
        if s["name"] == name:
            target = s
            break
    if not target:
        raise HTTPException(status_code=404, detail="Skill not found")
    if target["source"] != "workspace":
        raise HTTPException(status_code=403, detail="Cannot delete built-in skills")

    skill_dir = Path(target["path"]).parent
    if skill_dir.exists():
        shutil.rmtree(skill_dir)
    return {"deleted": True, "name": name}
