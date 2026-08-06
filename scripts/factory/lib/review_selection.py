"""Deterministic role selection for independent code-review councils."""

from . import council


SIGNAL_ROLE = {
    "security": "architecture", "architecture": "architecture",
    "customer-trust": "customer", "ui-taste": "ui-taste",
    "product-behavior": "product", "commercial": "commercial",
}
SIGNAL_PRECEDENCE = ("security", "architecture", "customer-trust",
                     "ui-taste", "product-behavior", "commercial")
SPECIAL_SIGNALS = ("ambiguous", "high-blast-radius", "irreversible")

_SIGNAL_ORDER = SIGNAL_PRECEDENCE + SPECIAL_SIGNALS


def _roles(value, label):
    roles = list(value or [])
    unknown = [role for role in roles if role not in council.ROLES]
    if unknown:
        raise ValueError(f"{label} contains unknown role {unknown[0]!r}")
    if len(roles) != len(set(roles)):
        raise ValueError(f"{label} must be duplicate-free")
    return roles


def _signals(value):
    normalized = []
    for entry in value:
        if not isinstance(entry, dict):
            raise ValueError("signals must be normalized objects")
        name = entry.get("name")
        evidence = entry.get("evidence")
        if name not in _SIGNAL_ORDER:
            raise ValueError(f"unknown review signal {name!r}")
        if (not isinstance(evidence, list) or not evidence
                or any(not isinstance(item, str) or not item.strip()
                       for item in evidence)):
            raise ValueError(f"signal {name!r} requires concrete evidence")
        normalized.append(entry)
    order = {name: index for index, name in enumerate(_SIGNAL_ORDER)}
    return sorted(normalized, key=lambda entry: order[entry["name"]])


def _conflicts(value):
    normalized = []
    for entry in value or []:
        if not isinstance(entry, dict):
            raise ValueError("conflicts must be normalized objects")
        roles = _roles(entry.get("roles"), "conflict roles")
        evidence = entry.get("evidence")
        if not roles:
            raise ValueError("conflict requires at least one role")
        if not isinstance(evidence, str) or not evidence.strip():
            raise ValueError("conflict requires concrete evidence")
        normalized.append({"roles": roles, "evidence": evidence})
    return normalized


def _omitted(selected, signalled_roles):
    selected_roles = {entry["role"] for entry in selected}
    return [
        {
            "role": role,
            "reasons": ["adaptive.ordinary-cap"
                        if role in signalled_roles
                        else "signal.not-applicable"],
        }
        for role in council.ROLES
        if role not in selected_roles
    ]


def _round_one(mode, signals):
    if mode == "full":
        selected = [
            {"role": role, "reasons": ["override.full"]}
            for role in council.ROLES
        ]
        return {"selected": selected, "omitted": []}

    mapped_reasons = {}
    candidates = []
    for entry in signals:
        name = entry["name"]
        role = SIGNAL_ROLE.get(name)
        if role is None:
            continue
        if role not in mapped_reasons:
            mapped_reasons[role] = []
            candidates.append(role)
        if name not in mapped_reasons[role]:
            mapped_reasons[role].append(name)

    selected = [{"role": "engineering-quality",
                 "reasons": ["baseline.correctness-evidence"]}]
    signal_names = {entry["name"] for entry in signals}
    if "ambiguous" in signal_names:
        architecture_reasons = ["fallback.general-backend"]
        architecture_reasons.extend(mapped_reasons.get("architecture", []))
        product_reasons = ["ambiguous"]
        product_reasons.extend(mapped_reasons.get("product", []))
        selected.extend([
            {"role": "architecture", "reasons": architecture_reasons},
            {"role": "product", "reasons": product_reasons},
        ])
    elif candidates:
        limit = 3 if signal_names.intersection(
            ("high-blast-radius", "irreversible")) else 2
        for role in candidates[:limit]:
            reasons = list(mapped_reasons[role])
            if len(selected) == 3:
                reasons.extend(name for name in SPECIAL_SIGNALS[1:]
                               if name in signal_names)
            selected.append({"role": role, "reasons": reasons})
    else:
        selected.append({"role": "architecture",
                         "reasons": ["fallback.general-backend"]})

    return {"selected": selected,
            "omitted": _omitted(selected, set(mapped_reasons))}


def _round_two(mode, signals, conflicts, blocking_roles, prior_roles,
               added_role):
    if not blocking_roles and not conflicts:
        raise ValueError("Round 2 is delta-only and requires a blocking finding "
                         "or conflict")
    if any(role not in prior_roles for role in blocking_roles):
        raise ValueError("blocking roles must be recalled from prior roles")
    conflict_roles = {role for conflict in conflicts
                      for role in conflict["roles"]}
    if any(role not in prior_roles for role in conflict_roles):
        raise ValueError("conflict roles must be recalled from prior roles")

    required = set(blocking_roles) | conflict_roles
    selected = []
    for role in council.ROLES:
        if role not in required:
            continue
        reasons = []
        if role in blocking_roles:
            reasons.append("round2.blocking-finding")
        if role in conflict_roles:
            reasons.append("round2.conflict")
        selected.append({"role": role, "reasons": reasons})

    if added_role:
        if not conflicts:
            raise ValueError("Round 2 is delta-only; an added role requires a conflict")
        if added_role not in council.ROLES:
            raise ValueError(f"added role contains unknown role {added_role!r}")
        if added_role in prior_roles or added_role in required:
            raise ValueError("added role must be a new omitted role")
        selected.append({"role": added_role,
                         "reasons": ["round2.next-omitted-lens"]})

    distinct = set(prior_roles) | {entry["role"] for entry in selected}
    if mode == "adaptive" and len(distinct) > 4:
        raise ValueError("adaptive review permits at most four distinct roles")
    return {"selected": selected,
            "omitted": _omitted(selected, {
                SIGNAL_ROLE[entry["name"]] for entry in signals
                if entry["name"] in SIGNAL_ROLE
            })}


def select_roles(*, mode, round_number, signals, conflicts=None,
                 blocking_roles=None, prior_roles=None, added_role=""):
    """Return a deterministic selected/omitted role plan for one round."""
    if mode not in ("adaptive", "full"):
        raise ValueError("mode must be 'adaptive' or 'full'")
    if round_number not in (1, 2):
        if round_number == 3:
            raise ValueError("review has a maximum two rounds")
        raise ValueError("round_number must be 1 or 2")

    normalized_signals = _signals(signals)
    normalized_conflicts = _conflicts(conflicts)
    normalized_prior = _roles(prior_roles, "prior_roles")
    normalized_blocking = _roles(blocking_roles, "blocking_roles")

    if round_number == 1:
        return _round_one(mode, normalized_signals)
    return _round_two(mode, normalized_signals, normalized_conflicts,
                      normalized_blocking, normalized_prior, added_role)
