"""
Session Manager
Manages OpenCode sessions with pooling, caching, and lifecycle management.

Provides efficient session reuse and automatic cleanup for the MCP server.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set
from weakref import WeakValueDictionary

from .models import Session, SessionStatus, SessionStatusType

logger = logging.getLogger(__name__)


@dataclass
class SessionInfo:
    """Extended session information with management metadata."""
    session: Session
    directory: str
    created_at: float = field(default_factory=time.time)
    last_used_at: float = field(default_factory=time.time)
    use_count: int = 0
    is_busy: bool = False
    title: Optional[str] = None
    
    @property
    def idle_time(self) -> float:
        """Time since last use in seconds."""
        return time.time() - self.last_used_at
    
    @property
    def age(self) -> float:
        """Age of the session in seconds."""
        return time.time() - self.created_at
    
    def mark_used(self) -> None:
        """Mark the session as recently used."""
        self.last_used_at = time.time()
        self.use_count += 1
    
    def mark_busy(self, busy: bool = True) -> None:
        """Mark the session as busy/idle."""
        self.is_busy = busy


class SessionManager:
    """
    Manages a pool of OpenCode sessions.
    
    Features:
    - Session pooling per directory
    - Automatic session reuse
    - Idle session cleanup
    - Busy session tracking
    - LRU-based session selection
    
    Example:
        ```python
        from serve_client import OpenCodeServeClient, SessionManager
        
        async with OpenCodeServeClient() as client:
            manager = SessionManager(client)
            
            # Get or create session for directory
            session_id = await manager.get_session("/my/project")
            
            # Use the session
            response = await client.prompt(session_id, "Hello")
            
            # Release when done
            manager.release_session(session_id)
            
            # Cleanup idle sessions
            await manager.cleanup_idle_sessions(max_idle=300)
        ```
    """
    
    DEFAULT_MAX_SESSIONS_PER_DIR = 3
    DEFAULT_MAX_TOTAL_SESSIONS = 10
    DEFAULT_MAX_IDLE_TIME = 600  # 10 minutes
    DEFAULT_MAX_SESSION_AGE = 3600  # 1 hour
    
    def __init__(
        self,
        client: Any,  # OpenCodeServeClient - avoid circular import
        max_sessions_per_dir: int = DEFAULT_MAX_SESSIONS_PER_DIR,
        max_total_sessions: int = DEFAULT_MAX_TOTAL_SESSIONS,
        max_idle_time: float = DEFAULT_MAX_IDLE_TIME,
        max_session_age: float = DEFAULT_MAX_SESSION_AGE,
        auto_cleanup: bool = True,
        cleanup_interval: float = 60.0,
    ):
        """
        Initialize the session manager.
        
        Args:
            client: OpenCodeServeClient instance
            max_sessions_per_dir: Max sessions per directory
            max_total_sessions: Max total sessions across all directories
            max_idle_time: Max idle time before cleanup (seconds)
            max_session_age: Max session age before cleanup (seconds)
            auto_cleanup: Enable automatic cleanup task
            cleanup_interval: Interval for cleanup checks (seconds)
        """
        self.client = client
        self.max_sessions_per_dir = max_sessions_per_dir
        self.max_total_sessions = max_total_sessions
        self.max_idle_time = max_idle_time
        self.max_session_age = max_session_age
        
        # Session storage: session_id -> SessionInfo
        self._sessions: Dict[str, SessionInfo] = {}
        
        # Directory index: directory -> set of session_ids
        self._dir_sessions: Dict[str, Set[str]] = {}
        
        # Busy sessions
        self._busy_sessions: Set[str] = set()
        
        # Cleanup task
        self._cleanup_task: Optional[asyncio.Task] = None
        self._auto_cleanup = auto_cleanup
        self._cleanup_interval = cleanup_interval
        self._shutdown = False
        
        # Lock for session creation to prevent race conditions
        self._creation_lock = asyncio.Lock()
    
    async def start(self) -> None:
        """Start the session manager (including cleanup task)."""
        if self._auto_cleanup and self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            logger.info("SessionManager started with auto-cleanup")
    
    async def stop(self) -> None:
        """Stop the session manager and cleanup."""
        self._shutdown = True
        
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
        
        # Cleanup all sessions
        await self.cleanup_all_sessions()
        logger.info("SessionManager stopped")
    
    async def get_session(
        self,
        directory: str,
        title: Optional[str] = None,
        prefer_existing: bool = True,
    ) -> str:
        """
        Get or create a session for a directory.
        
        Args:
            directory: Working directory
            title: Optional session title
            prefer_existing: Prefer reusing existing idle session
            
        Returns:
            Session ID
        """
        # Try to get existing idle session
        if prefer_existing:
            session_id = self._get_idle_session(directory)
            if session_id:
                info = self._sessions[session_id]
                info.mark_used()
                info.mark_busy(True)
                self._busy_sessions.add(session_id)
                logger.debug(f"Reusing session {session_id} for {directory}")
                return session_id
        
        # Check limits
        await self._enforce_limits(directory)
        
        # Create new session
        session = await self.client.create_session(
            title=title or f"MCP Session - {directory}",
            directory=directory,
        )
        
        # Register session
        info = SessionInfo(
            session=session,
            directory=directory,
            title=title,
        )
        info.mark_busy(True)
        
        self._sessions[session.id] = info
        
        if directory not in self._dir_sessions:
            self._dir_sessions[directory] = set()
        self._dir_sessions[directory].add(session.id)
        
        self._busy_sessions.add(session.id)
        
        logger.info(f"Created new session {session.id} for {directory}")
        return session.id
    
    def release_session(self, session_id: str) -> None:
        """
        Release a session back to the pool.
        
        Args:
            session_id: Session to release
        """
        if session_id in self._sessions:
            info = self._sessions[session_id]
            info.mark_busy(False)
            self._busy_sessions.discard(session_id)
            logger.debug(f"Released session {session_id}")
    
    def is_busy(self, session_id: str) -> bool:
        """Check if a session is currently busy."""
        return session_id in self._busy_sessions
    
    def get_session_info(self, session_id: str) -> Optional[SessionInfo]:
        """Get info for a session."""
        return self._sessions.get(session_id)
    
    def get_sessions_for_directory(self, directory: str) -> List[str]:
        """Get all session IDs for a directory."""
        return list(self._dir_sessions.get(directory, set()))
    
    def get_all_sessions(self) -> List[str]:
        """Get all managed session IDs."""
        return list(self._sessions.keys())
    
    def get_stats(self) -> Dict[str, Any]:
        """Get session manager statistics."""
        total = len(self._sessions)
        busy = len(self._busy_sessions)
        idle = total - busy
        
        by_directory = {
            d: len(s) for d, s in self._dir_sessions.items()
        }
        
        avg_age = 0.0
        avg_idle = 0.0
        if total > 0:
            ages = [info.age for info in self._sessions.values()]
            idles = [info.idle_time for info in self._sessions.values()]
            avg_age = sum(ages) / total
            avg_idle = sum(idles) / total
        
        return {
            "total_sessions": total,
            "busy_sessions": busy,
            "idle_sessions": idle,
            "sessions_by_directory": by_directory,
            "average_age_seconds": avg_age,
            "average_idle_seconds": avg_idle,
            "max_sessions_per_dir": self.max_sessions_per_dir,
            "max_total_sessions": self.max_total_sessions,
        }
    
    async def cleanup_idle_sessions(
        self,
        max_idle: Optional[float] = None,
        max_age: Optional[float] = None,
    ) -> int:
        """
        Cleanup idle and old sessions.
        
        Args:
            max_idle: Max idle time (defaults to self.max_idle_time)
            max_age: Max age (defaults to self.max_session_age)
            
        Returns:
            Number of sessions cleaned up
        """
        max_idle = max_idle or self.max_idle_time
        max_age = max_age or self.max_session_age
        
        to_cleanup = []
        
        for session_id, info in list(self._sessions.items()):
            # Skip busy sessions
            if session_id in self._busy_sessions:
                continue
            
            # Check idle time and age
            if info.idle_time > max_idle or info.age > max_age:
                to_cleanup.append(session_id)
        
        # Cleanup
        cleaned = 0
        for session_id in to_cleanup:
            try:
                await self._remove_session(session_id)
                cleaned += 1
            except Exception as e:
                logger.error(f"Failed to cleanup session {session_id}: {e}")
        
        if cleaned > 0:
            logger.info(f"Cleaned up {cleaned} idle/old sessions")
        
        return cleaned
    
    async def cleanup_all_sessions(self) -> int:
        """
        Cleanup all managed sessions.
        
        Returns:
            Number of sessions cleaned up
        """
        session_ids = list(self._sessions.keys())
        cleaned = 0
        
        for session_id in session_ids:
            try:
                await self._remove_session(session_id)
                cleaned += 1
            except Exception as e:
                logger.error(f"Failed to cleanup session {session_id}: {e}")
        
        return cleaned
    
    async def refresh_session_status(self, session_id: str) -> Optional[SessionStatus]:
        """
        Refresh session status from server.
        
        Args:
            session_id: Session to refresh
            
        Returns:
            Current session status
        """
        try:
            status = await self.client.get_session_status(session_id)
            
            if session_id in self._sessions:
                info = self._sessions[session_id]
                is_busy = status.type == SessionStatusType.BUSY
                info.mark_busy(is_busy)
                
                if is_busy:
                    self._busy_sessions.add(session_id)
                else:
                    self._busy_sessions.discard(session_id)
            
            return status
        except Exception as e:
            logger.error(f"Failed to refresh session status: {e}")
            return None
    
    def _get_idle_session(self, directory: str) -> Optional[str]:
        """Get an idle session for a directory (LRU selection)."""
        if directory not in self._dir_sessions:
            return None
        
        # Get idle sessions sorted by last used time
        candidates = []
        for session_id in self._dir_sessions[directory]:
            if session_id in self._busy_sessions:
                continue
            
            info = self._sessions.get(session_id)
            if info and not info.is_busy:
                candidates.append((session_id, info.last_used_at))
        
        if not candidates:
            return None
        
        # Return least recently used
        candidates.sort(key=lambda x: x[1])
        return candidates[0][0]
    
    async def _enforce_limits(self, directory: str) -> None:
        """Enforce session limits, cleaning up if needed."""
        # Check per-directory limit
        if directory in self._dir_sessions:
            dir_count = len(self._dir_sessions[directory])
            if dir_count >= self.max_sessions_per_dir:
                # Remove oldest idle session in directory
                await self._remove_oldest_idle(directory)
        
        # Check total limit
        if len(self._sessions) >= self.max_total_sessions:
            # Remove oldest idle session globally
            await self._remove_oldest_idle(None)
    
    async def _remove_oldest_idle(self, directory: Optional[str]) -> bool:
        """Remove the oldest idle session."""
        candidates = []
        
        sessions = (
            self._dir_sessions.get(directory, set())
            if directory else
            set(self._sessions.keys())
        )
        
        for session_id in sessions:
            if session_id in self._busy_sessions:
                continue
            
            info = self._sessions.get(session_id)
            if info and not info.is_busy:
                candidates.append((session_id, info.last_used_at))
        
        if not candidates:
            return False
        
        # Remove least recently used
        candidates.sort(key=lambda x: x[1])
        session_id = candidates[0][0]
        
        try:
            await self._remove_session(session_id)
            return True
        except Exception as e:
            logger.error(f"Failed to remove session {session_id}: {e}")
            return False
    
    async def _remove_session(self, session_id: str) -> None:
        """Remove a session from the pool and server."""
        info = self._sessions.pop(session_id, None)
        
        if info:
            # Remove from directory index
            if info.directory in self._dir_sessions:
                self._dir_sessions[info.directory].discard(session_id)
                if not self._dir_sessions[info.directory]:
                    del self._dir_sessions[info.directory]
        
        # Remove from busy set
        self._busy_sessions.discard(session_id)
        
        # Delete from server
        try:
            await self.client.delete_session(session_id)
            logger.debug(f"Deleted session {session_id} from server")
        except Exception as e:
            logger.warning(f"Failed to delete session {session_id} from server: {e}")
    
    async def _cleanup_loop(self) -> None:
        """Background task for periodic cleanup."""
        while not self._shutdown:
            try:
                await asyncio.sleep(self._cleanup_interval)
                await self.cleanup_idle_sessions()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cleanup loop error: {e}")
    
    # Context manager support
    async def __aenter__(self) -> "SessionManager":
        await self.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.stop()


class SessionContext:
    """
    Context manager for using a managed session.
    
    Automatically acquires and releases sessions.
    
    Example:
        ```python
        manager = SessionManager(client)
        
        async with SessionContext(manager, "/my/project") as session_id:
            response = await client.prompt(session_id, "Hello")
        # Session automatically released
        ```
    """
    
    def __init__(
        self,
        manager: SessionManager,
        directory: str,
        title: Optional[str] = None,
    ):
        self.manager = manager
        self.directory = directory
        self.title = title
        self.session_id: Optional[str] = None
    
    async def __aenter__(self) -> str:
        self.session_id = await self.manager.get_session(
            self.directory,
            title=self.title,
        )
        return self.session_id
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if self.session_id:
            self.manager.release_session(self.session_id)
