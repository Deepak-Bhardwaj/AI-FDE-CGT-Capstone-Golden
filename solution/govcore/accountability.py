"""Who is accountable for each consequential action, derived from the code that enforces it.

Section 19 carries a RACI table. It is prose, and prose cannot be wrong in a way that
fails a build. This module reconstructs the same map from the three registries that
actually decide - the action classes, the role definitions and the staff directory - and
reports where authority is unowned, unreachable or impossible to exercise.

The findings it can raise:

    UNOWNED         a consequential action with no accountable authority named
    UNREACHABLE     an action nobody in the role model can perform
    UNDECLARED      an action a role holds that the authority model has never heard of
    ORPHAN_ACTION   an action classified but held by no role, no agent and no caller
    NO_APPROVER     an accountable authority with nobody in the directory holding it
    NO_SECOND       dual control required, but fewer than two qualified people exist
    AGENT_HOLDS_D   an agent declared as holding a consequential action
    SOD_CONFLICT    one person holding two duties that must be held apart
    DUAL_CONTROL_DEFEATED
                    two approver accounts that resolve to the same person

Two permission systems overlap here and both are consulted: a role's declared actions, and
an agent tool contract's allowed callers. An action reachable only through an agent is
still reachable, and reporting otherwise would be false alarm.

An unreachable action is not automatically a defect. Refusing to act is the correct
behaviour when nobody is qualified - but it should be a stated position, not something a
team discovers at the moment they need it.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import agents, directory, security
from .authority import ACTION_CLASSES, REQUIRED_ROLE
from .types import ActionClass

UNOWNED = "UNOWNED"
UNREACHABLE = "UNREACHABLE"
UNDECLARED = "UNDECLARED"
ORPHAN_ACTION = "ORPHAN_ACTION"
NO_APPROVER = "NO_APPROVER"
NO_SECOND = "NO_SECOND"
AGENT_HOLDS_D = "AGENT_HOLDS_D"
SOD_CONFLICT = "SOD_CONFLICT"
DUAL_CONTROL_DEFEATED = "DUAL_CONTROL_DEFEATED"

#: Duties one person must not hold at once. Two accounts are not two people, and the system
#: enforces distinct identities at countersignature, not distinct humans.
SEGREGATED: tuple[tuple[str, str, str], ...] = (
    ("auditor", "quality_reviewer",
     "An auditor who is also a qualified person offers assurance about their own release "
     "decisions."),
    ("auditor", "identity_adjudicator",
     "An auditor who also adjudicates identity reviews their own adjudications."),
    ("auditor", "ops_coordinator",
     "An auditor who also runs operations audits their own exceptions."),
    ("auditor", "manufacturing_planner",
     "An auditor who also plans capacity audits their own schedule decisions."),
    ("auditor", "logistics_coordinator",
     "An auditor who also runs logistics audits their own custody decisions."),
    ("manufacturing_planner", "quality_reviewer",
     "Manufacturing proposes and Quality disposes. One person holding both is maker and "
     "checker at the same time."),
)

#: Roles that are not people. They may hold advisory actions; they can never be an approver.
AUTOMATED_ROLES = frozenset({"ai_service"})

#: Authorities this deployment deliberately does not staff. Naming them here is the
#: difference between a considered refusal and an oversight nobody noticed.
UNSTAFFED_BY_DESIGN: dict[str, str] = {
    "CLINICAL_AUTHORITY": "Clinical decisions belong to the treating clinician at the "
                          "treatment centre, who is not a user of this platform. The actions "
                          "requiring it are therefore unreachable here by design, and the "
                          "platform must refuse them rather than approximate them.",
}


@dataclass
class ActionOwner:
    action: str
    action_class: str
    authority: str | None
    roles: list[str] = field(default_factory=list)
    agent_callers: list[str] = field(default_factory=list)
    people: list[str] = field(default_factory=list)
    dual_control: bool = False
    unstaffed_reason: str | None = None

    @property
    def reachable(self) -> bool:
        return bool(self.people)

    @property
    def held_by_anything(self) -> bool:
        return bool(self.roles or self.agent_callers)

    def as_dict(self) -> dict:
        return {"action": self.action, "action_class": self.action_class,
                "authority": self.authority, "roles": self.roles,
                "agent_callers": self.agent_callers, "people": self.people,
                "dual_control": self.dual_control, "reachable": self.reachable,
                "unstaffed_reason": self.unstaffed_reason}


@dataclass
class Finding:
    kind: str
    subject: str
    detail: str

    def as_dict(self) -> dict:
        return {"kind": self.kind, "subject": self.subject, "detail": self.detail}


def _people_by_role() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for entry in directory.directory_listing():
        out.setdefault(entry["role"], []).append(entry["username"])
    return out


def owners() -> list[ActionOwner]:
    """Every declared action, with the roles and named people who can actually perform it."""
    staff = _people_by_role()
    by_agent_action: dict[str, set[str]] = {}
    for agent in agents.REGISTRY.values():
        by_agent_action.setdefault(agent.action, set()).update(agent.contract.allowed_callers)

    result: list[ActionOwner] = []
    for action, klass in ACTION_CLASSES.items():
        authority = REQUIRED_ROLE.get(action)
        roles = sorted(name for name, role in security.ROLES.items()
                       if action in role.actions)
        callers = sorted(by_agent_action.get(action, set()))
        human = {r for r in set(roles) | set(callers) if r not in AUTOMATED_ROLES}
        people = sorted({u for r in human for u in staff.get(r, [])})
        result.append(ActionOwner(
            action, klass.value, authority, roles, callers, people,
            dual_control=klass is ActionClass.D_CONSEQUENTIAL,
            unstaffed_reason=UNSTAFFED_BY_DESIGN.get(authority or "")))
    return sorted(result, key=lambda o: (o.action_class, o.action))


def findings() -> list[Finding]:
    """Where the authority model leaves a gap, in the words a governance reviewer needs."""
    out: list[Finding] = []
    for owner in owners():
        consequential = owner.action_class == ActionClass.D_CONSEQUENTIAL.value
        if consequential and not owner.authority:
            out.append(Finding(UNOWNED, owner.action,
                               "A consequential action with no accountable authority named. "
                               "Nobody can be asked to answer for it."))
        if not owner.held_by_anything and not owner.unstaffed_reason:
            out.append(Finding(ORPHAN_ACTION, owner.action,
                               "Classified in the authority model but held by no role, offered "
                               "by no agent and invoked nowhere. Dead authority is a liability: "
                               "it reads as a capability the system has."))
        elif not owner.people and not owner.unstaffed_reason:
            out.append(Finding(UNREACHABLE, owner.action,
                               "Only automated callers hold this action, so no person can "
                               "perform it."))
        if owner.authority and not owner.people and not owner.unstaffed_reason:
            out.append(Finding(NO_APPROVER, owner.action,
                               f"{owner.authority} is named accountable but no one in the "
                               f"directory holds a role carrying this action."))
        if consequential and owner.people and len(owner.people) < 2:
            out.append(Finding(NO_SECOND, owner.action,
                               f"Dual control is required but only {owner.people[0]} can "
                               f"perform it, so a second approver cannot exist. The action "
                               f"will refuse at countersignature rather than proceed."))

    declared = set(ACTION_CLASSES)
    for name, role in security.ROLES.items():
        for action in sorted(role.actions - declared):
            out.append(Finding(UNDECLARED, f"{name}:{action}",
                               "A role holds an action the authority model does not classify. "
                               "It fails closed to Class D, which contradicts the role."))

    for agent in agents.REGISTRY.values():
        if agent.action_class is ActionClass.D_CONSEQUENTIAL:
            out.append(Finding(AGENT_HOLDS_D, agent.agent_id,
                               "An agent is declared as holding a consequential action."))
    return out + segregation()


def _accounts_by_person() -> dict[str, list[dict]]:
    """Accounts grouped by the human behind them.

    Display name is a weak proxy for a person and is stated as such in the report. It is the
    only one this directory offers, and a weak check applied is worth more than a strong one
    deferred until an identity provider arrives.
    """
    out: dict[str, list[dict]] = {}
    for entry in directory.directory_listing():
        out.setdefault(entry["display_name"].strip().casefold(), []).append(entry)
    return out


def segregation() -> list[Finding]:
    """Duties that must be held apart, and approvals that only look like two people."""
    out: list[Finding] = []
    for accounts in _accounts_by_person().values():
        if len(accounts) < 2:
            continue
        held = {a["role"] for a in accounts}
        name = accounts[0]["display_name"]
        usernames = ", ".join(sorted(a["username"] for a in accounts))
        for first, second, reason in SEGREGATED:
            if {first, second} <= held:
                out.append(Finding(
                    SOD_CONFLICT, name,
                    f"{name} holds both {first} and {second} ({usernames}). {reason} "
                    f"Separate accounts are not separate people."))

    people_of = {a["username"]: a["display_name"].strip().casefold()
                 for accounts in _accounts_by_person().values() for a in accounts}
    for owner in owners():
        if owner.action_class != ActionClass.D_CONSEQUENTIAL.value or len(owner.people) < 2:
            continue
        humans = {people_of[u] for u in owner.people}
        if len(humans) < 2:
            out.append(Finding(
                DUAL_CONTROL_DEFEATED, owner.action,
                f"{owner.action} has {len(owner.people)} qualified accounts but they resolve "
                f"to one person. Countersignature would compare identities, pass, and record "
                f"a two-person approval that one person made."))
    return out


def map_() -> dict:
    all_owners = owners()
    issues = findings()
    consequential = [o for o in all_owners
                     if o.action_class == ActionClass.D_CONSEQUENTIAL.value]
    unreachable = [o for o in consequential if not o.reachable]
    return {
        "actions": len(all_owners),
        "consequential_actions": len(consequential),
        "owners": [o.as_dict() for o in all_owners],
        "authorities": sorted({o.authority for o in all_owners if o.authority}),
        "unstaffed_by_design": UNSTAFFED_BY_DESIGN,
        "unreachable_consequential": [o.action for o in unreachable],
        "findings": [f.as_dict() for f in issues],
        "complete": not issues,
        "meaning": ("Every declared action has a role that can perform it and, where it is "
                    "consequential, an accountable authority and two qualified approvers."
                    if not issues else
                    f"{len(issues)} gap(s) in the accountability model: "
                    + ", ".join(sorted({f.kind for f in issues}))),
        "caveat": "Derived from the action classes, the role model and the staff directory. "
                  "A name here means someone is qualified in the system, not that they have "
                  "been told they are accountable. That conversation is not a code artefact. "
                  "Two accounts are judged to be one person by display name, which is a weak "
                  "proxy; an identity provider would settle it properly.",
    }


# --------------------------------------------------------------------------- #
# Accountability model under change control (govcore.drift)
# --------------------------------------------------------------------------- #

MODEL_VERSION = "accountability/1.0"

#: The quietest way to lose an approver is to stop counting them. Widening the automated-role
#: set, adding an authority to the by-design allowlist or softening the reachability rule all
#: turn a gap into silence without touching a gate, so all three are sealed.
SEALED: dict[str, dict] = {
    "ACC-OWNERS": {"statement": "Each action's owners are derived from the role model and the "
                                "agent contracts, and only people count towards an approval.",
                   "fn": owners,
                   "constants": {"AUTOMATED_ROLES": tuple(sorted(AUTOMATED_ROLES)),
                                 "UNSTAFFED_BY_DESIGN":
                                     tuple(sorted(UNSTAFFED_BY_DESIGN.items()))}},
    "ACC-FINDINGS": {"statement": "Unowned, unreachable, undeclared, orphaned and unstaffable "
                                  "authority are each reported rather than tolerated.",
                     "fn": findings},
    "ACC-PEOPLE": {"statement": "Only a directory entry makes someone a possible approver.",
                   "fn": _people_by_role},
    "ACC-SEGREGATION": {"statement": "Duties that must be held apart are held apart, and two "
                                     "approver accounts belonging to one person are not two "
                                     "approvers.",
                        "fn": segregation,
                        "constants": {"SEGREGATED": tuple(sorted(
                            (a, b) for a, b, _ in SEGREGATED))}},
    "ACC-REACHABLE": {"statement": "An action is reachable only if a person can perform it.",
                      "fn": ActionOwner.reachable.fget},
}


def _main() -> int:
    m = map_()
    for owner in m["owners"]:
        if owner["action_class"] != ActionClass.D_CONSEQUENTIAL.value:
            continue
        who = ", ".join(owner["people"]) or "nobody"
        print(f"[{owner['action_class']}] {owner['action']:<24} "
              f"{str(owner['authority']):<22} {who}")
    for f in m["findings"]:
        print(f"\n[{f['kind']}] {f['subject']}\n    {f['detail']}")
    print(f"\n{m['meaning']}")
    return 0 if m["complete"] else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
