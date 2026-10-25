"""Telia Prepaid -sensorit."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, time, timedelta

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .api import Subscription, local_tz
from .const import DOMAIN, MANUFACTURER
from .coordinator import TeliaPrepaidConfigEntry, TeliaPrepaidCoordinator


def _days_remaining(sub: Subscription) -> int | None:
    return sub.days_remaining(dt_util.utcnow())


def next_local_midnight(now: datetime) -> datetime:
    """Seuraava vuorokauden vaihde Suomen aikaa (UTC), pari sekuntia yli."""
    tz = local_tz()
    day = now.astimezone(tz).date() + timedelta(days=1)
    return (datetime.combine(day, time.min, tz) + timedelta(seconds=2)).astimezone(dt_util.UTC)


@dataclass(frozen=True, kw_only=True)
class TeliaSensorDescription(SensorEntityDescription):
    value_fn: Callable[[Subscription], float | int | str | datetime | None]
    midnight_update: bool = False  # arvo riippuu päivämäärästä, ei vain haetuista tiedoista


SENSORS: tuple[TeliaSensorDescription, ...] = (
    TeliaSensorDescription(
        key="balance",
        translation_key="balance",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement="EUR",
        suggested_display_precision=2,
        value_fn=lambda s: s.balance,
    ),
    TeliaSensorDescription(
        key="bonus_balance",
        translation_key="bonus_balance",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement="EUR",
        suggested_display_precision=2,
        value_fn=lambda s: s.bonus_balance,
    ),
    TeliaSensorDescription(
        key="total_balance",
        translation_key="total_balance",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement="EUR",
        suggested_display_precision=2,
        value_fn=lambda s: s.total_balance,
    ),
    TeliaSensorDescription(
        key="valid_until",
        translation_key="valid_until",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda s: s.valid_until,
    ),
    TeliaSensorDescription(
        key="days_remaining",
        translation_key="days_remaining",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTime.DAYS,
        suggested_display_precision=0,
        value_fn=_days_remaining,
        midnight_update=True,
    ),
    TeliaSensorDescription(
        key="subscription_type",
        translation_key="subscription_type",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.subscription_type,
    ),
    TeliaSensorDescription(
        key="status",
        translation_key="status",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.status,
    ),
    TeliaSensorDescription(
        key="sim_type",
        translation_key="sim_type",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.sim_type,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TeliaPrepaidConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    known: set[str] = set()

    @callback
    def _add_new_subscriptions() -> None:
        """Tilille myöhemmin lisätyt liittymät saavat sensorinsa ilman uudelleenlatausta."""
        new = [number for number in coordinator.data or {} if number not in known]
        if not new:
            return
        known.update(new)
        async_add_entities(
            TeliaPrepaidSensor(coordinator, number, description)
            for number in new
            for description in SENSORS
        )

    _add_new_subscriptions()
    entry.async_on_unload(coordinator.async_add_listener(_add_new_subscriptions))


class TeliaPrepaidSensor(CoordinatorEntity[TeliaPrepaidCoordinator], SensorEntity):
    """Yhden liittymän yksi tieto."""

    _attr_has_entity_name = True
    entity_description: TeliaSensorDescription
    _unsub_midnight: CALLBACK_TYPE | None = None

    def __init__(
        self,
        coordinator: TeliaPrepaidCoordinator,
        number: str,
        description: TeliaSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._number = number
        self._attr_unique_id = f"{number}_{description.key}"
        sub = coordinator.data[number]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, number)},
            name=sub.name or f"Telia Prepaid {number}",
            manufacturer=MANUFACTURER,
            model=sub.subscription_type or "Telia Prepaid",
            serial_number=number,
            configuration_url=(
                f"https://prepaid.telia.fi/fi/account/{sub.subscription_id}"
                if sub.subscription_id
                else "https://prepaid.telia.fi/fi/account"
            ),
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if self.entity_description.midnight_update:
            self._schedule_midnight()

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub_midnight:
            self._unsub_midnight()
            self._unsub_midnight = None
        await super().async_will_remove_from_hass()

    @callback
    def _schedule_midnight(self) -> None:
        self._unsub_midnight = async_track_point_in_utc_time(
            self.hass, self._at_midnight, next_local_midnight(dt_util.utcnow())
        )

    @callback
    def _at_midnight(self, _now: datetime) -> None:
        self._schedule_midnight()
        self.async_write_ha_state()

    @property
    def _sub(self) -> Subscription | None:
        return (self.coordinator.data or {}).get(self._number)

    @property
    def available(self) -> bool:
        return super().available and self._sub is not None

    @property
    def native_value(self):
        sub = self._sub
        return None if sub is None else self.entity_description.value_fn(sub)
