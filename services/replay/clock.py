"""Clock abstraction for ThermalIntel V2.

Provides clean separation between wall-clock execution time and simulated replay time.
Enforces the core rule:
    as_of_utc (simulated observation point) != created_at_utc (database persistence time)
"""

from abc import ABC, abstractmethod
from datetime import datetime, timezone, timedelta
from typing import Union, Optional
import time


class Clock(ABC):
    """Abstract base clock interface."""

    @abstractmethod
    def now_utc(self) -> datetime:
        """Return current UTC datetime with timezone info."""
        pass

    @property
    def now(self) -> datetime:
        """Convenience property for current UTC datetime."""
        return self.now_utc()

    def now_iso(self) -> str:
        """Return current UTC time formatted as ISO 8601 string."""
        return self.now_utc().isoformat()

    @abstractmethod
    def sleep(self, seconds: float) -> None:
        """Pause or advance clock by given duration."""
        pass


class RealClock(Clock):
    """Standard system wall-clock using real system time."""

    def now_utc(self) -> datetime:
        return datetime.now(timezone.utc)

    def sleep(self, seconds: float) -> None:
        if seconds > 0:
            time.sleep(seconds)


class SimulatedClock(Clock):
    """Deterministic simulated clock for replay, backtesting, and evaluation.
    
    Allows explicit stepping, jumping, and advancing of virtual simulation time (as_of_utc)
    without mutating system wall-clock time.
    """

    def __init__(self, initial_time: Union[datetime, str]):
        self._initial_time = self._parse_to_utc(initial_time)
        self._current_time = self._initial_time

    @staticmethod
    def _parse_to_utc(dt_val: Union[datetime, str]) -> datetime:
        """Normalize datetime or ISO string to UTC timezone-aware datetime."""
        if isinstance(dt_val, str):
            dt = datetime.fromisoformat(dt_val.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        elif isinstance(dt_val, datetime):
            if dt_val.tzinfo is None:
                return dt_val.replace(tzinfo=timezone.utc)
            return dt_val
        raise TypeError(f"Expected datetime or ISO string, got {type(dt_val)}")

    def now_utc(self) -> datetime:
        return self._current_time

    def set_time(self, new_time: Union[datetime, str]) -> None:
        """Explicitly set the current simulated timestamp."""
        self._current_time = self._parse_to_utc(new_time)

    def advance(self, delta: Union[timedelta, float, int]) -> None:
        """Advance simulated time by a timedelta or duration in seconds."""
        if isinstance(delta, (int, float)):
            delta = timedelta(seconds=float(delta))
        self._current_time += delta

    def sleep(self, seconds: float) -> None:
        """In simulated time, sleeping advances the simulated clock."""
        if seconds > 0:
            self.advance(seconds)

    def reset(self) -> None:
        """Reset the simulated clock to its initial starting timestamp."""
        self._current_time = self._initial_time

    @property
    def initial_time_utc(self) -> datetime:
        """Return the starting timestamp."""
        return self._initial_time
