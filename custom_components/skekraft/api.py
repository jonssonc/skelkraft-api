"""Tunn wrapper runt SkeKraft-biblioteket med tokenhantering."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

try:  # sökväg enligt GitHub-repots example.py
    from skekraft.api import SkekraftAPI
except ImportError:  # sökväg enligt PyPI-beskrivningen (äldre)
    from external.skekraft.api import SkekraftAPI  # type: ignore[no-redef]

from .const import BASE_URL

_LOGGER = logging.getLogger(__name__)


class SkekraftAuthError(Exception):
    """Fel användarnamn/lösenord eller ogiltig inloggning."""


class SkekraftConnectionError(Exception):
    """Kunde inte nå Skellefteå Krafts API."""


def _refresh_ok(result: Any) -> bool:
    """Tolka svaret från refresh() – falskt/None/'False' betyder misslyckat."""
    if result is None or result is False:
        return False
    if isinstance(result, str) and result.strip().lower() in ("", "false"):
        return False
    return True


class SkekraftClient:
    """Hanterar inloggning, tokenförnyelse och anrop."""

    def __init__(self, username: str, password: str, token: str | None = None) -> None:
        self._username = username
        self._password = password
        self._api = SkekraftAPI(BASE_URL)
        self._lock = asyncio.Lock()
        self.token: str | None = token

    async def async_login(self) -> None:
        """Logga in med användarnamn/lösenord och spara token."""
        try:
            resp = await self._api.login(self._username, self._password)
        except Exception as err:  # noqa: BLE001
            _LOGGER.exception("SKEKRAFT: inloggningsanropet kastade ett fel")
            raise SkekraftConnectionError(str(err)) from err

        # OBS: logga aldrig token eller lösenord
        if isinstance(resp, dict):
            _LOGGER.warning(
                "SKEKRAFT: inloggningssvar ErrNumber=%r ErrDescription=%r nycklar=%s",
                resp.get("ErrNumber"),
                resp.get("ErrDescription"),
                list(resp.keys()),
            )
        else:
            _LOGGER.warning(
                "SKEKRAFT: inloggningssvar var inte en dict, typ=%s värde=%r",
                type(resp),
                resp,
            )

        ok = False
        if isinstance(resp, dict):
            try:
                ok = int(resp.get("ErrNumber")) == 1
            except (TypeError, ValueError):
                ok = False
        if not ok:
            desc = resp.get("ErrDescription") if isinstance(resp, dict) else resp
            raise SkekraftAuthError(str(desc))
        self.token = resp.get("Dst")

    async def async_ensure_token(self) -> None:
        """Förnya token; logga in på nytt om förnyelsen misslyckas."""
        async with self._lock:
            if self.token:
                try:
                    result = await self._api.refresh(self.token)
                except Exception as err:  # noqa: BLE001
                    _LOGGER.debug("Tokenförnyelse gav fel: %s", err)
                    result = False
                if _refresh_ok(result):
                    # Om biblioteket returnerar en ny token (inte 'true') – använd den.
                    if (
                        isinstance(result, str)
                        and result.strip().lower() != "true"
                        and len(result) > 20
                    ):
                        self.token = result
                    return
                _LOGGER.debug("Token ogiltig, loggar in på nytt")
            await self.async_login()

    async def async_relogin(self) -> None:
        async with self._lock:
            await self.async_login()

    async def async_call(self, name: str, *args: Any, **kwargs: Any) -> Any:
        """Anropa en metod i biblioteket."""
        try:
            return await getattr(self._api, name)(*args, **kwargs)
        except Exception as err:  # noqa: BLE001
            raise SkekraftConnectionError(f"{name}: {err}") from err
