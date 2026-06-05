"""Tests for Distributed Email Service."""
import sys
sys.path.insert(0, "../implementer")

from email_service import Email, EmailService


def test_send_delivers_to_all_recipients():
    """Test 1: Send delivers to all recipients including CC and BCC."""
    svc = EmailService()
    svc.create_account("alice@x.com", "Alice")
    svc.create_account("bob@x.com", "Bob")
    svc.create_account("carol@x.com", "Carol")
    svc.create_account("dave@x.com", "Dave")

    msg_id = svc.send(Email("alice@x.com", ["bob@x.com"], "Hi", "body",
                            cc=["carol@x.com"], bcc=["dave@x.com"]))

    # All recipients get it in inbox
    assert svc.list_folder("bob@x.com")["total"] == 1
    assert svc.list_folder("carol@x.com")["total"] == 1
    assert svc.list_folder("dave@x.com")["total"] == 1

    # Sender gets it in sent
    assert svc.list_folder("alice@x.com", "sent")["total"] == 1

    # BCC not visible in stored email
    email = svc.get_email("bob@x.com", msg_id)
    assert "dave@x.com" not in email.get("bcc", [])
    assert "dave@x.com" not in email["to"]
    assert "dave@x.com" not in email["cc"]
    print("PASS: test_send_delivers_to_all_recipients")


def test_threading():
    """Test 4: Threading groups replies correctly."""
    svc = EmailService()
    svc.create_account("a@x.com", "A")
    svc.create_account("b@x.com", "B")

    msg1 = svc.send(Email("a@x.com", ["b@x.com"], "Topic", "first"))
    msg2 = svc.send(Email("b@x.com", ["a@x.com"], "Re: Topic", "second",
                          in_reply_to=msg1))
    msg3 = svc.send(Email("a@x.com", ["b@x.com"], "Re: Topic", "third",
                          in_reply_to=msg2))

    thread = svc.get_thread("a@x.com", msg1)
    assert len(thread) == 3
    assert [e["message_id"] for e in thread] == [msg1, msg2, msg3]

    # New message without in_reply_to starts its own thread
    msg4 = svc.send(Email("a@x.com", ["b@x.com"], "Other", "unrelated"))
    thread2 = svc.get_thread("b@x.com", msg4)
    assert len(thread2) == 1
    print("PASS: test_threading")


def test_read_unread_tracking():
    """Test 5: Read/unread tracking per user."""
    svc = EmailService()
    svc.create_account("a@x.com", "A")
    svc.create_account("b@x.com", "B")

    msg_id = svc.send(Email("a@x.com", ["b@x.com"], "Subj", "Body"))

    # Sender auto-read, recipient unread
    counts = svc.get_unread_counts("b@x.com")
    assert counts["inbox"] == 1

    # get_email marks as read
    svc.get_email("b@x.com", msg_id)
    assert svc.get_unread_counts("b@x.com")["inbox"] == 0

    # mark_unread works
    svc.mark_unread("b@x.com", msg_id)
    assert svc.get_unread_counts("b@x.com")["inbox"] == 1

    # Sender's sent is read
    assert svc.get_unread_counts("a@x.com")["sent"] == 0
    print("PASS: test_read_unread_tracking")


def test_search():
    """Test 6: Search by keyword, sender, folder, filters."""
    svc = EmailService()
    svc.create_account("a@x.com", "A")
    svc.create_account("b@x.com", "B")

    svc.send(Email("a@x.com", ["b@x.com"], "Meeting notes", "discuss budget"))
    svc.send(Email("a@x.com", ["b@x.com"], "Lunch", "grab food",
                   attachments=[{"filename": "menu.pdf", "size": 100, "mime_type": "application/pdf"}]))

    # Keyword search (case-insensitive)
    results = svc.search("b@x.com", "MEETING")
    assert len(results) == 1
    assert results[0]["subject"] == "Meeting notes"

    # Filter by sender
    results = svc.search("b@x.com", "grab", from_addr="a@x.com")
    assert len(results) == 1

    # Filter by has_attachments
    results = svc.search("b@x.com", "grab", has_attachments=True)
    assert len(results) == 1
    results = svc.search("b@x.com", "budget", has_attachments=True)
    assert len(results) == 0
    print("PASS: test_search")


