"""The persistent loop that sync callers await on.

Every case here is something asyncio.run() gets wrong for a long-lived worker
process. The failures it caused were invisible: the callers wrap their work in
`except Exception`, so an agent whose investigations all died on a closed loop
looked like an agent with nothing to say.
"""

import asyncio
import threading

import pytest

from plantmind_core.aio import get_loop, run_sync


async def echo(value):
    await asyncio.sleep(0)
    return value


def test_repeated_calls_share_one_loop():
    assert run_sync(echo("first")) == "first"
    assert run_sync(echo("second")) == "second"
    assert run_sync(echo("third")) == "third"


def test_a_loop_bound_primitive_survives_repeated_calls():
    """asyncio.Semaphore binds to the loop that first contends it, and the
    LLM client holds one for the life of the process."""
    sem = asyncio.Semaphore(1)

    async def contend():
        async def one():
            async with sem:
                await asyncio.sleep(0)
            return 1
        return sum(await asyncio.gather(one(), one(), one()))

    assert run_sync(contend()) == 3
    assert run_sync(contend()) == 3          # RuntimeError on a fresh loop


def test_the_loop_is_not_closed_between_calls():
    run_sync(echo("x"))
    assert not get_loop().is_closed()


def test_each_thread_gets_its_own_loop():
    """Celery prefork workers and the watcher threads must not share one."""
    loops = {}

    def record(name):
        run_sync(echo("x"))
        loops[name] = get_loop()

    record("main")
    t = threading.Thread(target=record, args=("other",))
    t.start()
    t.join()

    assert loops["main"] is not loops["other"]


def test_calling_from_inside_a_running_loop_is_refused():
    """That caller is already async and should await directly; silently
    nesting would deadlock the loop it is running on."""
    async def inner():
        coro = echo("x")
        with pytest.raises(RuntimeError, match="running event loop"):
            run_sync(coro)
        coro.close()          # refused, so nobody awaited it

    run_sync(inner())


def test_exceptions_propagate_to_the_sync_caller():
    async def boom():
        raise ValueError("from the coroutine")

    with pytest.raises(ValueError, match="from the coroutine"):
        run_sync(boom())

    # and the loop is still usable afterwards
    assert run_sync(echo("ok")) == "ok"
