"""Update & Project Manager subsystem.

Exposed services:

* :class:`~backend.updates.registry.ProjectRegistry` — what can be updated
* :class:`~backend.updates.manager.UpdateManager` — check/update/rollback
* :class:`~backend.updates.sources.UpdateSource` — update strategy interface
* :class:`~backend.updates.backup.BackupManager` — recoverable backups
* :class:`~backend.updates.health.HealthCheckManager` — post-update checks
* :class:`~backend.updates.history.UpdateHistory` — update log (non-secret)
"""

from .backup import BackupManager
from .health import HealthCheckManager
from .history import UpdateHistory
from .manager import UpdateManager, UpdateManagerError
from .manifest import ProjectManifest
from .registry import ProjectRegistry, build_registry, default_registry
from .sources import (GitHubSource, LocalSource, UpdateSource, UpdateSourceError)
from .state import UpdateState

__all__ = [
    "BackupManager",
    "HealthCheckManager",
    "UpdateHistory",
    "UpdateManager",
    "UpdateManagerError",
    "ProjectManifest",
    "ProjectRegistry",
    "build_registry",
    "default_registry",
    "GitHubSource",
    "LocalSource",
    "UpdateSource",
    "UpdateSourceError",
    "UpdateState",
]