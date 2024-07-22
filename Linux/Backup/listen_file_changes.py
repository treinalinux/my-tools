#!/usr/bin/python3
#
# name...........: listen_file_changes
# author.........: Alan S. Alves
# date...........: 2024/7/22
# description....: Listen file change, if changed then Backup to nfs area
#
##############################################################################
##############################################################################

import os
import time
import shutil

##############################################################################
##############################################################################

src = "/home/alan"
area_nfs = "/area_nfs/backup"
files = [
    "groupchanges.log",
    "userchanges.log"]

###############################################################################
###############################################################################


def file_exist(filename):
    control = True
    exist_file = os.path.isfile(filename)

    if exist_file is False:
        print(f"NOTICE: The file '{filename}' is not exist!")
        control = False

    return control


def create_dir(area):
    now = time.localtime()
    dir_backup = (f"{area}/{now.tm_year}/{now.tm_mon}/{now.tm_mday}")
    dir_exist = os.path.isdir(dir_backup)

    if dir_exist is not True:
        os.makedirs(dir_backup)

    return dir_backup


def backup_now(src_filename, dst_dir):
    try:
        shutil.copy2(src_filename, dst_dir)
        print(f"OK....: Copied file '{src_filename}' to '{dst_dir}'")
    except Exception as e:
        print('Error.: ' + repr(e))


##############################################################################
##############################################################################

for f in files:
    dst = create_dir(area_nfs)
    src_f = (f"{src}/{f}")
    dst_f = (f"{dst}/{f}")

    src_f_exist = file_exist(src_f)
    dst_f_exist = file_exist(dst_f)

    if src_f_exist is False:
        break

    if dst_f_exist is False:
        with open(dst_f, "w") as empty_file:
            empty_file.write("")

    data = os.stat(f"{src_f}")
    data_file_bkp = os.stat(dst_f)

    file_src_is_change = data.st_mtime
    file_dst_is_old = data_file_bkp.st_mtime

    if file_src_is_change != file_dst_is_old:
        backup_now(src_f, dst)
