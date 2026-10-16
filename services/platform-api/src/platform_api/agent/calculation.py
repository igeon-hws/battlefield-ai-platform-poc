"""Evidence arithmetic. No domain mappings, identity rules, graph or source access."""

import json
from collections import Counter, defaultdict

ID_FIELDS = {"atcis": "trackKey", "knccs": "contactNo"}


def records_from(lists):
    if not lists or any(e.get("originalTool") != "list_equipment" for e in lists):
        raise ValueError("equipment list evidence required")
    pages = defaultdict(list)
    records: dict[tuple[str, str], tuple[dict, list[str]]] = {}
    for e in lists:
        system = e["systemId"]
        key = (
            system,
            json.dumps(
                {k: v for k, v in e["arguments"].items() if k not in ("cursor", "limit")},
                sort_keys=True,
            ),
        )
        pages[key].append(e)
        for row in e["data"]["items"]:
            native = row[ID_FIELDS[system]]
            record_key = (system, native)
            if record_key in records and records[record_key][0] != row:
                raise ValueError("inconsistent source evidence")
            previous = records.get(record_key)
            records[record_key] = (
                row,
                sorted(set((previous[1] if previous else []) + [e["evidenceId"]])),
            )
    for group in pages.values():
        ids = {r[ID_FIELDS[e["systemId"]]] for e in group for r in e["data"]["items"]}
        if not any(e["data"].get("nextCursor") is None for e in group) or any(
            len(ids) != e["data"]["matchedCount"] for e in group
        ):
            raise ValueError("incomplete equipment evidence")
    return records


def native_count(records, args):
    selected = {}
    counts: Counter[str] = Counter()
    for (system, native), (row, ids) in records.items():
        if any(f.system_id in (None, system) and row.get(f.field) != f.value for f in args.filters):
            continue
        selected[(system, native)] = (row, ids)
        if args.group_by:
            counts[system + ":" + str(row.get(args.group_by, "<missing>"))] += 1
    return {
        "interpretation": "native_records_only",
        "rawRecordCount": len(selected),
        "counts": dict(counts),
        "items": [
            {"systemId": s, "nativeId": n, "record": row, "evidenceIds": ids}
            for (s, n), (row, ids) in selected.items()
        ],
        "coverage": "complete",
    }


def semantic_count(records, args, identities, scopes, concepts):
    if not identities or not concepts:
        raise ValueError("Semantic identity/reference and concept evidence required")
    if any(e.get("systemId") != "semantic" for e in identities + scopes + concepts):
        raise ValueError(
            "Semantic evidence required; raw identity records are not resolved identities"
        )
    if any(e.get("originalTool") != "interpret_concept" for e in concepts):
        raise ValueError("Semantic interpretation evidence required")
    mappings = [
        e["data"].get("sourceMappings") for e in concepts if e["data"].get("status") == "resolved"
    ]
    if not mappings or any(m != mappings[0] for m in mappings):
        raise ValueError("missing or inconsistent interpretation mappings")
    mapping = mappings[0]
    supported_units = set()
    for e in scopes:
        if (
            e.get("originalTool") != "resolve_unit_scope"
            or e["data"].get("completeness") != "complete"
        ):
            raise ValueError("incomplete semantic scope evidence")
        supported_units.update(e["data"].get("unitIds", []))
    if args.unit_ids is not None and set(args.unit_ids) - supported_units:
        raise ValueError("unsupported scope units")
    groups: dict[str, set[tuple[str, str]]] = {}
    reference_to_group: dict[tuple[str, str], str] = {}
    reference_pages = defaultdict(list)
    for e in identities:
        if e.get("originalTool") == "find_equipment_refs":
            key = json.dumps(
                {k: v for k, v in e.get("arguments", {}).items() if k not in ("cursor", "limit")},
                sort_keys=True,
            )
            reference_pages[key].append(e["data"])
    for pages in reference_pages.values():
        canonical_ids = {i["canonicalId"] for p in pages for i in p.get("items", [])}
        if not any(
            p.get("nextCursor") is None and p.get("complete", p.get("completeness") == "complete")
            for p in pages
        ) or any(len(canonical_ids) != p["matchedCount"] for p in pages):
            raise ValueError("incomplete semantic reference evidence")
    for e in identities:
        if e.get("originalTool") not in ("find_equipment_refs", "resolve_entity"):
            raise ValueError("Semantic identity/reference evidence required")
        d = e["data"]
        for item in d.get("items", []) if e["originalTool"] == "find_equipment_refs" else [d]:
            if (
                not item.get("canonicalId")
                or item.get("status", item.get("identityStatus", "resolved")) != "resolved"
            ):
                raise ValueError("unresolved semantic identity")
            cid = item["canonicalId"]
            if args.kind and "kind" not in item:
                raise ValueError("semantic kind proof required")
            if args.kind and item.get("kind") != args.kind:
                continue
            refs = {(r["systemId"], r["nativeId"]) for r in item.get("sourceRefs", [])}
            for r in refs:
                if r in reference_to_group and reference_to_group[r] != cid:
                    raise ValueError("inconsistent canonical groups")
                reference_to_group[r] = cid
            groups.setdefault(cid, set()).update(refs)
    selected = []
    counts: Counter[str] = Counter()
    raw_count = 0
    used_records = set()
    for cid, refs in groups.items():
        if not refs:
            raise ValueError("missing semantic source references")
        if refs - records.keys():
            raise ValueError("incomplete identity observation coverage")
        observations = []
        in_scope = args.unit_ids is None
        for system, native in sorted(refs):
            row, ids = records[(system, native)]
            rules = mapping[system]
            unit = row.get(rules["unitField"])
            if args.unit_ids is not None and system + ":" + str(unit) in args.unit_ids:
                in_scope = True
            observations.append(
                {
                    "systemId": system,
                    "nativeId": native,
                    "availability": rules["availabilityValues"].get(
                        row.get(rules["availabilityField"]), "unknown"
                    ),
                    "unitId": unit,
                    "observedAt": row.get(rules["observedAtField"]),
                    "evidenceIds": ids,
                }
            )
        if not in_scope:
            continue
        used_records.update(refs)
        raw_count += len(refs)
        states = {o["availability"] for o in observations}
        status = next(iter(states)) if len(states) == 1 else "conflicting"
        counts[status] += 1
        selected.append(
            {
                "canonicalId": cid,
                "status": status,
                "sourceRefs": observations,
                "evidenceIds": sorted({i for o in observations for i in o["evidenceIds"]}),
            }
        )
    # Extra observations cannot silently disappear from a purported complete unfiltered count.
    if args.unit_ids is None and args.kind is None and records.keys() - used_records:
        raise ValueError("missing semantic identity coverage")
    return {
        "interpretation": "semantic_evidence",
        "rawRecordCount": raw_count,
        "resolvedUniqueCount": len(selected),
        "confirmedAvailable": counts["available"],
        "confirmedUnavailable": counts["unavailable"],
        "unknown": counts["unknown"],
        "conflicting": counts["conflicting"],
        "unresolvedIdentity": 0,
        "items": selected,
        "coverage": "complete",
    }
