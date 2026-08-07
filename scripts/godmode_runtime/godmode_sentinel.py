"""Privacy boundary and local one-use capabilities for Godmode."""

from __future__ import annotations

import base64
import getpass
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import sys
import tempfile
import time
from typing import Any

from .godmode_errors import AuthorizationError, PrivacyError


def _stdin_is_interactive() -> bool:
    try:
        if not sys.stdin.isatty():
            return False
    except (AttributeError, ValueError):
        return False
    if os.name == "nt":
        # On Windows, isatty() is true for any character device, including
        # NUL. Only a real console accepts GetConsoleMode, and getpass reads
        # from the console, so anything else would block forever.
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-10)  # STD_INPUT_HANDLE
        mode = ctypes.c_uint32()
        return bool(kernel32.GetConsoleMode(handle, ctypes.byref(mode)))
    return True


def _require_tty() -> None:
    if not _stdin_is_interactive():
        raise AuthorizationError(
            "No interactive terminal is available for password entry. "
            "Run this command from an interactive shell, or pass "
            "--password-stdin and pipe the password on standard input."
        )


def read_password_stdin() -> str:
    password = sys.stdin.readline().rstrip("\r\n")
    if not password:
        raise AuthorizationError("No password was received on standard input")
    return password


_SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\b(?:ghp|github_pat)_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"(?i)\b(?:authorization\s*:\s*bearer|bearer)\s+[A-Za-z0-9._~-]{12,}"),
    re.compile(r"(?i)\b(?:password|passwd|api[_-]?key|secret|token)\s*[:=]\s*[^\s,;]{8,}"),
)

# A mutating flag anywhere in a `git branch` invocation is checked before any
# safe pattern, because the verified failure mode was the reverse order: the
# read-only prefix matched `git branch` and the delete flag never got a look.
_GIT_BRANCH_MUTATION = re.compile(
    r"(?i)\bgit\s+branch\b.*\s(?:-[a-z]*[dmcf][a-z]*|--delete|--force|--move|--copy|"
    r"--set-upstream-to(?:=\S+)?|--unset-upstream|--edit-description)\b"
)

_ACTION_PATTERNS: tuple[tuple[str, re.Pattern[str], tuple[str, ...]], ...] = (
    (
        "git-history-or-remote",
        re.compile(
            r"(?i)\bgit\s+(?:push|commit|merge|rebase|reset|clean|tag|checkout|switch|"
            r"branch\s+(?:-[dDmM]|--delete)|worktree\s+(?:remove|prune|move)|"
            r"stash\s+(?:drop|pop|clear|apply|push|save|branch|create|store)|"
            r"remote\s+(?:add|remove|rm|rename|set-url|set-head|set-branches|prune|update))\b"
        ),
        ("repository history", "branches or worktrees", "possibly a remote"),
    ),
    (
        "database-mutation",
        re.compile(
            r"(?i)\b(?:drop|truncate|delete\s+from|alter\s+table|migrate|migration|"
            r"rollback|restore|seed\s+(?:database|db))\b"
        ),
        ("database schema or records", "rollback readiness"),
    ),
    (
        "release-or-external-write",
        re.compile(
            r"(?i)\b(?:deploy|publish|release|upload|send\s+(?:message|email)|"
            r"create\s+(?:pull request|issue)|post\s+to)\b"
        ),
        ("an external system", "other users or consumers"),
    ),
    (
        "filesystem-mutation",
        re.compile(
            r"(?i)(?:\brm\b|\brmdir\b|\bdel\b|\bremove-item\b|\bmove-item\b|"
            r"\bshutil\.rmtree\b|\bos\.remove\b)"
        ),
        ("local files", "recoverability"),
    ),
)

# Argument tokens the anchored safe listings may carry. Shell control and
# expansion characters are excluded so a read-only form cannot smuggle a second
# command, and a leading dash is excluded so a flag can never ride in as a
# positional argument.
_ARG = r"[^\s;&|<>`$\"'-][^\s;&|<>`$]*|'[^';&|<>`$]*'|\"[^\";&|<>`$]*\""
_VAL = r"[^\s;&|<>`$]+"

