"""Check XP reward ownership and spending in an ordered solution."""

from bisect import bisect_right
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
    """Track XP and reward instances. Full action feasibility belongs to route replay."""

    def __init__(self, skills: dict, rewards: dict, initial_state: dict, context: str):
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
        self.used_producers = self.completed | initial_state.get("travel_counts", {}).keys()
        self.context = context

    def _fail(self, field_name: str, message: str) -> None:
        raise DataError(f"{self.context}: {field_name}: {message}")

    def before_step(self, step: dict, path: str) -> None:
        if self.pending and (step["kind"] != "reward_use" or step["instance_id"] not in self.pending):
            self._fail(path, f"resolve immediate reward before proceeding: {min(self.pending)!r}")

    def _completion_gates_met(self, requirement: dict) -> bool:
        kind = requirement["kind"]
        if kind == "action_completed":
            return requirement["action_id"] in self.completed
        if kind == "all":
            return all(self._completion_gates_met(child) for child in requirement["requirements"])
        if kind == "any":
            return any(self._completion_gates_met(child) for child in requirement["requirements"])
        # Other gates are evaluated by full replay.
        return True

    def award(self, transition: dict, path: str) -> None:
        if transition.get("kind") == "reward_claim" and not self._completion_gates_met(transition["requirements"]):
            self._fail(path, "reward claim precedes a required completed action")
        if "kind" in transition:
            self.completed.add(transition["id"])
        effects = [effect for effect in transition["effects"] if effect["kind"] in ("xp", "xp_reward")]
        if not effects:
            return
        if transition["id"] in self.used_producers:
            self._fail(path, f"XP producer {transition['id']!r} already used")
        self.used_producers.add(transition["id"])
        for effect in effects:
            if effect["kind"] == "xp":
                self.xp[effect["skill_id"]] += effect["xp_tenths"]
                continue
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
