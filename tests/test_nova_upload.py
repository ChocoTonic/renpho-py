from unittest.mock import Mock

import pytest

from renpho import RenphoAPIError, RenphoClient
from renpho.crypto import decrypt_response, encrypt_request

# Composition-history fields used by the reference importer.
REPORT_FIELDS = """
bfmCtrl bfmMax bfmMin bfmStd bfpMax bfpMin bfpStd bmi bmiMax bmiMin bmiStd bmr bmrMax bmrMin
bmrStd bodyScore bodyType bodyage bodyfat bone boneMax boneMin fatFreeWeight ffmCtrl
laBodyFatMass laBodyFatPct laBodyFatStd laMuscle laMuscleMass laMuscleStd llBodyFatMass
llBodyFatPct llBodyFatStd llMuscle llMuscleMass llMuscleStd muscle muscleMassMax
muscleMassMin obesityDegree protein proteinMassMax proteinMassMin raBodyFatMass raBodyFatPct
raBodyFatStd raMuscle raMuscleMass raMuscleStd rlBodyFatMass rlBodyFatPct rlBodyFatStd
rlMuscle rlMuscleMass rlMuscleStd sinew sinewRatio smi smmMax smmMin smmStd subfat
tBodyFatMass tBodyFatPct tBodyFatStd tMuscle tMuscleMass tMuscleStd visfat water
waterMassMax waterMassMin weight weightControl weightMax weightMin weightStd weightTarget
whr z100Body z100FootL z100FootR z100HandL z100HandR z20Body z20FootL z20FootR z20HandL
z20HandR
""".split()


@pytest.fixture
def transfer():
    client = RenphoClient("user@example.com", "")
    client.user_id, client.token = "2", "test-token"
    report = dict.fromkeys(REPORT_FIELDS, 1.5)
    report.update(
        timeStamp=1721001600,
        localCreatedAt="2024-07-14 17:00:00",
        mac="aabbccddeeff",
        deviceType="00053",
        reportId="old",
        userId=1,
        gender=1,
        id=333,
        appId="source",
    )
    device = dict(report, bUserId=2, displayModuleType=1, isAuto=2, mac="AA:BB:CC:DD:EE:FF")
    client._transport.post = Mock()
    return client, report, device


def test_upload_wire_contract(transfer):
    client, report, device = transfer
    ack = [{"timeStamp": report["timeStamp"], "reportId": "assigned"}]
    post = client._transport.post
    post.return_value = {"code": 0, "data": encrypt_request(ack)["encryptData"]}
    assert (
        client.upload_nova_full_report(
            report, destination_report=device, timezone="America/Los_Angeles"
        )
        == "assigned"
    )
    post.assert_called_once()
    endpoint, envelope = post.call_args.args
    assert endpoint == "RenphoHealth/scale/uploadMeasureData"
    headers = post.call_args.kwargs["headers"]
    assert (headers["timeZone"], headers["zoneId"]) == ("-7", "America/Los_Angeles")
    assert headers["userId"] == "2" and headers["token"] == "test-token"
    assert headers["appVersion"] and headers["platform"]
    (row,) = decrypt_response(envelope["encryptData"])
    assert len(REPORT_FIELDS) == 89
    expected = {k: report[k] for k in REPORT_FIELDS if k != "weightControl"}
    assert row == dict(
        expected,
        WC=1.5,
        id=0,
        userId=2,
        bUserId=2,
        dataSource=1,
        gender=1,
        deviceType="00053",
        mac=device["mac"],
        displayModuleType=1,
        isAuto=2,
        localCreatedAt=report["localCreatedAt"],
        timeStamp=report["timeStamp"],
        timeZone="PST",
    )


@pytest.mark.parametrize(
    ("side", "changes"),
    [
        ("source", {"deviceType": "00007"}),
        ("source", {"z100FootR": None}),
        ("source", {"weightControl": float("nan")}),
        ("source", {"localCreatedAt": "wrong"}),
        ("destination", {"mac": "001122334455"}),
        ("destination", {"bUserId": 3}),
    ],
)
def test_invalid_report_before_network(transfer, side, changes):
    client, report, device = transfer
    (report if side == "source" else device).update(changes)
    with pytest.raises(ValueError):
        client.upload_nova_full_report(
            report, destination_report=device, timezone="America/Los_Angeles"
        )
    client._transport.post.assert_not_called()


@pytest.mark.parametrize(
    "response",
    [
        {"code": 429},
        {"code": 0, "data": []},
        {"code": 0, "data": "malformed"},
        {"code": 0, "data": [{"timeStamp": 1, "reportId": "unrelated"}]},
    ],
)
def test_unsuccessful_or_ambiguous_write_is_not_retried(transfer, response):
    client, report, device = transfer
    client._transport.post.return_value = response
    with pytest.raises(RenphoAPIError):
        client.upload_nova_full_report(
            report, destination_report=device, timezone="America/Los_Angeles"
        )
    client._transport.post.assert_called_once()
