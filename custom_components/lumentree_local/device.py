from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class LumentreeDevice:
    """Represents a local Lumentree device."""

    device_id: str
    name: str = "Lumentree"
    model: str = "Local"
    manufacturer: str = "Lumentree"
    firmware: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)

    @property
    def unique_id(self) -> str:
        return self.device_id

    @property
    def device_info(self) -> dict[str, Any]:
        """Return Home Assistant DeviceInfo-compatible metadata."""
        data: dict[str, Any] = {
            "identifiers": {("lumentree_local", self.device_id)},
            "name": self.name,
            "manufacturer": self.manufacturer,
            "model": self.model,
        }
        if self.firmware:
            data["sw_version"] = self.firmware
        return data
