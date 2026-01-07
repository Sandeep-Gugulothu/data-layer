import os
from abc import ABC, abstractmethod
from minio import Minio
from src.config import MINIO_ENDPOINT, MINIO_ACCESS_KEY, MINIO_SECRET_KEY, MINIO_SECURE, LOCAL_STORAGE_PATH, logger

class ObjectStorage(ABC):
    @abstractmethod
    def put(self, key: str, data: bytes) -> None:
        pass

    @abstractmethod
    def get(self, key: str) -> bytes:
        pass

    @abstractmethod
    def exists(self, key: str) -> bool:
        pass

class LocalStorage(ObjectStorage):
    def __init__(self, base_path: str = LOCAL_STORAGE_PATH):
        self.base_path = base_path
        os.makedirs(self.base_path, exist_ok=True)
        logger.info(f"Initialized LocalStorage fallback at {self.base_path}")

    def _get_path(self, key: str) -> str:
        path = os.path.join(self.base_path, key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        return path

    def put(self, key: str, data: bytes) -> None:
        with open(self._get_path(key), "wb") as f:
            f.write(data)

    def get(self, key: str) -> bytes:
        with open(self._get_path(key), "rb") as f:
            return f.read()

    def exists(self, key: str) -> bool:
        return os.path.exists(os.path.join(self.base_path, key))

class MinioStorage(ObjectStorage):
    def __init__(self):
        self.client = Minio(
            endpoint=MINIO_ENDPOINT,
            access_key=MINIO_ACCESS_KEY,
            secret_key=MINIO_SECRET_KEY,
            secure=MINIO_SECURE
        )
        self.bucket = "fdp-data"
        if not self.client.bucket_exists(self.bucket):
            self.client.make_bucket(self.bucket)
            logger.info(f"Created MinIO bucket: {self.bucket}")

    def put(self, key: str, data: bytes) -> None:
        from io import BytesIO
        self.client.put_object(
            bucket_name=self.bucket,
            object_name=key,
            data=BytesIO(data),
            length=len(data)
        )

    def get(self, key: str) -> bytes:
        response = self.client.get_object(self.bucket, key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    def exists(self, key: str) -> bool:
        try:
            self.client.stat_object(self.bucket, key)
            return True
        except Exception:
            return False

def get_storage() -> ObjectStorage:
    try:
        storage = MinioStorage()
        logger.info("Connected to MinIO object storage successfully.")
        return storage
    except Exception as e:
        logger.warning(f"Failed to connect to MinIO ({e}). Falling back to local filesystem storage.")
        return LocalStorage()
