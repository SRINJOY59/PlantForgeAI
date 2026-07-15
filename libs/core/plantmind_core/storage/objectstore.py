import io

from minio import Minio

from plantmind_core.config import get_settings

BUCKET = "docs"


class ObjectStore:
    """Thin wrapper over MinIO. Keys look like staging/<uuid>/<filename>
    before classification and raw/<doc_id>/<filename> after."""

    def __init__(self, client: Minio):
        self._client = client
        if not client.bucket_exists(BUCKET):
            client.make_bucket(BUCKET)

    @classmethod
    def from_settings(cls) -> "ObjectStore":
        s = get_settings()
        endpoint = s.minio_endpoint.replace("http://", "").replace("https://", "")
        client = Minio(endpoint, access_key=s.minio_user,
                       secret_key=s.minio_password,
                       secure=s.minio_endpoint.startswith("https"))
        return cls(client)

    def put(self, key: str, data: bytes, content_type="application/octet-stream"):
        self._client.put_object(BUCKET, key, io.BytesIO(data), len(data),
                                content_type=content_type)

    def get(self, key: str) -> bytes:
        resp = self._client.get_object(BUCKET, key)
        try:
            return resp.read()
        finally:
            resp.close()
            resp.release_conn()

    def move(self, src: str, dst: str):
        from minio.commonconfig import CopySource
        self._client.copy_object(BUCKET, dst, CopySource(BUCKET, src))
        self._client.remove_object(BUCKET, src)

    def delete(self, key: str):
        self._client.remove_object(BUCKET, key)

    def find_document(self, doc_id: str):
        """The raw object for a doc_id (key raw/<doc_id>/<filename>).
        Returns (filename, bytes) or None - used to serve citation sources."""
        prefix = f"raw/{doc_id}/"
        for obj in self._client.list_objects(BUCKET, prefix=prefix):
            filename = obj.object_name.rsplit("/", 1)[-1]
            return filename, self.get(obj.object_name)
        return None
