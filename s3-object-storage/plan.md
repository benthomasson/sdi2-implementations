# Plan (Iteration 1)

Task: S3-like Object Storage
=======================
SDI Vol 2 Reference: Chapter 9 - S3-like Object Storage

Overview
--------
Build an S3-like object storage system with buckets, objects, versioning,
multipart uploads, and metadata. Objects are stored with keys and can be
listed with prefix/delimiter for hierarchical browsing. Supports storage
classes and presigned URL simulation for temporary access.

Requirements
------------
1. Buckets: create, delete, list buckets. Bucket names must be globally unique.
2. Objects: put, get, delete objects with string keys and binary/string values.
3. Object metadata: content type, size, last modified, custom metadata headers.
4. Versioning: when enabled on a bucket, every put creates a new version.
   Get returns latest version by default, or a specific version by ID.
   Delete creates a delete marker (object appears deleted but versions remain).
5. Multipart upload: initiate, upload parts, complete/abort. Parts can be
   uploaded out of order. Complete assembles parts into final object.
6. List objects: list with prefix and delimiter support for hierarchical
   browsing (e.g., prefix="photos/2024/" delimiter="/" returns "folders").
7. Copy object: copy within or between buckets.
8. Presigned URLs: generate a token that grants temporary get/put access
   to a specific object with an expiry time.
9. Storage classes: STANDARD (default) and INFREQUENT_ACCESS (lower cost
   simulated). Objects can be transitioned between classes.
10. Bucket policies: simple allow/deny rules for operations per user.

Interface
---------
class ObjectStorage:
    def __init__(self):
        """Initialize the object storage service."""

    def create_bucket(self, bucket: str, versioning: bool = False) -> None:
        """Create a bucket."""

    def delete_bucket(self, bucket: str) -> None:
        """Delete an empty bucket."""

    def list_buckets(self) -> list[dict]:
        """List all buckets with creation date."""

    def put_object(self, bucket: str, key: str, data: bytes | str,
                   content_type: str = "application/octet-stream",
                   metadata: dict = None,
                   storage_class: str = "STANDARD") -> dict:
        """Store an object. Returns {version_id, etag, size}."""

    def get_object(self, bucket: str, key: str,
                   version_id: str = None) -> dict | None:
        """Retrieve an object. Returns {data, metadata, version_id, ...}."""

    def delete_object(self, bucket: str, key: str,
                      version_id: str = None) -> dict:
        """Delete an object (or specific version)."""

    def head_object(self, bucket: str, key: str) -> dict | None:
        """Get object metadata without data."""

    def list_objects(self, bucket: str, prefix: str = "",
                    delimiter: str = None, max_keys: int = 1000,
                    continuation_token: str = None) -> dict:
        """List objects. Returns {objects, common_prefixes, is_truncated,
        next_token}."""

    def list_object_versions(self, bucket: str, prefix: str = "") -> list[dict]:
        """List all versions of objects in a bucket."""

    def copy_object(self, src_bucket: str, src_key: str,
                    dst_bucket: str, dst_key: str) -> dict:
        """Copy an object."""

    def initiate_multipart(self, bucket: str, key: str) -> str:
        """Start a multipart upload. Returns upload_id."""

    def upload_part(self, bucket: str, key: str, upload_id: str,
                    part_number: int, data: bytes | str) -> dict:
        """Upload a part. Returns {etag}."""

    def complete_multipart(self, bucket: str, key: str,
                           upload_id: str) -> dict:
        """Complete multipart upload. Assembles all parts."""

    def abort_multipart(self, bucket: str, key: str,
                        upload_id: str) -> None:
        """Abort and clean up a multipart upload."""

    def generate_presigned_url(self, bucket: str, key: str,
                               operation: str = "GET",
                               expires_in: int = 3600) -> str:
        """Generate a presigned URL token."""

    def access_presigned(self, token: str, current_time: float = None) -> dict:
        """Access an object via presigned URL token."""

Example Usage
-------------
    s3 = ObjectStorage()
    s3.create_bucket("my-bucket", versioning=True)

    # Put object
    result = s3.put_object("my-bucket", "photos/cat.jpg", b"image-data",
                           content_type="image/jpeg",
                           metadata={"author": "alice"})
    v1 = result["version_id"]

    # Update (new version)
    result2 = s3.put_object("my-bucket", "photos/cat.jpg", b"updated-data")
    v2 = result2["version_id"]
    assert v1 != v2

    # Get latest
    obj = s3.get_object("my-bucket", "photos/cat.jpg")
    assert obj["data"] == b"updated-data"

    # Get specific version
    obj_v1 = s3.get_object("my-bucket", "photos/cat.jpg", version_id=v1)
    assert obj_v1["data"] == b"image-data"

    # List with prefix
    s3.put_object("my-bucket", "photos/dog.jpg", b"dog")
    s3.put_object("my-bucket", "docs/readme.txt", b"hello")

    listing = s3.list_objects("my-bucket", prefix="photos/")
    assert len(listing["objects"]) == 2

    # List with delimiter (folder-like)
    listing = s3.list_objects("my-bucket", prefix="", delimiter="/")
    assert "photos/" in listing["common_prefixes"]
    assert "docs/" in listing["common_prefixes"]

    # Multipart
    upload_id = s3.initiate_multipart("my-bucket", "big-file.bin")
    s3.upload_part("my-bucket", "big-file.bin", upload_id, 1, b"part1")
    s3.upload_part("my-bucket", "big-file.bin", upload_id, 2, b"part2")
    s3.complete_multipart("my-bucket", "big-file.bin", upload_id)
    obj = s3.get_object("my-bucket", "big-file.bin")
    assert obj["data"] == b"part1part2"

Constraints
-----------
- All in-memory storage.
- Object keys can be any string up to 1024 characters.
- Bucket names: 3-63 characters, lowercase alphanumeric and hyphens.
- Handle up to 100,000 objects per bucket.
- Version IDs are unique strings.
- Target: 300-500 lines of Python.

Testing Requirements
--------------------
1. Basic put/get/delete.
2. Versioning: multiple versions, get by version.
3. Delete marker hides object but versions remain.
4. List with prefix filtering.
5. List with delimiter produces common prefixes.
6. Multipart upload assembles correctly.
7. Abort multipart cleans up parts.
8. Copy object works within and between buckets.
9. Presigned URL grants temporary access.
10. Expired presigned URL is rejected.
11. Head object returns metadata without data.
12. Delete non-empty bucket fails.
13. Object metadata is preserved.

IMPORTANT - EFFORT LEVEL: MINIMAL
Keep plan VERY brief (2-3 paragraphs max). Focus only on algorithm choice. Skip architectural discussions and detailed analysis.

Plan written to `planner/plan.md`. 

**Summary:** Single-class in-memory implementation using dicts of version lists per key. UUIDs for version IDs, MD5 for ETags, HMAC tokens for presigned URLs. Delete markers as special versions. Prefix/delimiter listing by iterating sorted keys and truncating at delimiter boundaries. Multipart uploads stored as `dict[part_number, bytes]` and concatenated on complete. ~300-400 lines, high confidence.

[Committed changes to planner branch]