from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from PIL import Image


@dataclass(frozen=True)
class StoredImage:
    image_id: str
    path: Path
    sha256: str
    width: int
    height: int
    format: str


class ImageStore:
    def __init__(
        self,
        upload_dir: str | Path = "data/uploads/images",
        max_bytes: int = 12 * 1024 * 1024,
        allowed_extensions: set[str] | None = None,
    ) -> None:
        self.upload_dir = Path(upload_dir)
        self.max_bytes = max_bytes
        self.allowed_extensions = allowed_extensions or {".jpg", ".jpeg", ".png", ".webp"}
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    def save_upload(self, file_obj, filename: str) -> StoredImage:
        suffix = Path(filename or "").suffix.lower()
        if suffix not in self.allowed_extensions:
            raise ValueError(f"Unsupported image extension: {suffix}")

        image_id = f"img_{uuid4().hex}"
        target_path = self.upload_dir / f"{image_id}{suffix}"

        hasher = hashlib.sha256()
        total = 0

        with target_path.open("wb") as output:
            while True:
                chunk = file_obj.read(1024 * 1024)
                if not chunk:
                    break

                total += len(chunk)
                if total > self.max_bytes:
                    target_path.unlink(missing_ok=True)
                    raise ValueError(f"Image is too large. Max bytes: {self.max_bytes}")

                hasher.update(chunk)
                output.write(chunk)

        return self._validate_and_describe(
            image_id=image_id,
            path=target_path,
            sha256=hasher.hexdigest(),
        )

    def save_local_copy(self, source_path: str | Path) -> StoredImage:
        source = Path(source_path)
        if not source.exists():
            raise FileNotFoundError(f"Image file not found: {source}")

        suffix = source.suffix.lower()
        if suffix not in self.allowed_extensions:
            raise ValueError(f"Unsupported image extension: {suffix}")

        image_id = f"img_{uuid4().hex}"
        target_path = self.upload_dir / f"{image_id}{suffix}"
        shutil.copyfile(source, target_path)

        sha256 = hashlib.sha256(target_path.read_bytes()).hexdigest()
        return self._validate_and_describe(
            image_id=image_id,
            path=target_path,
            sha256=sha256,
        )

    def _validate_and_describe(self, image_id: str, path: Path, sha256: str) -> StoredImage:
        try:
            with Image.open(path) as image:
                image.verify()

            with Image.open(path) as image:
                width, height = image.size
                image_format = image.format or path.suffix.lstrip(".").upper()
        except Exception as exc:
            path.unlink(missing_ok=True)
            raise ValueError(f"Invalid image file: {exc}") from exc

        return StoredImage(
            image_id=image_id,
            path=path,
            sha256=sha256,
            width=width,
            height=height,
            format=image_format,
        )
