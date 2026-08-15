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


def _duplicates(values):
    seen = set()
    return sorted({value for value in values
                   if value in seen or seen.add(value)})


def _degradation_section(text):
    marker = "## Degradation"
    if marker not in text:
        return ""
    section = text.split(marker, 1)[1]
    return section.split("\n## ", 1)[0]


def receipt_errors(data, path, review_root=None, synthesis_text=None,
                   expected_item=None, expected_round=None,
                   prior_receipt=None):
    """Validate one persisted review-selection receipt.

    Schema errors are returned before semantic checks so corrupt input never
    reaches the selector or filesystem validation paths.
    """
    from .initrepo import load_schema
    from .validate import validate

    errors = validate(data, load_schema("review-selection"), path)
    if errors:
        return errors

    if expected_item is not None and data["item"] != expected_item:
        errors.append(
            f"{path}.item: {data['item']!r} does not match {expected_item!r}")
    if expected_round is not None and data["round"] != expected_round:
        errors.append(
            f"{path}.round: {data['round']!r} does not match filename round "
            f"{expected_round}")

    round_number = data["round"]
    if round_number not in (1, 2):
        errors.append(f"{path}.round: must be exactly 1 or 2")
    if not data["diff"]["changed_paths"] or any(
            not value.strip() for value in data["diff"]["changed_paths"]):
        errors.append(f"{path}.diff.changed_paths: must be non-empty strings")
    for index, signal in enumerate(data["signals"]):
        evidence = signal["evidence"]
        if not evidence or any(not value.strip() for value in evidence):
            errors.append(
                f"{path}.signals[{index}].evidence: must be non-empty strings")
    for group in ("selected", "omitted"):
        for index, entry in enumerate(data[group]):
            reasons = entry["reasons"]
            if not reasons or any(not value.strip() for value in reasons):
                errors.append(
                    f"{path}.{group}[{index}].reasons: must be non-empty strings")

    selected_roles = [entry["role"] for entry in data["selected"]]
    omitted_roles = [entry["role"] for entry in data["omitted"]]
    for group, roles in (("selected", selected_roles),
                         ("omitted", omitted_roles)):
        duplicate = _duplicates(roles)
        if duplicate:
            errors.append(f"{path}.{group}: duplicate roles {duplicate}")
    overlap = sorted(set(selected_roles) & set(omitted_roles))
    if overlap:
        errors.append(f"{path}: selected/omitted overlap {overlap}")
    partition = set(selected_roles) | set(omitted_roles)
    if partition != set(council.ROLES):
        errors.append(f"{path}: selected/omitted must partition all six roles")

    escalation = data["escalation"]
    if round_number == 2:
        if prior_receipt is None:
            errors.append(f"{path}: Round 2 requires a valid Round 1 receipt")
        else:
            prior_errors = receipt_errors(
                prior_receipt, f"{path} prior Round 1", review_root=review_root,
                expected_item=expected_item or data["item"], expected_round=1)
            if prior_errors:
                errors.append(f"{path}: Round 1 receipt is invalid")
            else:
                if data["mode"] != prior_receipt["mode"]:
                    errors.append(
                        f"{path}.mode: Round 2 must match Round 1 mode "
                        f"{prior_receipt['mode']!r}")
                if data["diff"] != prior_receipt["diff"]:
                    errors.append(
                        f"{path}.diff: cross-round identity must exactly "
                        "match Round 1 diff")
                try:
                    round_two_signals = _signals(data["signals"])
                except ValueError:
                    round_two_signals = None
                if (round_two_signals is not None
                        and round_two_signals != _signals(
                            prior_receipt["signals"])):
                    errors.append(
                        f"{path}.signals: cross-round identity must exactly "
                        "match Round 1 normalized signals")
                actual_prior = [entry["role"]
                                for entry in prior_receipt["selected"]]
                if escalation["prior_roles"] != actual_prior:
                    errors.append(
                        f"{path}.escalation.prior_roles: must exactly match "
                        "Round 1 selected roles")
    if round_number in (1, 2):
        try:
            expected = select_roles(
                mode=data["mode"], round_number=round_number,
                signals=data["signals"],
                conflicts=escalation["conflicts"],
                blocking_roles=escalation["blocking_roles"],
                prior_roles=escalation["prior_roles"],
                added_role=escalation["added_role"])
        except ValueError as exc:
            errors.append(f"{path}: selector refused receipt: {exc}")
        else:
            if data["selected"] != expected["selected"]:
                errors.append(f"{path}.selected: selector/receipt disagreement")
            if data["omitted"] != expected["omitted"]:
                errors.append(f"{path}.omitted: selector/receipt disagreement")

    outcome_roles = [entry["role"] for entry in data["outcomes"]]
    duplicate_outcomes = _duplicates(outcome_roles)
    if duplicate_outcomes:
        errors.append(f"{path}.outcomes: duplicate roles {duplicate_outcomes}")
    if set(outcome_roles) != set(selected_roles) or len(outcome_roles) != len(selected_roles):
        errors.append(f"{path}.outcomes: must exactly cover selected roles")

    non_returned = []
    for index, outcome in enumerate(data["outcomes"]):
        role = outcome["role"]
        status = outcome["status"]
        report = outcome["report"]
        expected_report = f"round-{round_number}/{role}.md"
        if status == "returned":
            if report != expected_report:
                errors.append(
                    f"{path}.outcomes[{index}].report: expected {expected_report!r}")
            elif review_root is not None:
                report_path = review_root / report
                if not report_path.exists() or not report_path.is_file() \
                        or not report_path.read_text(
                            encoding="utf-8", errors="replace").strip():
                    errors.append(
                        f"{path}.outcomes[{index}]: returned report missing or empty")
        else:
            non_returned.append(outcome)
            if report:
                errors.append(
                    f"{path}.outcomes[{index}].report: non-returned report must be empty")

    independence = data["independence"]
    degradation = independence["degradation"]
    if any(not value.strip() for value in degradation):
        errors.append(f"{path}.independence.degradation: must be non-empty strings")
    if independence["achieved"]:
        if not independence["requested"]:
            errors.append(f"{path}.independence: achieved requires requested")
        if degradation:
            errors.append(f"{path}.independence: achieved forbids degradation")
        if non_returned:
            errors.append(f"{path}.independence: achieved requires all outcomes returned")
    elif not degradation:
        errors.append(f"{path}.independence: unachieved review requires degradation")
    if non_returned and not degradation:
        errors.append(f"{path}: non-returned outcomes require degradation")

    degradation_required = not independence["achieved"] or bool(non_returned)
    if synthesis_text is not None and degradation_required:
        section = _degradation_section(synthesis_text)
        if not section:
            errors.append(f"{path}: synthesis requires ## Degradation")
        else:
            for detail in degradation:
                if detail not in section:
                    errors.append(
                        f"{path}: synthesis degradation missing {detail!r}")
            for outcome in non_returned:
                token = f"{outcome['role']}: {outcome['status']}"
                if token not in section:
                    errors.append(
                        f"{path}: synthesis degradation missing {token!r}")
    return errors
