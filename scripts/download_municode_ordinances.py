from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote_plus, urlparse

import requests


LIBRARY_BASE_URL = "https://library.municode.com"
API_BASE_URL = f"{LIBRARY_BASE_URL}/api"
DEFAULT_USER_AGENT = "CivilAI Municode ordinance downloader"


@dataclass(slots=True)
class CodePdfTarget:
    state: str
    client_id: int
    client_name: str
    product_id: int
    product_name: str
    publication_id: int
    latest_updated_date: str | None
    library_url: str
    pdf_url: str
    filename: str


class MunicodeDownloader:
    """Download official Municode publication PDFs for one state library."""

    def __init__(
        self,
        *,
        state: str,
        output_dir: Path,
        timeout_seconds: float,
        delay_seconds: float,
        retries: int,
        user_agent: str,
    ) -> None:
        self.state = state.lower()
        self.output_dir = output_dir
        self.timeout_seconds = timeout_seconds
        self.delay_seconds = delay_seconds
        self.retries = retries
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": user_agent,
                "Accept": "application/json,text/html,application/pdf,*/*",
                "Referer": f"{LIBRARY_BASE_URL}/{self.state}",
                "X-CSRF": "1",
            }
        )

    def warm_session(self) -> None:
        response = self._request("GET", f"{LIBRARY_BASE_URL}/{self.state}")
        response.raise_for_status()

    def get_state_id(self) -> int:
        states = self._get_json("States")
        state_row = next(
            (
                row
                for row in states
                if str(row.get("StateAbbreviation", "")).lower() == self.state
            ),
            None,
        )
        if not state_row:
            raise RuntimeError(f"State abbreviation not found in Municode API: {self.state}")
        return int(state_row["StateID"])

    def list_clients(self, state_id: int) -> list[dict[str, Any]]:
        clients = self._get_json(f"Clients/stateId/{state_id}")
        return sorted(clients, key=lambda item: str(item.get("ClientName", "")).lower())

    def list_pdf_targets(self, clients: list[dict[str, Any]], *, limit: int | None = None) -> list[CodePdfTarget]:
        targets: list[CodePdfTarget] = []
        selected_clients = clients[:limit] if limit else clients
        for index, client in enumerate(selected_clients, start=1):
            client_id = int(client["ClientID"])
            client_name = str(client.get("ClientName") or client_id)
            print(f"[{index}/{len(selected_clients)}] Checking {client_name}...", flush=True)

            try:
                content = self._get_json(f"ClientContent/{client_id}")
            except Exception as exc:
                print(f"  ! skipped: {exc}", flush=True)
                continue

            for code in content.get("codes", []):
                if not code.get("hasPdfDownloadEnabled") or not code.get("hasPdf"):
                    continue
                publication_id = code.get("publicationId")
                if not publication_id:
                    continue

                pdf_url = self.get_pdf_url(int(publication_id))
                product_name = str(code.get("productName") or "Code of Ordinances")
                product_id = int(code.get("productId") or 0)
                targets.append(
                    CodePdfTarget(
                        state=self.state.upper(),
                        client_id=client_id,
                        client_name=client_name,
                        product_id=product_id,
                        product_name=product_name,
                        publication_id=int(publication_id),
                        latest_updated_date=code.get("latestUpdatedDate"),
                        library_url=self.build_library_url(client_name, product_name),
                        pdf_url=pdf_url,
                        filename=self.build_filename(client_name, product_name, int(publication_id), pdf_url),
                    )
                )
                self._sleep()
        return targets

    def get_pdf_url(self, publication_id: int) -> str:
        url = self._get_json(f"PublicationPdfDownload/{publication_id}")
        if not isinstance(url, str) or not url.lower().startswith("http"):
            raise RuntimeError(f"Municode did not return a PDF URL for publication {publication_id}.")
        return url

    def download_pdf(self, target: CodePdfTarget, *, skip_existing: bool = True) -> Path:
        pdf_dir = self.output_dir / "pdf"
        pdf_dir.mkdir(parents=True, exist_ok=True)
        destination = pdf_dir / target.filename
        if skip_existing and destination.exists() and destination.stat().st_size > 0:
            print(f"  = exists: {destination.name}", flush=True)
            return destination

        with self._request("GET", target.pdf_url, stream=True) as response:
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            if "pdf" not in content_type.lower() and not target.pdf_url.lower().split("?")[0].endswith(".pdf"):
                raise RuntimeError(f"Expected PDF for {target.client_name}, got content-type {content_type!r}.")

            temporary_path = destination.with_suffix(".pdf.part")
            with temporary_path.open("wb") as file_handle:
                for chunk in response.iter_content(chunk_size=1024 * 512):
                    if chunk:
                        file_handle.write(chunk)
            temporary_path.replace(destination)

        print(f"  + downloaded: {destination.name}", flush=True)
        self._sleep()
        return destination

    def write_manifest(self, targets: list[CodePdfTarget], downloaded_paths: dict[int, Path]) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = self.output_dir / "manifest.csv"
        with manifest_path.open("w", newline="", encoding="utf-8") as file_handle:
            writer = csv.DictWriter(
                file_handle,
                fieldnames=[
                    "state",
                    "client_id",
                    "client_name",
                    "product_id",
                    "product_name",
                    "publication_id",
                    "latest_updated_date",
                    "library_url",
                    "pdf_url",
                    "local_pdf",
                ],
            )
            writer.writeheader()
            for target in targets:
                local_pdf = downloaded_paths.get(target.publication_id)
                writer.writerow(
                    {
                        "state": target.state,
                        "client_id": target.client_id,
                        "client_name": target.client_name,
                        "product_id": target.product_id,
                        "product_name": target.product_name,
                        "publication_id": target.publication_id,
                        "latest_updated_date": target.latest_updated_date or "",
                        "library_url": target.library_url,
                        "pdf_url": target.pdf_url,
                        "local_pdf": str(local_pdf) if local_pdf else "",
                    }
                )
        return manifest_path

    def write_json_manifest(self, targets: list[CodePdfTarget], downloaded_paths: dict[int, Path]) -> Path:
        manifest_path = self.output_dir / "manifest.json"
        payload = []
        for target in targets:
            local_pdf = downloaded_paths.get(target.publication_id)
            payload.append(
                {
                    "state": target.state,
                    "client_id": target.client_id,
                    "client_name": target.client_name,
                    "product_id": target.product_id,
                    "product_name": target.product_name,
                    "publication_id": target.publication_id,
                    "latest_updated_date": target.latest_updated_date,
                    "library_url": target.library_url,
                    "pdf_url": target.pdf_url,
                    "local_pdf": str(local_pdf) if local_pdf else None,
                }
            )
        manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return manifest_path

    def create_zip(self, zip_path: Path, downloaded_paths: dict[int, Path], manifest_paths: list[Path]) -> Path:
        zip_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for manifest_path in manifest_paths:
                archive.write(manifest_path, manifest_path.name)
            for path in sorted(downloaded_paths.values(), key=lambda item: item.name.lower()):
                archive.write(path, f"pdf/{path.name}")
        return zip_path

    def _get_json(self, path: str) -> Any:
        response = self._request("GET", f"{API_BASE_URL}/{path.lstrip('/')}")
        response.raise_for_status()
        return response.json()

    def _request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                response = self.session.request(method, url, timeout=self.timeout_seconds, **kwargs)
                if response.status_code in {429, 500, 502, 503, 504} and attempt < self.retries:
                    time.sleep(self.delay_seconds * (attempt + 2))
                    continue
                return response
            except requests.RequestException as exc:
                last_error = exc
                if attempt >= self.retries:
                    break
                time.sleep(self.delay_seconds * (attempt + 2))
        raise RuntimeError(f"Request failed for {url}: {last_error}")

    def _sleep(self) -> None:
        if self.delay_seconds > 0:
            time.sleep(self.delay_seconds)

    @staticmethod
    def build_library_url(client_name: str, product_name: str) -> str:
        client_slug = slugify_url_part(client_name)
        product_slug = slugify_url_part(product_name)
        return f"{LIBRARY_BASE_URL}/fl/{client_slug}/codes/{product_slug}"

    @staticmethod
    def build_filename(client_name: str, product_name: str, publication_id: int, pdf_url: str) -> str:
        filename = filename_from_content_disposition_url(pdf_url)
        if filename:
            return safe_filename(filename)
        return safe_filename(f"{client_name}, FL {product_name} publication {publication_id}.pdf")


