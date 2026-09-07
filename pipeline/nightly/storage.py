"""Small GCS adapter. Tokens, raw responses, and data never go to public logs."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from urllib.parse import quote

import requests


class StorageError(RuntimeError):
    pass


class Conflict(StorageError):
    pass


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


class GCS:
    def __init__(self, bucket: str):
        self.bucket = bucket
        self.http = requests.Session()
        executable = shutil.which("gcloud.cmd" if os.name == "nt" else "gcloud")
        if not executable:
            raise StorageError("Google Cloud CLI is not available on PATH")
        token = subprocess.run([executable, "auth", "print-access-token"], check=True,
                               capture_output=True, text=True).stdout.strip()
        if not token:
            raise StorageError("GCP access token is missing")
        self.http.headers["Authorization"] = f"Bearer {token}"
        self.base = f"https://storage.googleapis.com/storage/v1/b/{bucket}/o"

    def request(self, method: str, url: str, **kwargs):
        try:
            response = self.http.request(method, url, timeout=(30, 600), **kwargs)
        except requests.RequestException:
            raise StorageError("GCS transport interrupted; completion may need recovery") from None
        if response.status_code == 412:
            response.close()
            raise Conflict("GCS generation changed; do not overwrite the current state")
        if response.status_code == 404:
            response.close()
            raise FileNotFoundError("Checkpoint missing or expired; explicit recovery needed")
        if not response.ok:
            status = response.status_code
            response.close()
            raise StorageError(f"GCS request failed (HTTP {status}); response omitted")
        return response

    def metadata(self, name: str) -> dict:
        return self.request("GET", f"{self.base}/{quote(name, safe='')}").json()

    def read_json(self, name: str) -> tuple[dict, str]:
        meta = self.metadata(name)
        with self.request("GET", f"{self.base}/{quote(name, safe='')}",
                          params={"alt": "media", "generation": meta["generation"]},
                          stream=True) as response:
            content = bytearray()
            for chunk in response.iter_content(65536):
                content.extend(chunk)
                if len(content) > 1024 * 1024:
                    raise StorageError("Manifest exceeds 1 MiB")
        return json.loads(content), str(meta["generation"])

    def upload(self, name: str, path: Path, generation: str = "0") -> dict:
        sha = digest(path)
        # Resumable initiation carries a checksum in metadata; completion is
        # atomic. Never retry an uncertain completion with a blind overwrite.
        response = self.request(
            "POST", f"https://storage.googleapis.com/upload/storage/v1/b/{self.bucket}/o",
            params={"uploadType": "resumable", "ifGenerationMatch": generation},
            json={"name": name, "metadata": {"sha256": sha}},
            headers={"X-Upload-Content-Length": str(path.stat().st_size)},
        )
        location = response.headers["Location"]
        if not location.startswith("https://storage.googleapis.com/"):
            raise StorageError("Unexpected GCS upload origin")
        with path.open("rb") as stream:
            meta = self.request("PUT", location, data=stream,
                                headers={"Content-Length": str(path.stat().st_size)}).json()
        return {"object": name, "generation": str(meta["generation"]),
                "sha256": sha, "bytes": path.stat().st_size}

    def put_json(self, name: str, document: dict, scratch: Path, generation: str = "0"):
        path = scratch / "manifest-upload.json"
        path.write_text(json.dumps(document, sort_keys=True), encoding="utf-8")
        return self.upload(name, path, generation)

    def download(self, ref: dict, target: Path):
        count = 0
        with self.request("GET", f"{self.base}/{quote(ref['object'], safe='')}",
                          params={"alt": "media", "generation": ref["generation"]},
                          stream=True) as response, target.open("wb") as stream:
            for chunk in response.iter_content(1024 * 1024):
                count += len(chunk)
                if count > ref["bytes"]:
                    raise StorageError("Bundle exceeds its declared size")
                stream.write(chunk)
        if count != ref["bytes"] or digest(target) != ref["sha256"]:
            raise StorageError("Checkpoint digest/size mismatch")

    def copy(self, ref: dict, name: str) -> dict:
        url = (f"{self.base}/{quote(ref['object'], safe='')}/rewriteTo/b/"
               f"{self.bucket}/o/{quote(name, safe='')}")
        params = {"sourceGeneration": ref["generation"], "ifGenerationMatch": "0"}
        try:
            while True:
                result = self.request("POST", url, params=params, json={}).json()
                if result["done"]:
                    meta = result["resource"]
                    break
                params["rewriteToken"] = result["rewriteToken"]
        except Conflict:
            # A previous completion may have succeeded just before a job died.
            meta = self.metadata(name)
            if (meta.get("metadata", {}).get("sha256") != ref["sha256"]
                    or int(meta["size"]) != ref["bytes"]):
                raise Conflict("Existing snapshot differs from this run") from None
        return {**ref, "object": name, "generation": str(meta["generation"])}

    def delete(self, name: str, generation: str):
        self.request("DELETE", f"{self.base}/{quote(name, safe='')}",
                     params={"ifGenerationMatch": generation}).close()
