"""Pulls documents from an external S3 / MinIO bucket - a customer's own
object store or a CMMS export drop. Uses last-modified as the cursor."""

from connectors.base import Connector, SyncItem


class BucketConnector(Connector):
    def __init__(self, id: str, endpoint: str, bucket: str, access_key: str,
                 secret_key: str, prefix="", secure=True):
        super().__init__(id)
        from minio import Minio
        self._client = Minio(endpoint.replace("http://", "")
                             .replace("https://", ""),
                             access_key=access_key, secret_key=secret_key,
                             secure=secure)
        self._bucket = bucket
        self._prefix = prefix

    def fetch(self, since: str):
        objects = self._client.list_objects(self._bucket, prefix=self._prefix,
                                            recursive=True)
        fresh = [o for o in objects
                 if o.last_modified and o.last_modified.isoformat() > (since or "")]
        for obj in sorted(fresh, key=lambda o: o.last_modified):
            resp = self._client.get_object(self._bucket, obj.object_name)
            try:
                data = resp.read()
            finally:
                resp.close()
                resp.release_conn()
            yield SyncItem(filename=obj.object_name.rsplit("/", 1)[-1],
                           data=data, marker=obj.last_modified.isoformat())