def filename_from_content_disposition_url(pdf_url: str) -> str | None:
    parsed = urlparse(pdf_url)
    query = unquote_plus(parsed.query)
    match = re.search(r'filename="?([^";]+\.pdf)"?', query, flags=re.IGNORECASE)
    if match:
        return match.group(1)
    return None


def slugify_url_part(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return normalized or "unknown"


def safe_filename(value: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', " ", value)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    if not cleaned.lower().endswith(".pdf"):
        cleaned = f"{cleaned}.pdf"
    return cleaned[:180]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download official Municode ordinance/code PDFs for every municipality in one state library.",
    )
    parser.add_argument("--state", default="fl", help="Municode state abbreviation to crawl. Default: fl")
    parser.add_argument(
        "--output-dir",
        default="downloads/municode_fl",
        help="Directory for PDFs, manifests, and the zip file.",
    )
    parser.add_argument(
        "--zip-name",
        default=None,
        help="Zip filename. Default: municode_<state>_official_pdfs.zip",
    )
    parser.add_argument("--delay", type=float, default=0.35, help="Delay between API/download requests.")
    parser.add_argument("--timeout", type=float, default=90, help="HTTP timeout in seconds.")
    parser.add_argument("--retries", type=int, default=3, help="Retries for transient HTTP/network failures.")
    parser.add_argument("--limit", type=int, default=None, help="Optional client limit for testing.")
    parser.add_argument("--dry-run", action="store_true", help="Discover PDF targets without downloading files.")
    parser.add_argument("--overwrite", action="store_true", help="Re-download PDFs that already exist.")
    parser.add_argument("--no-zip", action="store_true", help="Download files and write manifests without creating a zip.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    state = args.state.lower().strip()
    output_dir = Path(args.output_dir)
    zip_name = args.zip_name or f"municode_{state}_official_pdfs.zip"
    zip_path = output_dir / zip_name

    downloader = MunicodeDownloader(
        state=state,
        output_dir=output_dir,
        timeout_seconds=args.timeout,
        delay_seconds=args.delay,
        retries=args.retries,
        user_agent=DEFAULT_USER_AGENT,
    )

    downloader.warm_session()
    state_id = downloader.get_state_id()
    clients = downloader.list_clients(state_id)
    print(f"Found {len(clients)} Municode clients for {state.upper()}.", flush=True)

    targets = downloader.list_pdf_targets(clients, limit=args.limit)
    print(f"Found {len(targets)} official PDF publication(s).", flush=True)

    downloaded_paths: dict[int, Path] = {}
    if not args.dry_run:
        for index, target in enumerate(targets, start=1):
            print(f"[{index}/{len(targets)}] Downloading {target.client_name} - {target.product_name}", flush=True)
            try:
                downloaded_paths[target.publication_id] = downloader.download_pdf(
                    target,
                    skip_existing=not args.overwrite,
                )
            except Exception as exc:
                print(f"  ! failed: {exc}", flush=True)

    csv_manifest = downloader.write_manifest(targets, downloaded_paths)
    json_manifest = downloader.write_json_manifest(targets, downloaded_paths)
    print(f"Manifest written: {csv_manifest}", flush=True)
    print(f"Manifest written: {json_manifest}", flush=True)

    if args.dry_run:
        print("Dry run complete. No PDFs downloaded and no zip created.", flush=True)
        return 0

    if args.no_zip:
        print("Zip creation skipped.", flush=True)
        return 0

    zip_path = downloader.create_zip(zip_path, downloaded_paths, [csv_manifest, json_manifest])
    print(f"Zip written: {zip_path}", flush=True)
    print(f"Downloaded {len(downloaded_paths)} of {len(targets)} PDF publication(s).", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
