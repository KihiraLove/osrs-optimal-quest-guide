"""Check XP rewards and progression gates in an ordered solution."""

from bisect import bisect_right
from collections import Counter
from dataclasses import dataclass, field

from .errors import DataError


@dataclass
class HeldReward:
    reward_id: str
    remaining_picks: int
    used_skills: set[str] = field(default_factory=set)


def _inventory(entries: list[dict]) -> dict[str, HeldReward]:
    return {
        entry["instance_id"]: HeldReward(
            entry["reward_id"], entry["remaining_picks"], set(entry.get("used_skill_ids", ()))
        )
        for entry in entries
    }


class RewardTrace:
    """Track XP, reward instances and progression state in route order."""

    def __init__(self, skills: dict, rewards: dict, tokens: dict, initial_state: dict, context: str):
        self.thresholds = {key: skill["xp_thresholds_tenths"] for key, skill in skills.items()}
        self.rewards = rewards
        self.amounts_by_level = {
            key: {row["level"]: row["xp_tenths"] for row in reward["amount"]["values"]}
            for key, reward in rewards.items()
            if reward["amount"]["kind"] == "by_level"
        }
        self.xp = initial_state["xp_tenths"].copy()
        self.held = _inventory(initial_state["held_rewards"])
        self.issued = set(self.held)
        self.awarded_rewards = {instance.reward_id for instance in self.held.values()}
        self.pending: set[str] = set()
        self.completed = set(initial_state["completed_action_ids"])
        self.used_transitions = self.completed | initial_state.get("travel_counts", {}).keys()
        self.counters = Counter(initial_state["counters"])
        self.flags = initial_state["flags"].copy()
        self.tokens = tokens
        self.context = context

    def _fail(self, field_name: str, message: str) -> None:
        raise DataError(f"{self.context}: {field_name}: {message}")

    def before_step(self, step: dict, path: str) -> None:
        if self.pending and (step["kind"] != "reward_use" or step["instance_id"] not in self.pending):
            self._fail(path, f"resolve immediate reward before proceeding: {min(self.pending)!r}")

    def _progress_gates_met(self, requirement: dict) -> bool:
        kind = requirement["kind"]
        if kind == "action_completed":
            return requirement["action_id"] in self.completed
        if kind == "counter":
            return self.counters[requirement["token_id"]] >= requirement["minimum"]
        if kind == "flag":
            return self.flags.get(requirement["token_id"], False) == requirement["value"]
        if kind == "all":
            return all(self._progress_gates_met(child) for child in requirement["requirements"])
        if kind == "any":
            return any(self._progress_gates_met(child) for child in requirement["requirements"])
        # Other gates are evaluated by full replay.
        return True

    def award(self, transition: dict, path: str) -> None:
        transition_id = transition["id"]
        effects = transition["effects"]
        if transition.get("repeat_limit") == 1 and transition_id in self.used_transitions:
            producer = "XP producer" if any(effect["kind"] in ("xp", "xp_reward") for effect in effects) else "one-time transition"
            self._fail(path, f"{producer} {transition_id!r} already used")
        if not self._progress_gates_met(transition["requirements"]):
            if transition.get("kind") == "reward_claim":
                self._fail(path, "reward claim precedes a required completed action, flag or counter threshold")
            self._fail(path, "required completed action, flag or counter threshold has not been reached")
        self.used_transitions.add(transition_id)
        if "kind" in transition:
            self.completed.add(transition_id)
        for effect in effects:
            if effect["kind"] == "xp":
                self.xp[effect["skill_id"]] += effect["xp_tenths"]
            elif effect["kind"] == "flag":
                self.flags[effect["token_id"]] = effect["value"]
            elif effect["kind"] == "counter":
                token_id = effect["token_id"]
                self.counters[token_id] += effect["delta"]
                maximum = self.tokens[token_id]["maximum"]
                if self.counters[token_id] < 0 or (maximum is not None and self.counters[token_id] > maximum):
                    self._fail(path, f"counter {token_id!r} moved outside its bounds")
            elif effect["kind"] == "xp_reward":
                self._mint(effect, path)

    def _mint(self, effect: dict, path: str) -> None:
        reward_id = effect["reward_id"]
        if reward_id in self.awarded_rewards:
            self._fail(path, f"reward {reward_id!r} was already awarded")
        self.awarded_rewards.add(reward_id)
        reward = self.rewards[reward_id]
        for ordinal in range(1, effect["quantity"] + 1):
            instance_id = f"{reward_id}.instance.{ordinal}"
            if instance_id in self.issued:
                self._fail(path, f"reward instance {instance_id!r} already issued")
            self.issued.add(instance_id)
            self.held[instance_id] = HeldReward(reward_id, reward["selection_count"])
            if not reward["retainable"]:
                self.pending.add(instance_id)

    def train(self, step: dict, path: str) -> None:
        skill = step["skill_id"]
        before = self.xp[skill]
        if step["before_xp_tenths"] != before:
            self._fail(f"{path}.before_xp_tenths", f"expected {before} from preceding XP steps")
        after = before + step["gain_xp_tenths"]
        if step["after_xp_tenths"] != after:
            self._fail(f"{path}.after_xp_tenths", f"expected {after} after the stated XP gain")
        self.xp[skill] = after

    def spend(self, step: dict, path: str) -> None:
        instance_id = step["instance_id"]
        instance = self.held.get(instance_id)
        if instance is None:
            self._fail(f"{path}.instance_id", f"reward instance {instance_id!r} is unavailable")
        if step["reward_id"] != instance.reward_id:
            self._fail(f"{path}.reward_id", f"instance {instance_id!r} belongs to {instance.reward_id!r}")
        reward = self.rewards[instance.reward_id]
        skill = step["skill_id"]
        level = bisect_right(self.thresholds[skill], self.xp[skill])
        if level < reward["minimum_level"]:
            self._fail(f"{path}.skill_id", f"{skill!r} requires base level {reward['minimum_level']}, has {level}")
        if reward["distinct_skills"] and skill in instance.used_skills:
            self._fail(f"{path}.skill_id", f"{skill!r} was already selected for this reward")
        amount = reward["amount"]
        expected = amount["xp_tenths"] if amount["kind"] == "fixed" else self.amounts_by_level[instance.reward_id][level]
        if step["gain_xp_tenths"] != expected:
            self._fail(f"{path}.gain_xp_tenths", f"expected a whole pick of {expected} XP tenths")
        self.xp[skill] += expected
        instance.remaining_picks -= 1
        if reward["distinct_skills"]:
            instance.used_skills.add(skill)
        if instance.remaining_picks == 0:
            del self.held[instance_id]
            self.pending.discard(instance_id)

    def finish(self, final_state: dict) -> None:
        if self.pending:
            self._fail("final_state.held_rewards", f"unresolved immediate reward {min(self.pending)!r}")
        if self.held != _inventory(final_state["held_rewards"]):
            self._fail("final_state.held_rewards", "does not match the remaining reward instances and picks")
        if self.counters != Counter(final_state["counters"]):
            self._fail("final_state.counters", "does not match the starting counters and ordered route effects")
