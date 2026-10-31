"""Read or operate controls of one test process on its isolated AT-SPI bus.

Run with /usr/bin/python3 for distro GObject introspection. This is a test-only
client of the public accessibility interface, without product hooks or imports.
"""
import argparse
import json

import gi

gi.require_version('Atspi', '2.0')
from gi.repository import Atspi  # noqa: E402 — select the GI version before importing it.


def nodes(pid):
    desktop = Atspi.get_desktop(0)
    applications = [desktop.get_child_at_index(i) for i in range(desktop.get_child_count())]
    stack = [app for app in applications if app.get_process_id() == pid]
    count = 0
    while stack:
        node = stack.pop()
        count += 1
        if count > 500:
            raise RuntimeError('Accessibility tree exceeded the test process bound.')
        yield node
        stack.extend(node.get_child_at_index(i) for i in reversed(range(node.get_child_count())))


def describe(node):
    result = {'name': node.get_name(), 'role': node.get_role_name(),
              'showing': node.get_state_set().contains(Atspi.StateType.SHOWING)}
    interfaces = node.get_interfaces()
    if 'Component' in interfaces:
        rect = node.get_component().get_extents(Atspi.CoordType.SCREEN)
        result['rect'] = [rect.x, rect.y, rect.width, rect.height]
    if 'Text' in interfaces:
        result['text'] = Atspi.Text.get_text(node, 0, -1)
    if 'Value' in interfaces:
        result['value'] = Atspi.Value.get_current_value(node)
    if 'Action' in interfaces:
        action = node.get_action()
        result['actions'] = [action.get_action_name(i) for i in range(action.get_n_actions())]
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--pid', type=int, required=True)
    parser.add_argument('--operation', choices=('dump', 'invoke', 'setvalue', 'settext', 'focus'), default='dump')
    parser.add_argument('--name')
    parser.add_argument('--role')
    parser.add_argument('--value')
    args = parser.parse_args()
    matches = [node for node in nodes(args.pid)
               if (args.name is None or node.get_name() == args.name)
               and (args.role is None or node.get_role_name() == args.role)]
    if args.operation == 'dump':
        print(json.dumps([describe(node) for node in matches], ensure_ascii=False))
        return
    required = {'invoke': 'Action', 'setvalue': 'Value', 'settext': 'EditableText', 'focus': 'Component'}[args.operation]
    matches = [node for node in matches if required in node.get_interfaces()]
    if len(matches) != 1:
        raise RuntimeError(f'Expected exactly one matching control; found {len(matches)}.')
    target = matches[0]
    if not target.get_state_set().contains(Atspi.StateType.SHOWING):
        raise RuntimeError('The specified control must be visible before operating it.')
    if args.operation == 'invoke':
        action = target.get_action()
        if action is None or action.get_n_actions() < 1 or not action.do_action(0):
            raise RuntimeError('The target did not accept its accessibility action.')
    elif args.operation == 'focus':
        if not Atspi.Component.grab_focus(target):
            raise RuntimeError('The target did not accept keyboard focus.')
    elif args.operation == 'setvalue':
        if not Atspi.Value.set_current_value(target, float(args.value)):
            raise RuntimeError('The target did not accept the numeric value.')
    elif args.operation == 'settext':
        if not Atspi.EditableText.set_text_contents(target, args.value):
            raise RuntimeError('The target did not accept the text.')
    print(json.dumps(describe(target), ensure_ascii=False))


if __name__ == '__main__':
    main()