# `git branch`, `git tag`, and `git remote` list state when bare but mutate it
# with the right flag or a positional name, so their safe forms are anchored to
# the end of the operation and enumerate only listing tokens; anything else
# falls through to the protected classifiers. Separators are limited to spaces
# and tabs so a newline cannot append a second command.
_SAFE_GIT_BRANCH = re.compile(
    r"(?i)^[ \t]*git[ \t]+branch"
    r"(?:[ \t]+(?:--show-current|--all|--remotes|--verbose|-[arv]{1,3}|"
    rf"--sort={_VAL}|--format={_VAL}|--column(?:={_VAL})?|--no-column|"
    rf"--(?:contains|no-contains|merged|no-merged|points-at)(?:[ \t]+(?:{_ARG}))?|"
    rf"--list(?:[ \t]+(?:{_ARG}))*))*"
    r"[ \t]*$"
)
_SAFE_GIT_TAG = re.compile(
    r"(?i)^[ \t]*git[ \t]+tag"
    rf"(?:[ \t]+(?:-l(?:[ \t]+(?:{_ARG}))*|--list(?:[ \t]+(?:{_ARG}))*|-n\d*|"
    rf"--sort={_VAL}|--format={_VAL}|--column(?:={_VAL})?|--no-column|"
    rf"--(?:contains|no-contains|merged|no-merged|points-at)(?:[ \t]+(?:{_ARG}))?))*"
    r"[ \t]*$"
)
_SAFE_GIT_REMOTE = re.compile(
    r"(?i)^[ \t]*git[ \t]+remote"
    r"(?:[ \t]+(?:-v|--verbose))*"
    rf"(?:[ \t]+(?:show|get-url)(?:[ \t]+(?:-n|--push|--all|{_ARG}))*)?"
    r"[ \t]*$"
)
_SAFE_PREFIXES = re.compile(
    r"(?i)^\s*(?:git\s+(?:status|diff|log|show|rev-parse|worktree\s+list|"
    r"stash\s+(?:list|show))|inspect|read|list|show|explain|doctor|privacy)\b"
)
_SAFE_INSPECTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    _SAFE_PREFIXES,
    _SAFE_GIT_BRANCH,
    _SAFE_GIT_TAG,
    _SAFE_GIT_REMOTE,
)

# §9.2 risk tiers. R1 (local compute/archive state) and R2 (worktree file
# mutation) are reserved for categories the classifier does not yet emit;
# every unmapped category resolves to R3 so an unknown can never rank below
# history mutation.
_TIER_BY_CATEGORY = {
    "read-only-inspection": "R0",
    "local-compute-or-state": "R1",
    "worktree-file-mutation": "R2",
    "git-branch-mutation": "R3",
    "git-history-or-remote": "R3",
    "database-mutation": "R3",
    "unclassified-mutation": "R3",
    "release-or-external-write": "R4",
    "filesystem-mutation": "R4",
}

_GIT_PUSH = re.compile(r"(?i)\bgit\s+push\b")

# Destructive, effectively irreversible forms. Each escalation is scoped to
# the category whose text it inspects, so `git stash drop` (a git mutation)
# is not escalated by the SQL DROP rule. The `-D` rule is case-sensitive on
# purpose: `-d` refuses to delete an unmerged branch, `-D` does not.
_R5_ESCALATIONS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "git-history-or-remote",
        re.compile(r"(?i)\bgit\s+push\b.*\s(?:--force(?:-with-lease)?|-[a-z]*f[a-z]*)\b"),
    ),
    ("git-history-or-remote", re.compile(r"(?i)\bgit\s+reset\b.*\s--hard\b")),
    (
        "git-history-or-remote",
        re.compile(r"(?i)\bgit\s+clean\b.*\s(?:--force|-[a-z]*f[a-z]*)\b"),
    ),
    ("git-branch-mutation", re.compile(r"(?i:\bgit\s+branch\b).*\s-[A-Za-z]*D[A-Za-z]*\b")),
    (
        "git-branch-mutation",
        re.compile(
            r"(?i)\bgit\s+branch\b(?=.*\s(?:-[a-z]*d[a-z]*|--delete)\b)"
            r"(?=.*\s(?:-[a-z]*f[a-z]*|--force)\b)"
        ),
    ),
    (
        "database-mutation",
        re.compile(r"(?i)\bdrop\s+(?:table|database|schema|index|view|user)\b|\btruncate\b"),
    ),
)


