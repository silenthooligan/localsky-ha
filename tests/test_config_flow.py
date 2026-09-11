"""Config-flow tests: manual pairing, token step, zeroconf, reauth."""
from ipaddress import ip_address
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.localsky.const import CONF_API_TOKEN, DOMAIN

from .conftest import INFO_AUTH, INFO_OPEN, INFO_TOO_OLD

USER_INPUT = {"host": "192.0.2.10", "port": 8090, "use_https": False}


def _zeroconf_info(
    props: dict | None = None, *, host: str = "192.0.2.10", port: int = 8090
) -> ZeroconfServiceInfo:
    return ZeroconfServiceInfo(
        ip_address=ip_address(host),
        ip_addresses=[ip_address(host)],
        hostname="localsky.local.",
        name="LocalSky (localsky)._localsky._tcp.local.",
        port=port,
        type="_localsky._tcp.local.",
        properties=props if props is not None else {
            "uuid": INFO_OPEN["uuid"],
            "version": "0.7.0",
            "auth": "disabled",
        },
    )


@pytest.mark.asyncio
async def test_user_flow_open_instance(hass: HomeAssistant) -> None:
    """No-auth instance pairs straight through."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM

    with patch(
        "custom_components.localsky.config_flow._probe",
        new=AsyncMock(return_value=INFO_OPEN),
    ), patch(
        "custom_components.localsky.async_setup_entry",
        new=AsyncMock(return_value=True),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "LocalSky (192.0.2.10)"
    assert result["data"]["host"] == "192.0.2.10"
    assert CONF_API_TOKEN not in result["data"]
    assert result["result"].unique_id == INFO_OPEN["uuid"]


@pytest.mark.asyncio
async def test_user_flow_auth_required(hass: HomeAssistant) -> None:
    """auth_required instance demands a valid token before creating."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    with patch(
        "custom_components.localsky.config_flow._probe",
        new=AsyncMock(return_value=INFO_AUTH),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "auth"

    # Wrong token re-renders the form with invalid_auth.
    with patch(
        "custom_components.localsky.config_flow._validate_token",
        new=AsyncMock(return_value=False),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_API_TOKEN: "lsk_bad"}
        )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}

    with patch(
        "custom_components.localsky.config_flow._validate_token",
        new=AsyncMock(return_value=True),
    ), patch(
        "custom_components.localsky.async_setup_entry",
        new=AsyncMock(return_value=True),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_API_TOKEN: "lsk_good"}
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_API_TOKEN] == "lsk_good"


