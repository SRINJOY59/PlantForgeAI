"""One event loop per worker thread, for sync code that has to await.

The agents consumer, the celery lanes and the watchers are all synchronous
loops that call into async code — the LLM client, the embedder, httpx. The
obvious way to bridge that is asyncio.run() at each call site, and it is
wrong here: asyncio.run() creates a loop, runs the coroutine, and *closes*
the loop. Everything the coroutine touched that cached a loop-bound resource
is now holding a corpse.

That matters because the expensive clients are process-wide singletons on
purpose. get_llm() hands back one LLMClient for the life of the process, and
that client owns an AsyncOpenAI connection pool and an asyncio.Semaphore. The
pool binds to whichever loop first drove it; the semaphore binds to whichever
loop first contended it. The second asyncio.run() therefore raises

    RuntimeError: Event loop is closed
    RuntimeError: <Semaphore ...> is bound to a different event loop

and since the callers wrap investigations in `except Exception`, the failure
reads as "the agent didn't have anything to say" rather than as a crash. The
first alert after a restart gets an investigation and every later one silently
does not.

So the loop outlives the call. One per thread — celery prefork workers and the
consumer each get their own, threads never share one, and nothing is closed
until the process goes."""

import asyncio
import threading

_local = threading.local()


def get_loop() -> asyncio.AbstractEventLoop:
    """This thread's long-lived loop, created on first use."""
    loop = getattr(_local, "loop", None)
    if loop is None or loop.is_closed():
        loop = asyncio.new_event_loop()
        _local.loop = loop
        # so bare asyncio.get_event_loop() inside library code finds this one
        # rather than building a second, unrelated loop beside it
        asyncio.set_event_loop(loop)
    return loop


def run_sync(coro):
    """Await `coro` from synchronous code on this thread's persistent loop.

    Drop-in for asyncio.run() everywhere the caller is sync and the awaited
    code may touch a cached client. Raises if a loop is already running here —
    that caller is async and should simply await instead of routing through
    this."""
    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        running = None
    if running is not None:
        raise RuntimeError(
            "run_sync() called from inside a running event loop; await the "
            "coroutine directly instead.")
    return get_loop().run_until_complete(coro)