def find_secret_shapes(value: Any, location: str = "$") -> list[str]:
    findings: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            findings.extend(find_secret_shapes(child, f"{location}.{key}"))
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            findings.extend(find_secret_shapes(child, f"{location}[{index}]"))
    elif isinstance(value, str):
        if any(pattern.search(value) for pattern in _SECRET_PATTERNS):
            findings.append(location)
    return findings


def enforce_private_payload(value: Any) -> None:
    findings = find_secret_shapes(value)
    if findings:
        locations = ", ".join(findings[:5])
        raise PrivacyError(
            f"Refusing to persist secret-shaped material at {locations}. "
            "Store evidence by hash or a redacted description instead."
        )


def _categorize(normalized: str) -> tuple[str, bool, list[str]]:
    """Order is the security property: mutation flags are checked before the
    safe listings so a delete can never hide behind a read-only prefix, and
    everything unrecognized fails closed as a mutation."""
    if _GIT_BRANCH_MUTATION.search(normalized):
        return (
            "git-branch-mutation",
            True,
            ["branch refs", "possibly unmerged local work"],
        )
    if any(pattern.search(normalized) for pattern in _SAFE_INSPECTION_PATTERNS):
        return "read-only-inspection", False, ["local read-only state"]
    for category, pattern, impact in _ACTION_PATTERNS:
        if pattern.search(normalized):
            return category, True, list(impact)
    return (
        "unclassified-mutation",
        True,
        ["unknown state; fail closed until explicitly scoped"],
    )


def _risk_tier(category: str, normalized: str) -> tuple[str, bool]:
    """§9.2 tier for a classified operation, and whether it is destructive
    enough (R5) to demand a second confirmation before any capability is
    spent. Escalations run first so a force form cannot keep its base tier."""
    if category == "read-only-inspection":
        return "R0", False
    for scoped_category, pattern in _R5_ESCALATIONS:
        if scoped_category == category and pattern.search(normalized):
            return "R5", True
    if category == "git-history-or-remote" and _GIT_PUSH.search(normalized):
        return "R4", False
    return _TIER_BY_CATEGORY.get(category, "R3"), False


