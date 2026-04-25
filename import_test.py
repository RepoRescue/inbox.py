"""T0/T1 baseline import + structural test.

inbox.py 0.0.6 was written for Python 2.7 era. The full SMTP smoke test
requires the legacy smtpd.process_message signature (no mail_options
kwarg) which only Python <3.5 had natively. For T0/T1 gating we use the
weaker import + class-shape test:

  T0 (Python 3.10): smtpd + asyncore exist -> import succeeds -> PASS
  T1 (Python 3.13): smtpd + asyncore REMOVED -> import fails -> FAIL

The full SMTP send/receive smoke_test.py is the T2 acceptance gate
(only runs after rescue patches the source).
"""
import sys


def main():
    import inbox  # must succeed

    ix = inbox.Inbox()
    assert hasattr(ix, "serve")
    assert hasattr(ix, "collate")
    assert hasattr(ix, "dispatch")

    @ix.collate
    def handler(to, sender, subject, body):
        return None

    assert ix.collator is handler

    # Class hierarchy intact
    assert issubclass(inbox.InboxServer, object)
    print("OK import_test passed")


if __name__ == "__main__":
    main()
