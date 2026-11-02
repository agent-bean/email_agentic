import asyncio
from contextlib import contextmanager
from contextvars import ContextVar


active_deadline = ContextVar("active_deadline", default=None)
attempt_reservation = ContextVar("attempt_reservation", default=None)
operation_scope = ContextVar("operation_scope", default="generation")


def remaining_budget(default):
    deadline = active_deadline.get()
    return max(0, min(default, deadline - asyncio.get_running_loop().time())) if deadline is not None else default


async def reserve_attempt(key):
    reserve = attempt_reservation.get()
    return await reserve(key) if reserve is not None else True


@contextmanager
def provider_operation(name):
    token = operation_scope.set(name)
    try:
        yield
    finally:
        operation_scope.reset(token)


@contextmanager
def processing_budget(seconds, reserve=None):
    token = active_deadline.set(asyncio.get_running_loop().time() + seconds)
    reservation_token = attempt_reservation.set(reserve)
    try:
        yield
    finally:
        active_deadline.reset(token)
        attempt_reservation.reset(reservation_token)
