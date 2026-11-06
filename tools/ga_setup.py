#!/usr/bin/env python3
"""Registers the museum's measurement plan (data/analytics.json) in a Google Analytics 4 property, so that its
reports and explorations can use every parameter the site sends: custom dimensions (event and user scope), custom
metrics, key events, and optionally the longest data retention (14 months).

    python3 tools/ga_setup.py --property 123456789                 # shows what it would create (dry run)
    python3 tools/ga_setup.py --property 123456789 --apply --retention

It needs an access token with the analytics.edit scope. Google blocks that scope for gcloud's own login ("this app
has tried to access sensitive information"), so the simplest way is a service account that is an Editor of the
property, impersonated from your normal gcloud login (no key file, no OAuth consent screen):

    gcloud auth login
    gcloud config set project MY-PROJECT
    gcloud services enable analyticsadmin.googleapis.com iamcredentials.googleapis.com
    gcloud iam service-accounts create ga-setup
    gcloud iam service-accounts add-iam-policy-binding ga-setup@MY-PROJECT.iam.gserviceaccount.com \\
      --member=user:YOU@gmail.com --role=roles/iam.serviceAccountTokenCreator
    # Google Analytics → Admin → Property access management → add ga-setup@MY-PROJECT.iam.gserviceaccount.com as Editor
    python3 tools/ga_setup.py --property 123456789 --service-account ga-setup@MY-PROJECT.iam.gserviceaccount.com --apply

With --service-account the script asks gcloud for your token (`gcloud auth print-access-token`, or --token) and
exchanges it for a short-lived service-account token with the analytics.edit scope (IAM Credentials API). A token
that already has the scope can be given directly with --token / GA_TOKEN (then the Admin API may also want
--quota-project / GA_QUOTA_PROJECT). The property number is in Google Analytics → Admin → Property details.
Definitions that already exist (same parameter) are left alone; nothing is ever deleted. Standard library only."""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = os.environ.get("PCM_GA_ADMIN_API", "https://analyticsadmin.googleapis.com/v1beta")
IAM = os.environ.get("PCM_IAM_API", "https://iamcredentials.googleapis.com/v1")
SCOPE = "https://www.googleapis.com/auth/analytics.edit"


def http_error(e: urllib.error.HTTPError) -> str:
    detail = e.read().decode("utf-8", "replace")
    try:
        detail = json.loads(detail)["error"]["message"]
    except (ValueError, KeyError, TypeError):
        pass
    return detail


def gcloud_token() -> str:
    exe = shutil.which("gcloud")
    if not exe:
        raise SystemExit("--service-account needs gcloud (logged in with `gcloud auth login`) or --token with your own token")
    r = subprocess.run([exe, "auth", "print-access-token"], capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout.strip():
        raise SystemExit("gcloud auth print-access-token failed (run `gcloud auth login` first):\n" + r.stderr.strip())
    return r.stdout.strip()


def impersonate(account: str, user_token: str) -> str:
    """Short-lived token of the service account with the analytics.edit scope (IAM Credentials generateAccessToken)."""
    req = urllib.request.Request(f"{IAM}/projects/-/serviceAccounts/{account}:generateAccessToken", method="POST",
                                 headers={"Authorization": f"Bearer {user_token}", "Content-Type": "application/json"},
                                 data=json.dumps({"scope": [SCOPE], "lifetime": "900s"}).encode())
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())["accessToken"]
    except urllib.error.HTTPError as e:
        hint = (" (your account needs the role Service Account Token Creator on it, and the IAM Credentials API must be "
                "enabled: see the help of this script)") if e.code in (403, 404) else ""
        raise SystemExit(f"Could not get a token for {account}: HTTP {e.code}: {http_error(e)}{hint}") from None


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
            detail = http_error(e)
            if e.code == 403 and "scope" in detail.lower():
                detail += " (the token lacks the analytics.edit scope: use --service-account)"
            elif e.code == 403:
                detail += " (is the account an Editor of this property, and the Admin API enabled in its project?)"
            raise SystemExit(f"Google Analytics Admin API: HTTP {e.code} on {method} {path}: {detail}") from None

    def all(self, path: str, key: str) -> list[dict]:
        out, token = [], ""
        while True:
            page = self.call("GET", f"{path}?pageSize=200" + (f"&pageToken={token}" if token else ""))
            out += page.get(key, [])
            token = page.get("nextPageToken")
            if not token:
                return out


def display_name(name: str) -> str:
    """GA only accepts letters, digits, underscore and space (no accents), starting with a letter, up to 82."""
    import unicodedata
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    plain = re.sub(r"\s+", " ", re.sub(r"[^A-Za-z0-9_ ]", " ", plain)).strip()
    return (plain if plain[:1].isalpha() else "P " + plain)[:82]


def plan() -> dict:
    return json.loads((ROOT / "data" / "analytics.json").read_text("utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--property", required=True, help="GA4 property number (Admin → Property details), not the G- id")
    ap.add_argument("--token", default=os.environ.get("GA_TOKEN", ""), help="OAuth access token (or GA_TOKEN)")
    ap.add_argument("--service-account", default=os.environ.get("GA_SERVICE_ACCOUNT", ""),
                    help="service account (Editor of the property) to impersonate from your gcloud login (or GA_SERVICE_ACCOUNT)")
    ap.add_argument("--quota-project", default=os.environ.get("GA_QUOTA_PROJECT", ""), help="Google Cloud project for the API quota")
    ap.add_argument("--apply", action="store_true", help="create what is missing (without it, only shows what would be done)")
    ap.add_argument("--retention", action="store_true", help="also set event data retention to 14 months (the default is 2)")
    a = ap.parse_args()
    if not re.fullmatch(r"\d{5,15}", a.property):
        raise SystemExit("--property is the property NUMBER (Admin → Property details), e.g. 123456789, not the G-XXXX id")
    p = plan()
    if a.service_account:
        a.token = impersonate(a.service_account, a.token or gcloud_token())
        a.quota_project = ""  # a service-account token is billed to its own project
    if not a.token:
        print("No token (--service-account, --token or GA_TOKEN): this is the plan that would be registered.\n")
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
    todo = [("customDimensions", {"parameterName": d["parameter"], "displayName": display_name(d["name"]), "description": d["description"][:150],
                                  "scope": d["scope"]}) for d in p["dimensions"] if (d["parameter"], d["scope"]) not in have_dims]
    todo += [("customMetrics", {"parameterName": m["parameter"], "displayName": display_name(m["name"]), "description": m["description"][:150],
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
