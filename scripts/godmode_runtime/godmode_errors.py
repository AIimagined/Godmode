"""Typed failures surfaced by the Godmode CLI."""


class GodmodeError(Exception):
    """Base failure with a safe user-facing message."""


class IdentityError(GodmodeError):
    """Project identity could not be resolved safely."""


class ArchiveError(GodmodeError):
    """Continuity archive validation or persistence failed."""


class PrivacyError(GodmodeError):
    """Data was rejected by the privacy boundary."""


class AuthorizationError(GodmodeError):
    """A protected action lacks a valid local capability."""


class ForgeError(GodmodeError):
    """A skill could not be created or validated safely."""
