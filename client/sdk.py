"""
ClubAI Python SDK

Client library for interacting with the ClubAI coordinator.
"""

import asyncio
import json
from pathlib import Path
from typing import Optional, AsyncIterator
from dataclasses import dataclass
import httpx

from shared.models import (
    TaskMode,
    TaskStatus,
    InferenceRequest,
    InferenceResponse,
)
from shared.crypto_utils import KeyPair, encrypt_for_recipient, decrypt_from_sender


class ClubAIError(Exception):
    """Base exception for ClubAI client errors."""
    pass


class AuthenticationError(ClubAIError):
    """Raised when authentication fails."""
    pass


class APIError(ClubAIError):
    """Raised when an API request fails."""
    def __init__(self, message: str, status_code: int = None):
        super().__init__(message)
        self.status_code = status_code


@dataclass
class ClientConfig:
    """Client configuration."""
    base_url: str = "http://localhost:8000"
    timeout: float = 120.0
    config_dir: Path = Path.home() / ".clubai"

    @property
    def token_file(self) -> Path:
        return self.config_dir / "token"

    @property
    def key_file(self) -> Path:
        return self.config_dir / "client.key"


class ClubAIClient:
    """
    Async client for the ClubAI distributed inference network.

    Usage:
        async with ClubAIClient() as client:
            await client.login("user@example.com", "password")
            response = await client.ask("What is the meaning of life?")
            print(response)
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        timeout: float = 120.0
    ):
        self.config = ClientConfig(base_url=base_url, timeout=timeout)
        self._client: Optional[httpx.AsyncClient] = None
        self._token: Optional[str] = None
        self._keypair: Optional[KeyPair] = None
        self._coordinator_public_key: Optional[str] = None

    async def __aenter__(self) -> "ClubAIClient":
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.disconnect()

    async def connect(self) -> None:
        """Initialize the HTTP client and load saved credentials."""
        self._client = httpx.AsyncClient(
            base_url=self.config.base_url,
            timeout=self.config.timeout
        )

        # Load saved token if exists
        if self.config.token_file.exists():
            self._token = self.config.token_file.read_text().strip()

        # Load or generate keypair
        self.config.config_dir.mkdir(parents=True, exist_ok=True)
        self._keypair = KeyPair.load_or_generate(self.config.key_file)

    async def disconnect(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        """Get the HTTP client."""
        if not self._client:
            raise RuntimeError("Client not connected. Call connect() first.")
        return self._client

    @property
    def is_authenticated(self) -> bool:
        """Check if client has a valid token."""
        return self._token is not None

    def _headers(self) -> dict:
        """Get request headers with authentication."""
        headers = {"Content-Type": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    async def _request(
        self,
        method: str,
        path: str,
        json_data: Optional[dict] = None,
        require_auth: bool = True
    ) -> dict:
        """Make an authenticated API request."""
        if require_auth and not self._token:
            raise AuthenticationError("Not authenticated. Call login() first.")

        response = await self.client.request(
            method,
            path,
            json=json_data,
            headers=self._headers()
        )

        if response.status_code == 401:
            raise AuthenticationError("Invalid or expired token")

        if response.status_code >= 400:
            try:
                error_detail = response.json().get("detail", response.text)
            except Exception:
                error_detail = response.text
            raise APIError(error_detail, response.status_code)

        return response.json()

    # =========================================================================
    # Authentication
    # =========================================================================

    async def register(self, email: str, password: str) -> dict:
        """
        Register a new user account.

        Args:
            email: User email
            password: Password (min 8 characters)

        Returns:
            Created user info

        Raises:
            APIError: If registration fails
        """
        result = await self._request(
            "POST",
            "/auth/register",
            json_data={"email": email, "password": password},
            require_auth=False
        )
        return result

    async def login(self, email: str, password: str) -> str:
        """
        Login and save the access token.

        Args:
            email: User email
            password: Password

        Returns:
            Access token

        Raises:
            AuthenticationError: If login fails
        """
        try:
            result = await self._request(
                "POST",
                "/auth/login",
                json_data={"email": email, "password": password},
                require_auth=False
            )
        except APIError as e:
            raise AuthenticationError(str(e))

        self._token = result["access_token"]

        # Save token
        self.config.config_dir.mkdir(parents=True, exist_ok=True)
        self.config.token_file.write_text(self._token)

        return self._token

    async def logout(self) -> None:
        """Clear saved credentials."""
        self._token = None
        if self.config.token_file.exists():
            self.config.token_file.unlink()

    async def get_me(self) -> dict:
        """Get current user information."""
        return await self._request("GET", "/auth/me")

    # =========================================================================
    # Inference
    # =========================================================================

    async def ask(
        self,
        prompt: str,
        mode: TaskMode = TaskMode.SUBTASKS,
        wait: bool = True,
        poll_interval: float = 1.0
    ) -> str:
        """
        Send an inference request and optionally wait for the response.

        Args:
            prompt: The prompt to send
            mode: Task division mode
            wait: Whether to wait for completion
            poll_interval: Seconds between status checks

        Returns:
            Response text if wait=True, else task_id
        """
        # Submit the request
        result = await self._request(
            "POST",
            "/inference",
            json_data={
                "prompt": prompt,
                "mode": mode.value
            }
        )

        task_id = result["task_id"]

        if not wait:
            return task_id

        # Poll for completion
        while True:
            status = await self.get_task_status(task_id)

            if status["status"] == TaskStatus.COMPLETED.value:
                return status.get("response", "")

            if status["status"] in (TaskStatus.FAILED.value, TaskStatus.PARTIAL.value):
                raise APIError(
                    f"Task failed with status: {status['status']}",
                    status_code=500
                )

            await asyncio.sleep(poll_interval)

    async def ask_async(
        self,
        prompt: str,
        mode: TaskMode = TaskMode.SUBTASKS
    ) -> str:
        """
        Submit an inference request without waiting.

        Args:
            prompt: The prompt to send
            mode: Task division mode

        Returns:
            Task ID for later status checking
        """
        return await self.ask(prompt, mode, wait=False)

    async def get_task_status(self, task_id: str) -> dict:
        """
        Get the status of an inference task.

        Args:
            task_id: Task ID returned from ask()

        Returns:
            Task status information
        """
        return await self._request("GET", f"/inference/{task_id}")

    # =========================================================================
    # Network Information
    # =========================================================================

    async def get_stats(self) -> dict:
        """Get network statistics."""
        return await self._request("GET", "/stats", require_auth=False)

    async def get_nodes(self) -> list[dict]:
        """Get list of active nodes."""
        return await self._request("GET", "/nodes")

    async def get_reputation(self) -> list[dict]:
        """Get node reputation leaderboard."""
        return await self._request("GET", "/reputation", require_auth=False)

    async def get_history(self, limit: int = 50) -> list[dict]:
        """
        Get user's task history.

        Args:
            limit: Maximum number of tasks to return

        Returns:
            List of task records
        """
        return await self._request("GET", f"/history?limit={limit}")


# Synchronous wrapper for simple usage
class ClubAIClientSync:
    """
    Synchronous wrapper for ClubAIClient.

    For use in non-async contexts.
    """

    def __init__(self, base_url: str = "http://localhost:8000"):
        self._client = ClubAIClient(base_url=base_url)
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def _get_loop(self) -> asyncio.AbstractEventLoop:
        if self._loop is None or self._loop.is_closed():
            self._loop = asyncio.new_event_loop()
        return self._loop

    def _run(self, coro):
        return self._get_loop().run_until_complete(coro)

    def connect(self) -> None:
        self._run(self._client.connect())

    def disconnect(self) -> None:
        self._run(self._client.disconnect())

    def login(self, email: str, password: str) -> str:
        return self._run(self._client.login(email, password))

    def ask(self, prompt: str, mode: TaskMode = TaskMode.SUBTASKS) -> str:
        return self._run(self._client.ask(prompt, mode))

    def get_stats(self) -> dict:
        return self._run(self._client.get_stats())
