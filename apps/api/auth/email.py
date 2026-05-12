"""Email delivery abstraction for magic links (console dev, SES stub for prod)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class EmailSender(Protocol):
    async def send_magic_link(
        self,
        *,
        to_email: str,
        magic_link_url: str,
        organization_name: str,
    ) -> None:
        """Deliver a single-use magic link to the recipient."""


class ConsoleEmailSender:
    """Prints the magic link URL to stdout for local development."""

    async def send_magic_link(
        self,
        *,
        to_email: str,
        magic_link_url: str,
        organization_name: str,
    ) -> None:
        print(  # noqa: T201 — intentional dev transport
            f"[ConsoleEmailSender] to={to_email} org={organization_name!r} "
            f"url={magic_link_url}",
            flush=True,
        )


class SesEmailSenderStub:
    """Reserved for Amazon SES integration; not wired in MVP."""

    async def send_magic_link(
        self,
        *,
        to_email: str,
        magic_link_url: str,
        organization_name: str,
    ) -> None:
        msg = (
            "SES email sender is not implemented; "
            "use email_backend=console in local dev."
        )
        raise NotImplementedError(msg)
