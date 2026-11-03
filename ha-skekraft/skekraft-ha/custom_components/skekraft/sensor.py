"""Sensorer för Skellefteå Kraft."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SkekraftCoordinator, as_list


def _to_float(value: Any) -> float | None:
    try:
        return float(str(value).replace(" ", "").replace(",", "."))
    except (TypeError, ValueError):
        return None


def _to_date(value: Any) -> date | None:
    """Tolka AgreementEnd; 9999-12-31 betyder löpande avtal."""
    if not value or str(value).startswith("9999"):
        return None
    try:
        return datetime.strptime(str(value)[:19], "%Y-%m-%dT%H:%M:%S").date()
    except ValueError:
        return None


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: SkekraftCoordinator = entry.runtime_data
    entities: list[SkekraftEntity] = []

    for reading in coordinator.data["consumption"]:
        entities.append(ConsumptionSensor(coordinator, reading))

    for sub in coordinator.data["subscriptions"]:
        nr = str(sub["info"].get("SubscriptionNr"))
        addr = sub["info"].get("SubscriptionAddress") or nr
        entities.append(DetailSensor(coordinator, nr, addr, "ElAreaCode", "Elområde"))
        entities.append(
            DetailSensor(coordinator, nr, addr, "YearConsumption1", "Årsförbrukning 1", "kWh")
        )
        entities.append(
            DetailSensor(coordinator, nr, addr, "YearConsumption2", "Årsförbrukning 2", "kWh")
        )
        entities.append(DetailSensor(coordinator, nr, addr, "DeliveredFrom", "Levereras från"))
        for agreement in sub["agreements"]:
            entities.append(AgreementSensor(coordinator, nr, addr, agreement))
        entities.append(DailyRawSensor(coordinator, nr, addr))

    async_add_entities(entities)


class SkekraftEntity(CoordinatorEntity[SkekraftCoordinator], SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator: SkekraftCoordinator, key: str) -> None:
        super().__init__(coordinator)
        entry_id = coordinator.config_entry.entry_id
        self._attr_unique_id = f"{entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name="Skellefteå Kraft",
            manufacturer="Skellefteå Kraft",
        )

    def _subscription(self, nr: str) -> dict[str, Any]:
        for sub in self.coordinator.data["subscriptions"]:
            if str(sub["info"].get("SubscriptionNr")) == nr:
                return sub
        return {}


class ConsumptionSensor(SkekraftEntity):
    """Förbrukning hittills denna månad per anläggning/leveranskategori."""

    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def __init__(self, coordinator: SkekraftCoordinator, reading: dict[str, Any]) -> None:
        self._addr = reading.get("Anladress")
        self._cat = reading.get("DeliveryCategory")
        super().__init__(coordinator, f"consumption_{self._addr}_{self._cat}")
        self._attr_name = f"Förbrukning denna månad {self._addr} {self._cat}"
        unit = reading.get("Unit")
        self._attr_native_unit_of_measurement = unit
        if str(unit).lower() == "kwh":
            self._attr_device_class = SensorDeviceClass.ENERGY

    @property
    def _reading(self) -> dict[str, Any]:
        for r in self.coordinator.data["consumption"]:
            if r.get("Anladress") == self._addr and r.get("DeliveryCategory") == self._cat:
                return r
        return {}

    @property
    def native_value(self) -> float | None:
        return _to_float(self._reading.get("Consumption"))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        r = self._reading
        return {
            "avläsningsdatum": r.get("ReadingDate"),
            "leveranskategori": self._cat,
            "adress": f"{self._addr}, {r.get('Anlpostnr')} {r.get('Anlort')}",
        }


class DetailSensor(SkekraftEntity):
    """Enskilt fält från getSubscriptionDetails."""

    def __init__(
        self,
        coordinator: SkekraftCoordinator,
        nr: str,
        addr: str,
        field: str,
        label: str,
        unit: str | None = None,
    ) -> None:
        super().__init__(coordinator, f"detail_{nr}_{field}")
        self._nr = nr
        self._field = field
        self._numeric = unit is not None
        self._attr_name = f"{label} {addr}"
        self._attr_native_unit_of_measurement = unit

    @property
    def native_value(self) -> Any:
        value = self._subscription(self._nr).get("details", {}).get(self._field)
        return _to_float(value) if self._numeric else value


class AgreementSensor(SkekraftEntity):
    """Elavtal: tillståndet är slutdatum (tomt för löpande avtal)."""

    _attr_device_class = SensorDeviceClass.DATE

    def __init__(
        self,
        coordinator: SkekraftCoordinator,
        nr: str,
        addr: str,
        agreement: dict[str, Any],
    ) -> None:
        self._agreement_id = str(agreement.get("AgreementId"))
        super().__init__(coordinator, f"agreement_{nr}_{self._agreement_id}")
        self._nr = nr
        self._attr_name = f"Avtal {agreement.get('Produkt')} {addr}"

    @property
    def _agreement(self) -> dict[str, Any]:
        for a in self._subscription(self._nr).get("agreements", []):
            if str(a.get("AgreementId")) == self._agreement_id:
                return a
        return {}

    @property
    def native_value(self) -> date | None:
        return _to_date(self._agreement.get("AgreementEnd"))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        a = self._agreement
        articles = [
            {
                "namn": art.get("ArticleName"),
                "enhet": art.get("ArticleUnit"),
                "värde": art.get("ArticleValue"),
            }
            for art in as_list((a.get("ArticleInfoItems") or {}).get("ArticleInfo"))
        ]
        return {
            "produkt": a.get("Produkt"),
            "beskrivning": a.get("Descriptions"),
            "avtal_id": self._agreement_id,
            "startdatum": a.get("AgreementBegin"),
            "slutdatum": a.get("AgreementEnd"),
            "artiklar": articles,
        }


class DailyRawSensor(SkekraftEntity):
    """Rådata från getMeterValues (dygnsvärden). Används för att kartlägga formatet."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: SkekraftCoordinator, nr: str, addr: str) -> None:
        super().__init__(coordinator, f"daily_raw_{nr}")
        self._nr = nr
        self._attr_name = f"Dygnsvärden rådata {addr}"

    @property
    def native_value(self) -> str:
        daily = self._subscription(self._nr).get("daily")
        if daily is None:
            return "ingen data"
        return self._subscription(self._nr).get("daily_date", "ok")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"rådata": self._subscription(self._nr).get("daily")}
