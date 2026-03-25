"""REST API routes for Agent status and control (used by Comobot Remote)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from comobot.api.deps import get_current_device, get_current_user

router = APIRouter(prefix="/api/agents", tags=["agents"])


@router.get("")
async def list_agents(
    request: Request,
    _auth=Depends(get_current_user),
):
    """List all agents with their status, model, channels, last activity.

    Currently Comobot has a single main agent loop with multiple channels.
    This endpoint presents each channel-bound agent persona as a separate entry.
    """
    agent = getattr(request.app.state, "agent", None)
    channels_mgr = getattr(request.app.state, "channels", None)

    agents = []

    # Main agent info
    if agent:
        agent_info = {
            "id": "main",
            "name": getattr(agent, "name", "TinyMusen"),
            "status": "running" if agent else "sleeping",
            "model": getattr(agent, "model", None),
            "channels": [],
            "current_task": None,
            "last_active_at": None,
        }

        # Add channel information
        if channels_mgr:
            for name, channel in channels_mgr.channels.items():
                ch_status = "running" if getattr(channel, "_running", False) else "sleeping"
                agent_info["channels"].append(name)
                # Also create per-channel "agent" entries for the mobile app
                agents.append({
                    "id": f"channel:{name}",
                    "name": f"{agent_info['name']} ({name})",
                    "status": ch_status,
                    "model": agent_info["model"],
                    "channels": [name],
                    "current_task": None,
                    "last_active_at": None,
                })

        # Insert main agent at the beginning
        agents.insert(0, agent_info)
    else:
        agents.append({
            "id": "main",
            "name": "Agent",
            "status": "sleeping",
            "model": None,
            "channels": [],
            "current_task": None,
            "last_active_at": None,
        })

    return {"agents": agents}


@router.get("/{agent_id}")
async def get_agent(
    agent_id: str,
    request: Request,
    _auth=Depends(get_current_user),
):
    """Get detailed agent info including current task progress."""
    agent = getattr(request.app.state, "agent", None)

    if agent_id == "main":
        return {
            "id": "main",
            "name": getattr(agent, "name", "TinyMusen") if agent else "Agent",
            "status": "running" if agent else "sleeping",
            "model": getattr(agent, "model", None) if agent else None,
            "channels": [],
            "current_task": None,
            "progress": None,
            "recent_sessions": [],
        }

    if agent_id.startswith("channel:"):
        channel_name = agent_id[8:]
        channels_mgr = getattr(request.app.state, "channels", None)
        if channels_mgr and channel_name in channels_mgr.channels:
            channel = channels_mgr.channels[channel_name]
            return {
                "id": agent_id,
                "name": f"{getattr(agent, 'name', 'Agent')} ({channel_name})",
                "status": "running" if getattr(channel, "_running", False) else "sleeping",
                "model": getattr(agent, "model", None) if agent else None,
                "channels": [channel_name],
                "current_task": None,
                "progress": None,
                "recent_sessions": [],
            }

    raise HTTPException(status_code=404, detail="Agent not found")


@router.post("/{agent_id}/pause")
async def pause_agent(
    agent_id: str,
    request: Request,
    _auth=Depends(get_current_user),
):
    """Pause an agent (stop processing new messages)."""
    agent = getattr(request.app.state, "agent", None)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not running")

    if agent_id == "main":
        if hasattr(agent, "pause"):
            agent.pause()
        return {"status": "paused", "agent_id": agent_id}

    if agent_id.startswith("channel:"):
        channel_name = agent_id[8:]
        channels_mgr = getattr(request.app.state, "channels", None)
        if channels_mgr and channel_name in channels_mgr.channels:
            channel = channels_mgr.channels[channel_name]
            if hasattr(channel, "stop"):
                await channel.stop()
            return {"status": "paused", "agent_id": agent_id}

    raise HTTPException(status_code=404, detail="Agent not found")


@router.post("/{agent_id}/resume")
async def resume_agent(
    agent_id: str,
    request: Request,
    _auth=Depends(get_current_user),
):
    """Resume a paused agent."""
    agent = getattr(request.app.state, "agent", None)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not running")

    if agent_id == "main":
        if hasattr(agent, "resume"):
            agent.resume()
        return {"status": "running", "agent_id": agent_id}

    if agent_id.startswith("channel:"):
        channel_name = agent_id[8:]
        channels_mgr = getattr(request.app.state, "channels", None)
        if channels_mgr and channel_name in channels_mgr.channels:
            channel = channels_mgr.channels[channel_name]
            if hasattr(channel, "start"):
                await channel.start()
            return {"status": "running", "agent_id": agent_id}

    raise HTTPException(status_code=404, detail="Agent not found")
