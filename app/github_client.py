import requests

from . import config

GITHUB_API = "https://api.github.com"


class GitHubClient:
    def __init__(self, token=None, repo=None):
        self.token = token or config.GITHUB_TOKEN
        self.repo = repo or config.GITHUB_REPO
        self._http = requests.Session()
        self._http.headers.update(
            {
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
            }
        )

    def list_open_issues(self, label=None):
        label = label or config.GITHUB_ISSUE_LABEL
        issues = []
        page = 1
        while True:
            resp = self._http.get(
                f"{GITHUB_API}/repos/{self.repo}/issues",
                params={"state": "open", "labels": label, "per_page": 100, "page": page},
                timeout=20,
            )
            resp.raise_for_status()
            batch = resp.json()
            # Exclude PRs, which the issues endpoint also returns.
            issues.extend(i for i in batch if "pull_request" not in i)
            if len(batch) < 100:
                break
            page += 1
        return issues

    def comment_on_issue(self, issue_number, body):
        resp = self._http.post(
            f"{GITHUB_API}/repos/{self.repo}/issues/{issue_number}/comments",
            json={"body": body},
            timeout=20,
        )
        resp.raise_for_status()
        return resp.json()
