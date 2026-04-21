"""Merge controller-issued via-points with the pilot's colación (readback).

The pilot's sequence is authoritative for order (ICAO rule: the pilot must
repeat the clearance). Any taxiway in the controller list that the pilot
did NOT read back is spliced in at the position that keeps progression
monotonic along the graph.
"""

from typing import Iterable


def merge_constraints(
    controller_via: Iterable[str],
    readback_via: Iterable[str],
) -> list[str]:
    """Stable-merge two ordered taxiway sequences.

    - Readback order is preserved.
    - Controller-only tokens are inserted at the earliest position that
      doesn't break the readback ordering. In practice: if the controller
      said ["B","D","E"] and the pilot said ["B","D"], the final merged
      list is ["B","D","E"]. If the pilot said ["D","B"], the merged list
      follows the pilot: ["D","B"] (controller "E" appended at the end).
    - Tokens are normalised to uppercase strings and de-duplicated by
      first appearance.
    """
    ctrl = [str(t).upper() for t in controller_via if t]
    pilot = [str(t).upper() for t in readback_via if t]

    # De-dup preserving order
    def _dedup(seq: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for t in seq:
            if t in seen:
                continue
            seen.add(t)
            out.append(t)
        return out

    ctrl = _dedup(ctrl)
    pilot = _dedup(pilot)

    if not ctrl:
        return pilot
    if not pilot:
        return ctrl

    # Start from the pilot order; splice controller-only tokens at the
    # earliest position that keeps the controller's relative order among
    # anchors already present in `merged`. When the pilot reordered those
    # anchors (no consistent position exists), append at the end.
    merged = list(pilot)

    for idx, tok in enumerate(ctrl):
        if tok in merged:
            continue
        before = [ctrl[i] for i in range(idx) if ctrl[i] in merged]
        after = [ctrl[i] for i in range(idx + 1, len(ctrl)) if ctrl[i] in merged]
        if not before and not after:
            merged.append(tok)
            continue
        max_before = max((merged.index(t) for t in before), default=-1)
        min_after = min((merged.index(t) for t in after), default=len(merged))
        insert_at = max_before + 1
        if insert_at > min_after:
            insert_at = len(merged)  # pilot reordered anchors → append
        merged.insert(insert_at, tok)

    return merged
