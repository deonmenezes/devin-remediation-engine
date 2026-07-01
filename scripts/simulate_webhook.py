#!/usr/bin/env python3
"""Fire a synthetic GitHub `issues.opened` webhook at a locally running
instance of the remediation engine, signed exactly like GitHub would sign it.

This exists so the event-driven trigger can be demoed end-to-end without
exposing a public webhook URL (no ngrok/tunnel needed). In production you'd
point a real GitHub webhook at /webhook/github instead.

Usage:
    GITHUB_WEBHOOK_SECRET=changeme python scripts/simulate_webhook.py
    python scripts/simulate_webhook.py --url http://localhost:8000/webhook/github
"""
import argparse
import hashlib
import hmac
import json
import os
import sys
import urllib.request


def sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:8000/webhook/github")
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPO", "deonmenezes/superset"))
    parser.add_argument("--secret", default=os.environ.get("GITHUB_WEBHOOK_SECRET", "changeme"))
    args = parser.parse_args()

    owner, name = args.repo.split("/", 1)
    payload = {
        "action": "opened",
        "issue": {
            "number": 999999,
            "title": "[security] SIMULATED: webhook trigger smoke test",
            "labels": [{"name": "devin-remediate"}, {"name": "security"}],
            "html_url": f"https://github.com/{args.repo}/issues/999999",
        },
        "repository": {"full_name": args.repo, "owner": {"login": owner}, "name": name},
    }
    body = json.dumps(payload).encode()

    req = urllib.request.Request(
        args.url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "issues",
            "X-Hub-Signature-256": sign(args.secret, body),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            print(resp.status, resp.read().decode())
    except urllib.error.HTTPError as e:
        print(e.code, e.read().decode(), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
