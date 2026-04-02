"""Unit tests for washer/dryer energy consumption sensors."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.smartthinq_sensors.wideq.const import WashDeviceFeatures
from custom_components.smartthinq_sensors.wideq.core_async import Session
from custom_components.smartthinq_sensors.wideq.device_info import PlatformType
from custom_components.smartthinq_sensors.wideq.devices.washerDryer import (
    WMDevice,
    WMStatus,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_device() -> WMDevice:
    """Construct a WMDevice with a minimal set of mocked dependencies."""
    client = MagicMock()
    client.session.get_energy_history = AsyncMock()

    device_info = MagicMock()
    device_info.platform_type = PlatformType.THINQ2
    device_info.device_id = "device-123"
    device_info.name = "Test Washer"

    return WMDevice(client, device_info)


def _make_session() -> Session:
    """Construct a Session with get2 stubbed out."""
    auth = MagicMock()
    session = Session(auth)
    session.get2 = AsyncMock()
    return session


# ---------------------------------------------------------------------------
# Session.get_energy_history
# ---------------------------------------------------------------------------


class TestSessionGetEnergyHistory:
    @pytest.mark.asyncio
    async def test_builds_laundry_url_with_defaults(self):
        session = _make_session()
        today = datetime.now().strftime("%Y-%m-%d")
        session.get2.return_value = {"item": []}

        await session.get_energy_history("dev-1")

        url = session.get2.call_args[0][0]
        assert "service/laundry/dev-1/energy-history" in url
        assert "period=day" in url
        assert f"startDate={today}" in url
        assert f"endDate={today}" in url

    @pytest.mark.asyncio
    async def test_custom_period_and_dates(self):
        session = _make_session()
        session.get2.return_value = {"item": []}

        await session.get_energy_history(
            "dev-1",
            period="hour",
            start_date="2024-01-01",
            end_date="2024-01-01",
        )

        url = session.get2.call_args[0][0]
        assert "period=hour" in url
        assert "startDate=2024-01-01" in url
        assert "endDate=2024-01-01" in url

    @pytest.mark.asyncio
    async def test_month_range(self):
        session = _make_session()
        session.get2.return_value = {"item": []}

        await session.get_energy_history(
            "dev-1",
            period="day",
            start_date="2024-03-01",
            end_date="2024-03-31",
        )

        url = session.get2.call_args[0][0]
        assert "startDate=2024-03-01" in url
        assert "endDate=2024-03-31" in url

    @pytest.mark.asyncio
    async def test_returns_api_response(self):
        session = _make_session()
        expected = {"item": [{"periodicEnergyData": "500"}], "total": "500"}
        session.get2.return_value = expected

        result = await session.get_energy_history("dev-1")

        assert result == expected

    @pytest.mark.asyncio
    async def test_no_hardcoded_washer_type(self):
        """Ensure washerType/twinYn params are not injected into the URL."""
        session = _make_session()
        session.get2.return_value = {}

        await session.get_energy_history("dev-1")

        url = session.get2.call_args[0][0]
        assert "washerType" not in url
        assert "twinYn" not in url


# ---------------------------------------------------------------------------
# WMDevice._sum_energy (static)
# ---------------------------------------------------------------------------


class TestSumEnergy:
    def test_empty_list_returns_zero(self):
        assert WMDevice._sum_energy([]) == 0

    def test_single_item(self):
        assert WMDevice._sum_energy([{"periodicEnergyData": "300"}]) == 300

    def test_multiple_items(self):
        items = [
            {"periodicEnergyData": "100"},
            {"periodicEnergyData": "200"},
            {"periodicEnergyData": "50"},
        ]
        assert WMDevice._sum_energy(items) == 350

    def test_handles_none_value(self):
        items = [{"periodicEnergyData": None}, {"periodicEnergyData": "100"}]
        assert WMDevice._sum_energy(items) == 100

    def test_handles_empty_string(self):
        items = [{"periodicEnergyData": ""}, {"periodicEnergyData": "200"}]
        assert WMDevice._sum_energy(items) == 200

    def test_handles_missing_key(self):
        items = [{}, {"periodicEnergyData": "150"}]
        assert WMDevice._sum_energy(items) == 150


# ---------------------------------------------------------------------------
# WMDevice._fetch_energy_items
# ---------------------------------------------------------------------------


class TestFetchEnergyItems:
    @pytest.mark.asyncio
    async def test_returns_item_list_on_success(self):
        device = _make_device()
        items = [{"periodicEnergyData": "500", "usedDate": "2024-01-15"}]
        device._client.session.get_energy_history.return_value = {"item": items}

        result = await device._fetch_energy_items(period="day")

        assert result == items

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_items_key(self):
        device = _make_device()
        device._client.session.get_energy_history.return_value = {}

        result = await device._fetch_energy_items(period="day")

        assert result == []

    @pytest.mark.asyncio
    async def test_returns_none_when_api_raises(self):
        device = _make_device()
        device._client.session.get_energy_history.side_effect = Exception("network error")

        result = await device._fetch_energy_items(period="day")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_api_returns_non_dict(self):
        device = _make_device()
        device._client.session.get_energy_history.return_value = None

        result = await device._fetch_energy_items(period="day")

        assert result is None

    @pytest.mark.asyncio
    async def test_passes_date_range_to_api(self):
        device = _make_device()
        device._client.session.get_energy_history.return_value = {"item": []}

        await device._fetch_energy_items(
            period="day",
            start_date="2024-03-01",
            end_date="2024-03-31",
        )

        device._client.session.get_energy_history.assert_called_once_with(
            "device-123",
            period="day",
            start_date="2024-03-01",
            end_date="2024-03-31",
        )


# ---------------------------------------------------------------------------
# WMDevice.get_energy_today
# ---------------------------------------------------------------------------


class TestGetEnergyToday:
    @pytest.mark.asyncio
    async def test_returns_first_item_energy(self):
        device = _make_device()
        with patch.object(
            device,
            "_fetch_energy_items",
            new=AsyncMock(return_value=[{"periodicEnergyData": "750"}]),
        ):
            result = await device.get_energy_today()

        assert result == 750

    @pytest.mark.asyncio
    async def test_returns_zero_for_empty_items(self):
        device = _make_device()
        with patch.object(device, "_fetch_energy_items", new=AsyncMock(return_value=[])):
            result = await device.get_energy_today()

        assert result == 0

    @pytest.mark.asyncio
    async def test_returns_none_when_fetch_fails(self):
        device = _make_device()
        with patch.object(device, "_fetch_energy_items", new=AsyncMock(return_value=None)):
            result = await device.get_energy_today()

        assert result is None

    @pytest.mark.asyncio
    async def test_requests_day_period(self):
        device = _make_device()
        mock_fetch = AsyncMock(return_value=[{"periodicEnergyData": "100"}])
        with patch.object(device, "_fetch_energy_items", new=mock_fetch):
            await device.get_energy_today()

        mock_fetch.assert_called_once_with(period="day")


# ---------------------------------------------------------------------------
# WMDevice.get_energy_this_month
# ---------------------------------------------------------------------------


class TestGetEnergyThisMonth:
    @pytest.mark.asyncio
    async def test_sums_all_daily_items(self):
        device = _make_device()
        items = [
            {"periodicEnergyData": "300"},
            {"periodicEnergyData": "400"},
            {"periodicEnergyData": "100"},
        ]
        with patch.object(device, "_fetch_energy_items", new=AsyncMock(return_value=items)):
            result = await device.get_energy_this_month()

        assert result == 800

    @pytest.mark.asyncio
    async def test_returns_zero_for_empty_month(self):
        device = _make_device()
        with patch.object(device, "_fetch_energy_items", new=AsyncMock(return_value=[])):
            result = await device.get_energy_this_month()

        assert result == 0

    @pytest.mark.asyncio
    async def test_returns_none_when_fetch_fails(self):
        device = _make_device()
        with patch.object(device, "_fetch_energy_items", new=AsyncMock(return_value=None)):
            result = await device.get_energy_this_month()

        assert result is None

    @pytest.mark.asyncio
    async def test_requests_first_day_of_month_as_start(self):
        device = _make_device()
        mock_fetch = AsyncMock(return_value=[])
        with patch.object(device, "_fetch_energy_items", new=mock_fetch):
            with patch(
                "custom_components.smartthinq_sensors.wideq.devices.washerDryer.datetime"
            ) as mock_dt:
                mock_dt.now.return_value = datetime(2024, 3, 15)
                await device.get_energy_this_month()

        call_kwargs = mock_fetch.call_args[1]
        assert call_kwargs["start_date"] == "2024-03-01"
        assert call_kwargs["end_date"] == "2024-03-15"


# ---------------------------------------------------------------------------
# WMDevice.get_energy_last_cycle
# ---------------------------------------------------------------------------


class TestGetEnergyLastCycle:
    @pytest.mark.asyncio
    async def test_returns_per_cycle_average_for_most_recent_day(self):
        device = _make_device()
        items = [
            {"periodicEnergyData": "0", "count": "0", "usedDate": "2024-01-10"},
            {"periodicEnergyData": "900", "count": "3", "usedDate": "2024-01-14"},
            {"periodicEnergyData": "600", "count": "2", "usedDate": "2024-01-15"},
        ]
        with patch.object(device, "_fetch_energy_items", new=AsyncMock(return_value=items)):
            result = await device.get_energy_last_cycle()

        # Most recent day (last in list) with activity: 600 / 2 = 300
        assert result == 300

    @pytest.mark.asyncio
    async def test_skips_days_with_zero_count(self):
        device = _make_device()
        items = [
            {"periodicEnergyData": "500", "count": "2", "usedDate": "2024-01-10"},
            {"periodicEnergyData": "0", "count": "0", "usedDate": "2024-01-15"},
        ]
        with patch.object(device, "_fetch_energy_items", new=AsyncMock(return_value=items)):
            result = await device.get_energy_last_cycle()

        # Most recent non-zero day is the first item (reversed search finds it last)
        assert result == 250

    @pytest.mark.asyncio
    async def test_returns_none_when_no_activity_found(self):
        device = _make_device()
        items = [
            {"periodicEnergyData": "0", "count": "0"},
            {"periodicEnergyData": "0", "count": "0"},
        ]
        with patch.object(device, "_fetch_energy_items", new=AsyncMock(return_value=items)):
            result = await device.get_energy_last_cycle()

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_for_empty_items(self):
        device = _make_device()
        with patch.object(device, "_fetch_energy_items", new=AsyncMock(return_value=[])):
            result = await device.get_energy_last_cycle()

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_fetch_fails(self):
        device = _make_device()
        with patch.object(device, "_fetch_energy_items", new=AsyncMock(return_value=None)):
            result = await device.get_energy_last_cycle()

        assert result is None

    @pytest.mark.asyncio
    async def test_integer_division(self):
        """Wh per cycle should be floor divided, not rounded."""
        device = _make_device()
        items = [{"periodicEnergyData": "700", "count": "3", "usedDate": "2024-01-15"}]
        with patch.object(device, "_fetch_energy_items", new=AsyncMock(return_value=items)):
            result = await device.get_energy_last_cycle()

        assert result == 233  # 700 // 3

    @pytest.mark.asyncio
    async def test_requests_seven_day_window(self):
        device = _make_device()
        mock_fetch = AsyncMock(return_value=[])
        with patch.object(device, "_fetch_energy_items", new=mock_fetch):
            with patch(
                "custom_components.smartthinq_sensors.wideq.devices.washerDryer.datetime"
            ) as mock_dt:
                mock_dt.now.return_value = datetime(2024, 3, 15)
                await device.get_energy_last_cycle()

        call_kwargs = mock_fetch.call_args[1]
        assert call_kwargs["start_date"] == "2024-03-08"
        assert call_kwargs["end_date"] == "2024-03-15"


# ---------------------------------------------------------------------------
# WMDevice._get_device_info_v2
# ---------------------------------------------------------------------------


class TestGetDeviceInfoV2:
    @pytest.mark.asyncio
    async def test_stores_all_energy_values(self):
        device = _make_device()
        device.get_energy_today = AsyncMock(return_value=500)
        device.get_energy_this_month = AsyncMock(return_value=8000)
        device.get_energy_last_cycle = AsyncMock(return_value=250)

        await device._get_device_info_v2()

        assert device._energy_today == 500
        assert device._energy_this_month == 8000
        assert device._energy_last_cycle == 250

    @pytest.mark.asyncio
    async def test_stores_none_when_api_unavailable(self):
        device = _make_device()
        device.get_energy_today = AsyncMock(return_value=None)
        device.get_energy_this_month = AsyncMock(return_value=None)
        device.get_energy_last_cycle = AsyncMock(return_value=None)

        await device._get_device_info_v2()

        assert device._energy_today is None
        assert device._energy_this_month is None
        assert device._energy_last_cycle is None


# ---------------------------------------------------------------------------
# WMStatus energy properties
# ---------------------------------------------------------------------------


class TestWMStatusEnergyProperties:
    def _make_status(self, energy_today=None, energy_this_month=None, energy_last_cycle=None):
        """Build a WMStatus backed by a mock device."""
        device = MagicMock(spec=WMDevice)
        device._energy_today = energy_today
        device._energy_this_month = energy_this_month
        device._energy_last_cycle = energy_last_cycle
        device.model_info = MagicMock()
        device.model_info.is_info_v2 = True

        status = WMStatus.__new__(WMStatus)
        status._device = device
        status._data = {}
        status._available_features = {}
        return status

    def test_energy_today_returns_value(self):
        status = self._make_status(energy_today=400)
        with patch.object(status, "_update_feature", return_value=400) as mock_uf:
            result = status.energy_today
        mock_uf.assert_called_once_with(WashDeviceFeatures.ENERGY_TODAY, 400, False)
        assert result == 400

    def test_energy_today_returns_none_when_not_available(self):
        status = self._make_status(energy_today=None)
        result = status.energy_today
        assert result is None

    def test_energy_this_month_returns_value(self):
        status = self._make_status(energy_this_month=9500)
        with patch.object(status, "_update_feature", return_value=9500):
            result = status.energy_this_month
        assert result == 9500

    def test_energy_this_month_returns_none_when_not_available(self):
        status = self._make_status(energy_this_month=None)
        assert status.energy_this_month is None

    def test_energy_last_cycle_returns_value(self):
        status = self._make_status(energy_last_cycle=300)
        with patch.object(status, "_update_feature", return_value=300):
            result = status.energy_last_cycle
        assert result == 300

    def test_energy_last_cycle_returns_none_when_not_available(self):
        status = self._make_status(energy_last_cycle=None)
        assert status.energy_last_cycle is None

    def test_energy_feature_helper_skips_none(self):
        status = self._make_status()
        with patch.object(status, "_update_feature") as mock_uf:
            result = status._energy_feature(WashDeviceFeatures.ENERGY_TODAY, None)
        mock_uf.assert_not_called()
        assert result is None

    def test_energy_feature_helper_calls_update_feature(self):
        status = self._make_status()
        with patch.object(status, "_update_feature", return_value=100) as mock_uf:
            result = status._energy_feature(WashDeviceFeatures.ENERGY_TODAY, 100)
        mock_uf.assert_called_once_with(WashDeviceFeatures.ENERGY_TODAY, 100, False)
        assert result == 100
