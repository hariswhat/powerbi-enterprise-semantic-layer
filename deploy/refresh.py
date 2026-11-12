"""Refresh sm_finance after deployment with the enhanced refresh API, applying
the incremental refresh policy, and wait for the result.

With applyRefreshPolicy the service creates and merges the policy's
partitions, reloads those inside the incremental window, and leaves older
partitions as they are. After a deployment that changes a policy table's
columns, the older partitions need a reload as well: run once with --table
and --no-policy (runbook section 3).

    python -m deploy.refresh --workspace-id <guid> --dataset-id <guid>
    python -m deploy.refresh --workspace-id <guid> --dataset-id <guid> --schedule 06:30
"""

from __future__ import annotations

import argparse
import sys
import time

API = "https://api.powerbi.com/v1.0/myorg"


FINAL = ("Completed", "Failed", "Cancelled", "Disabled", "TimedOut")


def refresh_body(
    tables: list[str] | None = None,
    apply_policy: bool = True,
    effective_date: str | None = None,
) -> dict:
    """effective_date pins the date the refresh policy treats as today. tst
    holds generated data ending 2026-06-30, so the release passes that date;
    otherwise the rolling window would drop the oldest fiscal year as real time
    moves on while the contracts still expect it."""
    body = {
        "type": "full",
        "commitMode": "transactional",
        "applyRefreshPolicy": apply_policy,
        "maxParallelism": 4,
        "retryCount": 1,
    }
    if tables:
        body["objects"] = [{"table": t} for t in tables]
    if effective_date:
        body["effectiveDate"] = effective_date
    return body


def schedule_body(times: list[str], time_zone: str = "Eastern Standard Time") -> dict:
    """Daily scheduled refresh. A scheduled refresh applies the incremental
    policy on its own."""
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    return {
        "value": {
            "enabled": True,
            "days": days,
            "times": times,
            "localTimeZoneId": time_zone,
            "notifyOption": "MailOnFailure",
        }
    }


def main() -> int:  # pragma: no cover
    import requests
    from azure.identity import DefaultAzureCredential

    p = argparse.ArgumentParser()
    p.add_argument("--workspace-id", required=True)
    p.add_argument("--dataset-id", required=True)
    p.add_argument("--table", action="append")
    p.add_argument("--no-policy", action="store_true", help="process every partition")
    p.add_argument("--effective-date", help="date the policy treats as today, YYYY-MM-DD")
    p.add_argument("--schedule", action="append", help="set a daily refresh at HH:MM instead")
    p.add_argument("--timeout-min", type=int, default=60)
    a = p.parse_args()
    token = (
        DefaultAzureCredential()
        .get_token("https://analysis.windows.net/powerbi/api/.default")
        .token
    )
    h = {"Authorization": f"Bearer {token}"}
    base = f"{API}/groups/{a.workspace_id}/datasets/{a.dataset_id}"
    if a.schedule:
        r = requests.patch(
            f"{base}/refreshSchedule", headers=h, json=schedule_body(a.schedule), timeout=60
        )
        r.raise_for_status()
        print("refresh schedule set:", ", ".join(a.schedule))
        return 0
    url = f"{base}/refreshes"
    body = refresh_body(a.table, not a.no_policy, a.effective_date)
    r = requests.post(url, headers=h, json=body, timeout=60)
    r.raise_for_status()
    status_url = r.headers["Location"]
    deadline = time.time() + a.timeout_min * 60
    while time.time() < deadline:
        s = requests.get(status_url, headers=h, timeout=60).json()
        print(s.get("status"), s.get("extendedStatus"))
        if s.get("status") in FINAL:
            return 0 if s["status"] == "Completed" else 1
        time.sleep(30)
    print("timed out waiting for refresh")
    return 1


if __name__ == "__main__":
    sys.exit(main())
