"""Calculate the profile's early skill targets and counted training XP."""


def priority_xp(profile: dict, skills: dict) -> dict[str, int]:
    return {
        skill: skills[skill]["xp_thresholds_tenths"][level - 1]
        for skill, level in profile.get("priority_skill_levels", {}).items()
    }


def outstanding(xp: dict, targets: dict[str, int]) -> dict[str, int]:
    return {skill: target for skill, target in targets.items() if xp[skill] < target}


def counted_training(step: dict, targets: dict[str, int]) -> int:
    if step["kind"] != "training":
        return 0
    floor = targets.get(step["skill_id"], 0)
    return max(0, step["after_xp_tenths"] - floor) - max(0, step["before_xp_tenths"] - floor)
