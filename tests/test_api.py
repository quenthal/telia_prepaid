"""Aikatietojen tulkinta."""
from datetime import datetime, timezone

from custom_components.telia_prepaid import api


def test_to_datetime_variants():
    utc = timezone.utc
    assert api._to_datetime("2027-10-16T21:00:00.000Z") == datetime(2027, 10, 16, 21, tzinfo=utc)
    assert api._to_datetime("$D2027-10-16T21:00:00.000Z") == datetime(2027, 10, 16, 21, tzinfo=utc)
    assert api._to_datetime("2027-10-16T21:00:00") == datetime(2027, 10, 16, 21, tzinfo=utc)
    assert api._to_datetime("2027-10-17T00:00:00+03:00") == datetime(2027, 10, 16, 21, tzinfo=utc)
    # pelkkä päivä = päivän alku Suomen aikaa (talviaika +02, kesäaika +03)
    assert api._to_datetime("2027-02-01") == datetime(2027, 1, 31, 22, tzinfo=utc)
    assert api._to_datetime("17.10.2027") == datetime(2027, 10, 16, 21, tzinfo=utc)
    assert api._to_datetime("ei päivä") is None
    assert api._to_datetime(None) is None


def test_days_remaining_uses_finnish_calendar_days():
    sub = api.Subscription(number="040", valid_until=datetime(2027, 10, 16, 21, tzinfo=timezone.utc))
    assert sub.valid_until_local.strftime("%d.%m.%Y %H:%M") == "17.10.2027 00:00"
    # 18.10.2026 klo 20.59 UTC = 23.59 Suomessa -> vielä 18.10.
    assert sub.days_remaining(datetime(2026, 10, 18, 20, 59, tzinfo=timezone.utc)) == 364
    # 18.10.2026 klo 21.01 UTC = 19.10. 00.01 Suomessa
    assert sub.days_remaining(datetime(2026, 10, 18, 21, 1, tzinfo=timezone.utc)) == 363
    assert sub.days_remaining(datetime(2027, 10, 17, 10, tzinfo=timezone.utc)) == 0
