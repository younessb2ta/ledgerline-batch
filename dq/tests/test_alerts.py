from __future__ import annotations

import json

import pytest
from dq import alerts


def test_payload_points_at_the_runbook():
    payload = alerts.build_alert(
        stage="gx",
        batch_id="20261101-42",
        project="ledgerline-514016",
        summary="2 expectations failed.",
        details="raw_orders.expect_column_values_to_be_unique observed=80 unexpected",
        run_url="https://github.com/younessb2ta/ledgerline-batch/actions/runs/1",
    )
    rendered = json.dumps(payload)
    assert "20261101-42" in rendered
    assert "docs/runbooks/gx-gate-failure.md" in rendered
    assert "actions/runs/1" in rendered
    assert payload["blocks"][0]["type"] == "header"


def test_unknown_stage_falls_back_to_the_index():
    payload = alerts.build_alert(stage="mystery", batch_id="b", project="p", summary="s")
    assert "docs/runbooks/README.md" in json.dumps(payload)


def test_no_webhook_is_a_clean_no_op(capsys):
    delivery = alerts.send(alerts.build_alert(stage="dbt", batch_id="b", project="p", summary="s"))
    assert delivery.delivered is False
    assert "SLACK_WEBHOOK_URL" in delivery.reason
    assert "not delivered" in capsys.readouterr().err


def test_dry_run_does_not_call_the_webhook(monkeypatch):
    def explode(*args, **kwargs):  # pragma: no cover - must not run
        raise AssertionError("requests.post must not be called during a dry run")

    monkeypatch.setattr(alerts.requests, "post", explode)
    delivery = alerts.send({}, dry_run=True)
    assert delivery.delivered is False
    assert delivery.reason == "dry run"


def test_delivery_posts_the_payload(monkeypatch):
    calls = {}

    class Response:
        status_code = 200
        text = "ok"

    def fake_post(url, json, timeout):
        calls["url"] = url
        calls["json"] = json
        calls["timeout"] = timeout
        return Response()

    monkeypatch.setattr(alerts.requests, "post", fake_post)
    payload = alerts.build_alert(stage="freshness", batch_id="b", project="p", summary="s")
    delivery = alerts.send(payload, webhook_url="https://hooks.slack.test/x")
    assert delivery.delivered is True
    assert calls["url"] == "https://hooks.slack.test/x"
    assert calls["json"] is payload


def test_http_error_is_reported_not_raised(monkeypatch):
    class Response:
        status_code = 500
        text = "boom"

    monkeypatch.setattr(alerts.requests, "post", lambda *a, **k: Response())
    delivery = alerts.send({}, webhook_url="https://hooks.slack.test/x")
    assert delivery.delivered is False
    assert "HTTP 500" in delivery.reason


def test_cli_dry_run_exits_zero(capsys):
    code = alerts.main(
        [
            "--stage",
            "volume",
            "--batch-id",
            "b",
            "--project",
            "p",
            "--summary",
            "deviation 60%",
            "--dry-run",
        ]
    )
    assert code == 0
    assert "deviation 60%" in capsys.readouterr().out


@pytest.mark.parametrize("stage", sorted(alerts.RUNBOOKS))
def test_every_stage_has_a_runbook(stage):
    title, path = alerts.RUNBOOKS[stage]
    assert title
    assert path.startswith("docs/runbooks/")