@pytest.mark.asyncio
async def test_user_flow_rejects_old_service(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    with patch(
        "custom_components.localsky.config_flow._probe",
        new=AsyncMock(return_value=INFO_TOO_OLD),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "service_too_old"}


@pytest.mark.asyncio
async def test_zeroconf_flow(hass: HomeAssistant) -> None:
    """Discovery prefills + confirms; uuid is the unique id."""
    with patch(
        "custom_components.localsky.config_flow._probe",
        new=AsyncMock(return_value=INFO_OPEN),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_ZEROCONF},
            data=_zeroconf_info(),
        )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "zeroconf_confirm"

    with patch(
        "custom_components.localsky.async_setup_entry",
        new=AsyncMock(return_value=True),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {}
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == INFO_OPEN["uuid"]


@pytest.mark.asyncio
async def test_zeroconf_dedupes_on_uuid(hass: HomeAssistant) -> None:
    """An unchanged known endpoint dedupes without a probe or mutation."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=INFO_OPEN["uuid"],
        data=USER_INPUT,
    )
    entry.add_to_hass(hass)

    with patch("custom_components.localsky.config_flow._probe") as probe:
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_ZEROCONF},
            data=_zeroconf_info(),
        )
    probe.assert_not_called()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.data == USER_INPUT


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reported_info",
    [
        {**INFO_OPEN, "service": "other"},
        {**INFO_OPEN, "api_version": "0.0.0"},
        {**INFO_OPEN, "api_version": "3.0.0"},
        {**INFO_OPEN, "api_version": "99.0.0"},
        {**INFO_OPEN, "uuid": "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"},
        {**INFO_OPEN, "uuid": None},
        [],
    ],
    ids=[
        "wrong-service", "old-api", "api-3", "api-99",
        "uuid-mismatch", "missing-uuid", "not-an-object",
    ],
)
async def test_zeroconf_rejected_move_preserves_entry(
    hass: HomeAssistant, reported_info
) -> None:
    """TXT identity alone cannot redirect an existing entry or its token."""
    original = {**USER_INPUT, CONF_API_TOKEN: "lsk_saved_fixture"}
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=INFO_OPEN["uuid"], data=original
    )
    entry.add_to_hass(hass)
    with patch(
        "custom_components.localsky.config_flow._probe",
        new=AsyncMock(return_value=reported_info),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_ZEROCONF},
            data=_zeroconf_info(host="192.0.2.20", port=18090),
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "not_localsky"
    assert entry.data == original
    assert entry.unique_id == INFO_OPEN["uuid"]
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("probe_error", [TimeoutError, ValueError])
async def test_zeroconf_unreachable_or_invalid_json_move_preserves_entry(
    hass: HomeAssistant, probe_error
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=INFO_OPEN["uuid"], data=USER_INPUT
    )
    entry.add_to_hass(hass)
    with patch(
        "custom_components.localsky.config_flow._probe",
        new=AsyncMock(side_effect=probe_error),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_ZEROCONF},
            data=_zeroconf_info(port=18090),
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "cannot_connect"
    assert entry.data == USER_INPUT
    assert entry.unique_id == INFO_OPEN["uuid"]


@pytest.mark.asyncio
@pytest.mark.parametrize("api_version", ["1.13.0", "2.0.0"])
async def test_zeroconf_verified_move_updates_only_endpoint(
    hass: HomeAssistant, api_version: str,
) -> None:
    original = {**USER_INPUT, CONF_API_TOKEN: "lsk_saved_fixture"}
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=INFO_OPEN["uuid"], data=original
    )
    entry.add_to_hass(hass)
    with patch(
        "custom_components.localsky.config_flow._probe",
        new=AsyncMock(return_value={**INFO_OPEN, "api_version": api_version}),
    ) as probe:
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_ZEROCONF},
            data=_zeroconf_info(host="192.0.2.20", port=18090),
        )
    # This probe has no token argument; it only reads the public info endpoint.
    assert probe.await_args.args[1:] == ("192.0.2.20", 18090, False)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.data == {**original, "host": "192.0.2.20", "port": 18090}
    assert entry.unique_id == INFO_OPEN["uuid"]
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1


@pytest.mark.asyncio
async def test_zeroconf_keeps_configured_https_endpoint(hass: HomeAssistant) -> None:
    original = {
        **USER_INPUT,
        "host": "localsky.example.test",
        "port": 443,
        "use_https": True,
        CONF_API_TOKEN: "lsk_saved_fixture",
    }
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=INFO_OPEN["uuid"], data=original
    )
    entry.add_to_hass(hass)
    with patch("custom_components.localsky.config_flow._probe") as probe:
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_ZEROCONF},
            data=_zeroconf_info(port=18090),
        )
    probe.assert_not_called()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.data == original
    assert entry.unique_id == INFO_OPEN["uuid"]


@pytest.mark.asyncio
@pytest.mark.parametrize("legacy_id", ["192.0.2.10:8090", None])
async def test_zeroconf_uuid_mismatch_cannot_adopt_legacy_entry(
    hass: HomeAssistant, legacy_id: str | None
) -> None:
    entry = MockConfigEntry(domain=DOMAIN, unique_id=legacy_id, data=USER_INPUT)
    entry.add_to_hass(hass)
    with patch(
        "custom_components.localsky.config_flow._probe",
        new=AsyncMock(return_value={**INFO_OPEN, "uuid": "different-instance"}),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_ZEROCONF},
            data=_zeroconf_info(),
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "not_localsky"
    assert entry.data == USER_INPUT
    assert entry.unique_id == legacy_id


@pytest.mark.asyncio
@pytest.mark.parametrize("source", [config_entries.SOURCE_ZEROCONF, config_entries.SOURCE_USER])
async def test_pairing_cannot_adopt_another_uuid_at_same_endpoint(
    hass: HomeAssistant, source: str
) -> None:
    """Reusing a host/port does not make a known UUID a legacy identity."""
    old_uuid = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
    entry = MockConfigEntry(domain=DOMAIN, unique_id=old_uuid, data=USER_INPUT)
    entry.add_to_hass(hass)
    with patch(
        "custom_components.localsky.config_flow._probe",
        new=AsyncMock(return_value=INFO_OPEN),
    ):
        if source == config_entries.SOURCE_ZEROCONF:
            result = await hass.config_entries.flow.async_init(
                DOMAIN, context={"source": source}, data=_zeroconf_info()
            )
            assert result["type"] is FlowResultType.FORM
            assert result["step_id"] == "zeroconf_confirm"
        else:
            result = await hass.config_entries.flow.async_init(
                DOMAIN, context={"source": source}
            )
            with patch(
                "custom_components.localsky.async_setup_entry",
                new=AsyncMock(return_value=True),
            ):
                result = await hass.config_entries.flow.async_configure(
                    result["flow_id"], USER_INPUT
                )
                await hass.async_block_till_done()
            assert result["type"] is FlowResultType.CREATE_ENTRY
            assert result["result"].unique_id == INFO_OPEN["uuid"]
    assert entry.data == USER_INPUT
    assert entry.unique_id == old_uuid


@pytest.mark.asyncio
async def test_reauth_flow(hass: HomeAssistant) -> None:
    """401 path: reauth swaps in a fresh token."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=INFO_AUTH["uuid"],
        data={**USER_INPUT, CONF_API_TOKEN: "lsk_old"},
    )
    entry.add_to_hass(hass)

    result = await entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    with patch(
        "custom_components.localsky.config_flow._validate_token",
        new=AsyncMock(return_value=True),
    ), patch(
        "custom_components.localsky.async_setup_entry",
        new=AsyncMock(return_value=True),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_API_TOKEN: "lsk_new"}
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_API_TOKEN] == "lsk_new"


