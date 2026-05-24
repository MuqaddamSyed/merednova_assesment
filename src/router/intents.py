"""Intent types for voice command routing."""

from enum import Enum


class Intent(Enum):
    SYSTEM = "system"
    TERMINAL = "terminal"
    CODING = "coding"
    NAVIGATION = "navigation"
    UNKNOWN = "unknown"
