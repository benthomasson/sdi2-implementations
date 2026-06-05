"""Tests for S3-like Object Storage."""
import sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'implementer'))

from s3_object_storage import ObjectStorage


def test_basic_put_get_delete():
    s3 = ObjectStorage()
    s3.create_bucket("test-bucket")
    result = s3.put_object("test-bucket", "hello.txt", b"hello world", content_type="text/plain", metadata={"author": "alice"})
    assert result["size"] == 11
    assert result["etag"]
    assert result["version_id"] is None  # non-versioned

    obj = s3.get_object("test-bucket", "hello.txt")
    assert obj["data"] == b"hello world"
    assert obj["content_type"] == "text/plain"
    assert obj["metadata"] == {"author": "alice"}

    s3.delete_object("test-bucket", "hello.txt")
    assert s3.get_object("test-bucket", "hello.txt") is None


def test_versioning():
    s3 = ObjectStorage()
    s3.create_bucket("ver-bucket", versioning=True)

    r1 = s3.put_object("ver-bucket", "file.txt", b"v1")
    r2 = s3.put_object("ver-bucket", "file.txt", b"v2")
    assert r1["version_id"] != r2["version_id"]

    # Latest
    assert s3.get_object("ver-bucket", "file.txt")["data"] == b"v2"
    # Specific version
    assert s3.get_object("ver-bucket", "file.txt", version_id=r1["version_id"])["data"] == b"v1"


def test_delete_marker():
    s3 = ObjectStorage()
    s3.create_bucket("dm-bucket", versioning=True)
    r1 = s3.put_object("dm-bucket", "file.txt", b"data")

    result = s3.delete_object("dm-bucket", "file.txt")
    assert result["delete_marker"] is True

    # Object appears deleted
    assert s3.get_object("dm-bucket", "file.txt") is None
    # But version still accessible
    assert s3.get_object("dm-bucket", "file.txt", version_id=r1["version_id"])["data"] == b"data"
    # Versions list shows both
    versions = s3.list_object_versions("dm-bucket")
    assert len(versions) == 2


def test_list_objects_prefix_delimiter():
    s3 = ObjectStorage()
    s3.create_bucket("list-bucket")
    s3.put_object("list-bucket", "photos/cat.jpg", b"cat")
    s3.put_object("list-bucket", "photos/dog.jpg", b"dog")
    s3.put_object("list-bucket", "docs/readme.txt", b"hi")

    # Prefix only
    listing = s3.list_objects("list-bucket", prefix="photos/")
    assert len(listing["objects"]) == 2

    # Delimiter only
    listing = s3.list_objects("list-bucket", prefix="", delimiter="/")
    assert "photos/" in listing["common_prefixes"]
    assert "docs/" in listing["common_prefixes"]
    assert len(listing["objects"]) == 0


def test_multipart_upload():
    s3 = ObjectStorage()
    s3.create_bucket("mp-bucket")
    uid = s3.initiate_multipart("mp-bucket", "big.bin")
    s3.upload_part("mp-bucket", "big.bin", uid, 2, b"part2")
    s3.upload_part("mp-bucket", "big.bin", uid, 1, b"part1")
    s3.complete_multipart("mp-bucket", "big.bin", uid)

    obj = s3.get_object("mp-bucket", "big.bin")
    assert obj["data"] == b"part1part2"


def test_abort_multipart():
    s3 = ObjectStorage()
    s3.create_bucket("ab-bucket")
    uid = s3.initiate_multipart("ab-bucket", "file.bin")
    s3.upload_part("ab-bucket", "file.bin", uid, 1, b"data")
    s3.abort_multipart("ab-bucket", "file.bin", uid)
    assert s3.get_object("ab-bucket", "file.bin") is None


def test_copy_object():
    s3 = ObjectStorage()
    s3.create_bucket("src-bucket")
    s3.create_bucket("dst-bucket")
    s3.put_object("src-bucket", "file.txt", b"copy me", metadata={"k": "v"})

    s3.copy_object("src-bucket", "file.txt", "dst-bucket", "copied.txt")
    obj = s3.get_object("dst-bucket", "copied.txt")
    assert obj["data"] == b"copy me"
    assert obj["metadata"] == {"k": "v"}


def test_presigned_url():
    s3 = ObjectStorage()
    s3.create_bucket("pre-bucket")
    s3.put_object("pre-bucket", "secret.txt", b"secret data")

    token = s3.generate_presigned_url("pre-bucket", "secret.txt", "GET", expires_in=100)
    obj = s3.access_presigned(token)
    assert obj["data"] == b"secret data"

    # Expired
    try:
        s3.access_presigned(token, current_time=time.time() + 200)
        assert False, "Should have raised"
    except ValueError as e:
        assert "expired" in str(e).lower()


def test_head_object():
    s3 = ObjectStorage()
    s3.create_bucket("head-bucket")
    s3.put_object("head-bucket", "f.txt", b"data", content_type="text/plain")
    h = s3.head_object("head-bucket", "f.txt")
    assert h["content_type"] == "text/plain"
    assert h["size"] == 4
    assert "data" not in h


def test_delete_nonempty_bucket():
    s3 = ObjectStorage()
    s3.create_bucket("full-bucket")
    s3.put_object("full-bucket", "f.txt", b"x")
    try:
        s3.delete_bucket("full-bucket")
        assert False, "Should have raised"
    except ValueError:
        pass


if __name__ == "__main__":
    for name, func in list(globals().items()):
        if name.startswith("test_") and callable(func):
            func()
            print(f"  PASS: {name}")
    print("\nAll tests passed!")
