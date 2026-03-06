"""Workflow execution engine."""

from __future__ import annotations

import asyncio
import json

from loguru import logger

from comobot.db.connection import Database
from comobot.orchestrator.variables import VariableContext


class WorkflowEngine:
    """Executes workflow definitions as DAG pipelines."""

    def __init__(self, db: Database, provider=None, bus=None):
        self.db = db
        self.provider = provider
        self.bus = bus

    async def execute(self, workflow_id: int, trigger_data: dict | None = None) -> dict:
        """Execute a workflow by ID."""
        row = await self.db.fetchone(
            "SELECT * FROM workflows WHERE id = ? AND enabled = 1", (workflow_id,)
        )
        if not row:
            raise ValueError(f"Workflow {workflow_id} not found or disabled")

        definition = json.loads(row["definition"])
        nodes = definition.get("nodes", [])
        edges = definition.get("edges", [])

        ctx = VariableContext()
        if trigger_data:
            for k, v in trigger_data.items():
                ctx.set(f"trigger.{k}", v)
        ctx.set("workflow.name", row["name"])

        run_id = await self._create_run(workflow_id, trigger_data)

        try:
            sorted_nodes = self._topological_sort(nodes, edges)
            for node in sorted_nodes:
                await self._execute_node(node, ctx)

            await self._finish_run(run_id, "completed", ctx)
            return {"status": "completed", "variables": ctx.to_dict()}
        except Exception as e:
            logger.error("Workflow {} failed: {}", workflow_id, e)
            await self._finish_run(run_id, "failed", ctx, str(e))
            return {"status": "failed", "error": str(e)}

    async def _execute_node(self, node: dict, ctx: VariableContext) -> None:
        """Execute a single node."""
        node_type = node.get("type", "")
        config = node.get("data", {})
        node_id = node.get("id", "unknown")

        logger.debug("Executing node {} ({})", node_id, node_type)

        if node_type == "trigger":
            pass  # Trigger data already in context

        elif node_type == "llm_call":
            await self._exec_llm(config, ctx)

        elif node_type == "tool":
            await self._exec_tool(config, ctx)

        elif node_type == "condition":
            pass  # Condition routing handled by edge traversal

        elif node_type == "response":
            await self._exec_response(config, ctx)

        elif node_type == "delay":
            delay_s = config.get("delay_seconds", 1)
            await asyncio.sleep(delay_s)

        elif node_type == "subagent":
            await self._exec_subagent(config, ctx)

    async def _exec_llm(self, config: dict, ctx: VariableContext) -> None:
        """Execute an LLM call node."""
        if not self.provider:
            ctx.set("llm.response", "[No LLM provider configured]")
            return

        prompt = ctx.resolve(config.get("system_prompt", ""))
        user_msg = ctx.resolve(config.get("user_message", "{{trigger.message}}"))
        model = config.get("model")
        temperature = config.get("temperature", 0.7)
        max_tokens = config.get("max_tokens", 2000)

        messages = []
        if prompt:
            messages.append({"role": "system", "content": prompt})
        messages.append({"role": "user", "content": user_msg})

        response = await self.provider.chat(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        ctx.set("llm.response", response.content or "")

    async def _exec_tool(self, config: dict, ctx: VariableContext) -> None:
        """Execute a tool node."""
        tool_type = config.get("tool_type", "")
        if tool_type == "http_request":
            import httpx

            url = ctx.resolve(config.get("url", ""))
            method = config.get("method", "GET").upper()
            async with httpx.AsyncClient() as client:
                resp = await client.request(method, url, timeout=30)
                ctx.set("tool.result", resp.text[:10000])
        else:
            ctx.set("tool.result", f"[Tool type '{tool_type}' not implemented]")

    async def _exec_response(self, config: dict, ctx: VariableContext) -> None:
        """Execute a response node (send message)."""
        if not self.bus:
            return
        from comobot.bus.events import OutboundMessage

        content = ctx.resolve(config.get("content", "{{llm.response}}"))
        channel = ctx.resolve(config.get("channel", "{{trigger.channel}}"))
        chat_id = ctx.resolve(config.get("chat_id", "{{trigger.chat_id}}"))
        await self.bus.publish_outbound(
            OutboundMessage(channel=channel, chat_id=chat_id, content=content)
        )

    async def _exec_subagent(self, config: dict, ctx: VariableContext) -> None:
        """Execute a subagent node."""
        ctx.set("tool.result", "[SubAgent execution not yet implemented]")

    def _topological_sort(self, nodes: list[dict], edges: list[dict]) -> list[dict]:
        """Sort nodes in DAG execution order."""
        node_map = {n["id"]: n for n in nodes}
        adj: dict[str, list[str]] = {n["id"]: [] for n in nodes}
        in_degree: dict[str, int] = {n["id"]: 0 for n in nodes}

        for edge in edges:
            src, tgt = edge["source"], edge["target"]
            if src in adj and tgt in in_degree:
                adj[src].append(tgt)
                in_degree[tgt] += 1

        queue = [nid for nid, deg in in_degree.items() if deg == 0]
        result = []
        while queue:
            nid = queue.pop(0)
            result.append(node_map[nid])
            for neighbor in adj[nid]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        return result

    async def match_trigger(self, channel: str, chat_id: str, message: str) -> int | None:
        """Check if a message matches any workflow trigger rules. Returns workflow_id or None."""
        rows = await self.db.fetchall(
            "SELECT id, trigger_rules FROM workflows WHERE enabled = 1 AND trigger_rules IS NOT NULL"
        )
        for row in rows:
            rules = json.loads(row["trigger_rules"]) if row["trigger_rules"] else {}
            if self._matches_rules(rules, channel, chat_id, message):
                return row["id"]
        return None

    @staticmethod
    def _matches_rules(rules: dict, channel: str, chat_id: str, message: str) -> bool:
        """Check if trigger rules match the incoming message."""
        if not rules:
            return False

        rule_channel = rules.get("channel")
        if rule_channel and rule_channel != channel:
            return False

        keywords = rules.get("keywords", [])
        if keywords:
            msg_lower = message.lower()
            if not any(kw.lower() in msg_lower for kw in keywords):
                return False

        prefix = rules.get("prefix")
        if prefix and not message.startswith(prefix):
            return False

        return True

    async def _create_run(self, workflow_id: int, trigger_data: dict | None) -> int:
        cursor = await self.db.execute(
            "INSERT INTO workflow_runs (workflow_id, trigger_data, status) VALUES (?, ?, 'running')",
            (workflow_id, json.dumps(trigger_data) if trigger_data else None),
        )
        return cursor.lastrowid

    async def _finish_run(
        self, run_id: int, status: str, ctx: VariableContext, error: str | None = None
    ) -> None:
        await self.db.execute(
            "UPDATE workflow_runs SET status = ?, variables = ?, error = ?, "
            "finished_at = datetime('now') WHERE id = ?",
            (status, json.dumps(ctx.to_dict()), error, run_id),
        )
