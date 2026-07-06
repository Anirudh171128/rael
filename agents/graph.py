from __future__ import annotations

import importlib
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import yaml

logger = logging.getLogger(__name__)

# ─── Paths ──────────────────────────────────────────────────────────────────
SPEC_PATH = Path(__file__).resolve().parent.parent / "rael.yaml"
END = "__end__"


# ─── Data structures ────────────────────────────────────────────────────────
@dataclass
class MessageEnvelope:
    """The typed envelope every agent-to-agent handoff uses (§2 of the spec)."""
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    correlation_id: str = ""
    sender: str = ""
    recipient: str = ""
    type: str = "event"          # event | command | escalation | data_update
    payload: dict = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class AgentSpec:
    """Parsed agent definition from the YAML."""
    name: str
    module_path: str
    function_name: str | None = None
    functions: dict[str, str] = field(default_factory=dict)
    role: str = ""
    triggers: list = field(default_factory=list)
    reads: list[str] = field(default_factory=list)
    writes: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    constraints: dict = field(default_factory=dict)
    config: dict = field(default_factory=dict)
    gates: list[dict] = field(default_factory=list)
    human_gate: dict | None = None
    routing: list[dict] = field(default_factory=list)
    emits_message: dict | None = None
    status: str = "active"

    # Resolved at boot
    _module: Any = field(default=None, repr=False)
    _run_fn: Callable | None = field(default=None, repr=False)
    _extra_fns: dict[str, Callable] = field(default_factory=dict, repr=False)


@dataclass
class PipelineStep:
    node: str
    next_on: dict[str, str] = field(default_factory=dict)
    type: str = "agent"
    condition: str = ""
    true_action: str = ""
    false_action: str = ""
    next: str = ""
    post_action: str = ""


@dataclass
class PipelineSpec:
    name: str
    description: str
    entry_event: str
    requires: list[str] = field(default_factory=list)
    steps: list[PipelineStep] = field(default_factory=list)


@dataclass
class ToolSpec:
    name: str
    module_path: str
    function_name: str
    description: str = ""
    _fn: Callable | None = field(default=None, repr=False)


