"""End-to-end SMTP smoke test for inbox.py.

Starts an Inbox SMTP server in a background thread, sends a real email to
it via smtplib, and asserts that the @inbox.collate handler received it.
"""
import smtplib
import socket
import sys
import threading
import time

import inbox


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def main():
    received = []
    done = threading.Event()

    ix = inbox.Inbox()

    @ix.collate
    def handler(to, sender, subject, body):
        received.append({"to": to, "sender": sender,
                         "subject": subject, "body": body})
        done.set()

    port = _free_port()
    host = "127.0.0.1"

    def run():
        ix.serve(port=port, address=host)

    t = threading.Thread(target=run, daemon=True)
    t.start()

    # Wait for the SMTP socket to come up
    deadline = time.time() + 5
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                break
        except OSError:
            time.sleep(0.05)
    else:
        print("FAIL: SMTP server did not start", file=sys.stderr)
        sys.exit(2)

    msg = ("From: alice@example.com\r\n"
           "To: bob@example.com\r\n"
           "Subject: hello-from-smoke\r\n\r\n"
           "test body line\r\n")
    s = smtplib.SMTP(host, port, timeout=5)
    s.sendmail("alice@example.com", ["bob@example.com"], msg)
    s.quit()

    if not done.wait(5):
        print("FAIL: handler never invoked", file=sys.stderr)
        sys.exit(3)

    rec = received[0]
    assert rec["sender"] == "alice@example.com", rec
    assert rec["to"] == ["bob@example.com"], rec
    assert rec["subject"] == "hello-from-smoke", rec
    assert "test body line" in rec["body"], rec
    print("OK smoke_test passed:", rec["subject"])


if __name__ == "__main__":
    main()
