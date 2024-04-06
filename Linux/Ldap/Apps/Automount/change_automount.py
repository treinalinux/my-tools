#!/usr/bin/env python3
#
# name.........: change_automount
# description..: Change value of entry automount for new value
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


def create_file_ldif(dn, account_ad, attribute, value_attribute):
    msg = (f"""{dn}
changetype: modify
replace: {attribute}
{attribute}: {value_attribute}
""")

    file_ldif = (f"/tmp/{ANALYST}-{account_ad}-file.ldif")
    append_msg_file(msg, file_ldif)


def get_dn_account_ad(account_ad, base_search):
    ldap_search = "ldapsearch -Q -LLL -o ldif-wrap=no -b"
    get_dn = (f"{ldap_search} '{base_search}' cn={account_ad} dn")
    result = os.popen(get_dn).read()

    if result != '':
        dn = result.rstrip("\n")
    else:
        print(f"\nA entrada: '{account_ad}' não foi localizda no AD! \n")
        raise SystemExit("Finalizado com erro!\n")

    return dn


def get_account_ad(account_ad, base_search, attribute):
    search = "ldapsearch -Q -LLL -o ldif-wrap=no -b"
    get_attribute = (f"{search} '{base_search}' cn={account_ad} {attribute}")
    result = os.popen(get_attribute).read()
    result_attribute = result.splitlines()[1]
    arr = result_attribute.split()[1:]
    print(f"{account_ad}\t{arr[0]} {arr[1]}")


def change_nis_map_entry(account_ad, nis_map_entry, value_entry):
    result_dn = get_dn_account_ad(account_ad, BASE_AUTOMOUNT)
    create_file_ldif(result_dn, account_ad, nis_map_entry, value_entry)

    print(f"\nAlterando o de automount da entrada '{account_ad}':\n\nDE:")
    get_account_ad(account_ad, BASE_AUTOMOUNT, nis_map_entry)

    ldap_modify(account_ad)

    print("\nPARA:")
    get_account_ad(account_ad, BASE_AUTOMOUNT, nis_map_entry)
    print("...")


def ldap_modify(account_ad):
    file_ldif = (f"/tmp/{ANALYST}-{account_ad}-file.ldif")
    ldapmodify_attribute = (f"ldapmodify -Q -f {file_ldif}")

    os.popen(ldapmodify_attribute).read()

    os.remove(file_ldif)


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    print("Import o módulo para usar o recurso!")
