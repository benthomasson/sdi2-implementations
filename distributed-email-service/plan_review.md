# Plan Review: Distributed Email Service

## Plan Strengths

- BCC handled correctly: delivered to BCC recipients' inboxes but stripped from the stored email dict (`_store_email` omits BCC field). Anyone retrieving the email can't see BCC addresses.
- Threading via `msg_to_thread` mapping: `in_reply_to` chain lookups find the thread root. Thread ID = first message's ID. All replies correctly grouped.
- Pagination with index-based cursors: `list_folder` reverses the folder list (newest first), slices by offset, returns `next_cursor` when more pages exist.
- Read/unread tracking: sender auto-marked read on send, recipient starts unread, `get_email` auto-marks read.
- Draft lifecycle: save creates a minimal email record so it appears in folder listings, `send_draft` removes the draft record and re-sends as a normal email.
- Search: case-insensitive substring match over subject and body with filters for sender, attachments, read status.

## Plan Gaps

1. **`test_email.py` is a script, not a pytest test.** It runs assertions inline at module level — pytest would execute it on import. The actual tests are in `test_email_service.py`. No impact on correctness, just confusing duplication.

2. **Pagination cursors are offset-based, not stable.** If a new email arrives between page requests, the cursor shifts and a message could be skipped or repeated. Cursor-based pagination (keyed on message ID or timestamp) would be more robust.

3. **`move_to_folder` scans all folders to find the source.** O(folders * messages) per move. A reverse index (message_id -> current folder) would be O(1).

4. **Sender's sent folder marks the message as read, but sent emails also appear in sender's own unread count for "sent".** Line 79 adds sender to `read_status`, correctly preventing this.

5. **`update_draft` doesn't verify the draft belongs to the requesting user.** Any user could update any draft if they know the draft_id.

## Implementation Issues (0 test failures)

No test failures. Clean implementation at 239 lines with all 9 test cases passing.
