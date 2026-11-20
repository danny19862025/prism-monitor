"""Plain data types shared by every sensor source and the UI."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Fan:
    name: str
    rpm: int | None = None       # real speed when the sensor reports RPM
    percent: float | None = None  # duty cycle when only a percentage exists (e.g. NVIDIA)
    source: str = ''

    def text(self) -> str:
        if self.rpm is not None:
            return f'{self.rpm} RPM'
        if self.percent is not None:
            return f'{self.percent:.0f}%'
        return '—'


@dataclass(frozen=True)
class Battery:
    name: str
    percent: int | None
    source: str = ''
    level: str = ''  # e.g. "Low"/"Full" when a device reports no exact percentage

    def text(self) -> str:
        if self.percent is not None:
            return f'{self.percent}%'
        return self.level or '—'


@dataclass(frozen=True)
class Fps:
    app: str
    fps: float
    frametime_ms: float
    low_1pct: float | None = None


@dataclass
class Snapshot:
    fans: list[Fan] = field(default_factory=list)
    batteries: list[Battery] = field(default_factory=list)
    fps: Fps | None = None
    notes: dict[str, str] = field(default_factory=dict)  # section -> why it is empty
