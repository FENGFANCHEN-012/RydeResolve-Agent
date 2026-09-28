"""References to policy parameters supplied by the platform for this case.

Only explicit keys in trusted case-policy sections are citable. The complaint,
profiles, and evaluation answer keys never become policy authority.
"""


_CASE_SECTIONS = ("platform_policy", "cancellation_policy")


def normalize_case_policy_ref(ref: str, valid_refs: set[str]) -> str:
    """Map a citation of a real case-policy key to its canonical form.

    The Judge sometimes writes a key without its section ("free_wait_time_min")
    or under the other section name; both still point at a real field, so they
    are rewritten rather than stripped as hallucinated. Anything else is
    returned unchanged for the caller's whitelist check.
    """
    if not isinstance(ref, str) or ref in valid_refs:
        return ref
    bare = ref.strip()
    for section in _CASE_SECTIONS:
        if bare.startswith(section + "."):
            bare = bare[len(section) + 1:]
            break
    for section in _CASE_SECTIONS:
        candidate = f"{section}.{bare}"
        if candidate in valid_refs:
            return candidate
    return ref


def case_policy_refs(context: dict | None) -> set[str]:
    if not isinstance(context, dict):
        return set()
    refs: set[str] = set()
    for section in _CASE_SECTIONS:
        fields = context.get(section)
        if isinstance(fields, dict):
            refs.update(
                f"{section}.{key}"
                for key in fields
                if isinstance(key, str) and key and not key.startswith("_")
            )
    return refs
