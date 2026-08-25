import io

from minio import Minio

from plantmind_core.config import get_settings

BUCKET = "docs"


def _client_for(endpoint: str, s) -> Minio:
    host = endpoint.replace("http://", "").replace("https://", "")
    # region is passed explicitly so minio-py never tries to discover it. Left
    # unset it calls GET /<bucket>?location= on first use, which the signing
    # client cannot do - its endpoint is the browser's hostname, unreachable
    # from in here. The region is signed, so both clients must use the same one.
    return Minio(host, access_key=s.minio_user, secret_key=s.minio_password,
                 secure=endpoint.startswith("https"), region=s.minio_region)


class ObjectStore:
    """Thin wrapper over MinIO. Keys look like staging/<uuid>/<filename>
    before classification and raw/<doc_id>/<filename> after.

    Two clients, deliberately. Everything server-side talks to MinIO on the
    compose network (minio:9000). Presigned URLs are different: they are
    consumed by a browser, and SigV4 signs the Host header, so a URL signed for
    minio:9000 and then string-rewritten to localhost:9000 arrives with a host
    the signature was never computed over - MinIO recomputes, disagrees, and
    returns SignatureDoesNotMatch. The public client exists so the signature is
    calculated against the host the browser will actually send.
    """

    def __init__(self, client: Minio, public: Minio | None = None):
        self._client = client
        self._public = public or client
        if not client.bucket_exists(BUCKET):
            client.make_bucket(BUCKET)

    @classmethod
    def from_settings(cls) -> "ObjectStore":
        s = get_settings()
        return cls(_client_for(s.minio_endpoint, s),
                   _client_for(s.minio_public_endpoint, s))

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

    def exists(self, key: str) -> bool:
        try:
            self._client.stat_object(BUCKET, key)
            return True
        except Exception:
            return False

    def move(self, src: str, dst: str):
        from minio.commonconfig import CopySource
        self._client.copy_object(BUCKET, dst, CopySource(BUCKET, src))
        self._client.remove_object(BUCKET, src)

    def delete(self, key: str):
        self._client.remove_object(BUCKET, key)

    def _clean_doc_id(self, doc_id: str) -> str:
        if not doc_id:
            return ""
        return str(doc_id).removeprefix("doc:").strip()

    def find_document(self, doc_id: str):
        """The raw object for a doc_id (key raw/<doc_id>/<filename>).
        Returns (filename, bytes) or None - used to serve citation sources."""
        clean = self._clean_doc_id(doc_id)
        if not clean:
            return None

        # 1. Exact prefix match: raw/<clean>/
        prefix = f"raw/{clean}/"
        for obj in self._client.list_objects(BUCKET, prefix=prefix):
            filename = obj.object_name.rsplit("/", 1)[-1]
            return filename, self.get(obj.object_name)

        # 2. Search all objects in raw/ for matching filename, folder hash, or partial ID
        clean_lower = clean.lower()
        for obj in self._client.list_objects(BUCKET, prefix="raw/", recursive=True):
            parts = obj.object_name.split("/")
            if len(parts) >= 3:
                folder_id = parts[1].lower()
                fname = parts[-1]
                if (folder_id.startswith(clean_lower) or clean_lower.startswith(folder_id)
                        or fname.lower() == clean_lower or clean_lower in fname.lower()):
                    return fname, self.get(obj.object_name)
        return None

    def presigned_url(self, doc_id: str, expires_minutes: int = 5) -> str | None:
        """A short-lived URL the browser can fetch straight from MinIO, so a
        large PDF does not stream through the gateway.

        Listed on the internal client (a real network call on the compose
        network) but signed on the public one, which only has to carry the
        hostname the browser will send - it is never connected to, which is why
        its region is pinned in config rather than discovered.
        """
        from datetime import timedelta
        clean = self._clean_doc_id(doc_id)
        if not clean:
            return None

        prefix = f"raw/{clean}/"
        for obj in self._client.list_objects(BUCKET, prefix=prefix):
            return self._public.presigned_get_object(
                BUCKET, obj.object_name, expires=timedelta(minutes=expires_minutes)
            )

        clean_lower = clean.lower()
        for obj in self._client.list_objects(BUCKET, prefix="raw/", recursive=True):
            parts = obj.object_name.split("/")
            if len(parts) >= 3:
                folder_id = parts[1].lower()
                fname = parts[-1]
                if (folder_id.startswith(clean_lower) or clean_lower.startswith(folder_id)
                        or fname.lower() == clean_lower or clean_lower in fname.lower()):
                    return self._public.presigned_get_object(
                        BUCKET, obj.object_name, expires=timedelta(minutes=expires_minutes)
                    )
        return None

    def document_filename(self, doc_id: str) -> str | None:
        """The readable name behind a doc_id, straight off the object key.

        Storage always knows this - the key is raw/<doc_id>/<filename> - which
        makes it a reliable fallback for citations whose graph node never got a
        filename prop, or that were emitted before the node existed.
        """
        clean = self._clean_doc_id(doc_id)
        if not clean:
            return None

        prefix = f"raw/{clean}/"
        for obj in self._client.list_objects(BUCKET, prefix=prefix):
            return obj.object_name.rsplit("/", 1)[-1]

        clean_lower = clean.lower()
        for obj in self._client.list_objects(BUCKET, prefix="raw/", recursive=True):
            parts = obj.object_name.split("/")
            if len(parts) >= 3:
                folder_id = parts[1].lower()
                fname = parts[-1]
                if (folder_id.startswith(clean_lower) or clean_lower.startswith(folder_id)
                        or fname.lower() == clean_lower or clean_lower in fname.lower()):
                    return fname
        return None
