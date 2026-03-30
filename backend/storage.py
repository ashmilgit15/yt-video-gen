import os
import shutil
import tempfile
from dataclasses import dataclass

import boto3

from config import settings


CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True)
class StoredFile:
    provider: str
    key: str
    filename: str
    mime_type: str


class StorageBackend:
    provider = "base"

    def persist_video(
        self, source_path: str, video_id: str, filename: str
    ) -> StoredFile:
        raise NotImplementedError

    def materialize(self, key: str) -> str:
        raise NotImplementedError

    def cleanup_materialized(self, materialized_path: str, key: str) -> None:
        raise NotImplementedError

    def resolve_local_path(self, key: str) -> str | None:
        return None

    def open_stream(self, key: str):
        raise NotImplementedError


class LocalStorageBackend(StorageBackend):
    provider = "local"

    def __init__(self) -> None:
        self.root_dir = os.path.abspath(settings.storage_local_dir)
        os.makedirs(self.root_dir, exist_ok=True)

    def _path_for_key(self, key: str) -> str:
        return os.path.join(self.root_dir, key.replace("/", os.sep))

    def persist_video(
        self, source_path: str, video_id: str, filename: str
    ) -> StoredFile:
        key = f"videos/{video_id}/{filename}"
        destination = self._path_for_key(key)
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        shutil.move(source_path, destination)
        return StoredFile(
            provider=self.provider,
            key=key,
            filename=filename,
            mime_type="video/mp4",
        )

    def materialize(self, key: str) -> str:
        return self._path_for_key(key)

    def cleanup_materialized(self, materialized_path: str, key: str) -> None:
        return None

    def resolve_local_path(self, key: str) -> str | None:
        return self._path_for_key(key)

    def open_stream(self, key: str):
        with open(self._path_for_key(key), "rb") as file_handle:
            while chunk := file_handle.read(CHUNK_SIZE):
                yield chunk


class S3StorageBackend(StorageBackend):
    provider = "s3"

    def __init__(self) -> None:
        if not settings.storage_s3_bucket:
            raise RuntimeError("STORAGE_S3_BUCKET is required when STORAGE_BACKEND=s3.")

        self.bucket = settings.storage_s3_bucket
        self.prefix = settings.storage_s3_prefix.strip("/")
        self.client = boto3.client(
            "s3",
            region_name=settings.storage_s3_region,
            endpoint_url=settings.storage_s3_endpoint_url,
            aws_access_key_id=settings.storage_s3_access_key_id,
            aws_secret_access_key=settings.storage_s3_secret_access_key,
        )

    def _object_key(self, key: str) -> str:
        return f"{self.prefix}/{key}" if self.prefix else key

    def persist_video(
        self, source_path: str, video_id: str, filename: str
    ) -> StoredFile:
        key = f"videos/{video_id}/{filename}"
        self.client.upload_file(
            source_path,
            self.bucket,
            self._object_key(key),
            ExtraArgs={"ContentType": "video/mp4"},
        )
        os.remove(source_path)
        return StoredFile(
            provider=self.provider,
            key=key,
            filename=filename,
            mime_type="video/mp4",
        )

    def materialize(self, key: str) -> str:
        suffix = os.path.splitext(key)[1] or ".mp4"
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        temp_file.close()
        self.client.download_file(self.bucket, self._object_key(key), temp_file.name)
        return temp_file.name

    def cleanup_materialized(self, materialized_path: str, key: str) -> None:
        if os.path.exists(materialized_path):
            os.remove(materialized_path)

    def open_stream(self, key: str):
        response = self.client.get_object(Bucket=self.bucket, Key=self._object_key(key))
        stream = response["Body"]
        try:
            while chunk := stream.read(CHUNK_SIZE):
                yield chunk
        finally:
            stream.close()


def get_storage_backend() -> StorageBackend:
    if settings.is_s3_storage:
        return S3StorageBackend()
    return LocalStorageBackend()


def get_backend_for_provider(provider: str | None) -> StorageBackend:
    if provider == "s3":
        return S3StorageBackend()
    return LocalStorageBackend()


storage_backend = get_storage_backend()
