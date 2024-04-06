#!/bin/python3
#
# name.........: app_automount
# description..: App for add/change/remove entry on automount
# author.......: Alan da Silva Alves
# version......: 0.0.1
#
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

import argparse
from add_automount import add_nis_map_entry as add
from change_automount import change_nis_map_entry as change
from remove_automount import delete_nis_map_entry as remove


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

parser = argparse.ArgumentParser(
        description='Manager automount add/change/remove',
        prog='app_automount', usage='%(prog)s [options]'
    )

parser.add_argument(
        '-s', '--sn_code', type=str, required=True,
        help='-- Request Number to control'
    )

parser.add_argument(
        '-n', '--name_account', type=str, required=True,
        help='-- Name account or name entry using'
    )

parser.add_argument(
        '-m', '--manager_account', type=str, required=False,
        help='-- Name account manager for enable account'
    )

parser.add_argument(
        '-a', '--action', type=str, required=True,
        help='-- add/change/remove entry automount on AD'
    )

parser.add_argument(
        '-l', '--local', type=str, required=False,
        help='-- Local on AD, em example: auto.home'
    )

parser.add_argument(
        '-v', '--value_attribute', type=str, required=False,
        help='''-- Value Attribute for entry with options Example:
        -rw,sync perola.empresa.corp:/home_unix/alan'''
    )

args = parser.parse_args()


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

def main():
    attr = "nisMapEntry"

    if args.action == "add":
        add(args.name_account, args.local, attr, args.value_attribute)

    elif args.action == "change":
        change(args.name_account, attr, args.value_attribute)

    elif args.action == "remove":
        remove(args.name_account, attr)
        print("...")

    else:
        print("Required '-a', you need use with action add/change/remove")


main()
