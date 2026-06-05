# Plan Review: S3-like Object Storage

## Plan Strengths

- Versioning via `key -> list[ObjectVersion]`. Non-versioned buckets overwrite (`[version]`), versioned buckets append. Clean separation in `put_object` lines 106-109.
- Delete markers as `ObjectVersion(is_delete_marker=True)`. `_latest_version` returns `None` when latest is a delete marker, hiding the object while preserving history.
- Prefix/delimiter listing: iterates sorted keys, finds first delimiter occurrence after prefix, and collects `common_prefixes` for "folder-like" browsing. Pagination via `continuation_token` using key comparison.
- Multipart upload: parts stored in `dict[part_number, bytes]`, assembled in sorted order on `complete_multipart`. Out-of-order upload supported naturally.
- Presigned URLs: HMAC-SHA256 token generation with bucket/key/operation/uuid payload. Token-to-metadata dict with expiry time. `current_time` parameter in `access_presigned` enables deterministic testing.
- Copy delegates to `get_object` + `put_object`, preserving content_type, metadata, and storage_class.
- Bucket name validation via regex `^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$`.
- `delete_bucket` checks both non-versioned objects and versioned objects (including behind delete markers).

## Plan Gaps

1. **`list_objects` counts common prefixes toward iteration but not toward `max_keys`.** Lines 191-197: keys that match a delimiter prefix are added to `common_prefixes` and `continue` past the `max_keys` check. S3's actual behavior counts common prefixes toward the key limit.

2. **`_BUCKET_RE` excludes 3-character bucket names.** The regex `{1,61}` for the middle portion requires minimum 3 total characters, but a 3-char name like `"abc"` works because the regex allows `[a-z0-9]` + `[a-z0-9-]{1,61}` + `[a-z0-9]`, which means minimum length is 3 (1+1+1). Actually correct.

3. **`_SECRET` is a class variable generated once per class load.** Line 39: `_SECRET = uuid.uuid4().hex`. All instances share the same secret. In a real system this would be per-deployment, but for in-memory simulation this is fine.

4. **Presigned URL tokens accumulate without cleanup.** `_presigned` dict grows unbounded — expired tokens are never pruned. Only checked on access.

5. **`transition_storage_class` mutates the `ObjectVersion` in place.** Line 324: `v.storage_class = storage_class`. No validation of valid storage class values. Any string accepted.

6. **Bucket policy evaluation is first-match.** Lines 338-345: iterates policies and returns on first matching DENY or ALLOW. No priority ordering beyond insertion order. Default is allow-all when no policy matches.

## Implementation Issues (0 test failures)

No test failures. Clean implementation at 346 lines. 10/10 tests pass covering put/get/delete, versioning, delete markers, prefix/delimiter listing, multipart, copy, presigned URLs, head, and non-empty bucket deletion.
