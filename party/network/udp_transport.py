#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UDP Transport Layer
Handles UDP socket operations with NAT hole punching
"""

import asyncio
import socket
from typing import Callable, Dict, Optional, Tuple

from utils.core.logging import get_logger

log = get_logger()

# Hole punching configuration

# Keepalive configuration


class UDPTransport:
    """Async UDP transport with hole punching support"""

    def __init__(self, local_port: int = 0):
        """Initialize UDP transport

        Args:
            local_port: Local port to bind to (0 for auto-assign)
        """
        self._local_port = local_port
        self._socket: Optional[socket.socket] = None
        self._bound = False
        self._receive_task: Optional[asyncio.Task] = None
        self._running = False

        # Message handlers by source address
        self._handlers: Dict[Tuple[str, int], Callable[[bytes, Tuple[str, int]], None]] = {}
        self._default_handler: Optional[Callable[[bytes, Tuple[str, int]], None]] = None

        # Pending receives (for hole punching)
        self._pending_receives: asyncio.Queue = asyncio.Queue()

    @property
    def local_port(self) -> int:
        """Get the bound local port"""
        return self._local_port

    async def bind(self) -> int:
        """Bind to local port

        Returns:
            The bound port number
        """
        if self._bound:
            return self._local_port

        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.setblocking(False)

        # Allow address reuse
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        # Bind to specified port (or 0 for auto-assign)
        self._socket.bind(("0.0.0.0", self._local_port))

        # Get assigned port
        self._local_port = self._socket.getsockname()[1]
        self._bound = True

        log.info(f"[UDP] Bound to port {self._local_port}")
        return self._local_port

    async def stop(self):
        """Stop the transport"""
        self._running = False

        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
            self._receive_task = None

        if self._socket:
            self._socket.close()
            self._socket = None

        self._bound = False
        log.info("[UDP] Transport stopped")

    async def send(self, data: bytes, addr: Tuple[str, int]):
        """Send UDP packet

        Args:
            data: Data to send
            addr: Destination (ip, port) tuple
        """
        if not self._socket:
            raise RuntimeError("Transport not bound")

        loop = asyncio.get_event_loop()
        try:
            await loop.sock_sendto(self._socket, data, addr)
        except Exception as e:
            log.warning(f"[UDP] Send failed to {addr}: {e}")
            raise

    async def recv(self, timeout: float = 5.0) -> Tuple[bytes, Tuple[str, int]]:
        """Receive a UDP packet with timeout

        Args:
            timeout: Timeout in seconds

        Returns:
            Tuple of (data, (ip, port))

        Raises:
            asyncio.TimeoutError: If no packet received within timeout
        """
        try:
            return await asyncio.wait_for(
                self._pending_receives.get(),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            raise
