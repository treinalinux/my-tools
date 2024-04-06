#!/usr/bin/env python3
#
# name.........: remove_automount
# description..: Remove one entry automount for new value
# author.......: Alan da Silva Alves
# version......: 0.0.1
#
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

import os

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

ANALYST = os.environ.get('USER')
BASE_AUTOMOUNT = "OU=automount,OU=NIS,OU=UNIX,OU=POSIX,DC=EMPRESA,DC=CORP"

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


def append_msg_file(message, file_name):
    with open(file_name, 'a') as file_msg:
        file_msg.write(message)


def get_cn_account_ad(account_ad, base_search):
    ldap_search = "ldapsearch -Q -LLL -o ldif-wrap=no -b"
    get_dn = (f"{ldap_search} '{base_search}' cn={account_ad} dn")
    result = os.popen(get_dn).read()

    if result != '':
        cn = result.split()[1]
    else:
        print(f"\nEntrada '{account_ad}' inexistente no AD!")
        raise SystemExit("...\n")

    return cn


def get_account_ad(account_ad, base_search, attribute):
    search = "ldapsearch -Q -LLL -o ldif-wrap=no -b"
    get_attribute = (f"{search} '{base_search}' cn={account_ad} {attribute}")
    result = os.popen(get_attribute).read()
    result_attribute = result.splitlines()[1]
    result_dn = result.splitlines()[0]
    arr = result_attribute.split()[1:]
    print(result_dn)
    print(f"{account_ad}\t{arr[0]} {arr[1]}")


def delete_nis_map_entry(account_ad, nis_map_entry):
    result_cn = get_cn_account_ad(account_ad, BASE_AUTOMOUNT)

    print(f"\nRemovendo o automount da entrada '{account_ad}':\n")
    get_account_ad(account_ad, BASE_AUTOMOUNT, nis_map_entry)

    ldap_delete(result_cn)

    print("...")


def ldap_delete(account_cn):
    ldap_delete = (f"ldapdelete -Q {account_cn}")

    result = os.popen(ldap_delete).read()


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    print("Import o módulo para usar o recurso!")
