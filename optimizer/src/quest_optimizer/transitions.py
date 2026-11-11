"""Exact state transitions for local quest planning and replay."""

from bisect import bisect_right
from collections import Counter
from copy import copy, deepcopy

from .reward_trace import RewardTrace


class RouteState(RewardTrace):
    def __init__(self, tables: dict, policies: dict, initial: dict, context: str = "route"):
        super().__init__(
            tables["skills"], tables["xp_rewards"], tables["tokens"], initial, context, locations=tables["locations"],
        )
        self.tables = tables
        self.policies = policies
        self.location = initial["location_id"]
        self.elapsed = initial["modeled_elapsed_seconds"]
        self.boosts = initial.get("active_boosts", {}).copy()
        self.cooldowns = initial.get("cooldowns", {}).copy()
        self.choices = initial.get("choices", {}).copy()
        self.action_counts = Counter({action_id: 1 for action_id in self.completed})
        self.action_counts.update({
            action_id: count - 1 for action_id, count in initial.get("action_counts", {}).items()
        })
        self.travel_counts = Counter(initial.get("travel_counts", {}))

    def level(self, skill: str) -> int:
        return bisect_right(self.thresholds[skill], self.xp[skill])

    def _combat_level(self, formula: dict) -> int:
        def total(terms):
            return sum(
                term["weight"] * (
                    self.level(term["skill_id"]) * term["level_multiplier"] // term["level_divisor"]
                )
                for term in terms
            )

        return (total(formula["base_terms"]) + max(map(total, formula["styles"]))) // formula["divisor"]

    def _progress_gates_met(self, requirement: dict) -> bool:
        kind = requirement["kind"]
        if kind == "skill":
            skill = requirement["skill_id"]
            boost = self.boosts.get(skill)
            bonus = boost["bonus_levels"] if requirement["boostable"] and boost else 0
            return self.level(skill) + bonus >= requirement["minimum_level"]
        if kind == "combat_level":
            formula = self.tables["combat_formulas"][requirement["formula_id"]]
            return self._combat_level(formula) >= requirement["minimum_level"]
        if kind == "policy":
            return self.policies.get(requirement["name"]) == requirement["value"]
        if kind == "elapsed_time":
            return self.elapsed >= requirement["minimum_seconds"]
        if kind == "cooldown_ready":
            return requirement["token_id"] not in self.cooldowns
        if kind == "choice":
            return self.choices.get(requirement["token_id"]) == requirement["option"]
        return super()._progress_gates_met(requirement)

    def _advance(self, seconds: int) -> None:
        self.elapsed += seconds
        self.boosts = {
            skill: boost for skill, boost in self.boosts.items() if boost["expires_at_seconds"] > self.elapsed
        }
        self.cooldowns = {token: ready for token, ready in self.cooldowns.items() if ready > self.elapsed}

    def _transition(
        self, table: str, transition_id: str, seconds: int, path: str, *, planned_outcome: dict | None = None,
    ) -> None:
        record = self.tables[table].get(transition_id)
        if record is None:
            self._fail(path, f"unknown {table} ID {transition_id!r}")
        is_action = table == "actions"
        start = record["start_location_id"] if is_action else record["from_location_id"]
        end = record["end_location_id"] if is_action else record["to_location_id"]
        if self.location != start:
            self._fail(path, f"{transition_id!r} starts at {start!r}, currently at {self.location!r}")
        if seconds != record["duration"]["expected_seconds"]:
            self._fail(f"{path}.modeled_seconds", f"expected {record['duration']['expected_seconds']} from the catalog")
        counts = self.action_counts if is_action else self.travel_counts
        limit = record.get("repeat_limit")
        if limit is not None and counts[transition_id] >= limit:
            self._fail(path, f"{transition_id!r} has reached its repeat limit of {limit}")
        for effect in record["effects"]:
            if effect["kind"] == "choose" and effect["token_id"] in self.choices:
                self._fail(path, f"choice {effect['token_id']!r} is already set")
            if effect["kind"] == "skill_boost" and not self.policies["allow_boosts"]:
                self._fail(path, "skill boosts are disabled by the profile")
        # Requirements refer to the starting state. Timed effects start at arrival.
        self.award(record, path, planned_outcome=planned_outcome)
        self.location = end
        if limit is not None:
            counts[transition_id] += 1
        self._advance(seconds)
        for effect in record["effects"]:
            kind = effect["kind"]
            if kind == "choose":
                self.choices[effect["token_id"]] = effect["option"]
            elif kind == "skill_boost":
                self.boosts[effect["skill_id"]] = {
                    "bonus_levels": effect["bonus_levels"],
                    "expires_at_seconds": self.elapsed + effect["duration_seconds"],
                }
            elif kind == "start_cooldown":
                self.cooldowns[effect["token_id"]] = self.elapsed + effect["duration_seconds"]

    def reward_override(self, reward: dict, skill: str, path: str) -> bool:
        if skill not in self.xp:
            self._fail(f"{path}.skill_id", f"unknown skill {skill!r}")
        eligible = reward["eligible_skills"]
        override = eligible != "all" and skill not in eligible
        if override and (reward["kind"] != "quest_lamp" or self.policies["quest_lamp_skill_policy"] != "any_skill"):
            self._fail(f"{path}.skill_id", f"{skill!r} is ineligible for {reward['id']!r}")
        return override

    def _apply(self, step: dict, path: str) -> None:
        self.before_step(step, path)
        kind = step["kind"]
        if kind == "action":
            self._transition(
                "actions", step["action_id"], step["modeled_seconds"], path, planned_outcome=step.get("planned_outcome"),
            )
        elif kind == "travel":
            self._transition("travel_edges", step["edge_id"], step["modeled_seconds"], path)
        elif kind == "reward_use":
            reward = self.rewards.get(step["reward_id"])
            if reward is None:
                self._fail(f"{path}.reward_id", f"unknown reward {step['reward_id']!r}")
            override = self.reward_override(reward, step["skill_id"], path)
            if override != step["overrides_observed_skill_restriction"]:
                self._fail(f"{path}.overrides_observed_skill_restriction", f"expected {override} under the profile policy")
            self.spend(step, path)
        elif kind == "training":
            if step["skill_id"] not in self.xp:
                self._fail(f"{path}.skill_id", f"unknown skill {step['skill_id']!r}")
            if step["resume_location_id"] != self.location:
                self._fail(f"{path}.resume_location_id", f"expected current waypoint {self.location!r}")
            for gate in step["required_by"]:
                if not any(gate in self.tables[table] for table in ("actions", "travel_edges", "xp_rewards", "skills")):
                    self._fail(f"{path}.required_by", f"unknown action, travel edge, reward or skill {gate!r}")
            if step["gain_xp_tenths"] <= 0:
                self._fail(f"{path}.gain_xp_tenths", "training must add positive XP")
            self.train(step, path)
        elif kind == "wait":
            if step["modeled_seconds"] <= 0:
                self._fail(f"{path}.modeled_seconds", "waiting must advance the clock")
            self._advance(step["modeled_seconds"])
        else:
            self._fail(f"{path}.kind", f"unknown step kind {kind!r}")

    def apply(self, step: dict, path: str = "step") -> "RouteState":
        """Apply a step to a copy so a failed transition leaves its input intact."""
        result = copy(self)
        for field in (
            "xp", "issued", "awarded_rewards", "pending", "completed", "used_transitions",
            "counters", "inventory", "bank_inventory", "flags", "boosts", "cooldowns", "choices",
            "action_counts", "travel_counts",
        ):
            setattr(result, field, getattr(self, field).copy())
        result.held = deepcopy(self.held)
        result._apply(step, path)
        return result

    def snapshot(self) -> dict:
        held = []
        for instance_id, reward in sorted(self.held.items()):
            entry = {
                "instance_id": instance_id, "reward_id": reward.reward_id, "remaining_picks": reward.remaining_picks,
            }
            if reward.used_skills:
                entry["used_skill_ids"] = sorted(reward.used_skills)
            held.append(entry)
        state = {
            "location_id": self.location,
            "xp_tenths": self.xp.copy(),
            "completed_action_ids": sorted(self.completed),
            "flags": {key: value for key, value in self.flags.items() if value},
            "counters": {key: value for key, value in self.counters.items() if value},
            "inventory": {key: value for key, value in self.inventory.items() if value},
            "held_rewards": held,
            "modeled_elapsed_seconds": self.elapsed,
        }
        optional = {
            "bank_inventory": {key: value for key, value in self.bank_inventory.items() if value},
            "active_boosts": deepcopy(self.boosts),
            "cooldowns": self.cooldowns.copy(),
            "choices": self.choices.copy(),
            "action_counts": {key: count for key, count in self.action_counts.items() if count > 1},
            "travel_counts": dict(self.travel_counts),
        }
        state.update({key: value for key, value in optional.items() if value})
        return state