# ─── Graph Engine ────────────────────────────────────────────────────────────
class GraphEngine:
    """Reads rael.yaml and provides the runtime dispatch for the entire
    multi-agent system."""

    def __init__(self, spec_path: Path = SPEC_PATH):
        self.spec_path = spec_path
        self.raw: dict = {}
        self.agents: dict[str, AgentSpec] = {}
        self.tools: dict[str, ToolSpec] = {}
        self.pipelines: dict[str, PipelineSpec] = {}
        self.static_edges: list[tuple[str, str]] = []
        self.conditional_edges: list[dict] = []
        self.scheduled_jobs: list[dict] = []
        self.human_checkpoints: list[dict] = []
        self.message_bus: list[MessageEnvelope] = []     # in-process event bus
        self._loaded = False

    # ── Boot ──────────────────────────────────────────────────────────────
    def load(self) -> None:
        """Parse YAML, resolve all module/tool references, build routing tables."""
        with open(self.spec_path) as f:
            self.raw = yaml.safe_load(f)

        self._load_tools()
        self._load_agents()
        self._load_edges()
        self._load_pipelines()
        self.scheduled_jobs = self.raw.get("scheduled_jobs", [])
        self.human_checkpoints = self.raw.get("human_checkpoints", [])
        self._loaded = True
        logger.info(
            "GraphEngine loaded: %d agents, %d tools, %d pipelines, %d edges",
            len(self.agents), len(self.tools), len(self.pipelines),
            len(self.static_edges) + len(self.conditional_edges),
        )

    def _load_tools(self) -> None:
        for name, spec in self.raw.get("tools", {}).items():
            tool = ToolSpec(
                name=name,
                module_path=spec["module"],
                function_name=spec["function"],
                description=spec.get("description", ""),
            )
            try:
                mod = importlib.import_module(tool.module_path)
                tool._fn = getattr(mod, tool.function_name)
            except (ImportError, AttributeError) as e:
                logger.warning("Tool '%s' could not resolve %s.%s: %s",
                               name, tool.module_path, tool.function_name, e)
            self.tools[name] = tool

    def _load_agents(self) -> None:
        for name, spec in self.raw.get("agents", {}).items():
            agent = AgentSpec(
                name=name,
                module_path=spec.get("module", ""),
                function_name=spec.get("function"),
                functions=spec.get("functions", {}),
                role=spec.get("role", ""),
                triggers=spec.get("triggers", []),
                reads=spec.get("reads", []),
                writes=spec.get("writes", []),
                tools=spec.get("tools", []),
                constraints=spec.get("constraints", {}),
                config=spec.get("config", {}),
                gates=spec.get("gates", []),
                human_gate=spec.get("human_gate"),
                routing=spec.get("routing", []),
                emits_message=spec.get("emits_message"),
                status=spec.get("status", "active"),
            )
            # Resolve the Python module and callable(s).
            try:
                agent._module = importlib.import_module(agent.module_path)
                if agent.function_name:
                    agent._run_fn = getattr(agent._module, agent.function_name)
                for alias, fn_name in agent.functions.items():
                    agent._extra_fns[alias] = getattr(agent._module, fn_name)
            except (ImportError, AttributeError) as e:
                logger.warning("Agent '%s' module resolution failed: %s", name, e)
            self.agents[name] = agent

    def _load_edges(self) -> None:
        edges = self.raw.get("edges", {})
        for e in edges.get("static", []):
            self.static_edges.append((e["from"], e["to"]))
        self.conditional_edges = edges.get("conditional", [])

    def _load_pipelines(self) -> None:
        for name, spec in self.raw.get("pipelines", {}).items():
            steps = []
            for s in spec.get("steps", []):
                steps.append(PipelineStep(
                    node=s["node"],
                    next_on=s.get("next_on", {}),
                    type=s.get("type", "agent"),
                    condition=s.get("condition", ""),
                    true_action=s.get("true_action", ""),
                    false_action=s.get("false_action", ""),
                    next=s.get("next", ""),
                    post_action=s.get("post_action", ""),
                ))
            self.pipelines[name] = PipelineSpec(
                name=name,
                description=spec.get("description", ""),
                entry_event=spec.get("entry_event", name),
                requires=spec.get("requires", []),
                steps=steps,
            )

    # ── Runtime: tool invocation ──────────────────────────────────────────
    def get_tool(self, name: str) -> Callable | None:
        """Resolve a tool name to its callable. Returns None if not found."""
        tool = self.tools.get(name)
        return tool._fn if tool else None

    def get_agent_tools(self, agent_name: str) -> dict[str, Callable]:
        """Return the {name: fn} map of tools available to an agent."""
        agent = self.agents.get(agent_name)
        if not agent:
            return {}
        return {
            t: self.tools[t]._fn
            for t in agent.tools
            if t in self.tools and self.tools[t]._fn is not None
        }

    # ── Runtime: message bus ──────────────────────────────────────────────
    def emit(self, sender: str, recipient: str, msg_type: str,
             payload: dict, correlation_id: str = "") -> MessageEnvelope:
        """Emit a message onto the in-process bus."""
        env = MessageEnvelope(
            correlation_id=correlation_id or str(uuid.uuid4()),
            sender=sender,
            recipient=recipient,
            type=msg_type,
            payload=payload,
        )
        self.message_bus.append(env)
        logger.debug("Message %s → %s (%s): %s",
                      sender, recipient, msg_type, list(payload.keys()))
        return env

    def consume(self, recipient: str, msg_type: str | None = None) -> list[MessageEnvelope]:
        """Consume (pop) messages addressed to `recipient`."""
        matched = []
        remaining = []
        for msg in self.message_bus:
            if msg.recipient == recipient and (msg_type is None or msg.type == msg_type):
                matched.append(msg)
            else:
                remaining.append(msg)
        self.message_bus = remaining
        return matched

    # ── Runtime: edge resolution ──────────────────────────────────────────
    def resolve_next(self, from_node: str, state: dict) -> str:
        """Given the current node and state, resolve which node executes next
        by evaluating conditional edges, falling back to static edges."""
        # 1. Check conditional edges first.
        for edge in self.conditional_edges:
            if edge["from"] != from_node:
                continue
            field_path = edge["condition_field"]
            value = self._get_nested(state, field_path)
            routes = edge.get("routes", {})
            str_value = str(value).lower() if value is not None else ""
            if str_value in routes:
                return routes[str_value]

        # 2. Fall back to static edges.
        for src, dst in self.static_edges:
            if src == from_node:
                return dst

        return END

    def _get_nested(self, d: dict, path: str) -> Any:
        """Resolve 'outreach.approved' → d['outreach']['approved']."""
        keys = path.split(".")
        cur = d
        for k in keys:
            if isinstance(cur, dict):
                cur = cur.get(k)
            else:
                return None
        return cur

    # ── Runtime: agent execution ──────────────────────────────────────────
    async def invoke_agent(self, agent_name: str, *args, **kwargs) -> Any:
        """Call an agent's run function with the given arguments."""
        agent = self.agents.get(agent_name)
        if not agent:
            raise ValueError(f"Unknown agent: {agent_name}")
        fn = agent._run_fn
        if fn is None:
            raise ValueError(f"Agent '{agent_name}' has no run function resolved")
        return await fn(*args, **kwargs)

    async def invoke_agent_fn(self, agent_name: str, fn_alias: str, *args, **kwargs) -> Any:
        """Call a named sub-function on an agent (e.g. reporting_agent.morning)."""
        agent = self.agents.get(agent_name)
        if not agent:
            raise ValueError(f"Unknown agent: {agent_name}")
        fn = agent._extra_fns.get(fn_alias)
        if fn is None:
            raise ValueError(f"Agent '{agent_name}' has no function '{fn_alias}'")
        return await fn(*args, **kwargs)

    # ── Runtime: pipeline execution ───────────────────────────────────────
    async def run_pipeline(self, pipeline_name: str, state: dict) -> dict:
        """Execute a named pipeline by walking its steps, using next_on routing
        from each agent's result to determine the next step."""
        pipeline = self.pipelines.get(pipeline_name)
        if not pipeline:
            raise ValueError(f"Unknown pipeline: {pipeline_name}")

        state.setdefault("trail", [])
        step_idx = 0
        steps = pipeline.steps

        while step_idx < len(steps):
            step = steps[step_idx]
            node = step.node
            state["trail"].append(node)

            # Decision gate (inline condition, not a real agent).
            if step.type == "decision_gate":
                from backend.app.config import settings
                from backend.app.events import log_event

                condition_met = self._eval_condition(step.condition, state, settings)
                action = step.true_action if condition_met else step.false_action
                score = state.get("score")
                lead_id = state.get("lead_id")

                await log_event(
                    "Orchestrator", "gate",
                    f"Lead {lead_id} qualified (score {score}) → decision: "
                    + ("hold for rep approval" if action == "hold_for_approval" else "execute outreach autonomously"),
                    lead_id=lead_id,
                    level="attention" if action == "hold_for_approval" else "info",
                )
                # Gate always proceeds to the next node.
                next_node = step.next or END
                step_idx = self._find_step(steps, next_node, step_idx)
                continue

            # Regular agent node.
            result = await self._invoke_pipeline_step(node, state)

            # Determine the next action hint from the agent's result.
            next_action = getattr(result, "next_action", None) or "default"
            # Merge any data the agent returned into state.
            if hasattr(result, "data") and isinstance(result.data, dict):
                state.update(result.data)

            # Emit message if the agent spec says so.
            agent_spec = self.agents.get(node)
            if agent_spec and agent_spec.emits_message:
                self.emit(
                    sender=node,
                    recipient=agent_spec.emits_message.get("recipient", "orchestrator"),
                    msg_type=agent_spec.emits_message.get("type", "event"),
                    payload={k: state.get(k) for k in agent_spec.emits_message.get("payload", [])},
                    correlation_id=str(state.get("lead_id", "")),
                )

            # Post-action after discovery/signals: GUARDRAIL — never auto-enrich.
            # Apollo credits are spent only after the rep approves, so new leads
            # raise an enrichment request instead of entering lead_pipeline.
            # (POST /api/leads/{id}/enrich is the only path that runs it.)
            if step.post_action in ("pipeline_new_leads", "request_enrichment"):
                await self._request_enrichment(state.get("created_lead_ids", []))

            # Route to the next step.
            next_node = step.next_on.get(next_action, step.next_on.get("default", END))
            if next_node == END:
                break
            step_idx = self._find_step(steps, next_node, step_idx)

        return state

    async def _request_enrichment(self, lead_ids: list[int]) -> None:
        """Ask the human before spending Apollo credits on freshly found leads.

        Logs an attention event and pushes an `enrich_request` over the WebSocket
        so the dashboard pops the approval prompt the moment companies land."""
        if not lead_ids:
            return
        from sqlalchemy import select

        from backend.app.database import SessionLocal
        from backend.app.events import log_event
        from backend.app.models import Lead
        from backend.app.websocket import manager

        async with SessionLocal() as s:
            leads = (
                await s.execute(select(Lead).where(Lead.id.in_(lead_ids)))
            ).scalars().all()
            summary = [
                {
                    "lead_id": l.id,
                    "company_name": l.company_name,
                    "fit_score": l.fit_score,
                    "trigger_event": l.trigger_event,
                }
                for l in leads
            ]

        names = ", ".join(x["company_name"] for x in summary[:4])
        more = f" +{len(summary) - 4} more" if len(summary) > 4 else ""
        await log_event(
            "Orchestrator", "enrich_request",
            f"Found {len(summary)} new compan{'ies' if len(summary) != 1 else 'y'} ({names}{more}). "
            "Waiting for your go-ahead before spending Apollo credits on contacts.",
            level="attention",
            extra={"lead_ids": lead_ids},
        )
        await manager.broadcast({"channel": "enrich_request", "leads": summary})

    async def _invoke_pipeline_step(self, node: str, state: dict) -> Any:
        """Invoke the correct agent for a pipeline step, passing lead_id if needed."""
        agent = self.agents.get(node)
        if not agent or not agent._run_fn:
            raise ValueError(f"Cannot invoke pipeline node '{node}': agent not resolved")

        lead_id = state.get("lead_id")

        # Introspect the function signature to pass the right args.
        import inspect
        sig = inspect.signature(agent._run_fn)
        params = list(sig.parameters.keys())

        if "lead_id" in params and "reply_text" in params:
            return await agent._run_fn(lead_id, state.get("reply_text", ""))
        elif "lead_id" in params:
            return await agent._run_fn(lead_id)
        else:
            return await agent._run_fn()

    def _find_step(self, steps: list[PipelineStep], node_name: str, current_idx: int) -> int:
        """Find the index of a step by node name. Returns len(steps) if not found (= end)."""
        for i, s in enumerate(steps):
            if s.node == node_name:
                return i
        return len(steps)

    def _eval_condition(self, condition: str, state: dict, settings: Any) -> bool:
        """Evaluate a simple condition string like 'approval_mode == true'."""
        if "approval_mode" in condition:
            return settings.approval_mode
        return False

    # ── Runtime: dispatch (replaces the old Orchestrator.dispatch) ─────────
    async def dispatch(self, event_type: str, payload: dict | None = None) -> dict:
        """Top-level event dispatch. Maps event names to pipelines or direct
        agent calls using the YAML spec."""
        payload = payload or {}

        # Check if this event maps to a pipeline.
        for pname, pspec in self.pipelines.items():
            if pspec.entry_event == event_type:
                state = {**payload, "trail": []}
                result = await self.run_pipeline(pname, state)
                return {"ok": True, "event": event_type, "result": result}

        # Direct event → agent function mapping.
        event_map = {
            "reply_received": ("reply_handler_agent", "run"),
            "approval": ("orchestrator", None),       # special handling
            "meeting_scheduled": ("briefing_agent", "run"),
            "outcome": ("orchestrator", None),         # special handling
            "morning_brief": ("reporting_agent", "morning"),
            "end_of_day": ("reporting_agent", "end_of_day"),
            "memory_sweep": ("memory_agent", "run"),
        }

        if event_type in event_map:
            agent_name, fn_alias = event_map[event_type]
            if fn_alias and fn_alias in self.agents[agent_name]._extra_fns:
                result = await self.invoke_agent_fn(agent_name, fn_alias)
            elif fn_alias == "run":
                result = await self._invoke_by_event(agent_name, event_type, payload)
            else:
                result = await self._invoke_by_event(agent_name, event_type, payload)
            return {"ok": True, "event": event_type,
                    "result": getattr(result, "summary", result)}

        return {"ok": False, "detail": f"unknown event '{event_type}'"}

    async def _invoke_by_event(self, agent_name: str, event_type: str, payload: dict) -> Any:
        """Invoke an agent based on the event type and payload."""
        agent = self.agents.get(agent_name)
        if not agent:
            return {"error": f"agent {agent_name} not found"}

        # For agents that need lead_id + extra args.
        lead_id = payload.get("lead_id")
        if event_type == "reply_received":
            return await agent._run_fn(lead_id, payload.get("text", ""))
        elif event_type == "meeting_scheduled":
            return await agent._run_fn(lead_id)
        elif lead_id is not None and agent._run_fn:
            import inspect
            sig = inspect.signature(agent._run_fn)
            if "lead_id" in sig.parameters:
                return await agent._run_fn(lead_id)
        if agent._run_fn:
            return await agent._run_fn()
        return {"error": f"no run function for {agent_name}"}

    # ── Introspection ─────────────────────────────────────────────────────
    def describe(self) -> dict:
        """Return a summary of the loaded graph for debugging / the API."""
        return {
            "system": self.raw.get("system", {}),
            "agents": {n: {"role": a.role, "tools": a.tools, "status": a.status}
                       for n, a in self.agents.items()},
            "pipelines": {n: p.description for n, p in self.pipelines.items()},
            "edges": {
                "static": self.static_edges,
                "conditional": len(self.conditional_edges),
            },
            "tools": {n: t.description for n, t in self.tools.items()},
            "message_bus_depth": len(self.message_bus),
        }

    def get_agent_spec(self, name: str) -> dict | None:
        """Return the raw YAML spec for a named agent."""
        return self.raw.get("agents", {}).get(name)

    def list_agent_tools(self, name: str) -> list[dict]:
        """Return the tool specs available to an agent."""
        agent = self.agents.get(name)
        if not agent:
            return []
        return [
            {"name": t, "description": self.tools[t].description}
            for t in agent.tools if t in self.tools
        ]

    def get_agent_config(self, name: str, key: str | None = None, default: Any = None) -> Any:
        """Return an agent's YAML config dict, or a specific key within it.

        Usage:
            engine.get_agent_config("discovery_agent")  → full config dict
            engine.get_agent_config("discovery_agent", "max_candidates", 24)
        """
        agent = self.agents.get(name)
        if not agent:
            return default
        if key is None:
            return agent.config
        return agent.config.get(key, default)


# ─── Singleton ───────────────────────────────────────────────────────────────
engine = GraphEngine()

def boot() -> GraphEngine:
    """Load the YAML spec and return the engine. Called once at app startup."""
    if not engine._loaded:
        engine.load()
    return engine
