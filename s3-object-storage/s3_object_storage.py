"""S3-like Object Storage - in-memory implementation."""

import hashlib
import hmac
import re
import time
import uuid
from dataclasses import dataclass, field


@dataclass
class ObjectVersion:
    version_id: str
    data: bytes
    content_type: str
    metadata: dict
    size: int
    etag: str
    last_modified: float
    storage_class: str
    is_delete_marker: bool = False


@dataclass
class Bucket:
    name: str
    created: float
    versioning: bool
    objects: dict = field(default_factory=dict)  # key -> list[ObjectVersion]
    multipart_uploads: dict = field(default_factory=dict)  # upload_id -> {part_num: bytes}
    multipart_meta: dict = field(default_factory=dict)  # upload_id -> key
    policies: list = field(default_factory=list)


class ObjectStorage:
    """S3-like object storage with buckets, versioning, multipart uploads, and presigned URLs."""

    _BUCKET_RE = re.compile(r'^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$')
    _SECRET = uuid.uuid4().hex

    def __init__(self):
        self._buckets: dict[str, Bucket] = {}
        self._presigned: dict[str, dict] = {}

    def _require_bucket(self, name: str) -> Bucket:
        if name not in self._buckets:
            raise KeyError(f"Bucket '{name}' does not exist")
        return self._buckets[name]

    @staticmethod
    def _etag(data: bytes) -> str:
        return hashlib.md5(data).hexdigest()

    def _latest_version(self, bucket: Bucket, key: str) -> ObjectVersion | None:
        versions = bucket.objects.get(key)
        if not versions:
            return None
        latest = versions[-1]
        if latest.is_delete_marker:
            return None
        return latest

    # --- Buckets ---

    def create_bucket(self, bucket: str, versioning: bool = False) -> None:
        """Create a bucket."""
        if not self._BUCKET_RE.match(bucket):
            raise ValueError(f"Invalid bucket name: '{bucket}'")
        if bucket in self._buckets:
            raise ValueError(f"Bucket '{bucket}' already exists")
        self._buckets[bucket] = Bucket(name=bucket, created=time.time(), versioning=versioning)

    def delete_bucket(self, bucket: str) -> None:
        """Delete an empty bucket."""
        b = self._require_bucket(bucket)
        for key, versions in b.objects.items():
            if versions and not versions[-1].is_delete_marker:
                raise ValueError(f"Bucket '{bucket}' is not empty")
            # Even if latest is delete marker, check if there are non-marker versions in versioned bucket
            if b.versioning and any(not v.is_delete_marker for v in versions):
                raise ValueError(f"Bucket '{bucket}' is not empty (has versioned objects)")
        del self._buckets[bucket]

    def list_buckets(self) -> list[dict]:
        """List all buckets with creation date."""
        return [{"name": b.name, "created": b.created} for b in self._buckets.values()]

    # --- Objects ---

    def put_object(self, bucket: str, key: str, data: bytes | str,
                   content_type: str = "application/octet-stream",
                   metadata: dict = None, storage_class: str = "STANDARD") -> dict:
        """Store an object. Returns {version_id, etag, size}."""
        b = self._require_bucket(bucket)
        if len(key) > 1024:
            raise ValueError("Key too long")
        if isinstance(data, str):
            data = data.encode("utf-8")
        etag = self._etag(data)
        vid = str(uuid.uuid4()) if b.versioning else None
        version = ObjectVersion(
            version_id=vid, data=data, content_type=content_type,
            metadata=metadata or {}, size=len(data), etag=etag,
            last_modified=time.time(), storage_class=storage_class,
        )
        if b.versioning:
            b.objects.setdefault(key, []).append(version)
        else:
            b.objects[key] = [version]
        return {"version_id": vid, "etag": etag, "size": len(data)}

    def get_object(self, bucket: str, key: str, version_id: str = None) -> dict | None:
        """Retrieve an object. Returns {data, metadata, version_id, ...} or None."""
        b = self._require_bucket(bucket)
        versions = b.objects.get(key)
        if not versions:
            return None
        if version_id:
            for v in versions:
                if v.version_id == version_id:
                    if v.is_delete_marker:
                        return None
                    return self._version_to_dict(v, include_data=True)
            return None
        latest = self._latest_version(b, key)
        if latest is None:
            return None
        return self._version_to_dict(latest, include_data=True)

    def delete_object(self, bucket: str, key: str, version_id: str = None) -> dict:
        """Delete an object or specific version."""
        b = self._require_bucket(bucket)
        versions = b.objects.get(key)
        if not versions:
            raise KeyError(f"Object '{key}' not found")
        if version_id:
            b.objects[key] = [v for v in versions if v.version_id != version_id]
            if not b.objects[key]:
                del b.objects[key]
            return {"deleted": True, "version_id": version_id}
        if b.versioning:
            vid = str(uuid.uuid4())
            marker = ObjectVersion(
                version_id=vid, data=b"", content_type="", metadata={},
                size=0, etag="", last_modified=time.time(),
                storage_class="STANDARD", is_delete_marker=True,
            )
            versions.append(marker)
            return {"deleted": True, "delete_marker": True, "version_id": vid}
        else:
            del b.objects[key]
            return {"deleted": True}

    def head_object(self, bucket: str, key: str) -> dict | None:
        """Get object metadata without data."""
        b = self._require_bucket(bucket)
        v = self._latest_version(b, key)
        if v is None:
            return None
        return self._version_to_dict(v, include_data=False)

    @staticmethod
    def _version_to_dict(v: ObjectVersion, include_data: bool) -> dict:
        d = {
            "version_id": v.version_id,
            "content_type": v.content_type,
            "metadata": v.metadata,
            "size": v.size,
            "etag": v.etag,
            "last_modified": v.last_modified,
            "storage_class": v.storage_class,
        }
        if include_data:
            d["data"] = v.data
        return d

    # --- Listing ---

    def list_objects(self, bucket: str, prefix: str = "", delimiter: str = None,
                     max_keys: int = 1000, continuation_token: str = None) -> dict:
        """List objects with prefix/delimiter support and pagination."""
        b = self._require_bucket(bucket)
        all_keys = sorted(k for k in b.objects if k.startswith(prefix) and self._latest_version(b, k) is not None)

        if continuation_token:
            all_keys = [k for k in all_keys if k > continuation_token]

        common_prefixes = set()
        objects = []

        for key in all_keys:
            if delimiter:
                rest = key[len(prefix):]
                idx = rest.find(delimiter)
                if idx >= 0:
                    common_prefixes.add(prefix + rest[:idx + len(delimiter)])
                    continue
            if len(objects) >= max_keys:
                return {
                    "objects": objects,
                    "common_prefixes": sorted(common_prefixes),
                    "is_truncated": True,
                    "next_token": objects[-1]["key"],
                }
            v = self._latest_version(b, key)
            objects.append({"key": key, **self._version_to_dict(v, include_data=False)})

        return {
            "objects": objects,
            "common_prefixes": sorted(common_prefixes),
            "is_truncated": False,
            "next_token": None,
        }

    def list_object_versions(self, bucket: str, prefix: str = "") -> list[dict]:
        """List all versions of objects in a bucket."""
        b = self._require_bucket(bucket)
        result = []
        for key in sorted(b.objects):
            if not key.startswith(prefix):
                continue
            for v in b.objects[key]:
                entry = {"key": key, "version_id": v.version_id,
                         "is_delete_marker": v.is_delete_marker,
                         "last_modified": v.last_modified, "size": v.size, "etag": v.etag}
                result.append(entry)
        return result

    # --- Copy ---

    def copy_object(self, src_bucket: str, src_key: str,
                    dst_bucket: str, dst_key: str) -> dict:
        """Copy an object between or within buckets."""
        obj = self.get_object(src_bucket, src_key)
        if obj is None:
            raise KeyError(f"Source object '{src_key}' not found in '{src_bucket}'")
        return self.put_object(dst_bucket, dst_key, obj["data"],
                               content_type=obj["content_type"],
                               metadata=dict(obj["metadata"]),
                               storage_class=obj["storage_class"])

    # --- Multipart ---

    def initiate_multipart(self, bucket: str, key: str) -> str:
        """Start a multipart upload. Returns upload_id."""
        self._require_bucket(bucket)
        upload_id = str(uuid.uuid4())
        b = self._buckets[bucket]
        b.multipart_uploads[upload_id] = {}
        b.multipart_meta[upload_id] = key
        return upload_id

    def upload_part(self, bucket: str, key: str, upload_id: str,
                    part_number: int, data: bytes | str) -> dict:
        """Upload a part. Returns {etag}."""
        b = self._require_bucket(bucket)
        if upload_id not in b.multipart_uploads:
            raise KeyError(f"Upload '{upload_id}' not found")
        if isinstance(data, str):
            data = data.encode("utf-8")
        b.multipart_uploads[upload_id][part_number] = data
        return {"etag": self._etag(data)}

    def complete_multipart(self, bucket: str, key: str, upload_id: str) -> dict:
        """Complete multipart upload. Assembles all parts in order."""
        b = self._require_bucket(bucket)
        if upload_id not in b.multipart_uploads:
            raise KeyError(f"Upload '{upload_id}' not found")
        parts = b.multipart_uploads.pop(upload_id)
        b.multipart_meta.pop(upload_id, None)
        if not parts:
            raise ValueError("No parts uploaded")
        assembled = b"".join(parts[k] for k in sorted(parts))
        return self.put_object(bucket, key, assembled)

    def abort_multipart(self, bucket: str, key: str, upload_id: str) -> None:
        """Abort and clean up a multipart upload."""
        b = self._require_bucket(bucket)
        if upload_id not in b.multipart_uploads:
            raise KeyError(f"Upload '{upload_id}' not found")
        del b.multipart_uploads[upload_id]
        b.multipart_meta.pop(upload_id, None)

    # --- Presigned URLs ---

    def generate_presigned_url(self, bucket: str, key: str,
                               operation: str = "GET", expires_in: int = 3600) -> str:
        """Generate a presigned URL token for temporary access."""
        self._require_bucket(bucket)
        token = hmac.new(self._SECRET.encode(), f"{bucket}/{key}/{operation}/{uuid.uuid4()}".encode(),
                         hashlib.sha256).hexdigest()
        self._presigned[token] = {
            "bucket": bucket, "key": key, "operation": operation.upper(),
            "expires_at": time.time() + expires_in,
        }
        return token

    def access_presigned(self, token: str, current_time: float = None) -> dict:
        """Access an object via presigned URL token."""
        if token not in self._presigned:
            raise ValueError("Invalid presigned URL token")
        info = self._presigned[token]
        now = current_time if current_time is not None else time.time()
        if now > info["expires_at"]:
            raise ValueError("Presigned URL has expired")
        if info["operation"] == "GET":
            obj = self.get_object(info["bucket"], info["key"])
            if obj is None:
                raise KeyError("Object not found")
            return obj
        elif info["operation"] == "PUT":
            return {"bucket": info["bucket"], "key": info["key"], "operation": "PUT",
                    "message": "PUT access granted"}
        raise ValueError(f"Unknown operation: {info['operation']}")

    # --- Storage class transition ---

    def transition_storage_class(self, bucket: str, key: str, storage_class: str) -> None:
        """Transition an object to a different storage class."""
        b = self._require_bucket(bucket)
        v = self._latest_version(b, key)
        if v is None:
            raise KeyError(f"Object '{key}' not found")
        v.storage_class = storage_class

    # --- Bucket policies ---

    def set_bucket_policy(self, bucket: str, policy: dict) -> None:
        """Set a bucket policy. Policy: {principal, effect, actions}."""
        b = self._require_bucket(bucket)
        b.policies.append(policy)

    def check_bucket_policy(self, bucket: str, principal: str, action: str) -> bool:
        """Check if an action is allowed by bucket policy. Returns True if allowed."""
        b = self._require_bucket(bucket)
        if not b.policies:
            return True  # no policies = allow all
        for policy in b.policies:
            if policy.get("principal") in (principal, "*"):
                if action in policy.get("actions", []):
                    if policy.get("effect") == "DENY":
                        return False
                    elif policy.get("effect") == "ALLOW":
                        return True
        return True  # default allow
