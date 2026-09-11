"""Archive completed research reports in a GitCode repository."""

import base64
import re
from urllib.parse import quote, urlparse

import httpx

from app.config import settings
from app.core.logging import get_logger
from app.models.research_report_model import RESEARCH_STATUS_DONE, ResearchReport

logger = get_logger(__name__)


class GitCodeNotConfigured(RuntimeError):
    """GitCode repository or PAT is not configured."""


class GitCodePublishError(RuntimeError):
    """A GitCode API operation failed."""


class GitCodeService:
    def __init__(self) -> None:
        self.repo_url = settings.gitcode_repo_url.rstrip("/")
        self.api_base = settings.gitcode_api_base_url.rstrip("/")
        self.branch = settings.gitcode_branch.strip() or "main"
        self.token = settings.gitcode_token.strip()

    @property
    def configured(self) -> bool:
        return bool(self.token and self.repo_url)

    def _repo_parts(self) -> tuple[str, str]:
        parsed = urlparse(self.repo_url)
        parts = [part for part in parsed.path.strip("/").split("/") if part]
        if len(parts) < 2:
            raise GitCodeNotConfigured("GitCode repository URL is invalid")
        return parts[0], parts[1].removesuffix(".git")

    @staticmethod
    def _safe_title(report: ResearchReport) -> str:
        title = (report.title or report.topic or "深度研究").strip()
        title = re.sub(r"[\r\n]+", " ", title)
        title = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", title)
        title = re.sub(r"\s+", "_", title).strip(" ._")
        # Keep paths readable on mobile while avoiding excessively long URLs.
        return title[:120].rstrip(" ._") or "深度研究"

    def _file_path(self, report: ResearchReport) -> str:
        """Use report title plus creation time as the repository filename."""
        timestamp = (
            report.created_at.strftime("%Y%m%d-%H%M%S")
            if report.created_at
            else "unknown-time"
        )
        # Include a stable report suffix so same-title reports created in the
        # same second never overwrite one another in the archive repository.
        suffix = str(report.id).split("-")[0] if report.id else "unknown"
        return f"reports/{self._safe_title(report)}_{timestamp}_{suffix}.md"

    @staticmethod
    def _legacy_file_path(report: ResearchReport) -> str:
        """Path used before the human-readable naming scheme was introduced."""
        return f"reports/{report.id}.md"

    def _endpoint(self, owner: str, repo: str, path: str) -> str:
        encoded_path = "/".join(quote(part, safe="") for part in path.split("/"))
        return (
            f"{self.api_base}/repos/{quote(owner, safe='')}/"
            f"{quote(repo, safe='')}/contents/{encoded_path}"
        )

    def report_url(self, report: ResearchReport) -> str:
        owner, repo = self._repo_parts()
        path = quote(self._file_path(report), safe="/")
        return (
            f"https://gitcode.com/{owner}/{repo}/blob/"
            f"{quote(self.branch, safe='')}/{path}"
        )

    def _markdown(self, report: ResearchReport) -> str:
        title = (report.title or report.topic or "深度研究报告").strip()
        topic = (report.topic or "").strip()
        body = (report.report_md or "").strip()
        metadata = [
            f"# {title}",
            "",
            f"> 研究主题：{topic}",
            f"> 报告 ID：{report.id}",
        ]
        if report.created_at:
            metadata.append(f"> 生成时间：{report.created_at.isoformat()}")
        return "\n".join(metadata) + "\n\n" + body + "\n"

    @staticmethod
    def _response_detail(response: httpx.Response) -> str:
        try:
            body = response.json()
            if isinstance(body, dict):
                return str(body.get("message") or body.get("msg") or "")
        except (ValueError, TypeError):
            pass
        return ""

    def _ensure_success(self, response: httpx.Response, action: str) -> None:
        if response.status_code in (200, 201):
            return
        detail = self._response_detail(response)
        suffix = f": {detail[:200]}" if detail else ""
        raise GitCodePublishError(
            f"GitCode {action} failed (HTTP {response.status_code}){suffix}"
        )

    async def publish_report(self, report: ResearchReport) -> str:
        """Create/update a report and remove its old UUID-only filename."""
        if report.status != RESEARCH_STATUS_DONE or not (report.report_md or "").strip():
            raise GitCodePublishError(
                "Refusing to archive a research report that is not successfully completed"
            )
        if not self.configured:
            raise GitCodeNotConfigured("GitCode PAT is not configured")

        owner, repo = self._repo_parts()
        path = self._file_path(report)
        endpoint = self._endpoint(owner, repo, path)
        headers = {"Authorization": f"Bearer {self.token}"}
        payload_base = {
            "content": base64.b64encode(
                self._markdown(report).encode("utf-8")
            ).decode("ascii"),
            "message": f"docs: archive research report {report.id}",
            "branch": self.branch,
        }
        timeout = httpx.Timeout(30.0, connect=10.0)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                existing = await client.get(
                    endpoint,
                    params={"ref": self.branch},
                    headers=headers,
                )
                if existing.status_code == 200:
                    body = existing.json()
                    sha = body.get("sha") if isinstance(body, dict) else None
                    if not sha:
                        raise GitCodePublishError(
                            "GitCode did not return the existing file SHA"
                        )
                    response = await client.put(
                        endpoint,
                        json={**payload_base, "sha": sha},
                        headers=headers,
                    )
                elif existing.status_code == 404:
                    response = await client.post(
                        endpoint, json=payload_base, headers=headers
                    )
                else:
                    raise GitCodePublishError(
                        f"GitCode file lookup failed (HTTP {existing.status_code})"
                    )
                self._ensure_success(response, "publish")

                # Migrate files created by the old UUID-only naming scheme.
                # The new file is committed first, so a failed delete cannot
                # lose the report.
                legacy_path = self._legacy_file_path(report)
                if legacy_path != path:
                    legacy_endpoint = self._endpoint(owner, repo, legacy_path)
                    legacy = await client.get(
                        legacy_endpoint,
                        params={"ref": self.branch},
                        headers=headers,
                    )
                    if legacy.status_code == 200:
                        legacy_body = legacy.json()
                        legacy_sha = (
                            legacy_body.get("sha")
                            if isinstance(legacy_body, dict)
                            else None
                        )
                        if not legacy_sha:
                            raise GitCodePublishError(
                                "GitCode did not return the legacy file SHA"
                            )
                        deleted = await client.request(
                            "DELETE",
                            legacy_endpoint,
                            json={
                                "message": f"docs: rename research report {report.id}",
                                "sha": legacy_sha,
                                "branch": self.branch,
                            },
                            headers=headers,
                        )
                        self._ensure_success(deleted, "remove legacy file")
                    elif legacy.status_code != 404:
                        raise GitCodePublishError(
                            f"GitCode legacy file lookup failed "
                            f"(HTTP {legacy.status_code})"
                        )
        except GitCodePublishError:
            raise
        except httpx.HTTPError as exc:
            raise GitCodePublishError(f"GitCode network request failed: {exc}") from exc
        except (ValueError, TypeError) as exc:
            raise GitCodePublishError(f"GitCode response parsing failed: {exc}") from exc

        body = response.json()
        content = body.get("content") if isinstance(body, dict) else None
        html_url = content.get("html_url") if isinstance(content, dict) else None
        url = html_url or self.report_url(report)
        logger.info(
            "Research report archived to GitCode: report=%s path=%s",
            report.id,
            path,
        )
        return str(url)
