#!/usr/bin/env python3
#
# name.........: mod_ldap_app
# description..: Module ldap to search and change
# author.......: Alan da Silva Alves
# version......: 0.0.2
# create at....: 04/23/2024
#
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

import os

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

ANALYST = os.environ.get("USER")
LDAP_SEARCH = "ldapsearch -Y GSSAPI -Q -LLL -o ldif-wrap=no"
LOGS_USER = "/var/log/empresa/user_changes.log"
LOGS_GROUP = "/var/log/empresa/group_changes.log"


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


def append_msg_file(message, file_name):
    with open(file_name, 'a') as file_msg:
        file_msg.write(message)


def ldap_search(obj_class, obj_name, obj_custom=None, value="dn"):
    """TODO: Docstring for ldap_search.

    :obj_class: TODO
    :returns: TODO

    """
    obj_class = (f"objectclass={obj_class}")
    obj_name = (f"cn={obj_name}")

    if obj_custom is not None:
        search_obj = (f"'(&({obj_class})({obj_custom})({obj_name}))' {value}")
    else:
        search_obj = (f"'(&({obj_class})({obj_name}))'")

    cmd_search = (f"{LDAP_SEARCH} {search_obj} {value}")
    result = os.popen(cmd_search).read()

    return result


def return_value(obj_class, obj_name, obj_custom=None, value=None):
    """TODO: Docstring for return_value.

    :obj_class: TODO
    :value: TODO
    :obj_custom: TODO
    :returns: TODO

    """
    if obj_custom is not None:
        result_value = ldap_search(obj_class, obj_name, obj_custom, value)
    else:
        result_value = ldap_search(obj_class, obj_name)

    if value is None:
        r_value = return_dn(result_value)
    else:
        r_value = return_value_obj(result_value, value)

    return r_value


def return_dn(message):
    r_value = message.split("\n")[0]

    if r_value.startswith("dn"):
        return r_value
    else:
        return False


def return_value_obj(message, value):
    r_value = message.split("\n")[1]
    r_obj = value.split(":")[0]

    if r_value.startswith(r_obj):
        return r_value
    else:
        return False


def match_str(message, value):
    """TODO: Docstring for match_str.
    :returns: TODO

    """

    if value in message:
        return value


def ldap_add_obj(message):
    """TODO: Docstring for ldap_add_obj.
    :returns: TODO

    """
    ldap_add = (f"ldapadd -Q <<EOF\n{message}EOF")
    os.popen(ldap_add).read()


def ldap_modify_obj(message):
    """TODO: Docstring for ldap_modify_obj.
    :returns: TODO

    """
    ldap_modify = (f"ldapmodify -Q <<EOF\n{message}\nEOF")
    result = os.popen(ldap_modify).read()
    return result


def ldap_delete_obj(obj_cn):
    """TODO: Docstring for ldap_delete_obj.

    :obj_cn: TODO
    :returns: TODO

    """
    ldap_delete = (f"ldapdelete -Q {obj_cn}")

    os.popen(ldap_delete).read()


def get_cn_path(obj_class, obj_name):
    dn_obj = return_value(obj_class, obj_name)
    cn_obj = dn_obj.split(" ")[1]

    return cn_obj


def add_attribute_obj(dn_obj, attribute, value):
    mod = "changetype: modify"
    message = (f"{dn_obj}\n{mod}\nadd: {attribute}\n{attribute}: {value}\n")
    result = ldap_modify_obj(message)
    return result


def remove_attribute_obj(dn_obj, attribute, value):
    mod = "changetype: modify"
    message = (f"{dn_obj}\n{mod}\ndelete: {attribute}\n{attribute}: {value}\n")
    result = ldap_modify_obj(message)
    return result


def add_group_user_member_uid(dn_group, user_name):
    """TODO: Docstring for add_group_user_member_uid.

    :dn_group: TODO
    :user_name: TODO
    :returns: TODO

    """
    fail = (f"Erro ao adicionar '{user_name}' memberUid do {dn_group}.\n")
    ok = (f"'{user_name}' foi adicionada no grupo {dn_group} com sucesso.\n")

    result = add_attribute_obj(dn_group, "memberUid", user_name)

    print(result)


def add_group_user_member(dn_group, cn_user):
    """TODO: Docstring for add_group_user.

    :dn_group: TODO
    :cn_user: TODO
    :returns: TODO

    """
    fail = (f"Erro ao adicionar '{cn_user}' memberUid do grupo {dn_group}.\n")
    ok = (f"'{cn_user}' foi adicionada no grupo {dn_group} com sucesso.\n")

    try:
        add_attribute_obj(dn_group, "member", cn_user)
    except Exception as e:
        append_msg_file(e, LOGS_GROUP)
        append_msg_file(fail, LOGS_GROUP)
    else:
        append_msg_file(ok, LOGS_GROUP)


def add_group_user(group_name, user_name):
    """TODO: Docstring for add_group_user.

    :group_name: TODO
    :user_name: TODO
    :returns: TODO

    """
    dn_group = return_value("group", group_name)
    cn_user = get_cn_path("user", user_name)

    add_group_user_member(dn_group, cn_user)
    add_group_user_member_uid(dn_group, user_name)


def remove_group_user_member_uid(dn_group, user_name):
    """TODO: Docstring for remove_group_user_member_uid.

    :dn_group: TODO
    :user_name: TODO
    :returns: TODO

    """
    fail = (f"Erro ao remover '{user_name}' do memberUid no {dn_group}.\n")
    ok = (f"'{user_name}' foi removida do memberUid do {dn_group}.\n")

    try:
        remove_attribute_obj(dn_group, "memberUid", user_name)
    except Exception as e:
        append_msg_file(e, LOGS_GROUP)
        append_msg_file(fail, LOGS_GROUP)
    else:
        append_msg_file(ok, LOGS_GROUP)


def remove_group_user_member(dn_group, cn_user):
    """TODO: Docstring for remove_group_user_member.

    :dn_group: TODO
    :cn_user: TODO
    :returns: TODO

    """
    fail = (f"Erro ao remover '{cn_user}' do member do grupo '{dn_group}'.\n")
    ok = (f"'{cn_user}' foi removida do member do '{dn_group}' com sucesso.\n")

    try:
        remove_attribute_obj(dn_group, "member", cn_user)
    except Exception as e:
        append_msg_file(e, LOGS_GROUP)
        append_msg_file(fail, LOGS_GROUP)
    else:
        append_msg_file(ok, LOGS_GROUP)


def remove_group_user(group_name, user_name):
    """TODO: Docstring for remove_group_user.

    :group_name: TODO
    :user_name: TODO
    :returns: TODO

    """
    dn_group = return_value("group", group_name)
    cn_user = get_cn_path("user", user_name)

    remove_group_user_member(dn_group, cn_user)
    remove_group_user_member_uid(dn_group, user_name)


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


if __name__ == '__main__':

    print("\nimport o modulo para usar o recurso:\n")
