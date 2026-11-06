#!/usr/bin/env python3
"""Registers the museum's measurement plan (data/analytics.json) in a Google Analytics 4 property, so that its
reports and explorations can use every parameter the site sends: custom dimensions (event and user scope), custom
metrics, key events, and optionally the longest data retention (14 months).

    python3 tools/ga_setup.py --property 123456789                 # shows what it would create (dry run)
    python3 tools/ga_setup.py --property 123456789 --apply --retention

It needs an OAuth access token with the analytics.edit scope, in --token or GA_TOKEN. With the Google Cloud SDK:

    gcloud auth application-default login \\
      --scopes=https://www.googleapis.com/auth/analytics.edit,https://www.googleapis.com/auth/cloud-platform
    export GA_TOKEN=$(gcloud auth application-default print-access-token)

(the Admin API also wants a Google Cloud project with "Google Analytics Admin API" enabled: --quota-project, or
GA_QUOTA_PROJECT). The property number is in Google Analytics → Admin → Property details. Definitions that already
exist (same parameter) are left alone; nothing is ever deleted. Standard library only."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = os.environ.get("PCM_GA_ADMIN_API", "https://analyticsadmin.googleapis.com/v1beta")


class Admin:
    def __init__(self, prop: str, token: str, quota: str | None):
        self.base, self.headers = f"{API}/properties/{prop}", {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        if quota:
            self.headers["x-goog-user-project"] = quota

    def call(self, method: str, path: str, body: dict | None = None) -> dict:
        req = urllib.request.Request(self.base + path, method=method, headers=self.headers,
                                     data=json.dumps(body).encode() if body is not None else None)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")
            try:
                detail = json.loads(detail)["error"]["message"]
            except (ValueError, KeyError, TypeError):
                pass
            raise SystemExit(f"Google Analytics Admin API: HTTP {e.code} on {method} {path}: {detail}") from None

    def all(self, path: str, key: str) -> list[dict]:
        out, token = [], ""
        while True:
            page = self.call("GET", f"{path}?pageSize=200" + (f"&pageToken={token}" if token else ""))
            out += page.get(key, [])
            token = page.get("nextPageToken")
            if not token:
                return out


def plan() -> dict:
    return json.loads((ROOT / "data" / "analytics.json").read_text("utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--property", required=True, help="GA4 property number (Admin → Property details), not the G- id")
    ap.add_argument("--token", default=os.environ.get("GA_TOKEN", ""), help="OAuth access token (or GA_TOKEN)")
    ap.add_argument("--quota-project", default=os.environ.get("GA_QUOTA_PROJECT", ""), help="Google Cloud project for the API quota")
    ap.add_argument("--apply", action="store_true", help="create what is missing (without it, only shows what would be done)")
    ap.add_argument("--retention", action="store_true", help="also set event data retention to 14 months (the default is 2)")
    a = ap.parse_args()
    if not re.fullmatch(r"\d{5,15}", a.property):
        raise SystemExit("--property is the property NUMBER (Admin → Property details), e.g. 123456789, not the G-XXXX id")
    p = plan()
    if not a.token:
        print("No token (--token or GA_TOKEN): this is the plan that would be registered.\n")
        for d in p["dimensions"]:
            print(f"  dimension  {d['scope']:<5} {d['parameter']:<20} {d['name']}")
        for m in p["metrics"]:
            print(f"  metric     {m['unit']:<7} {m['parameter']:<18} {m['name']}")
        for k in p["keyEvents"]:
            print(f"  key event  {k}")
        return 0
    ga = Admin(a.property, a.token, a.quota_project or None)
    have_dims = {(d["parameterName"], d.get("scope")) for d in ga.all("/customDimensions", "customDimensions")}
    have_metrics = {m["parameterName"] for m in ga.all("/customMetrics", "customMetrics")}
    have_keys = {k["eventName"] for k in ga.all("/keyEvents", "keyEvents")}
    todo = [("customDimensions", {"parameterName": d["parameter"], "displayName": d["name"], "description": d["description"][:150],
                                  "scope": d["scope"]}) for d in p["dimensions"] if (d["parameter"], d["scope"]) not in have_dims]
    todo += [("customMetrics", {"parameterName": m["parameter"], "displayName": m["name"], "description": m["description"][:150],
                                "measurementUnit": m["unit"], "scope": "EVENT"}) for m in p["metrics"] if m["parameter"] not in have_metrics]
    todo += [("keyEvents", {"eventName": k, "countingMethod": "ONCE_PER_EVENT"}) for k in p["keyEvents"] if k not in have_keys]
    print(f"Property {a.property}: {len(have_dims)} dimensions, {len(have_metrics)} metrics and {len(have_keys)} key events already there; "
          f"{len(todo)} to create.")
    for kind, body in todo:
        label = body.get("parameterName") or body.get("eventName")
        if a.apply:
            ga.call("POST", f"/{kind}", body)
        print(f"  {'created' if a.apply else 'would create'} {kind[:-1]} {label}")
    if a.retention:
        if a.apply:
            ga.call("PATCH", "/dataRetentionSettings?updateMask=eventDataRetention,resetUserDataOnNewActivity",
                    {"eventDataRetention": "FOURTEEN_MONTHS", "resetUserDataOnNewActivity": True})
        print(f"  {'set' if a.apply else 'would set'} event data retention to 14 months")
    if not a.apply and (todo or a.retention):
        print("\nNothing changed: run again with --apply.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
