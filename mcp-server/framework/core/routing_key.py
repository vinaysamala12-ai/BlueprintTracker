"""Composable routing key schema for multi-tenant tenant routing.

Product teams define routing dimensions by constructing a :class:`RoutingKeySchema`
and passing it to :func:`~framework.core.tenant_routing_provider.add_tenant_routing_provider`
in ``src/custom/server.py``::

    from framework import add_tenant_routing_provider, RoutingKeySchema, issuer_info, token_claim, header

    add_tenant_routing_provider(
        "customer",
        schema=RoutingKeySchema(
            issuer_info("issuer_environment"),
            token_claim("coid"),
            header("x-aptean-database", default="*", wildcard_fallback=True),
        ),
        file="config/customer-resources.json",
        app_config_prefix="customer-routing",
    )

All segment types accept ``wildcard_fallback=True``, which means:

* Pass 1 (exact): segment value is matched as-is against the rule field.
* Pass 2 (wildcard): segment is skipped and the rule field must equal ``"*"``.

Only the last (or any explicitly flagged) segment should carry
``wildcard_fallback``.  ``literal`` segments are preserved for backward
compatibility but the preferred approach is ``app_config_prefix`` on
:class:`RoutingKeySchema`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

_logger = logging.getLogger(__name__)


# ── Segment base ──────────────────────────────────────────────────────────────


class RoutingKeySegment:
    """Abstract base for one position in a routing key."""

    wildcard_fallback: bool = False

    def resolve(self, context: Dict[str, Any]) -> Optional[str]:
        """Resolve this segment's value from the current request context."""
        raise NotImplementedError

    @property
    def field_name(self) -> str:
        """Rule-dict field name used for storage and matching.  Empty for literals."""
        return ""


# ── Concrete segment types ────────────────────────────────────────────────────


@dataclass
class literal(RoutingKeySegment):
    """Fixed text segment — kept for backward compatibility.

    Prefer the ``app_config_prefix`` parameter on :class:`RoutingKeySchema`
    or :func:`set_routing_key_schema` to set the App Configuration key prefix.
    Leading ``literal`` segments in ``segments`` are still recognised as a
    prefix for backward compatibility.

    Example::

        literal("tenant-routing")   # always the string "tenant-routing"
    """

    value: str
    wildcard_fallback: bool = False

    def resolve(self, context: Dict[str, Any]) -> Optional[str]:
        return self.value

    @property
    def field_name(self) -> str:
        return ""  # literals are not stored in rule dicts


@dataclass
class issuer_info(RoutingKeySegment):
    """Segment derived from issuer configuration (e.g. ``issuer_environment``).

    The ``field`` argument is the key inside the issuer config dict returned by
    ``app_config.get_issuer_config()``.  The most common field is
    ``"issuer_environment"``.

    Example::

        issuer_info("issuer_environment")
    """

    field: str
    wildcard_fallback: bool = False

    def resolve(self, context: Dict[str, Any]) -> Optional[str]:
        from .config import app_config  # deferred to avoid circular import

        issuer_url = str(context.get("issuer_url", "")).strip()
        if not issuer_url:
            return None
        if self.field == "issuer_environment":
            return app_config.get_environment_for_issuer(issuer_url)
        cfg = app_config.get_issuer_config(issuer_url)
        if not cfg:
            return None
        val = cfg.get(self.field)
        return str(val).strip() if val is not None else None

    @property
    def field_name(self) -> str:
        return self.field


@dataclass
class token_claim(RoutingKeySegment):
    """Segment derived from a JWT token claim (e.g. ``"coid"`` or ``"uoid"``).

    The ``claim`` argument is the JWT payload key.  The same name is used as
    the rule-dict field name.

    Example::

        token_claim("coid")
    """

    claim: str
    wildcard_fallback: bool = False

    def resolve(self, context: Dict[str, Any]) -> Optional[str]:
        val = context.get(self.claim)
        return str(val).strip() if val is not None else None

    @property
    def field_name(self) -> str:
        return self.claim


@dataclass
class header(RoutingKeySegment):
    """Segment derived from a request header.

    Args:
        name: HTTP header name (case-insensitive lookup, e.g. ``"x-aptean-database"``).
        default: Value used when the header is absent.  Use ``"*"`` so the
            segment resolves to the wildcard value rather than blocking routing.
        wildcard_fallback: When ``True``, a second routing pass attempts to
            match rules where this field equals ``"*"`` (catch-all rule).
        rule_field: The key used in rule dicts for this segment.  Defaults to
            a sanitised form of ``name`` (lowercase, hyphens → underscores).
            Override to ``"database_name"`` to stay compatible with existing
            rule files that use that field name.

    Example::

        header("x-aptean-database", default="*", wildcard_fallback=True)
    """

    name: str
    default: Optional[str] = None
    wildcard_fallback: bool = False
    rule_field: str = field(default="")

    def __post_init__(self) -> None:
        if not self.rule_field:
            self.rule_field = self.name.lower().replace("-", "_")

    def resolve(self, context: Dict[str, Any]) -> Optional[str]:
        headers = context.get("headers") or {}
        name_lower = self.name.lower()
        for k, v in headers.items():
            if k.lower() == name_lower and v:
                return str(v).strip()
        return self.default

    @property
    def field_name(self) -> str:
        return self.rule_field


