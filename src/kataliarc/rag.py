"""OpenAI vector-store search for Toulmin and accepted-ADR indexing operations."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import time
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


class RAGError(RuntimeError):
    """Sanitized retrieval error that never includes request credentials."""


def _dotenv_value(dotenv: Path, key: str) -> str | None:
    """Read one simple dotenv assignment without printing or exporting it."""
    try:
        lines = dotenv.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    assignment = re.compile(r"^\s*(?:export\s+)?" + re.escape(key) + r"\s*=\s*(.*)$")
    for line in lines:
        match = assignment.match(line)
        if not match:
            continue
        value = match.group(1).strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        else:
            value = value.split(" #", 1)[0].strip()
        return value or None
    return None


def configured_value(name: str, config_root: Path) -> str | None:
    value = os.environ.get(name)
    if value:
        return value
    return _dotenv_value(config_root / ".env", name)


def load_rag_settings(config: dict, config_root: Path) -> dict:
    rag = config.get("rag", {}) if isinstance(config.get("rag", {}), dict) else {}
    vector_store_id = rag.get("vector_store_id") or configured_value("OPENAI_VECTOR_STORE_ID", config_root)
    return {
        "enabled": bool(rag.get("enabled", bool(vector_store_id))),
        "provider": rag.get("provider", "openai-vector-store"),
        "vector_store_id": vector_store_id,
        "max_results": rag.get("max_results", 10),
        "max_queries": rag.get("max_queries", 24),
    }


class OpenAIVectorStoreRetriever:
    """Search an existing vector store; this adapter never creates or updates stores."""

    def __init__(self, api_key: str, vector_store_id: str, *, timeout: float = 25.0, opener: Callable = urlopen):
        if not api_key:
            raise RAGError("OPENAI_API_KEY is not configured.")
        if not vector_store_id:
            raise RAGError("OpenAI vector store ID is not configured.")
        self._api_key = api_key
        self.vector_store_id = vector_store_id
        self.timeout = timeout
        self.opener = opener

    def update_attributes(self, file_id: str, attributes: dict) -> dict:
        """Update vector-store file metadata without deleting the source file."""
        return self._json_request(
            "POST",
            f"/vector_stores/{quote(self.vector_store_id, safe='')}/files/{quote(file_id, safe='')}",
            {"attributes": attributes},
        )

    def _json_request(self, method: str, path: str, body: dict | None = None) -> dict:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = Request(
            f"https://api.openai.com/v1{path}",
            data=data,
            headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json", "OpenAI-Beta": "assistants=v2"},
            method=method,
        )
        try:
            with self.opener(request, timeout=self.timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise RAGError(f"OpenAI vector-store operation failed (HTTP {exc.code}).") from None
        except URLError as exc:
            raise RAGError(f"OpenAI vector-store operation could not connect ({type(exc.reason).__name__}).") from None
        except (TimeoutError, OSError):
            raise RAGError("OpenAI vector-store operation failed due to a network or timeout error.") from None
        except (UnicodeError, json.JSONDecodeError):
            raise RAGError("OpenAI vector-store operation returned an invalid response.") from None
        if not isinstance(result, dict):
            raise RAGError("OpenAI vector-store operation returned an invalid response.")
        return result

    def _list_files(self) -> list[dict]:
        store_id = quote(self.vector_store_id, safe="")
        after = None
        result: list[dict] = []
        for _ in range(100):
            query = {"limit": 100}
            if after:
                query["after"] = after
            page = self._json_request("GET", f"/vector_stores/{store_id}/files?{urlencode(query)}")
            data = page.get("data", [])
            if isinstance(data, list):
                result.extend(item for item in data if isinstance(item, dict))
            if not page.get("has_more") or not data:
                break
            after = data[-1].get("id") if isinstance(data[-1], dict) else None
            if not after:
                break
        return result

    def _delete_vector_store_file(self, file_id: str) -> None:
        self._json_request(
            "DELETE",
            f"/vector_stores/{quote(self.vector_store_id, safe='')}/files/{quote(file_id, safe='')}",
        )

    def _upload_markdown(self, filename: str, document: str) -> str:
        boundary = "----kataliarc-" + os.urandom(18).hex()
        body = b"".join([
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"purpose\"\r\n\r\nassistants\r\n".encode(),
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\nContent-Type: text/markdown; charset=utf-8\r\n\r\n".encode(),
            document.encode("utf-8"),
            f"\r\n--{boundary}--\r\n".encode(),
        ])
        request = Request(
            "https://api.openai.com/v1/files",
            data=body,
            headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        try:
            with self.opener(request, timeout=self.timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise RAGError(f"OpenAI file upload failed (HTTP {exc.code}).") from None
        except URLError as exc:
            raise RAGError(f"OpenAI file upload could not connect ({type(exc.reason).__name__}).") from None
        except (TimeoutError, OSError):
            raise RAGError("OpenAI file upload failed due to a network or timeout error.") from None
        except (UnicodeError, json.JSONDecodeError):
            raise RAGError("OpenAI file upload returned an invalid response.") from None
        file_id = result.get("id") if isinstance(result, dict) else None
        if not isinstance(file_id, str) or not file_id:
            raise RAGError("OpenAI file upload response did not include a file ID.")
        return file_id

    def index_accepted_adr(
        self,
        *,
        filename: str,
        document: str,
        attributes: dict,
        existing_file_id: str | None = None,
        on_uploaded: Callable[[str], None] | None = None,
        poll_attempts: int = 30,
        poll_interval: float = 1.0,
    ) -> dict:
        """Attach an accepted ADR idempotently; called by an asynchronous CLI worker."""
        index_key = attributes.get("index_key")
        files = self._list_files()
        existing = next((item for item in files if isinstance(item.get("attributes"), dict) and item["attributes"].get("index_key") == index_key), None)
        if existing is None and existing_file_id:
            existing = next((item for item in files if item.get("id") == existing_file_id), None)
        file_id = existing.get("id") if existing else existing_file_id
        if existing and existing.get("status") in {"failed", "cancelled"}:
            self._delete_vector_store_file(file_id)
            existing = None
        if not file_id:
            file_id = self._upload_markdown(filename, document)
            if on_uploaded:
                on_uploaded(file_id)
        if not existing:
            attached = self._json_request(
                "POST",
                f"/vector_stores/{quote(self.vector_store_id, safe='')}/files",
                {"file_id": file_id, "attributes": attributes},
            )
        else:
            attached = existing
            # Retry metadata updates if the prior run attached the file before recording completion.
            if attached.get("attributes") != attributes:
                attached = self.update_attributes(file_id, attributes)
        status = attached.get("status")
        for _ in range(poll_attempts):
            if status == "completed":
                return {"file_id": file_id, "status": status, "attributes": attached.get("attributes", attributes)}
            if status in {"failed", "cancelled"}:
                error = attached.get("last_error") or {}
                raise RAGError(f"OpenAI vectorization {status}: {error.get('code', 'unknown error')}.")
            if poll_interval:
                time.sleep(poll_interval)
            attached = self._json_request(
                "GET",
                f"/vector_stores/{quote(self.vector_store_id, safe='')}/files/{quote(file_id, safe='')}",
            )
            status = attached.get("status")
        raise RAGError("OpenAI vectorization is still in progress; retry indexing later.")

    def search(self, query: str, *, max_results: int = 10) -> list[dict]:
        if not 1 <= max_results <= 50:
            raise ValueError("max_results must be between 1 and 50")
        store_id = quote(self.vector_store_id, safe="")
        body = json.dumps({"query": query, "max_num_results": max_results}).encode("utf-8")
        request = Request(
            f"https://api.openai.com/v1/vector_stores/{store_id}/search",
            data=body,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with self.opener(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise RAGError(f"OpenAI vector-store search failed (HTTP {exc.code}).") from None
        except URLError as exc:
            raise RAGError(f"OpenAI vector-store search could not connect ({type(exc.reason).__name__}).") from None
        except (TimeoutError, OSError):
            raise RAGError("OpenAI vector-store search failed due to a network or timeout error.") from None
        except (UnicodeError, json.JSONDecodeError):
            raise RAGError("OpenAI vector-store search returned an invalid response.") from None

        data = payload.get("data", []) if isinstance(payload, dict) else []
        results = []
        for index, item in enumerate(data):
            if not isinstance(item, dict):
                continue
            content = item.get("content", [])
            text = "\n".join(part.get("text", "") for part in content if isinstance(part, dict) and part.get("type") == "text")
            if not text.strip():
                continue
            attributes = item.get("attributes") if isinstance(item.get("attributes"), dict) else {}
            file_id = item.get("file_id")
            filename = item.get("filename")
            results.append({
                "file_id": file_id,
                "filename": filename,
                "adr_id": attributes.get("adr_id") or attributes.get("decision_id"),
                "result_index": index,
                "score": item.get("score"),
                "attributes": attributes,
                "text": text,
                "source_ref": {
                    "type": "historical_adr",
                    "file_id": file_id,
                    "filename": filename,
                    "adr_id": attributes.get("adr_id") or attributes.get("decision_id"),
                    "attributes": attributes,
                },
            })
        return results