def test_drafts_save_update_send():
    """Test 7: Drafts: save, update, send."""
    svc = EmailService()
    svc.create_account("a@x.com", "A")
    svc.create_account("b@x.com", "B")

    draft_id = svc.save_draft("a@x.com", Email("a@x.com", ["b@x.com"], "Draft", "v1"))
    assert svc.list_folder("a@x.com", "drafts")["total"] == 1

    # Update draft
    svc.update_draft("a@x.com", draft_id, Email("a@x.com", ["b@x.com"], "Draft updated", "v2"))
    email = svc.get_email("a@x.com", draft_id)
    assert email["subject"] == "Draft updated"

    # Send draft
    msg_id = svc.send_draft("a@x.com", draft_id)
    assert svc.list_folder("a@x.com", "drafts")["total"] == 0
    assert svc.list_folder("a@x.com", "sent")["total"] == 1
    assert svc.list_folder("b@x.com", "inbox")["total"] == 1
    print("PASS: test_drafts_save_update_send")


def test_trash_restore_permanent_delete():
    """Test 8+11: Trash, restore, permanent delete."""
    svc = EmailService()
    svc.create_account("a@x.com", "A")
    svc.create_account("b@x.com", "B")

    msg_id = svc.send(Email("a@x.com", ["b@x.com"], "Hi", "body"))

    # Delete moves to trash
    svc.delete("b@x.com", msg_id)
    assert svc.list_folder("b@x.com", "trash")["total"] == 1
    assert svc.list_folder("b@x.com", "inbox")["total"] == 0

    # Restore from trash
    svc.move_to_folder("b@x.com", msg_id, "inbox")
    assert svc.list_folder("b@x.com", "inbox")["total"] == 1
    assert svc.list_folder("b@x.com", "trash")["total"] == 0

    # Delete again -> trash, delete again -> permanent
    svc.delete("b@x.com", msg_id)
    svc.delete("b@x.com", msg_id)
    assert svc.list_folder("b@x.com", "trash")["total"] == 0
    print("PASS: test_trash_restore_permanent_delete")


def test_pagination():
    """Test 9: Pagination with cursors."""
    svc = EmailService()
    svc.create_account("a@x.com", "A")
    svc.create_account("b@x.com", "B")

    ids = []
    for i in range(7):
        ids.append(svc.send(Email("a@x.com", ["b@x.com"], f"Msg {i}", f"body {i}")))

    # Page 1
    p1 = svc.list_folder("b@x.com", "inbox", limit=3)
    assert len(p1["emails"]) == 3
    assert p1["total"] == 7
    assert p1["next_cursor"] is not None

    # Page 2
    p2 = svc.list_folder("b@x.com", "inbox", limit=3, cursor=p1["next_cursor"])
    assert len(p2["emails"]) == 3
    assert p2["next_cursor"] is not None

    # Page 3 (last page, 1 remaining)
    p3 = svc.list_folder("b@x.com", "inbox", limit=3, cursor=p2["next_cursor"])
    assert len(p3["emails"]) == 1
    assert p3["next_cursor"] is None

    # Newest first: page 1 should have the latest messages
    assert p1["emails"][0]["subject"] == "Msg 6"
    print("PASS: test_pagination")


def test_folder_management():
    """Test 3: Folder management: move, create custom."""
    svc = EmailService()
    svc.create_account("a@x.com", "A")
    svc.create_account("b@x.com", "B")

    msg_id = svc.send(Email("a@x.com", ["b@x.com"], "Work", "important"))

    svc.create_folder("b@x.com", "projects")
    svc.move_to_folder("b@x.com", msg_id, "projects")
    assert svc.list_folder("b@x.com", "projects")["total"] == 1
    assert svc.list_folder("b@x.com", "inbox")["total"] == 0
    print("PASS: test_folder_management")


def test_example_usage():
    """Verify the example usage from the task description works."""
    svc = EmailService()
    svc.create_account("alice@example.com", "Alice")
    svc.create_account("bob@example.com", "Bob")

    msg_id = svc.send(Email("alice@example.com", ["bob@example.com"],
                            "Meeting tomorrow", "Let's meet at 10am"))
    inbox = svc.list_folder("bob@example.com", "inbox")
    assert inbox["total"] == 1

    email = svc.get_email("bob@example.com", msg_id)
    assert email["subject"] == "Meeting tomorrow"

    reply_id = svc.send(Email("bob@example.com", ["alice@example.com"],
                              "Re: Meeting tomorrow", "Sounds good!",
                              in_reply_to=msg_id))
    thread = svc.get_thread("alice@example.com", msg_id)
    assert len(thread) == 2

    counts = svc.get_unread_counts("alice@example.com")
    assert counts["inbox"] >= 1

    results = svc.search("bob@example.com", "meeting")
    assert len(results) >= 1
    print("PASS: test_example_usage")


if __name__ == "__main__":
    test_send_delivers_to_all_recipients()
    test_threading()
    test_read_unread_tracking()
    test_search()
    test_drafts_save_update_send()
    test_trash_restore_permanent_delete()
    test_pagination()
    test_folder_management()
    test_example_usage()
    print("\nAll 9 tests passed!")
