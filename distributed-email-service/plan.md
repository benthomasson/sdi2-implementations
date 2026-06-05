# Plan (Iteration 1)

Task: Distributed Email Service
==========================
SDI Vol 2 Reference: Chapter 8 - Distributed Email Service

Overview
--------
Build an email service supporting send, receive, folder management, threading,
and search. Emails are organized into folders (inbox, sent, drafts, trash, and
custom folders). Conversations are threaded by subject/references. The system
tracks read/unread status and supports full-text search over email content.

Requirements
------------
1. User accounts with email addresses.
2. Send email: from, to (multiple recipients), cc, bcc, subject, body,
   attachments (metadata only — filename, size, mime type).
3. Receive: incoming emails are delivered to recipients' inboxes.
4. Folders: inbox, sent, drafts, trash, and user-created custom folders.
   Move emails between folders.
5. Threading: group emails into conversations by subject line and
   In-Reply-To / References headers. Replies to a thread are grouped.
6. Read/unread tracking per user per email.
7. Search: full-text search over subject and body. Filter by folder,
   sender, date range, read/unread, has attachments.
8. Drafts: save and update drafts before sending.
9. Trash: move to trash, restore from trash, permanent delete.
10. Pagination: list emails in a folder with cursor-based pagination.
11. Unread counts per folder.

Interface
---------
class Email:
    def __init__(self, from_addr: str, to: list[str], subject: str,
                 body: str, cc: list[str] = None, bcc: list[str] = None,
                 attachments: list[dict] = None, in_reply_to: str = None):
        """An email message."""

class EmailService:
    def __init__(self):
        """Initialize the email service."""

    def create_account(self, email: str, name: str) -> None:
        """Create a user account."""

    def send(self, email: Email) -> str:
        """Send an email. Returns the message ID. Delivers to all recipients."""

    def save_draft(self, user: str, email: Email) -> str:
        """Save a draft. Returns draft ID."""

    def send_draft(self, user: str, draft_id: str) -> str:
        """Send a saved draft. Returns message ID."""

    def list_folder(self, user: str, folder: str = "inbox",
                    limit: int = 20, cursor: str = None) -> dict:
        """List emails in a folder. Returns {emails, next_cursor, total}."""

    def get_email(self, user: str, message_id: str) -> dict | None:
        """Get a single email. Marks as read."""

    def get_thread(self, user: str, thread_id: str) -> list[dict]:
        """Get all emails in a conversation thread."""

    def move_to_folder(self, user: str, message_id: str,
                       folder: str) -> None:
        """Move an email to a folder."""

    def delete(self, user: str, message_id: str) -> None:
        """Move to trash (or permanently delete if already in trash)."""

    def mark_read(self, user: str, message_id: str) -> None:
        """Mark an email as read."""

    def mark_unread(self, user: str, message_id: str) -> None:
        """Mark as unread."""

    def search(self, user: str, query: str, folder: str = None,
               from_addr: str = None, has_attachments: bool = None,
               is_read: bool = None, limit: int = 20) -> list[dict]:
        """Search emails by keyword and filters."""

    def create_folder(self, user: str, folder_name: str) -> None:
        """Create a custom folder."""

    def get_unread_counts(self, user: str) -> dict[str, int]:
        """Return unread count per folder."""

Example Usage
-------------
    svc = EmailService()
    svc.create_account("alice@example.com", "Alice")
    svc.create_account("bob@example.com", "Bob")

    # Send
    msg_id = svc.send(Email("alice@example.com", ["bob@example.com"],
                            "Meeting tomorrow", "Let's meet at 10am"))

    # Bob's inbox
    inbox = svc.list_folder("bob@example.com", "inbox")
    assert inbox["total"] == 1

    # Read
    email = svc.get_email("bob@example.com", msg_id)
    assert email["subject"] == "Meeting tomorrow"

    # Reply (creates thread)
    reply_id = svc.send(Email("bob@example.com", ["alice@example.com"],
                              "Re: Meeting tomorrow", "Sounds good!",
                              in_reply_to=msg_id))

    thread = svc.get_thread("alice@example.com", msg_id)
    assert len(thread) == 2

    # Unread counts
    counts = svc.get_unread_counts("alice@example.com")
    assert counts["inbox"] >= 1

    # Search
    results = svc.search("bob@example.com", "meeting")
    assert len(results) >= 1

Constraints
-----------
- All in-memory storage.
- Message IDs are unique strings.
- Threading by In-Reply-To chain.
- Search is case-insensitive substring match.
- Handle up to 100,000 emails across all users.
- Target: 200-400 lines of Python.

Testing Requirements
--------------------
1. Send delivers to all recipients.
2. CC and BCC work correctly (BCC hidden from others).
3. Folder management: move, create custom, delete.
4. Threading groups replies correctly.
5. Read/unread tracking per user.
6. Search by keyword, sender, folder.
7. Drafts: save, update, send.
8. Trash and restore.
9. Pagination with cursors.
10. Unread counts are accurate.
11. Permanent delete from trash.

IMPORTANT - EFFORT LEVEL: MINIMAL
Keep plan VERY brief (2-3 paragraphs max). Focus only on algorithm choice. Skip architectural discussions and detailed analysis.

Plan written to `PLAN.md`. Key highlights:

- **Data model**: Message store keyed by UUID, per-user folder lists, read-status sets, thread chains via `in_reply_to` lookup
- **Threading**: Thread ID = first message's ID; replies chain via `msg_to_thread` mapping
- **Pagination**: Index-based cursors (simple str-encoded integers)
- **Search**: Brute-force case-insensitive substring scan — fine at 100K scale
- **BCC**: Delivered but stripped from the email dict visible to other recipients
- **One open question**: Task says "save and update drafts" but interface only has `save_draft` — implementer should decide whether to overload it or add `update_draft`

Confidence: **HIGH** — well-specified problem with a clean in-memory solution.

[Committed changes to planner branch]