@pytest.mark.asyncio
@pytest.mark.parametrize("legacy_id", ["192.0.2.10:8090", None])
async def test_zeroconf_adopts_legacy_host_keyed_entry(
    hass: HomeAssistant, legacy_id: str | None
) -> None:
    """Pre-0.6 entries were keyed host:port; discovery adopts the uuid
    onto them instead of offering the same instance as new."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=USER_INPUT,
        unique_id=legacy_id,
        title="LocalSky (192.0.2.10)",
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.localsky.config_flow._probe",
        new=AsyncMock(return_value=INFO_OPEN),
    ) as probe:
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_ZEROCONF},
            data=_zeroconf_info(),
        )
    assert probe.await_args.args[1:] == ("192.0.2.10", 8090, False)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.unique_id == INFO_OPEN["uuid"]
    # The entry itself is otherwise untouched.
    assert entry.data["host"] == "192.0.2.10"


@pytest.mark.asyncio
async def test_user_flow_adopts_legacy_host_keyed_entry(hass: HomeAssistant) -> None:
    """Manually re-adding a legacy instance upgrades the existing entry
    instead of creating a duplicate."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=USER_INPUT,
        unique_id="192.0.2.10:8090",
        title="LocalSky (192.0.2.10)",
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    with patch(
        "custom_components.localsky.config_flow._probe",
        new=AsyncMock(return_value=INFO_OPEN),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.unique_id == INFO_OPEN["uuid"]
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1
