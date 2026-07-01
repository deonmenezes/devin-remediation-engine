import base64

import requests

from . import config

GITHUB_API = "https://api.github.com"
GITHUB_GRAPHQL = "https://api.github.com/graphql"


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

    # --- pull requests / commit statuses (the "deps-verify" merge gate) --------
    #
    # GitHub Actions can't run on this private fork (the account's Actions billing
    # is blocked), so the engine acts as external CI: it validates a dependency
    # PR and reports the result as a commit status. This is the same mechanism
    # CircleCI / Jenkins / Buildkite use - a first-class GitHub merge gate.

    def list_open_pulls(self):
        pulls, page = [], 1
        while True:
            resp = self._http.get(
                f"{GITHUB_API}/repos/{self.repo}/pulls",
                params={"state": "open", "per_page": 100, "page": page},
                timeout=20,
            )
            resp.raise_for_status()
            batch = resp.json()
            pulls.extend(batch)
            if len(batch) < 100:
                break
            page += 1
        return pulls

    def list_pr_files(self, number):
        files, page = [], 1
        while True:
            resp = self._http.get(
                f"{GITHUB_API}/repos/{self.repo}/pulls/{number}/files",
                params={"per_page": 100, "page": page},
                timeout=20,
            )
            resp.raise_for_status()
            batch = resp.json()
            files.extend(batch)
            if len(batch) < 100:
                break
            page += 1
        return files

    def get_file_at_ref(self, path, ref):
        """Return the decoded text of a file at a given ref, or None if absent."""
        resp = self._http.get(
            f"{GITHUB_API}/repos/{self.repo}/contents/{path}",
            params={"ref": ref},
            timeout=20,
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("encoding") != "base64":
            return payload.get("content")
        return base64.b64decode(payload["content"]).decode("utf-8", "replace")

    def status_state_for_context(self, sha, context):
        """Current state of a specific commit-status context, or None if unset."""
        resp = self._http.get(
            f"{GITHUB_API}/repos/{self.repo}/commits/{sha}/statuses",
            params={"per_page": 100},
            timeout=20,
        )
        resp.raise_for_status()
        for status in resp.json():  # newest first
            if status.get("context") == context:
                return status.get("state")
        return None

    def post_status(self, sha, state, context, description, target_url=None):
        body = {"state": state, "context": context, "description": description[:140]}
        if target_url:
            body["target_url"] = target_url
        resp = self._http.post(
            f"{GITHUB_API}/repos/{self.repo}/statuses/{sha}",
            json=body,
            timeout=20,
        )
        resp.raise_for_status()
        return resp.json()

    def mark_pr_ready(self, node_id):
        """Flip a draft PR to ready-for-review (draft PRs can't be merged)."""
        query = (
            "mutation($id:ID!){markPullRequestReadyForReview(input:{pullRequestId:$id})"
            "{pullRequest{isDraft}}}"
        )
        resp = self._http.post(
            GITHUB_GRAPHQL, json={"query": query, "variables": {"id": node_id}}, timeout=20
        )
        resp.raise_for_status()
        return resp.json()
