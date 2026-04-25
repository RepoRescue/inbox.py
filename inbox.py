# -*- coding: utf-8 -*-
"""inbox.py — SMTP for Humans.

Modernised for Python 3.12+ (where stdlib ``smtpd`` and ``asyncore`` were
removed) on top of ``aiosmtpd``. Public API is preserved:

    inbox.Inbox()                           — config holder
    @ix.collate                             — decorator registering the
                                              handler(to, sender, subject, body)
    ix.serve(port=, address=)               — blocking SMTP server loop
    ix.dispatch()                           — CLI: addr port
    inbox.InboxServer(handler, localaddr, remoteaddr)
                                            — internal SMTP server class
"""

import argparse
import time
from email.parser import Parser

from logbook import Logger

from aiosmtpd.controller import Controller


log = Logger(__name__)


class _InboxHandler(object):
    """aiosmtpd-style async handler that dispatches into a user callable.

    The user callable must have signature ``handler(to, sender, subject, body)``
    matching the original inbox.py 0.0.6 contract.
    """

    def __init__(self, user_handler):
        self._user_handler = user_handler

    async def handle_DATA(self, server, session, envelope):  # noqa: N802 (aiosmtpd API)
        sender = envelope.mail_from
        rcpttos = list(envelope.rcpt_tos)

        raw = envelope.content
        if isinstance(raw, (bytes, bytearray)):
            try:
                body = raw.decode("utf-8")
            except UnicodeDecodeError:
                body = raw.decode("latin-1", errors="replace")
        else:
            body = raw

        log.info("Collating message from {0}".format(sender))
        try:
            subject = Parser().parsestr(body)["subject"]
        except Exception:  # pragma: no cover - defensive
            subject = None
        log.debug(dict(to=rcpttos, sender=sender, subject=subject, body=body))

        if self._user_handler is not None:
            try:
                self._user_handler(
                    to=rcpttos, sender=sender, subject=subject, body=body
                )
            except Exception as exc:  # pragma: no cover
                log.error("User handler raised: {0}".format(exc))
                return "554 Transaction failed"
        return "250 OK"


class InboxServer(object):
    """Logging-enabled SMTP server with handler support.

    Constructor signature is preserved from inbox.py 0.0.6:

        InboxServer(handler, localaddr, remoteaddr)

    where ``localaddr`` is a ``(host, port)`` tuple and ``remoteaddr`` is
    accepted for backwards compatibility but unused (the original
    smtpd-based implementation passed it to ``smtpd.SMTPServer``; with
    aiosmtpd the server has no upstream relay concept by default).
    """

    def __init__(self, handler, localaddr, remoteaddr=None, **kwargs):
        self._user_handler = handler
        self._handler = _InboxHandler(handler)
        self.localaddr = tuple(localaddr) if localaddr else (None, None)
        self.remoteaddr = remoteaddr
        self._controller = None

    @property
    def addr(self):
        return self.localaddr

    def process_message(self, peer, mailfrom, rcpttos, data, **kwargs):
        """Backwards-compatible synchronous dispatch.

        Mirrors the original behaviour for callers that still drive the
        server manually. Tolerates the post-Python-3.5 ``mail_options`` /
        ``rcpt_options`` smtpd signature via ``**kwargs``.
        """
        log.info("Collating message from {0}".format(mailfrom))
        if isinstance(data, (bytes, bytearray)):
            try:
                data = data.decode("utf-8")
            except UnicodeDecodeError:
                data = data.decode("latin-1", errors="replace")
        subject = Parser().parsestr(data)["subject"]
        log.debug(dict(to=rcpttos, sender=mailfrom, subject=subject, body=data))
        if self._user_handler is None:
            return None
        return self._user_handler(
            to=rcpttos, sender=mailfrom, subject=subject, body=data
        )

    def start(self):
        host, port = self.localaddr
        self._controller = Controller(self._handler, hostname=host, port=port)
        self._controller.start()

    def stop(self):
        if self._controller is not None:
            try:
                self._controller.stop()
            except Exception:  # pragma: no cover
                pass
            self._controller = None


class Inbox(object):
    """A simple SMTP Inbox."""

    def __init__(self, port=None, address=None):
        self.port = port
        self.address = address
        self.collator = None
        self._server = None

    def collate(self, collator):
        """Function decorator. Used to specify inbox handler."""
        self.collator = collator
        return collator

    def serve(self, port=None, address=None):
        """Serve the SMTP server on the given port and address.

        Blocking. Returns when the calling thread is interrupted via
        ``KeyboardInterrupt`` or when ``stop()`` is called from another
        thread.
        """
        port = port or self.port
        address = address or self.address

        log.info("Starting SMTP server at {0}:{1}".format(address, port))

        self._server = InboxServer(self.collator, (address, port), None)
        self._server.start()

        try:
            while self._server is not None and self._server._controller is not None:
                time.sleep(0.2)
        except KeyboardInterrupt:
            log.info("Cleaning up")
        finally:
            if self._server is not None:
                self._server.stop()
                self._server = None

    def stop(self):
        """Stop a running ``serve()`` loop from another thread."""
        if self._server is not None:
            self._server.stop()

    def dispatch(self):
        """Command-line dispatch."""
        parser = argparse.ArgumentParser(description="Run an Inbox server.")
        parser.add_argument(
            "addr", metavar="addr", type=str, help="addr to bind to"
        )
        parser.add_argument(
            "port", metavar="port", type=int, help="port to bind to"
        )
        args = parser.parse_args()
        self.serve(port=args.port, address=args.addr)


__all__ = ["Inbox", "InboxServer"]
