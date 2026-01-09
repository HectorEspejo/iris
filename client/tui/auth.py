"""
Auto-Authentication Module for Iris TUI.

Handles automatic login/registration without user intervention.
"""

import secrets
import httpx
from pathlib import Path
from typing import Optional, Tuple
import yaml


class AutoAuth:
    """Automatic authentication handler."""

    def __init__(self, coordinator_url: str = "http://168.119.10.189:8000"):
        self.coordinator_url = coordinator_url
        self.iris_dir = Path.home() / ".iris"
        self.token_path = self.iris_dir / "token"
        self.config_path = self.iris_dir / "config.yaml"
        self._token: Optional[str] = None

    @property
    def token(self) -> Optional[str]:
        """Get current token."""
        return self._token

    async def ensure_authenticated(self) -> Tuple[bool, str]:
        """
        Ensure user is authenticated, handling all cases automatically.

        Returns:
            Tuple of (success: bool, message: str)
        """
        # Try existing token first
        if self.token_path.exists():
            token = self.token_path.read_text().strip()
            if await self._validate_token(token):
                self._token = token
                return True, "Token validated"

        # Try login with saved credentials
        config = self._load_config()
        email = config.get("auth_email")
        password = config.get("auth_password")

        if email and password:
            success, msg = await self._login(email, password)
            if success:
                return True, msg

        # Auto-register new account
        node_id = config.get("node_id", f"node-{secrets.token_hex(4)}")
        email = f"{node_id}@iris.local"
        password = secrets.token_urlsafe(32)

        # Try to register
        success, msg = await self._register(email, password)
        if not success and "already exists" in msg.lower():
            # Account exists, try login
            success, msg = await self._login(email, password)
            if success:
                return True, msg

        if success:
            # Save credentials for future use
            self._save_credentials(email, password)
            # Now login
            success, msg = await self._login(email, password)
            return success, msg

        return False, msg

    async def _validate_token(self, token: str) -> bool:
        """Validate token with coordinator."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.coordinator_url}/auth/me",
                    headers={"Authorization": f"Bearer {token}"}
                )
                return response.status_code == 200
        except Exception:
            return False

    async def _login(self, email: str, password: str) -> Tuple[bool, str]:
        """Login and save token."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{self.coordinator_url}/auth/login",
                    data={"username": email, "password": password}
                )

                if response.status_code == 200:
                    data = response.json()
                    token = data.get("access_token")
                    if token:
                        self._save_token(token)
                        self._token = token
                        return True, "Logged in"
                    return False, "No token in response"

                return False, f"Login failed: {response.status_code}"

        except Exception as e:
            return False, f"Login error: {e}"

    async def _register(self, email: str, password: str) -> Tuple[bool, str]:
        """Register new account."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{self.coordinator_url}/auth/register",
                    json={"email": email, "password": password}
                )

                if response.status_code == 200:
                    return True, "Registered"
                elif response.status_code == 400:
                    detail = response.json().get("detail", "")
                    return False, detail

                return False, f"Registration failed: {response.status_code}"

        except Exception as e:
            return False, f"Registration error: {e}"

    def _save_token(self, token: str) -> None:
        """Save token to file."""
        self.iris_dir.mkdir(parents=True, exist_ok=True)
        self.token_path.write_text(token)

    def _save_credentials(self, email: str, password: str) -> None:
        """Save credentials to config for re-login."""
        config = self._load_config()
        config["auth_email"] = email
        config["auth_password"] = password
        self._save_config(config)

    def _load_config(self) -> dict:
        """Load config from YAML."""
        try:
            if self.config_path.exists():
                with open(self.config_path) as f:
                    return yaml.safe_load(f) or {}
        except Exception:
            pass
        return {}

    def _save_config(self, config: dict) -> None:
        """Save config to YAML."""
        try:
            self.iris_dir.mkdir(parents=True, exist_ok=True)
            with open(self.config_path, "w") as f:
                yaml.safe_dump(config, f, default_flow_style=False)
        except Exception:
            pass

    def clear_token(self) -> None:
        """Clear saved token."""
        if self.token_path.exists():
            self.token_path.unlink()
        self._token = None
