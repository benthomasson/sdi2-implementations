"""Distributed Email Service — in-memory implementation."""

import uuid
from datetime import datetime, timezone


class Email:
    def __init__(self, from_addr, to, subject, body, cc=None, bcc=None,
                 attachments=None, in_reply_to=None):
        self.from_addr = from_addr
        self.to = to
        self.subject = subject
        self.body = body
        self.cc = cc or []
        self.bcc = bcc or []
        self.attachments = attachments or []
        self.in_reply_to = in_reply_to


class EmailService:
    def __init__(self):
        self.accounts = {}           # email -> name
        self.emails = {}             # msg_id -> email dict
        self.user_folders = {}       # user -> {folder_name: [msg_ids]}
        self.read_status = {}        # user -> set of read msg_ids
        self.threads = {}            # thread_id -> [msg_ids]
        self.msg_to_thread = {}      # msg_id -> thread_id
        self.drafts = {}             # draft_id -> Email object

    def _init_user(self, email):
        if email not in self.user_folders:
            self.user_folders[email] = {
                "inbox": [], "sent": [], "drafts": [], "trash": []
            }
            self.read_status[email] = set()

    def create_account(self, email, name):
        self.accounts[email] = name
        self._init_user(email)

    def _store_email(self, email_obj, msg_id, timestamp):
        """Store an email dict from an Email object."""
        self.emails[msg_id] = {
            "message_id": msg_id,
            "from": email_obj.from_addr,
            "to": list(email_obj.to),
            "cc": list(email_obj.cc),
            "subject": email_obj.subject,
            "body": email_obj.body,
            "attachments": list(email_obj.attachments),
            "timestamp": timestamp,
            "in_reply_to": email_obj.in_reply_to,
        }

    def _assign_thread(self, msg_id, in_reply_to):
        if in_reply_to and in_reply_to in self.msg_to_thread:
            thread_id = self.msg_to_thread[in_reply_to]
            self.threads[thread_id].append(msg_id)
        else:
            thread_id = msg_id
            self.threads[thread_id] = [msg_id]
        self.msg_to_thread[msg_id] = thread_id
        self.emails[msg_id]["thread_id"] = thread_id

    def _add_to_folder(self, user, folder, msg_id):
        self._init_user(user)
        if folder not in self.user_folders[user]:
            self.user_folders[user][folder] = []
        self.user_folders[user][folder].append(msg_id)

    def send(self, email):
        msg_id = str(uuid.uuid4())
        ts = datetime.now(timezone.utc).isoformat()
        self._store_email(email, msg_id, ts)
        self._assign_thread(msg_id, email.in_reply_to)

        # Deliver to sender's sent folder
        self._add_to_folder(email.from_addr, "sent", msg_id)
        self.read_status.setdefault(email.from_addr, set()).add(msg_id)

        # Deliver to all recipients' inboxes
        all_recipients = set(email.to + email.cc + email.bcc)
        for rcpt in all_recipients:
            self._add_to_folder(rcpt, "inbox", msg_id)

        return msg_id

    def save_draft(self, user, email):
        draft_id = str(uuid.uuid4())
        self.drafts[draft_id] = email
        self._add_to_folder(user, "drafts", draft_id)
        # Store a minimal email record so it can be listed/retrieved
        self.emails[draft_id] = {
            "message_id": draft_id,
            "from": email.from_addr,
            "to": list(email.to),
            "cc": list(email.cc),
            "subject": email.subject,
            "body": email.body,
            "attachments": list(email.attachments),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "in_reply_to": email.in_reply_to,
            "is_draft": True,
        }
        return draft_id

    def update_draft(self, user, draft_id, email):
        """Update an existing draft."""
        if draft_id not in self.drafts:
            raise ValueError("Draft not found")
        self.drafts[draft_id] = email
        self.emails[draft_id].update({
            "from": email.from_addr,
            "to": list(email.to),
            "cc": list(email.cc),
            "subject": email.subject,
            "body": email.body,
            "attachments": list(email.attachments),
            "in_reply_to": email.in_reply_to,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def send_draft(self, user, draft_id):
        if draft_id not in self.drafts:
            raise ValueError("Draft not found")
        email = self.drafts.pop(draft_id)
        # Remove from drafts folder
        if draft_id in self.user_folders.get(user, {}).get("drafts", []):
            self.user_folders[user]["drafts"].remove(draft_id)
        # Remove draft email record
        self.emails.pop(draft_id, None)
        # Send as normal
        return self.send(email)

    def list_folder(self, user, folder="inbox", limit=20, cursor=None):
        self._init_user(user)
        folder_msgs = self.user_folders.get(user, {}).get(folder, [])
        # Reverse chronological (newest first)
        ordered = list(reversed(folder_msgs))
        total = len(ordered)

        start = int(cursor) if cursor else 0
        page = ordered[start:start + limit]

        next_cursor = None
        if start + limit < total:
            next_cursor = str(start + limit)

        emails = [self.emails[mid] for mid in page if mid in self.emails]
        return {"emails": emails, "next_cursor": next_cursor, "total": total}

    def get_email(self, user, message_id):
        email = self.emails.get(message_id)
        if email is None:
            return None
        self.mark_read(user, message_id)
        return email

    def get_thread(self, user, thread_id):
        msg_ids = self.threads.get(thread_id, [])
        return [self.emails[mid] for mid in msg_ids if mid in self.emails]

    def move_to_folder(self, user, message_id, folder):
        self._init_user(user)
        # Remove from current folder
        for fname, msgs in self.user_folders[user].items():
            if message_id in msgs:
                msgs.remove(message_id)
                break
        # Add to target folder
        self._add_to_folder(user, folder, message_id)

    def delete(self, user, message_id):
        self._init_user(user)
        trash = self.user_folders[user].get("trash", [])
        if message_id in trash:
            # Permanent delete
            trash.remove(message_id)
        else:
            self.move_to_folder(user, message_id, "trash")

    def mark_read(self, user, message_id):
        self.read_status.setdefault(user, set()).add(message_id)

    def mark_unread(self, user, message_id):
        self.read_status.setdefault(user, set()).discard(message_id)

    def search(self, user, query, folder=None, from_addr=None,
               has_attachments=None, is_read=None, limit=20):
        self._init_user(user)
        query_lower = query.lower()

        # Collect candidate message IDs
        if folder:
            candidates = self.user_folders[user].get(folder, [])
        else:
            candidates = set()
            for msgs in self.user_folders[user].values():
                candidates.update(msgs)

        results = []
        read_set = self.read_status.get(user, set())

        for mid in candidates:
            e = self.emails.get(mid)
            if not e:
                continue
            # Text match
            if query_lower not in e["subject"].lower() and \
               query_lower not in e["body"].lower():
                continue
            # Filters
            if from_addr and e["from"] != from_addr:
                continue
            if has_attachments is not None:
                if has_attachments != bool(e["attachments"]):
                    continue
            if is_read is not None:
                if is_read != (mid in read_set):
                    continue
            results.append(e)
            if len(results) >= limit:
                break

        return results

    def create_folder(self, user, folder_name):
        self._init_user(user)
        if folder_name not in self.user_folders[user]:
            self.user_folders[user][folder_name] = []

    def get_unread_counts(self, user):
        self._init_user(user)
        read_set = self.read_status.get(user, set())
        counts = {}
        for fname, msgs in self.user_folders[user].items():
            counts[fname] = sum(1 for mid in msgs if mid not in read_set)
        return counts
