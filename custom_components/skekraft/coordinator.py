"""Datahämtning för Skellefteå Kraft."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import SkekraftAuthError, SkekraftClient, SkekraftConnectionError
from .const import CONF_TOKEN, DOMAIN, UPDATE_INTERVAL_MINUTES

_LOGGER = logging.getLogger(__name__)


def as_list(value: Any) -> list:
    """API:et returnerar ibland en dict där man väntar sig en lista."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


class SkekraftCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Hämtar all data från Skellefteå Kraft."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=UPDATE_INTERVAL_MINUTES),
            config_entry=entry,
        )
        self.client = SkekraftClient(
            entry.data[CONF_USERNAME],
            entry.data[CONF_PASSWORD],
            entry.data.get(CONF_TOKEN),
        )

    def _persist_token(self) -> None:
        token = self.client.token
        if token and token != self.config_entry.data.get(CONF_TOKEN):
            self.hass.config_entries.async_update_entry(
                self.config_entry, data={**self.config_entry.data, CONF_TOKEN: token}
            )

    async def async_keepalive(self, _now=None) -> None:
        """Förnya token regelbundet (körs av en timer)."""
        try:
            await self.client.async_ensure_token()
            self._persist_token()
        except SkekraftAuthError:
            self.config_entry.async_start_reauth(self.hass)
        except SkekraftConnectionError as err:
            _LOGGER.warning("Kunde inte förnya token just nu: %s", err)

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            await self.client.async_ensure_token()
            self._persist_token()
            return await self._fetch()
        except SkekraftAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except SkekraftConnectionError as err:
            raise UpdateFailed(str(err)) from err

    async def _call(self, name: str, *args: Any, **kwargs: Any) -> Any:
        """Anropa API:et; om svaret är tomt, försök en gång efter ny inloggning."""
        result = await self.client.async_call(name, *args, **kwargs)
        if result is None:
            await self.client.async_relogin()
            self._persist_token()
            result = await self.client.async_call(name, *args, **kwargs)
        return result

    async def _fetch(self) -> dict[str, Any]:
        consumption = await self._call("getCurrentMonthConsumptions")
        data: dict[str, Any] = {
            "consumption": as_list((consumption or {}).get("MeterReading")),
            "subscriptions": [],
        }

        subs = await self._call("getSubscriptions")
        day = (dt_util.now() - timedelta(days=2)).strftime("%Y-%m-%d")

        for sub in as_list((subs or {}).get("SubscriptionInfo")):
            nr = sub.get("SubscriptionNr")
            cid = sub.get("CustomerId")
            entry: dict[str, Any] = {
                "info": sub,
                "details": {},
                "agreements": [],
                "daily": None,
                "daily_date": day,
            }
            try:
                entry["details"] = (
                    await self.client.async_call(
                        "getSubscriptionDetails",
                        nr,
                        cid,
                        sub.get("Source"),
                        sub.get("Utility"),
                    )
                    or {}
                )
            except SkekraftConnectionError as err:
                _LOGGER.debug("getSubscriptionDetails misslyckades: %s", err)
            try:
                agreements = await self.client.async_call("getAgreements", nr, cid)
                entry["agreements"] = as_list((agreements or {}).get("AgreementInfo"))
            except SkekraftConnectionError as err:
                _LOGGER.debug("getAgreements misslyckades: %s", err)
            try:
                entry["daily"] = await self.client.async_call(
                    "getMeterValues", nr, day, day, groupBy="Day"
                )
            except SkekraftConnectionError as err:
                _LOGGER.debug("getMeterValues misslyckades: %s", err)
            data["subscriptions"].append(entry)

        return data
