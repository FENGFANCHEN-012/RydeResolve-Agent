"""References to policy parameters supplied by the platform for this case.

Only explicit keys in trusted case-policy sections are citable. The complaint,
profiles, and evaluation answer keys never become policy authority.
"""


def case_policy_refs(context: dict | None) -> set[str]:
    if not isinstance(context, dict):
        return set()
    refs: set[str] = set()
    for section in ("platform_policy", "cancellation_policy"):
        fields = context.get(section)
        if isinstance(fields, dict):
            refs.update(
                f"{section}.{key}"
                for key in fields
                if isinstance(key, str) and key and not key.startswith("_")
            )
    return refs
