"""Alibaba Cloud NLS Token auto-management.

Uses AccessKey ID / Secret to call CreateToken API, caches the token,
and refreshes it automatically before expiry.
"""

from __future__ import annotations

import asyncio
import time

from loguru import logger

# China-Shanghai NLS meta endpoint
_NLS_META_DOMAIN = "nls-meta.cn-shanghai.aliyuncs.com"
_REFRESH_MARGIN = 600  # refresh 10 minutes before expiry


class TokenManager:
    """Manages an Alibaba Cloud NLS access token lifecycle.

    Token is obtained via the China-region ``CreateToken`` OpenAPI and cached
    until close to expiry.  Thread-safe via asyncio.Lock.
    """

    def __init__(self, access_key_id: str, access_key_secret: str) -> None:
        self._ak_id = access_key_id
        self._ak_secret = access_key_secret
        self._token: str | None = None
        self._expire_time: float = 0  # unix timestamp
        self._lock = asyncio.Lock()

    @property
    def is_expired(self) -> bool:
        return time.time() >= (self._expire_time - _REFRESH_MARGIN)

    async def get_token(self) -> str:
        """Return a valid token, refreshing if needed."""
        if self._token and not self.is_expired:
            return self._token
        async with self._lock:
            # Double-check after acquiring lock
            if self._token and not self.is_expired:
                return self._token
            await self._refresh()
            assert self._token is not None
            return self._token

    async def _refresh(self) -> None:
        """Call CreateToken API via the China-region OpenAPI SDK."""
        try:
            token, expire_time = await self._create_token_via_sdk()
            self._token = token
            self._expire_time = expire_time
            remaining = expire_time - time.time()
            logger.info(
                "NLS token refreshed, expires in {:.0f}min ({})",
                remaining / 60,
                time.strftime("%H:%M:%S", time.localtime(expire_time)),
            )
        except Exception as e:
            logger.error("Failed to refresh NLS token: {}", e)
            raise RuntimeError(f"NLS token refresh failed: {e}") from e

    async def _create_token_via_sdk(self) -> tuple[str, float]:
        """Use aliyun-python-sdk-core to call CreateToken.

        Runs the synchronous SDK call in a thread executor.
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._create_token_sync)

    def _create_token_sync(self) -> tuple[str, float]:
        """Synchronous CreateToken call via OpenAPI."""
        try:
            from aliyunsdkcore.client import AcsClient
            from aliyunsdkcore.request import CommonRequest
        except ImportError:
            raise RuntimeError(
                "aliyun-python-sdk-core not installed. "
                "Install with: pip install aliyun-python-sdk-core"
            )

        import json

        client = AcsClient(self._ak_id, self._ak_secret, "cn-shanghai")
        request = CommonRequest()
        request.set_method("POST")
        request.set_domain(_NLS_META_DOMAIN)
        request.set_version("2019-02-28")
        request.set_action_name("CreateToken")

        response = client.do_action_with_exception(request)
        data = json.loads(response)

        token_obj = data.get("Token", {})
        token_id = token_obj.get("Id")
        expire_time = token_obj.get("ExpireTime", 0)

        if not token_id:
            raise RuntimeError(f"CreateToken returned no token: {data}")

        return token_id, float(expire_time)

    async def _create_token_via_http(self) -> tuple[str, float]:
        """Fallback: create token via direct HTTP call with V1 signature.

        This avoids the aliyun-python-sdk-core dependency but requires
        manual signature computation.  Currently unused — kept as reference.
        """
        raise NotImplementedError("HTTP token creation not yet implemented")