# ── Schema ────────────────────────────────────────────────────────────────────


class RoutingKeySchema:
    """Defines the routing dimensions and the App Configuration key structure.

    ``segments`` should contain only routing-dimension segments (``issuer_info``,
    ``token_claim``, ``header``).  The App Configuration key prefix is set via
    ``app_config_prefix`` — it is distinct from the routing dimensions and is
    ignored by the file-based provider.

    """

    def __init__(
        self,
        *segments: RoutingKeySegment,
        separator: str = "/",
        app_config_prefix: Optional[str] = None,
    ) -> None:
        self.segments = list(segments)
        self.separator = separator
        self.app_config_prefix = app_config_prefix

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _effective_prefix(self) -> str:
        """Return the App Configuration key prefix.

        Precedence:
        1. ``app_config_prefix`` if explicitly set (empty string = no prefix).
        2. Leading ``literal`` segments in ``self.segments`` (backward compat).
        3. ``""`` — no prefix (raw ``RoutingKeySchema()`` constructor calls).
        """
        if self.app_config_prefix is not None:
            return self.app_config_prefix.rstrip(self.separator)
        prefix_parts: List[str] = []
        for seg in self.segments:
            if isinstance(seg, literal):
                prefix_parts.append(seg.value)
            else:
                break
        return self.separator.join(prefix_parts)

    def _dimension_segments(self) -> List[RoutingKeySegment]:
        """Segments that contribute to routing dimensions (non-literal)."""
        return [s for s in self.segments if not isinstance(s, literal)]

    # ── Key candidates ────────────────────────────────────────────────────────

    def build_key_candidates(self, context: Dict[str, Any]) -> List[str]:
        """Return routing-key candidates (most-specific first) for *context*.

        Returns an empty list when any required (non-wildcard) segment cannot be
        resolved, which causes routing to skip silently.

        For each segment with ``wildcard_fallback=True``, an additional candidate
        is generated with that position replaced by ``"*"``.
        """
        prefix = self._effective_prefix()
        prefix_parts = prefix.split(self.separator) if prefix else []
        dim_segs = self._dimension_segments()

        resolved_dims: List[str] = []
        for seg in dim_segs:
            val = seg.resolve(context)
            if not val:
                if seg.wildcard_fallback:
                    val = "*"
                else:
                    _logger.debug(
                        "routing_key: required segment '%s' resolved to empty; skipping route lookup",
                        seg.field_name or type(seg).__name__,
                    )
                    return []
            resolved_dims.append(val)

        all_parts = prefix_parts + resolved_dims
        exact = self.separator.join(all_parts)
        candidates: List[str] = [exact]

        n_prefix = len(prefix_parts)
        for i, seg in enumerate(dim_segs):
            if seg.wildcard_fallback and resolved_dims[i] != "*":
                fallback = list(all_parts)
                fallback[n_prefix + i] = "*"
                cand = self.separator.join(fallback)
                if cand not in candidates:
                    candidates.append(cand)

        return candidates

    # ── App Configuration helpers ─────────────────────────────────────────────

    def build_key_filter(self) -> str:
        """Return an Azure App Configuration ``key_filter`` string.

        The filter covers all keys under the schema's App Config prefix.
        For example, a prefix of ``"tenant-routing"`` yields
        ``"tenant-routing/*"``.
        """
        prefix = self._effective_prefix()
        return f"{prefix}{self.separator}*" if prefix else "*"

    def parse_key_to_rule_fields(self, key: str) -> Optional[Dict[str, str]]:
        """Parse an App Configuration key into named rule fields.

        Returns ``None`` when the key does not have the expected number of
        segments or when the prefix does not match.
        """
        prefix = self._effective_prefix()
        prefix_parts = prefix.split(self.separator) if prefix else []
        dim_segs = [s for s in self._dimension_segments() if s.field_name]

        parts = key.split(self.separator)
        if len(parts) != len(prefix_parts) + len(dim_segs):
            return None

        if prefix_parts:
            actual_prefix = self.separator.join(parts[: len(prefix_parts)])
            if actual_prefix != prefix:
                return None

        result: Dict[str, str] = {}
        for seg, part in zip(dim_segs, parts[len(prefix_parts) :]):
            result[seg.field_name] = part

        return result

    # ── Introspection ─────────────────────────────────────────────────────────

    @property
    def matching_field_names(self) -> List[str]:
        """Ordered list of rule-dict field names (non-literal segments only)."""
        return [
            seg.field_name
            for seg in self.segments
            if not isinstance(seg, literal) and seg.field_name
        ]

    @property
    def wildcard_field_names(self) -> List[str]:
        """Field names for segments that support wildcard fallback."""
        return [
            seg.field_name
            for seg in self.segments
            if not isinstance(seg, literal) and seg.wildcard_fallback and seg.field_name
        ]
