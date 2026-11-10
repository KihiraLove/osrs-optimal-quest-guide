"""Static checks shared by the catalog, profile and solution entry points."""

from pathlib import Path
from typing import TYPE_CHECKING

from .errors import DataError

if TYPE_CHECKING:
    from .data import Contracts


def _fail(context: str, field: str, message: str) -> None:
    raise DataError(f"{context}: {field}: {message}")


class CatalogValidator:
    """Validate relationships between documents that have passed their schemas."""

    def __init__(
        self,
        catalog: dict,
        contracts: "Contracts",
        origins: dict[str, list[Path]] | None = None,
    ):
        self.catalog = catalog
        self.contracts = contracts
        self.tables: dict[str, dict[str, dict]] = {}
        self.contexts: dict[str, str] = {}
        for collection, records in catalog.items():
            if not isinstance(records, list):
                continue
            table = self.tables[collection] = {}
            for index, record in enumerate(records):
                record_id = record["id"]
                details = []
                if origins is not None:
                    details.append(str(origins[collection][index]))
                if "evidence" in record:
                    details.append("sources: " + ", ".join(record["evidence"]["source_ids"]))
                context = f"{collection} {record_id}"
                if details:
                    context += " (" + "; ".join(details) + ")"
                if record_id in self.contexts:
                    _fail(context, "id", f"Duplicate entity ID: {record_id}; first seen in {self.contexts[record_id]}")
                self.contexts[record_id] = context
                table[record_id] = record

    def _ref(self, table: str, value: str, context: str, field: str) -> dict:
        record = self.tables.get(table, {}).get(value)
        if record is None:
            _fail(context, field, f"unknown {table} ID {value!r}")
        return record

    def _token(self, token_id: str, kind: str, context: str, field: str) -> dict:
        token = self._ref("tokens", token_id, context, field)
        if token["kind"] != kind:
            _fail(context, field, f"{token_id!r} is a {token['kind']} token; expected {kind}")
        return token

    def _level_count(self, skill_id: str, context: str, field: str) -> int:
        return len(self._ref("skills", skill_id, context, field)["xp_thresholds_tenths"])

    def _choice(self, token_id: str, option: str | None, context: str, field: str) -> None:
        token = self._token(token_id, "choice", context, field)
        if option is not None and option not in token["options"]:
            _fail(context, field, f"unknown option {option!r} for choice token {token_id!r}")

    def _combat_maximum(self, formula: dict) -> int:
        context = self.contexts[formula["id"]]

        def sum_terms(terms: list[dict], field: str) -> int:
            total = 0
            for index, term in enumerate(terms):
                level = self._level_count(term["skill_id"], context, f"{field}.{index}.skill_id")
                total += term["weight"] * (level * term["level_multiplier"] // term["level_divisor"])
            return total

        base = sum_terms(formula["base_terms"], "base_terms")
        style = max(sum_terms(terms, f"styles.{index}") for index, terms in enumerate(formula["styles"]))
        return (base + style) // formula["divisor"]

    def _requirement(self, rule: dict, context: str, field: str, combat_maxima: dict[str, int]) -> None:
        kind = rule["kind"]
        if kind in ("all", "any"):
            for index, child in enumerate(rule["requirements"]):
                self._requirement(child, context, f"{field}.requirements.{index}", combat_maxima)
        elif kind == "skill":
            maximum = self._level_count(rule["skill_id"], context, f"{field}.skill_id")
            if rule["minimum_level"] > maximum:
                _fail(context, f"{field}.minimum_level", f"exceeds level table for {rule['skill_id']!r} ({maximum})")
        elif kind == "combat_level":
            formula_id = rule["formula_id"]
            self._ref("combat_formulas", formula_id, context, f"{field}.formula_id")
            if rule["minimum_level"] > combat_maxima[formula_id]:
                _fail(context, f"{field}.minimum_level", f"exceeds the maximum for formula {formula_id!r}")
        elif kind == "action_completed":
            self._ref("actions", rule["action_id"], context, f"{field}.action_id")
        elif kind == "item":
            self._ref("items", rule["item_id"], context, f"{field}.item_id")
        elif kind in ("flag", "counter", "cooldown_ready"):
            token_kind = "cooldown" if kind == "cooldown_ready" else kind
            token = self._token(rule["token_id"], token_kind, context, f"{field}.token_id")
            if kind == "counter" and token["maximum"] is not None and rule["minimum"] > token["maximum"]:
                _fail(context, f"{field}.minimum", f"exceeds the cap for {rule['token_id']!r}")
        elif kind == "choice":
            self._choice(rule["token_id"], rule["option"], context, f"{field}.option")
        elif kind == "policy":
            validator = self.contracts.policy_validators.get(rule["name"])
            if validator is None:
                _fail(context, f"{field}.name", f"unknown policy {rule['name']!r}")
            if not validator.is_valid(rule["value"]):
                _fail(context, f"{field}.value", f"invalid value for policy {rule['name']!r}")
        elif kind != "elapsed_time":
            _fail(context, f"{field}.kind", f"unsupported requirement kind {kind!r}")

    def _transition(self, record: dict, combat_maxima: dict[str, int], producers: dict[str, str]) -> None:
        context = self.contexts[record["id"]]
        self._requirement(record["requirements"], context, "requirements", combat_maxima)
        duration = record["duration"]
        if not duration["min_seconds"] <= duration["expected_seconds"] <= duration["max_seconds"]:
            _fail(context, "duration", "expected min_seconds <= expected_seconds <= max_seconds")
        consumed = set()
        for index, item in enumerate(record["consumes"]):
            item_id = item["item_id"]
            field = f"consumes.{index}.item_id"
            self._ref("items", item_id, context, field)
            if item_id in consumed:
                _fail(context, field, f"duplicate consumption of {item_id!r}; combine quantities")
            consumed.add(item_id)

        state_writes = set()
        for index, effect in enumerate(record["effects"]):
            field = f"effects.{index}"
            kind = effect["kind"]
            if kind in ("xp", "skill_boost"):
                self._ref("skills", effect["skill_id"], context, f"{field}.skill_id")
            elif kind == "item":
                self._ref("items", effect["item_id"], context, f"{field}.item_id")
            elif kind == "xp_reward":
                reward_id = effect["reward_id"]
                self._ref("xp_rewards", reward_id, context, f"{field}.reward_id")
                if reward_id in producers:
                    _fail(context, f"{field}.reward_id", f"duplicate producer for {reward_id!r}: {producers[reward_id]}")
                producers[reward_id] = context
            elif kind in ("flag", "counter", "start_cooldown"):
                token_kind = "cooldown" if kind == "start_cooldown" else kind
                token = self._token(effect["token_id"], token_kind, context, f"{field}.token_id")
                if kind == "counter" and token["maximum"] is not None and abs(effect["delta"]) > token["maximum"]:
                    _fail(context, f"{field}.delta", f"magnitude exceeds the cap for {effect['token_id']!r}")
            elif kind == "choose":
                self._choice(effect["token_id"], effect["option"], context, f"{field}.option")
            else:
                _fail(context, f"{field}.kind", f"unsupported effect kind {kind!r}")
            if kind in ("xp", "xp_reward") and record.get("repeat_limit") != 1:
                _fail(context, field, "XP and XP rewards require a one-time transition (repeat_limit: 1)")
            if kind in ("flag", "counter", "start_cooldown", "choose", "skill_boost"):
                target = effect["skill_id"] if kind == "skill_boost" else effect["token_id"]
                if target in state_writes:
                    _fail(context, field, f"multiple writes to {target!r} in one transition")
                state_writes.add(target)

    def _activities(self) -> None:
        activities = self.tables["activities"]
        for record_id, activity in activities.items():
            context = self.contexts[record_id]
            parent = activity["parent_activity_id"]
            if parent is not None:
                self._ref("activities", parent, context, "parent_activity_id")
            for index, action_id in enumerate(activity["completion_action_ids"]):
                field = f"completion_action_ids.{index}"
                action = self._ref("actions", action_id, context, field)
                if action["activity_id"] != record_id:
                    _fail(context, field, f"completion action {action_id!r} must belong to {record_id!r}")
                if action["repeat_limit"] != 1:
                    _fail(context, field, f"completion action {action_id!r} must be one-time")
        checked = set()
        for activity_id in activities:
            ancestors = set()
            while activity_id is not None and activity_id not in checked:
                if activity_id in ancestors:
                    _fail(self.contexts[activity_id], "parent_activity_id", "activity parent cycle")
                ancestors.add(activity_id)
                activity_id = activities[activity_id]["parent_activity_id"]
            checked.update(ancestors)

    def _reward(self, reward: dict) -> None:
        context = self.contexts[reward["id"]]
        eligible = reward["eligible_skills"]
        if eligible != "all":
            for index, skill_id in enumerate(eligible):
                self._ref("skills", skill_id, context, f"eligible_skills.{index}")
        level_counts = {skill_id: len(skill["xp_thresholds_tenths"]) for skill_id, skill in self.tables["skills"].items()}
        minimum = reward["minimum_level"]
        observed = self.tables["skills"] if eligible == "all" else eligible
        reachable = [level_counts[skill] for skill in observed if level_counts[skill] >= minimum]
        if not reachable:
            _fail(context, "minimum_level", "no eligible skill has this level in the catalog")
        if reward["distinct_skills"] and reward["selection_count"] > len(reachable):
            _fail(context, "selection_count", "exceeds the number of eligible skills at the minimum level")
        amount = reward["amount"]
        if amount["kind"] == "by_level":
            maximum = max(level_counts.values()) if reward["kind"] == "quest_lamp" else max(reachable)
            levels = set()
            for index, row in enumerate(amount["values"]):
                level = row["level"]
                if level in levels or level > maximum:
                    _fail(context, f"amount.values.{index}.level", f"duplicate or out-of-range level {level}")
                levels.add(level)
            for level in range(minimum, maximum + 1):
                if level not in levels:
                    _fail(context, "amount.values", f"missing XP amount for eligible level {level}")

    def validate_catalog(self) -> None:
        for collection, table in self.tables.items():
            if collection == "sources":
                continue
            for record_id, record in table.items():
                for index, source_id in enumerate(record["evidence"]["source_ids"]):
                    if source_id not in self.tables["sources"]:
                        _fail(self.contexts[record_id], f"evidence.source_ids.{index}", f"unknown provenance source {source_id!r}")
        for skill_id, skill in self.tables["skills"].items():
            thresholds = skill["xp_thresholds_tenths"]
            if thresholds[0] != 0:
                _fail(self.contexts[skill_id], "xp_thresholds_tenths.0", "level 1 must start at zero XP")
            for index, (previous, current) in enumerate(zip(thresholds, thresholds[1:]), start=1):
                if previous >= current:
                    _fail(self.contexts[skill_id], f"xp_thresholds_tenths.{index}", "thresholds must strictly increase")

        self._activities()
        maxima = {
            formula_id: self._combat_maximum(formula)
            for formula_id, formula in self.tables.get("combat_formulas", {}).items()
        }
        for reward in self.tables["xp_rewards"].values():
            self._reward(reward)

        producers: dict[str, str] = {}
        for record in self.tables["actions"].values():
            context = self.contexts[record["id"]]
            if record["activity_id"] is not None:
                self._ref("activities", record["activity_id"], context, "activity_id")
            for field in ("start_location_id", "end_location_id"):
                self._ref("locations", record[field], context, field)
            self._transition(record, maxima, producers)
        for record in self.tables["travel_edges"].values():
            context = self.contexts[record["id"]]
            for field in ("from_location_id", "to_location_id"):
                self._ref("locations", record[field], context, field)
            self._transition(record, maxima, producers)
        if self.catalog["status"] == "reviewed":
            for reward_id in self.tables["xp_rewards"]:
                if reward_id not in producers:
                    _fail(self.contexts[reward_id], "id", "reviewed reward requires a producer")

    def _reward_skill(self, reward: dict, skill: str, policies: dict, context: str, field: str) -> bool:
        maximum = self._level_count(skill, context, field)
        if maximum < reward["minimum_level"]:
            _fail(context, field, f"{skill!r} cannot reach the reward's minimum level")
        eligible = reward["eligible_skills"]
        override = eligible != "all" and skill not in eligible
        if override and not (reward["kind"] == "quest_lamp" and policies["quest_lamp_skill_policy"] == "any_skill"):
            _fail(context, field, f"{skill!r} is ineligible for reward {reward['id']!r}")
        return override

    def _state(self, state: dict, policies: dict, context: str, field: str) -> None:
        self._ref("locations", state["location_id"], context, f"{field}.location_id")
        for skill in state["xp_tenths"]:
            self._ref("skills", skill, context, f"{field}.xp_tenths.{skill}")
        missing = sorted(self.tables["skills"].keys() - state["xp_tenths"].keys())
        if missing:
            _fail(context, f"{field}.xp_tenths", "missing XP for " + ", ".join(missing))
        for index, action_id in enumerate(state["completed_action_ids"]):
            self._ref("actions", action_id, context, f"{field}.completed_action_ids.{index}")
        completed = set(state["completed_action_ids"])
        for action_id, count in state.get("action_counts", {}).items():
            path = f"{field}.action_counts.{action_id}"
            action = self._ref("actions", action_id, context, path)
            if action_id not in completed or count > action["repeat_limit"]:
                _fail(context, path, "count must belong to a completed action and respect its repeat_limit")
        for edge_id, count in state.get("travel_counts", {}).items():
            path = f"{field}.travel_counts.{edge_id}"
            edge = self._ref("travel_edges", edge_id, context, path)
            if "repeat_limit" not in edge or count > edge["repeat_limit"]:
                _fail(context, path, "count must belong to a limited travel edge and respect its repeat_limit")
        for item_id in state["inventory"]:
            self._ref("items", item_id, context, f"{field}.inventory.{item_id}")
        for token_id in state["flags"]:
            self._token(token_id, "flag", context, f"{field}.flags.{token_id}")
        for token_id, amount in state["counters"].items():
            path = f"{field}.counters.{token_id}"
            token = self._token(token_id, "counter", context, path)
            if token["maximum"] is not None and amount > token["maximum"]:
                _fail(context, path, f"value exceeds token cap of {token['maximum']}")
        for token_id, option in state.get("choices", {}).items():
            self._choice(token_id, option, context, f"{field}.choices.{token_id}")
        elapsed = state["modeled_elapsed_seconds"]
        for token_id, ready_at in state.get("cooldowns", {}).items():
            path = f"{field}.cooldowns.{token_id}"
            self._token(token_id, "cooldown", context, path)
            if ready_at <= elapsed:
                _fail(context, path, "ready time must be after modeled_elapsed_seconds")
        for skill_id, boost in state.get("active_boosts", {}).items():
            path = f"{field}.active_boosts.{skill_id}"
            self._ref("skills", skill_id, context, path)
            if not policies["allow_boosts"]:
                _fail(context, path, "active boost conflicts with the profile's allow_boosts policy")
            if boost["expires_at_seconds"] <= elapsed:
                _fail(context, f"{path}.expires_at_seconds", "expiry must be after modeled_elapsed_seconds")
        instances = set()
        for index, instance in enumerate(state["held_rewards"]):
            path = f"{field}.held_rewards.{index}"
            reward = self._ref("xp_rewards", instance["reward_id"], context, f"{path}.reward_id")
            if instance["instance_id"] in instances:
                _fail(context, f"{path}.instance_id", "duplicate held reward instance")
            instances.add(instance["instance_id"])
            if not reward["retainable"]:
                _fail(context, f"{path}.reward_id", "immediate-use reward cannot be held in a saved state")
            spent = reward["selection_count"] - instance["remaining_picks"]
            if spent < 0:
                _fail(context, f"{path}.remaining_picks", "exceeds reward selection_count")
            used = instance.get("used_skill_ids", [])
            if len(used) != (spent if reward["distinct_skills"] else 0):
                _fail(context, f"{path}.used_skill_ids", "must record exactly the spent distinct skill picks")
            for pick, skill in enumerate(used):
                self._reward_skill(reward, skill, policies, context, f"{path}.used_skill_ids.{pick}")

    def _dataset(self, document: dict, context: str, prefix: str = "") -> None:
        for field in ("dataset_id", "dataset_version"):
            if document[field] != self.catalog[field]:
                _fail(context, prefix + field, f"expected {self.catalog[field]!r}, found {document[field]!r}")

    def validate_profile(self, profile: dict, origin: Path | None = None) -> None:
        context = f"profile {profile['profile_id']}"
        if origin is not None:
            context += f" ({origin})"
        self._dataset(profile, context)
        if self.catalog["status"] == "synthetic" and profile["status"] != "synthetic":
            _fail(context, "status", "a synthetic catalog requires a synthetic profile")
        if profile["status"] == "reviewed" and self.catalog["status"] != "reviewed":
            _fail(context, "status", "a reviewed profile requires a reviewed catalog")
        for index, action_id in enumerate(profile["goal_action_ids"]):
            self._ref("actions", action_id, context, f"goal_action_ids.{index}")
        self._state(profile["initial_state"], profile["policies"], context, "initial_state")

    def validate_solution(self, solution: dict, profile: dict, origin: Path | None = None) -> None:
        context = f"solution {solution['solution_id']}"
        if origin is not None:
            context += f" ({origin})"
        inputs = solution["inputs"]
        self._dataset(inputs, context, "inputs.")
        if inputs["profile_id"] != profile["profile_id"]:
            _fail(context, "inputs.profile_id", f"expected {profile['profile_id']!r}")
        if solution["policies"] != profile["policies"]:
            _fail(context, "policies", "must match the supplied profile")
        if profile["status"] == "synthetic":
            if solution["solver"]["status"] != "example" or solution["verification"]["catalog_release_ready"]:
                _fail(context, "solver.status / verification.catalog_release_ready", "synthetic inputs require an example solution")
        for skill in solution["manual_training_xp_tenths_by_skill"]:
            self._ref("skills", skill, context, f"manual_training_xp_tenths_by_skill.{skill}")
        self._state(solution["final_state"], solution["policies"], context, "final_state")
        steps = set()
        for index, step in enumerate(solution["steps"]):
            field = f"steps.{index}"
            if step["step_id"] in steps:
                _fail(context, f"{field}.step_id", "duplicate solution step ID")
            steps.add(step["step_id"])
            kind = step["kind"]
            if kind == "action":
                self._ref("actions", step["action_id"], context, f"{field}.action_id")
            elif kind == "travel":
                self._ref("travel_edges", step["edge_id"], context, f"{field}.edge_id")
            elif kind == "reward_use":
                reward = self._ref("xp_rewards", step["reward_id"], context, f"{field}.reward_id")
                override = self._reward_skill(reward, step["skill_id"], solution["policies"], context, f"{field}.skill_id")
                if override != step["overrides_observed_skill_restriction"]:
                    _fail(context, f"{field}.overrides_observed_skill_restriction", "must match observed eligibility and profile policy")
            elif kind == "training":
                self._ref("skills", step["skill_id"], context, f"{field}.skill_id")
                self._ref("locations", step["resume_location_id"], context, f"{field}.resume_location_id")
                for gate_index, gate_id in enumerate(step["required_by"]):
                    if not any(gate_id in self.tables[table] for table in ("actions", "travel_edges", "xp_rewards")):
                        _fail(context, f"{field}.required_by.{gate_index}", f"unknown action, travel edge or reward ID {gate_id!r}")
            elif kind != "wait":
                _fail(context, f"{field}.kind", f"unsupported solution step kind {kind!r}")
