from __future__ import annotations

from .logging import log
from .color import Color

class Labeled:
    def __init__(self, label: str, obj: any) -> None:
        self.label: str = label
        self.obj: any = obj
    def __repr__(self) -> str:
        return repr(self.obj)
    
MATCH_LABELS: str = "(self.label == obj.label) if hasattr(obj, 'label') else False"
MATCH_LABELS_ALLOW_UNLABELED: str = "(self.label == obj.label) if hasattr(obj, 'label') else True"

class Group:
    def __init__(self, label: str, ruleset: list[str], debug_group: bool = False) -> None:
        self.label: str = label
        self.debug_group: bool = debug_group
        self.members: list = []
        self.ruleset: list[str] = ruleset
        self.latestlog: log | None = None
        if self.debug_group:
            log(f"new debug group recorded: {label=}").print()
    def add_member(self, obj: any, label: str | None = None) -> None:
        if label is not None:
            obj = Labeled(label, obj)
        add_member_log: log = log(f"{Color.blue}attempting to add new member to group '{self.label}': {obj} repr={repr(obj)} label='{obj.label if hasattr(obj, 'label') else 'null'}'") if self.debug_group else None
        if self.member_added(obj.obj if hasattr(obj, "obj") else obj, add_member_log):
            self.members.append(obj)
            if self.debug_group:
                add_member_log.sublog(f"{Color.light_green}member added successfully!")
                add_member_log.print()
        elif self.debug_group:
            add_member_log.sublog(f"{Color.red}member addition cancelled")
            add_member_log.print()
    def member_added(self, obj: any, add_member_log: log | None = None) -> bool:
        if self.debug_group and add_member_log:
            add_member_log.sublog("received request to add new member (group.member_added)")
        for i, rule in enumerate(self.ruleset, start=1):
            if self.debug_group and add_member_log:
                rule_log: log = add_member_log.sublog(f"evaluating rule #{i}: '{rule}'")
            if not eval(rule, globals() | locals() | {"obj": obj}):
                if self.debug_group and add_member_log:
                    rule_log.sublog(f"{Color.red}evaluation unsuccessful (returned falsy value)")
                return False
            if self.debug_group and add_member_log:
                rule_log.sublog(f"{Color.light_green}evaluation successful (returned truthy value)")
        if self.debug_group and add_member_log:
            add_member_log.sublog(f"{Color.light_green}all rules passed successfully, returning true")
        return True
    def remove_member(self, obj: any) -> None:
        remove_member_log: log = log(f"{Color.blue}attempting to remove member from group '{self.label}': {obj} repr={repr(obj)} label='{obj.label if hasattr(obj, 'label') else 'null'}'") if self.debug_group else None
        for i, member in enumerate(self.members):
            remove_member_log.sublog(f"searching member #{i + 1}") if remove_member_log else ...
            if member is obj:
                self.members.pop(i)
                break
        else:
            remove_member_log.sublog(f"{Color.red}member not found, nothing was removed.") if remove_member_log else ...
            remove_member_log.print() if remove_member_log else ...
            return
        remove_member_log.sublog(f"{Color.light_green}member removed successfully!") if remove_member_log else ...
        remove_member_log.print() if remove_member_log else ...
    def find_member(self, label: str) -> None:
        find_member_log: log = log(f"{Color.blue}attempting to find member in group '{self.label}': label='{label}'") if self.debug_group else None
        for i, member in enumerate(self.members):
            find_member_log.sublog(f"searching member #{i + 1}") if find_member_log else ...
            if not hasattr(member, "label"):
                find_member_log.sublog(f"{Color.yellow}/!\\ member has no label") if find_member_log else ...
            if member.label == label:
                find_member_log.sublog(f"{Color.light_green}found matching member: {member} repr={repr(member)} label='{label}'") if find_member_log else ...
                find_member_log.print() if find_member_log else ...
                return member
        else:
            find_member_log.sublog(f"{Color.red}member not found.") if find_member_log else ...
            find_member_log.print() if find_member_log else ...
            return