def classify_action(operation: str, extra_protected: tuple[str, ...] = ()) -> dict[str, Any]:
    """Deterministic preview of what an operation would touch.

    `extra_protected` lets a local policy widen the protected set by category
    name; it can only add protection, never remove it, because a policy file
    inside the repository must not be able to declare a mutation safe.
    """
    normalized = operation.strip()
    if not normalized:
        raise AuthorizationError("Operation description cannot be empty")
    category, protected, impact = _categorize(normalized)
    if not protected and category in tuple(extra_protected):
        protected = True
        impact = list(impact) + ["protection extended by local authorization policy"]
    tier, second_confirmation = _risk_tier(category, normalized)
    return {
        "protected": protected,
        "category": category,
        "operation_digest": hashlib.sha256(normalized.encode()).hexdigest(),
        "impact": impact,
        "tier": tier,
        "second_confirmation_required": second_confirmation,
    }


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.chmod(temporary, 0o600)
        except OSError:
            pass
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _decode(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


POLICY_FILENAME = ".godmode-authorization-policy.json"

_DEFAULT_TTL_SECONDS = 180


class CapabilityBroker:
    """Password-backed capability issuer; it never executes an operation."""

    def __init__(self, archive: Any) -> None:
        self.archive = archive
        self.path = Path(archive.root) / "godmode-authorization.json"

    def _policy(self) -> dict[str, Any]:
        """Optional per-project policy (§24.3), allowed only to tighten.

        The file lives inside the repository, which means anything writable
        by the code under review could edit it; that is why its TTL is
        clamped to 60..900 seconds and `password_required` can extend the
        protected set but nothing here can mark an action safe. A malformed
        file refuses rather than degrades, because silently ignoring it
        would silently drop the protections it was written to add.
        """
        anchor = getattr(self.archive, "anchor", None)
        root = getattr(anchor, "project_root", None)
        if not root:
            return {}
        path = Path(root) / POLICY_FILENAME
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, json.JSONDecodeError) as exc:
            raise AuthorizationError(
                f"Authorization policy file is unreadable; fix or remove {POLICY_FILENAME}"
            ) from exc
        if not isinstance(raw, dict):
            raise AuthorizationError(f"{POLICY_FILENAME} must contain a JSON object")
        policy: dict[str, Any] = {}
        ttl = raw.get("capability_ttl_seconds")
        if ttl is not None:
            if isinstance(ttl, bool) or not isinstance(ttl, int):
                raise AuthorizationError("capability_ttl_seconds must be an integer")
            policy["capability_ttl_seconds"] = min(900, max(60, ttl))
        required = raw.get("password_required")
        if required is not None:
            if not isinstance(required, list) or not all(
                isinstance(name, str) for name in required
            ):
                raise AuthorizationError("password_required must be a list of category names")
            policy["password_required"] = tuple(required)
        return policy

    def _classify(self, operation: str) -> dict[str, Any]:
        """Classification with the local policy's extensions applied."""
        return classify_action(
            operation, extra_protected=self._policy().get("password_required", ())
        )

    def _mint_context(self) -> dict[str, str]:
        """Identity a capability binds to at mint time.

        A capability approved in one repository must not be spendable in
        another, on another worktree, or against a different HEAD than the
        one the approver looked at. The worktree path is hashed because the
        binding needs identity, not the private path itself.
        """
        anchor = getattr(self.archive, "anchor", None)
        if anchor is None:
            return {}
        worktree = str(getattr(anchor, "worktree_root", None) or "")
        return {
            "project_key": str(getattr(anchor, "project_key", "") or ""),
            "worktree": hashlib.sha256(worktree.encode("utf-8")).hexdigest(),
            "head": str(getattr(anchor, "head", None) or ""),
        }

    def configured(self) -> bool:
        return self.path.exists()

    def configure(self, password: str) -> None:
        if self.configured():
            raise AuthorizationError("Authorization is already configured")
        if len(password) < 12:
            raise AuthorizationError("Local authorization password must be at least 12 characters")
        salt = secrets.token_bytes(16)
        derived = hashlib.scrypt(
            password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32
        )
        payload = {
            "version": 1,
            "salt": _encode(salt),
            "password_hash": _encode(derived),
            "signing_key": _encode(secrets.token_bytes(32)),
            "consumed": [],
        }
        _atomic_json(self.path, payload)

    def configure_interactive(self) -> None:
        _require_tty()
        first = getpass.getpass("Create Godmode local authorization password: ")
        second = getpass.getpass("Confirm password: ")
        if first != second:
            raise AuthorizationError("Passwords do not match")
        self.configure(first)

    def _load(self) -> dict[str, Any]:
        if not self.configured():
            raise AuthorizationError("Run `authorize setup` before issuing capabilities")
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise AuthorizationError("Local authorization store is unreadable") from exc
        required = {"salt", "password_hash", "signing_key", "consumed"}
        if not required.issubset(data):
            raise AuthorizationError("Local authorization store is invalid")
        return data

    @staticmethod
    def _password_matches(password: str, data: dict[str, Any]) -> bool:
        candidate = hashlib.scrypt(
            password.encode("utf-8"),
            salt=_decode(data["salt"]),
            n=2**14,
            r=8,
            p=1,
            dklen=32,
        )
        return hmac.compare_digest(candidate, _decode(data["password_hash"]))

    def issue(
        self,
        operation: str,
        password: str,
        ttl_seconds: int | None = None,
        context: dict[str, str] | None = None,
    ) -> str:
        policy = self._policy()
        classification = classify_action(
            operation, extra_protected=policy.get("password_required", ())
        )
        if not classification["protected"]:
            raise AuthorizationError("Read-only inspection does not need a capability")
        if ttl_seconds is None:
            # The policy value was already clamped to 60..900 when read.
            ttl_seconds = policy.get("capability_ttl_seconds", _DEFAULT_TTL_SECONDS)
        elif ttl_seconds < 10 or ttl_seconds > 600:
            raise AuthorizationError("Capability lifetime must be between 10 and 600 seconds")
        data = self._load()
        if not self._password_matches(password, data):
            raise AuthorizationError("Authorization failed")
        if context is None:
            context = self._mint_context()
        now = int(time.time())
        body = {
            "version": 1,
            "operation_digest": classification["operation_digest"],
            "category": classification["category"],
            "issued_at": now,
            "expires_at": now + ttl_seconds,
            "nonce": secrets.token_hex(16),
        }
        if context:
            # Signed with the rest of the body, so the binding cannot be
            # stripped from a token after it is minted.
            body["context"] = dict(context)
        encoded = _encode(json.dumps(body, sort_keys=True, separators=(",", ":")).encode())
        signature = _encode(hmac.new(_decode(data["signing_key"]), encoded.encode(), hashlib.sha256).digest())
        token = f"gm1.{encoded}.{signature}"
        self.archive.append(
            "action",
            "capability-issued",
            {
                "category": body["category"],
                "operation_digest": body["operation_digest"],
                "expires_at": body["expires_at"],
                "capability_digest": hashlib.sha256(token.encode()).hexdigest(),
            },
            evidence=[],
        )
        return token

    def issue_interactive(self, operation: str, ttl_seconds: int | None = None) -> str:
        _require_tty()
        password = getpass.getpass("Godmode authorization password: ")
        return self.issue(operation, password, ttl_seconds)

    def request(self, operation: str, purpose: str = "") -> dict[str, Any]:
        """Record a durable request for authorization the agent cannot grant itself.

        The only previous route to a capability was a synchronous terminal prompt,
        which an agent cannot drive: it has no terminal, and the environment where
        the prompt is impossible is exactly the one the product ships into. So the
        request is separated from the grant. The agent states what it needs and
        why, durably; a human or host decides later, out of band; the agent then
        consumes the result.

        This does not weaken the boundary. A request grants nothing, and an agent
        that could mint its own approval would not need to ask.
        """
        classification = self._classify(operation)
        if not classification["protected"]:
            raise AuthorizationError("Read-only inspection does not need a capability")
        record = self.archive.append(
            "action",
            f"request:{classification['category']}",
            {
                "state": "requested",
                "operation": operation[:300],
                "purpose": purpose[:300],
                "category": classification["category"],
                "operation_digest": classification["operation_digest"],
                "preview": classification,
                "grants_nothing": True,
            },
            evidence=[],
        )
        return {
            "request": f"REQ-{record['record_hash'][:12]}",
            "operation": operation[:300],
            "category": classification["category"],
            "state": "requested",
            "next_action": "a human or host runs `authorize grant --request <id>`; the agent cannot grant its own request",
        }

    def requests(self, state: str | None = None) -> list[dict[str, Any]]:
        """Requests and their outcomes, newest last."""
        decided: dict[str, str] = {}
        for record in self.archive.select(kind="action", limit=500):
            data = record["data"]
            if data.get("state") in ("granted", "denied") and data.get("request"):
                decided[data["request"]] = data["state"]

        found: list[dict[str, Any]] = []
        for record in self.archive.select(kind="action", limit=500):
            data = record["data"]
            if data.get("state") != "requested":
                continue
            identifier = f"REQ-{record['record_hash'][:12]}"
            current = decided.get(identifier, "requested")
            if state and current != state:
                continue
            found.append({
                "request": identifier,
                "state": current,
                "operation": data.get("operation", ""),
                "purpose": data.get("purpose", ""),
                "category": data.get("category", ""),
                "sequence": record["sequence"],
            })
        return found

    def _find_request(self, identifier: str) -> dict[str, Any]:
        for entry in self.requests():
            if entry["request"] == identifier:
                return entry
        raise AuthorizationError(f"No such request: {identifier}")

    def grant(
        self, identifier: str, password: str, ttl_seconds: int | None = None
    ) -> dict[str, Any]:
        """Approve a recorded request. Still requires the secret the agent lacks."""
        entry = self._find_request(identifier)
        if entry["state"] != "requested":
            raise AuthorizationError(f"{identifier} is already {entry['state']}")
        token = self.issue(entry["operation"], password, ttl_seconds)
        if ttl_seconds is None:
            ttl_seconds = self._policy().get("capability_ttl_seconds", _DEFAULT_TTL_SECONDS)
        self.archive.append(
            "action",
            f"grant:{entry['category']}",
            {"state": "granted", "request": identifier, "operation": entry["operation"]},
            evidence=[],
        )
        return {"request": identifier, "state": "granted", "capability": token,
                "operation": entry["operation"], "expires_in_seconds": ttl_seconds}

    def deny(self, identifier: str, reason: str) -> dict[str, Any]:
        """Refuse a request, on the record.

        A denial is kept because a request that simply goes quiet is
        indistinguishable from one nobody saw, and the difference matters to
        whoever reads the trail later.
        """
        if not reason.strip():
            raise AuthorizationError("A denial requires a reason")
        entry = self._find_request(identifier)
        if entry["state"] != "requested":
            raise AuthorizationError(f"{identifier} is already {entry['state']}")
        self.archive.append(
            "action",
            f"deny:{entry['category']}",
            {"state": "denied", "request": identifier, "reason": reason[:300],
             "operation": entry["operation"]},
            evidence=[],
        )
        return {"request": identifier, "state": "denied", "reason": reason[:300]}

    def consume(
        self, operation: str, token: str, context: dict[str, str] | None = None
    ) -> dict[str, Any]:
        classification = self._classify(operation)
        if not classification["protected"]:
            return classification
        data = self._load()
        parts = token.split(".")
        if len(parts) != 3 or parts[0] != "gm1":
            raise AuthorizationError("Capability format is invalid")
        expected = hmac.new(
            _decode(data["signing_key"]), parts[1].encode(), hashlib.sha256
        ).digest()
        try:
            supplied = _decode(parts[2])
            body = json.loads(_decode(parts[1]).decode("utf-8"))
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AuthorizationError("Capability payload is invalid") from exc
        if not hmac.compare_digest(expected, supplied):
            raise AuthorizationError("Capability signature is invalid")
        if body.get("operation_digest") != classification["operation_digest"]:
            raise AuthorizationError("Capability is scoped to a different operation")
        if int(body.get("expires_at", 0)) < int(time.time()):
            raise AuthorizationError("Capability has expired")
        minted_context = body.get("context")
        if minted_context:
            # The refusal happens before the nonce is burned so a token spent
            # in the wrong place is refused, not consumed.
            current = context if context is not None else self._mint_context()
            for field, label in (
                ("project_key", "repository"),
                ("worktree", "worktree"),
                ("head", "HEAD"),
            ):
                if str(minted_context.get(field, "")) != str(current.get(field, "")):
                    raise AuthorizationError(
                        f"capability was minted for another {label}; "
                        "re-issue it from the current context"
                    )
        else:
            # Tokens minted before context binding existed still work, but
            # the caller is told the binding is absent rather than implied.
            classification["unscoped"] = True
        nonce_digest = hashlib.sha256(str(body.get("nonce", "")).encode()).hexdigest()
        if nonce_digest in data["consumed"]:
            raise AuthorizationError("Capability has already been consumed")
        data["consumed"] = (data["consumed"] + [nonce_digest])[-2048:]
        _atomic_json(self.path, data)
        self.archive.append(
            "action",
            "capability-consumed",
            {
                "category": classification["category"],
                "operation_digest": classification["operation_digest"],
                "capability_digest": hashlib.sha256(token.encode()).hexdigest(),
            },
            evidence=[],
        )
        return classification
