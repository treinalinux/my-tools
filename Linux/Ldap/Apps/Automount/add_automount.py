#!/usr/bin/env python3
#
# name.........: add_automount
# description..: Add new entry in automount
# author.......: Alan da Silva Alves
# version......: 1.0.2
#
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

import os

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

ANALYST = os.environ.get('USER')
BASE_AUTOMOUNT = "OU=automount,OU=NIS,OU=UNIX,OU=POSIX,DC=EMPRESA,DC=CORP"
LOGS = "/var/log/empresa/user_changes.log"
APP = "add_automount"

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


def append_msg_file(message, file_name):
    with open(file_name, 'a') as file_msg:
        file_msg.write(message)


def create_file_ldif(dn, account_ad, map_name, attribute, value_attribute):

    msg = (f"""{dn}
objectClass: nisObject
cn: {account_ad}
{attribute}: {value_attribute}
nisMapName: {map_name}
""")

    file_ldif = (f"/tmp/{ANALYST}-{account_ad}-file.ldif")
    append_msg_file(msg, file_ldif)


def get_nis_map_name(nis_map, base_search):
    ldap_search = "ldapsearch -Q -LLL -o ldif-wrap=no -b"
    get_dn = (f"{ldap_search} '{base_search}' cn={nis_map} dn")
    result = os.popen(get_dn).read()

    if result == '':
        print(f"\nO nisMapName: '{nis_map}' nao existe no AD!")
        raise SystemExit("\nVerifique se o nome esta correto!\n")


def get_dn_account_ad(account_ad, base_search):
    ldap_search = "ldapsearch -Q -LLL -o ldif-wrap=no -b"
    get_dn = (f"{ldap_search} '{base_search}' cn={account_ad} dn")
    result = os.popen(get_dn).read()

    if result != '':
        print(f"\nA entrada: '{account_ad}' existe no AD!")
        dn = result.rstrip("\n")
        print(dn)
        raise SystemExit("\nVerifique se o nome esta correto!\n")


def get_account_ad(account_ad, base_search, attribute):
    search = "ldapsearch -Q -LLL -o ldif-wrap=no -b"
    get_attribute = (f"{search} '{base_search}' cn={account_ad} {attribute}")
    result = os.popen(get_attribute).read()
    result_attribute = result.splitlines()[1]
    arr = result_attribute.split()[1:]
    print(f"{account_ad}\t{arr[0]} {arr[1]}")


def add_nis_map_entry(account_ad, map_name, nis_map_entry, value_entry):
    get_dn_account_ad(account_ad, BASE_AUTOMOUNT)
    new_dn = (f"dn: CN={account_ad},CN={map_name},{BASE_AUTOMOUNT}")
    create_file_ldif(new_dn, account_ad, map_name, nis_map_entry, value_entry)

    print(f"\nAdicionando entrada para '{account_ad}' em {map_name}...")

    ldap_add(account_ad)
    get_account_ad(account_ad, BASE_AUTOMOUNT, nis_map_entry)

    print("...")


def ldap_add(account_ad):
    file_ldif = (f"/tmp/{ANALYST}-{account_ad}-file.ldif")
    ldap_add_attribute = (f"ldapadd -Q -f {file_ldif}")

    os.popen(ldap_add_attribute).read()

    os.remove(file_ldif)


def control_add(sn_code, manager, account_ad, map_name, attr, value_attr):
    get_nis_map_name(map_name, BASE_AUTOMOUNT)
    m_account = (f"manager={manager} account={account_ad}")
    f_log = (f"{sn_code} \t{ANALYST} \t{APP} \t{m_account} \t{value_attr}")

    add_nis_map_entry(account_ad, map_name, attr, value_attr)

    log_action = (f"date \t{f_log}\n")
    append_msg_file(log_action, LOGS)

    print("")


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


if __name__ == '__main__':
    print("Import o módulo para usar o recurso!")
