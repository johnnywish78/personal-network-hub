"""Update & Project Manager subsystem.

Exposed services:

* :class:`~backend.updates.registry.ProjectRegistry` — what can be updated
* :class:`~backend.updates.manager.UpdateManager` — check/update/rollback
* :class:`~backend.updates.sources.UpdateSource` — update strategy interface
* :class:`~backend.updates.backup.BackupManager` — recoverable backups
* :class:`~backend.updates.health.HealthCheckManager` — post-update checks
* :class:`~backend.updates.history.UpdateHistory` — update log (non-secret)

The re-exports below are best-effort: the CLI relies on a graceful failure
message when third-party dependencies are missing, so a failed import here
must not crash ``python3 -m backend.updates.cli`` before it can report the
problem. Callers that need a module import it directly.
"""

try:
    from .backup import BackupManager
    from .health import HealthCheckManager
    from .history import UpdateHistory
    from .manager import UpdateManager, UpdateManagerError
    from .manifest import ProjectManifest
    from .registry import ProjectRegistry, build_registry, default_registry
    from .sources import (GitHubSource, LocalSource, UpdateSource, UpdateSourceError)
    from .state import UpdateState
except ImportError:  # pragma: no cover - optional-dependency guard
    pass

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