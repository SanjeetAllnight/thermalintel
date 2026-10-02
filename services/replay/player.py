"""Replay Player Engine for ThermalIntel V2.

Provides backend service-oriented controls for playing, pausing, stepping,
speed adjustment, jumping, and resetting scenario simulations over simulated time.

Implements Requirement 3:
'Create a replay engine supporting:
 - play
 - pause
 - step
 - speed
 - jump to timestamp
 - reset
 - current simulated timestamp
 Keep this backend/service-oriented. Do not create UI code.'
"""

from __future__ import annotations

import logging
from enum import Enum
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any, Union, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from scenarios.schema import Scenario
from services.replay.clock import Clock, SimulatedClock
from services.replay.provider import ScenarioProvider
from services.replay.pipeline import ReplayPipeline, StepExecutionResult

logger = logging.getLogger(__name__)


class PlayerState(str, Enum):
    """Lifecycle state of the replay player."""
    READY = "ready"
    PLAYING = "playing"
    PAUSED = "paused"
    FINISHED = "finished"
    STOPPED = "stopped"


class ReplayPlayer:
    """Backend engine controlling deterministic simulation playback."""

    def __init__(
        self,
        scenario: Scenario,
        clock: Optional[SimulatedClock] = None,
        pipeline: Optional[ReplayPipeline] = None,
        default_step_seconds: float = 3600.0,
        speed: float = 1.0,
    ):
        self.scenario = scenario
        self.clock = clock or SimulatedClock(scenario.start_time_utc)
        self.pipeline = pipeline or ReplayPipeline(clock=self.clock, seed=scenario.metadata.seed or 42)
        self.provider = ScenarioProvider(scenario=scenario, clock=self.clock)
        self.default_step_seconds = default_step_seconds
        self._speed = max(0.1, float(speed))
        self._state = PlayerState.READY
        self._history: List[StepExecutionResult] = []
        self._step_listeners: List[Callable[[StepExecutionResult], None]] = []

    @property
    def state(self) -> PlayerState:
        """Current operational state of player."""
        return self._state

    @property
    def is_playing(self) -> bool:
        return self._state == PlayerState.PLAYING

    @property
    def is_paused(self) -> bool:
        return self._state == PlayerState.PAUSED

    @property
    def is_finished(self) -> bool:
        return self._state == PlayerState.FINISHED

    @property
    def speed(self) -> float:
        """Current simulation speed multiplier."""
        return self._speed

    @property
    def current_simulated_timestamp(self) -> str:
        """Current virtual simulation timestamp (as_of_utc) in ISO 8601 UTC format."""
        return self.clock.now_iso()

    @property
    def current_time(self) -> datetime:
        """Current virtual simulation datetime."""
        return self.clock.now_utc()

    @property
    def history(self) -> List[StepExecutionResult]:
        """Chronological record of all step execution results."""
        return list(self._history)

    def set_speed(self, speed: float) -> None:
        """Adjust playback speed multiplier (must be > 0)."""
        if speed <= 0:
            raise ValueError(f"Speed must be positive, got {speed}")
        self._speed = float(speed)

    def play(self, speed: Optional[float] = None) -> None:
        """Start or resume playback."""
        if speed is not None:
            self.set_speed(speed)
        if self._state == PlayerState.FINISHED:
            logger.info("Player reached end of scenario. Resetting before play.")
            self.reset()
        self._state = PlayerState.PLAYING

    def pause(self) -> None:
        """Pause playback at the current simulated timestamp."""
        self._state = PlayerState.PAUSED

    def stop(self) -> None:
        """Stop playback."""
        self._state = PlayerState.STOPPED

    def add_step_listener(self, listener: Callable[[StepExecutionResult], None]) -> None:
        """Register a callback invoked whenever a simulation step is executed."""
        self._step_listeners.append(listener)

    def step(self, step_seconds: Optional[float] = None) -> Optional[StepExecutionResult]:
        """Advance simulation by one discrete step.
        
        If step_seconds is not provided, advances to the next chronological event timestamp
        or uses default_step_seconds * speed.
        """
        timeline = self.scenario.get_timeline_timestamps()
        current_dt = self.clock.now_utc()

        # Find next timeline event timestamp strictly greater than current
        future_timestamps = [
            ts for ts in timeline
            if datetime.fromisoformat(ts.replace("Z", "+00:00")).replace(tzinfo=timezone.utc) > current_dt
        ]

        if step_seconds is not None:
            delta = timedelta(seconds=float(step_seconds) * self._speed)
            self.clock.advance(delta)
        elif future_timestamps:
            # Advance directly to next scheduled observation/event timestamp
            next_ts = future_timestamps[0]
            self.clock.set_time(next_ts)
        else:
            # Past all known events, advance by default step
            self.clock.advance(self.default_step_seconds * self._speed)

        new_sim_iso = self.clock.now_iso()
        new_sim_dt = self.clock.now_utc()

        # Fetch observations pending up to the new timestamp
        pending_obs = self.provider.fetch_observations(as_of=new_sim_dt, consume=True)

        # Process through full pipeline
        step_result = self.pipeline.process_observations(pending_obs, as_of_utc=new_sim_iso)
        self._history.append(step_result)

        # Check if scenario is completed
        remaining = [
            ts for ts in timeline
            if datetime.fromisoformat(ts.replace("Z", "+00:00")).replace(tzinfo=timezone.utc) > new_sim_dt
        ]
        if not remaining and not pending_obs:
            self._state = PlayerState.FINISHED

        # Notify listeners
        for listener in self._step_listeners:
            try:
                listener(step_result)
            except Exception as e:
                logger.warning("Error in replay step listener: %s", e)

        return step_result

    def jump_to(self, timestamp: Union[datetime, str]) -> Optional[StepExecutionResult]:
        """Jump simulation directly to a target timestamp.
        
        If target is in the future relative to current time, steps through all intervals.
        If target is in the past, resets and replays from start to the target.
        """
        if isinstance(timestamp, str):
            target_dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            if target_dt.tzinfo is None:
                target_dt = target_dt.replace(tzinfo=timezone.utc)
        elif isinstance(timestamp, datetime):
            target_dt = timestamp if timestamp.tzinfo else timestamp.replace(tzinfo=timezone.utc)
        else:
            raise TypeError(f"Expected datetime or ISO string, got {type(timestamp)}")

        current_dt = self.clock.now_utc()

        if target_dt < current_dt:
            # Rewind requested: reset and advance to target
            self.reset()

        last_result: Optional[StepExecutionResult] = None
        # Step through timeline until clock reaches or passes target_dt
        while self.clock.now_utc() < target_dt:
            curr = self.clock.now_utc()
            timeline = self.scenario.get_timeline_timestamps()
            next_events = [
                ts for ts in timeline
                if curr < datetime.fromisoformat(ts.replace("Z", "+00:00")).replace(tzinfo=timezone.utc) <= target_dt
            ]
            if next_events:
                last_result = self.step()
            else:
                # Advance remaining gap to target_dt
                gap_seconds = (target_dt - self.clock.now_utc()).total_seconds()
                if gap_seconds > 0:
                    last_result = self.step(step_seconds=gap_seconds / self._speed)
                break

        return last_result

    def reset(self) -> None:
        """Reset player to initial starting timestamp and clear all state."""
        self.clock.reset()
        self.provider.reset()
        self.pipeline.reset()
        self._history.clear()
        self._state = PlayerState.READY
        logger.info("ReplayPlayer reset to %s", self.scenario.start_time_utc)

    def run_to_completion(self) -> List[StepExecutionResult]:
        """Execute all steps until all scenario events are consumed."""
        self.play()
        timeline = self.scenario.get_timeline_timestamps()
        curr_dt = self.clock.now_utc()

        for ts in timeline:
            ts_dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if ts_dt.tzinfo is None:
                ts_dt = ts_dt.replace(tzinfo=timezone.utc)
            if ts_dt > curr_dt:
                self.clock.set_time(ts)
                pending_obs = self.provider.fetch_observations(as_of=ts_dt, consume=True)
                step_result = self.pipeline.process_observations(pending_obs, as_of_utc=self.clock.now_iso())
                self._history.append(step_result)

        self._state = PlayerState.FINISHED
        return list(self._history)
