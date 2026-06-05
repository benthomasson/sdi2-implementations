from email_service import Email, EmailService

svc = EmailService()
svc.create_account('alice@example.com', 'Alice')
svc.create_account('bob@example.com', 'Bob')

msg_id = svc.send(Email('alice@example.com', ['bob@example.com'],
                        'Meeting tomorrow', "Let's meet at 10am"))

inbox = svc.list_folder('bob@example.com', 'inbox')
assert inbox['total'] == 1, f'Expected 1, got {inbox["total"]}'

email = svc.get_email('bob@example.com', msg_id)
assert email['subject'] == 'Meeting tomorrow'

reply_id = svc.send(Email('bob@example.com', ['alice@example.com'],
                          'Re: Meeting tomorrow', 'Sounds good!',
                          in_reply_to=msg_id))

thread = svc.get_thread('alice@example.com', msg_id)
assert len(thread) == 2, f'Expected 2, got {len(thread)}'

counts = svc.get_unread_counts('alice@example.com')
assert counts['inbox'] >= 1, f'Expected >=1, got {counts["inbox"]}'

results = svc.search('bob@example.com', 'meeting')
assert len(results) >= 1, f'Expected >=1, got {len(results)}'

msg2 = svc.send(Email('alice@example.com', ['bob@example.com'],
                       'Secret', 'hidden', bcc=['carol@example.com']))

svc.create_account('carol@example.com', 'Carol')
draft_id = svc.save_draft('carol@example.com', Email('carol@example.com', ['alice@example.com'], 'Draft subj', 'Draft body'))
drafts = svc.list_folder('carol@example.com', 'drafts')
assert drafts['total'] == 1
sent_id = svc.send_draft('carol@example.com', draft_id)
drafts2 = svc.list_folder('carol@example.com', 'drafts')
assert drafts2['total'] == 0

svc.delete('bob@example.com', msg_id)
trash = svc.list_folder('bob@example.com', 'trash')
assert trash['total'] == 1
svc.move_to_folder('bob@example.com', msg_id, 'inbox')
inbox2 = svc.list_folder('bob@example.com', 'inbox')
assert msg_id in [e['message_id'] for e in inbox2['emails']]

svc.delete('bob@example.com', msg_id)
svc.delete('bob@example.com', msg_id)
trash2 = svc.list_folder('bob@example.com', 'trash')
assert msg_id not in [e['message_id'] for e in trash2['emails']]

for i in range(5):
    svc.send(Email('alice@example.com', ['bob@example.com'], f'Page {i}', f'body {i}'))
page1 = svc.list_folder('bob@example.com', 'inbox', limit=2)
assert len(page1['emails']) == 2
assert page1['next_cursor'] is not None
page2 = svc.list_folder('bob@example.com', 'inbox', limit=2, cursor=page1['next_cursor'])
assert len(page2['emails']) == 2

svc.create_folder('bob@example.com', 'work')
svc.move_to_folder('bob@example.com', reply_id, 'work')
work = svc.list_folder('bob@example.com', 'work')
assert work['total'] == 1

svc.mark_unread('bob@example.com', reply_id)
counts2 = svc.get_unread_counts('bob@example.com')
assert counts2['work'] == 1

print('All tests passed!')
