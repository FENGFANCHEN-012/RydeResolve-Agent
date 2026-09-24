"""
Pipeline Trace

Records what each agent received, what it returned, and every LLM call made
inside it, so the dashboard can show the pipeline step by step.

Uses contextvars, so nothing needs to be passed through the agents:
- `step(agent, title, input)` wraps one agent step (no-op when no tracer is active)
- `LLMClient.chat` calls `record_llm_call(...)`, which attaches the exact prompt
  and raw response to whichever step is running

Events (all JSON-serialisable dicts with a "type" key):
    step_start  {id, agent, title, input}
    llm_call    {step_id, prompt, response, duration_ms, error}
    retrieval   {step_id, dispute_type, clauses}
    step_end    {id, agent, output, duration_ms}
    step_error  {id, agent, error, duration_ms}
    result / error / done   (emitted by the API layer)
"""
import asyncio
import contextvars
import json
import time
from contextlib import asynccontextmanager
from typing import Any

_tracer: contextvars.ContextVar["Tracer | None"] = contextvars.ContextVar("rr_tracer", default=None)
_step_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("rr_step_id", default=None)


def to_jsonable(value: Any) -> Any:
    """Convert Pydantic models / enums / anything else into plain JSON data."""
    return json.loads(json.dumps(value, default=_default))


def _default(obj):
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "value"):  # Enum
        return obj.value
    return str(obj)


class Tracer:
    """Collects events for one pipeline run and streams them via a queue."""

    def __init__(self):
        self.events: list[dict] = []
        self.queue: asyncio.Queue = asyncio.Queue()
        self._counter = 0

    def next_id(self) -> str:
        self._counter += 1
        return f"s{self._counter}"

    def emit(self, event: dict) -> None:
        event = to_jsonable({**event, "ts": round(time.time(), 3)})
        self.events.append(event)
        self.queue.put_nowait(event)

    def close(self) -> None:
        self.queue.put_nowait(None)  # end-of-stream marker


def set_tracer(tracer: Tracer | None):
    return _tracer.set(tracer)


def current_tracer() -> Tracer | None:
    return _tracer.get()


@asynccontextmanager
async def step(agent: str, title: str, input: Any = None):
    """
    Wrap one agent step. Set `holder["output"]` inside the block to record
    what the step returned.

        async with step("Classifier", "Classify dispute", {...}) as s:
            result = await classifier.classify(ctx)
            s["output"] = result
    """
    holder: dict = {"output": None}
    tracer = current_tracer()
    if tracer is None:
        yield holder
        return

    step_id = tracer.next_id()
    tracer.emit({"type": "step_start", "id": step_id, "agent": agent, "title": title, "input": input})
    token = _step_id.set(step_id)
    t0 = time.perf_counter()
    try:
        yield holder
    except Exception as exc:
        tracer.emit({"type": "step_error", "id": step_id, "agent": agent, "error": str(exc),
                     "duration_ms": _ms(t0)})
        raise
    else:
        tracer.emit({"type": "step_end", "id": step_id, "agent": agent, "output": holder["output"],
                     "duration_ms": _ms(t0)})
    finally:
        _step_id.reset(token)


def record_llm_call(prompt: str, response: str | None, duration_ms: int, error: str | None = None) -> None:
    """Called by LLMClient for every request; attaches it to the running step."""
    tracer = current_tracer()
    if tracer is None:
        return
    tracer.emit({"type": "llm_call", "step_id": _step_id.get(), "prompt": prompt,
                 "response": response, "duration_ms": duration_ms, "error": error})


def record_retrieval(query_type: str, clauses: list[dict]) -> None:
    """Attach the policy clauses a RAG lookup returned to the running step.
    Call it on the event loop (after awaiting the lookup), not inside a thread."""
    tracer = current_tracer()
    if tracer is None:
        return
    tracer.emit({"type": "retrieval", "step_id": _step_id.get(), "dispute_type": query_type,
                 "clauses": [{"source": c.get("source"), "section": c.get("section"),
                              "reference": f"{c.get('source', 'unknown')}#{c.get('chunk_index', i)}",
                              "similarity": c.get("similarity"),
                              "excerpt": (c.get("clause") or "")[:400]}
                             for i, c in enumerate(clauses)]})


def _ms(t0: float) -> int:
    return int((time.perf_counter() - t0) * 1000)
