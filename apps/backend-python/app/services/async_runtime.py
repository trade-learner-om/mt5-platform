import asyncio
from functools import partial
from typing import Any, Awaitable, Callable, TypeVar

T = TypeVar("T")


async def run_sync(func: Callable[..., T], /, *args: Any, **kwargs: Any) -> T:
    bound = partial(func, *args, **kwargs)
    return await asyncio.to_thread(bound)


async def run_coro_in_thread(factory: Callable[..., Awaitable[T]], /, *args: Any, **kwargs: Any) -> T:
    async def _runner() -> T:
        return await factory(*args, **kwargs)

    return await asyncio.to_thread(asyncio.run, _runner())
