"""Check whether the catalog can make progress from a supplied account state."""

from collections import Counter, defaultdict
from math import inf


def unreachable_records(catalog: dict, profile: dict) -> dict[str, list[str]]:
    """Compute an optimistic fixed point over directed, gated transitions.

    Manual skill training and waiting are possible. The audit accumulates
    possible resources and flags across paths so it can reject impossible
    dependencies without choosing a route or claiming joint feasibility.
    """
    initial = profile["initial_state"]
    locations = {initial["location_id"]}
    completed = set(initial["completed_action_ids"])
    used_edges = set(initial.get("travel_counts", {}))
    inventory = Counter(initial["inventory"])
    bank_inventory = initial.get("bank_inventory", {})
    restrictions = {location["id"]: location["prohibited_item_ids"]
                    for location in catalog["locations"] if "prohibited_item_ids" in location}
    depositable = set()
    withdrawable = set()
    consumable = set()
    counters = Counter(initial["counters"])
    flags = defaultdict(set)
    choices = defaultdict(set)
    initial_choices = initial.get("choices", {})
    limits = {token["id"]: token["maximum"] for token in catalog["tokens"]}

    def requirement_met(rule: dict) -> bool:
        kind = rule["kind"]
        if kind == "all":
            return all(requirement_met(child) for child in rule["requirements"])
        if kind == "any":
            return any(requirement_met(child) for child in rule["requirements"])
        if kind == "action_completed":
            return rule["action_id"] in completed
        if kind == "flag":
            token_id = rule["token_id"]
            return rule["value"] == initial["flags"].get(token_id, False) or rule["value"] in flags[token_id]
        if kind == "choice":
            token_id = rule["token_id"]
            return rule["option"] == initial_choices.get(token_id) or rule["option"] in choices[token_id]
        if kind == "counter":
            return counters[rule["token_id"]] >= rule["minimum"]
        if kind == "item":
            return inventory[rule["item_id"]] >= rule["quantity"]
        if kind == "restricted_items":
            item_ids = restrictions[rule["location_id"]]
            if rule["container"] == "bank_inventory":
                if rule["present"]:
                    return any(bank_inventory.get(item_id, 0) or (item_id in depositable and inventory[item_id])
                               for item_id in item_ids)
                return all(not bank_inventory.get(item_id, 0) or item_id in withdrawable for item_id in item_ids)
            if rule["present"]:
                return any(inventory[item_id] for item_id in item_ids)
            # Check that every initially carried item could leave the pack.
            # These removals may occur on separate paths.
            return all(not initial["inventory"].get(item_id, 0) or item_id in depositable or item_id in consumable
                       for item_id in item_ids)
        if kind == "policy":
            return profile["policies"].get(rule["name"]) == rule["value"]
        # Static catalog validation has checked skill bounds and combat maxima.
        return True

    def collect_effects(record: dict, remaining: int | float) -> None:
        consumable.update(item["item_id"] for item in record["consumes"])
        for effect in record["effects"]:
            kind = effect["kind"]
            if kind == "item":
                inventory[effect["item_id"]] += effect["quantity"] * remaining
            elif kind == "bank_transfer":
                item_ids = restrictions[effect["location_id"]]
                if effect["direction"] == "deposit":
                    depositable.update(item_ids)
                else:
                    for item_id in set(item_ids) - withdrawable:
                        inventory[item_id] += bank_inventory.get(item_id, 0)
                    withdrawable.update(item_ids)
            elif kind == "counter" and effect["delta"] > 0:
                token_id = effect["token_id"]
                maximum = limits[token_id]
                counters[token_id] = min(
                    counters[token_id] + effect["delta"] * remaining,
                    maximum if maximum is not None else inf,
                )
            elif kind == "flag":
                flags[effect["token_id"]].add(effect["value"])
            elif kind == "choose" and effect["token_id"] not in initial_choices:
                choices[effect["token_id"]].add(effect["option"])

    pending = []
    for action in catalog["actions"]:
        used = initial.get("action_counts", {}).get(action["id"], int(action["id"] in completed))
        remaining = action["repeat_limit"] - used
        if remaining > 0:
            pending.append((action, action["start_location_id"], action["end_location_id"], completed, remaining))
    for edge in catalog["travel_edges"]:
        used = initial.get("travel_counts", {}).get(edge["id"], 0)
        remaining = edge.get("repeat_limit", inf) - used
        if remaining > 0:
            pending.append((edge, edge["from_location_id"], edge["to_location_id"], used_edges, remaining))

    while pending:
        blocked = []
        for record, start, end, reached, remaining in pending:
            enough_items = all(inventory[item["item_id"]] >= item["quantity"] for item in record["consumes"])
            if start in locations and enough_items and requirement_met(record["requirements"]):
                reached.add(record["id"])
                locations.add(end)
                collect_effects(record, remaining)
            else:
                blocked.append((record, start, end, reached, remaining))
        if len(blocked) == len(pending):
            break
        pending = blocked

    return {
        "actions": sorted(row["id"] for row in catalog["actions"] if row["id"] not in completed),
        "travel_edges": sorted(row["id"] for row in catalog["travel_edges"] if row["id"] not in used_edges),
        "locations": sorted(row["id"] for row in catalog["locations"] if row["id"] not in locations),
    }
