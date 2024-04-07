#!/usr/bin/env python3
#
# name.........: app_automount
# description..: Manager cli to automount with add/change/remove
# author.......: Alan da Silva Alves
# version......: 1.0.1
#
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

import argparse
import sys
from add_automount import add_nis_map_entry as add_entry
from change_automount import change_nis_map_entry as change_entry
from remove_automount import delete_nis_map_entry as remove_entry

# ---------------------------------------------------------------------------
# Class
# ---------------------------------------------------------------------------


class CmdAutomount(object):
    def __init__(self):
        parser = argparse.ArgumentParser(
            usage='''app_automount <command> [<args>]

The automount commands are:

add      Add entry to automount.
change   Change an automount entry.
remove   Remove entry from automount.
 ''')
        parser.add_argument('command', help='app_automount commands')
        parser.add_argument(
                '-v', '--version', help='show version and exit',
                action='version', version='1.0.1')

        # Read the first argument (add/change/remove)
        args = parser.parse_args(sys.argv[1:2])

        # Use dispatch pattern to invoke method with same name of the argument
        getattr(self, args.command)()

    def add(self):
        parser = argparse.ArgumentParser(
                description='Add entry automount on AD.')
        parser.add_argument(
                '-s', '--sn_code', required=True, help='Request number.')
        parser.add_argument(
                '-m', '--manager', required=False,
                help='Account Manager to add entry of users.')
        parser.add_argument(
                '-n', '--name_entry', required=True,
                help='Name entry, to user name or simple area /IceStation.')
        parser.add_argument(
                '-l', '--local', required=True, help='Local ldap auto.home.')
        parser.add_argument(
                '-v', '--value_attribute', required=True,
                help='Value Attribute for entry: opts nfssrv:/home_unix/alan')

        # Ignore the first argument and read the rest
        args = parser.parse_args(sys.argv[2:])
        app_automount_add(
                args.sn_code, args.manager, args.name_entry,
                args.local, args.value_attribute)

    def change(self):
        parser = argparse.ArgumentParser(
                description='Change the value to entry on automount')
        parser.add_argument(
                '-s', '--sn_code', required=True, help='Request number.')
        parser.add_argument(
                '-n', '--name_entry', required=True,
                help='Name entry, to user name or simple area /IceStation.')
        parser.add_argument(
                '-l', '--local', required=True, help='Local ldap auto.home.')
        parser.add_argument(
                '-v', '--value_attribute', required=True,
                help='Value Attribute for entry: opts nfssrv:/home_unix/alan')

        args = parser.parse_args(sys.argv[2:])
        app_automount_change(
                args.sn_code, args.name_entry, args.local,
                args.value_attribute)

    def remove(self):
        parser = argparse.ArgumentParser(
                description='Change the value to one entry')
        parser.add_argument(
                '-s', '--sn_code', required=True, help='Request number.')
        parser.add_argument(
                '-n', '--name_entry', required=True,
                help='Name entry, to user name or simple area /IceStation.')

        args = parser.parse_args(sys.argv[2:])
        app_automount_remove(args.sn_code, args.name_entry)

# ---------------------------------------------------------------------------
# Functions
# ---------------------------------------------------------------------------


def app_automount_add(sn_code, manager, name_entry, local, value_attribute):
    attr = "nisMapEntry"
    add_entry(name_entry, local, attr, value_attribute)


def app_automount_change(sn_code, name_entry, local, value_attribute):
    attr = "nisMapEntry"
    change_entry(name_entry, attr, value_attribute)


def app_automount_remove(sn_code, name_entry):
    attr = "nisMapEntry"
    remove_entry(name_entry, attr)

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    CmdAutomount()
