"""Typed failures surfaced by the Godmode CLI."""


class GodmodeError(Exception):
    """Base failure with a safe user-facing message.

    `exit_code` is the process exit the CLI answers with: 2 for a refused
    or malformed command (the value every class returned before codes
    were typed), and one code per class a caller may want to branch on
    without parsing the message. 130 and 143 are reserved for SIGINT and
    SIGTERM, answered by `godmode_console.main`."""

    exit_code = 2


class IdentityError(GodmodeError):
    """Project identity could not be resolved safely."""

    exit_code = 5


class ArchiveError(GodmodeError):
    """Continuity archive validation or persistence failed."""


class PrivacyError(GodmodeError):
    """Data was rejected by the privacy boundary."""

    exit_code = 3


class AuthorizationError(GodmodeError):
    """A protected action lacks a valid local capability."""

    exit_code = 4


class ForgeError(GodmodeError):
    """A skill could not be created or validated safely."""

    exit_code = 6


class CorpusError(GodmodeError):
    """The project's authority corpus could not be resolved."""

    exit_code = 7


class UsageError(GodmodeError):
    """The command line itself could not be parsed."""
