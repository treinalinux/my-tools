#!/usr/bin/env python3
#
# name.........: simple_colors
# description..: Simple colors to terminal
# author.......: Alan da Silva Alves
# version......: 1.0.0
#
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


def c_success(text):
    print(f"\033[32m{text}\033[m")


def c_failure(text):
    print(f"\033[1;31m{text}\033[m")


def c_warning(text):
    print(f"\033[33m{text}\033[m")


def c_info(text):
    print(f"\033[35m{text}\033[m")

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


if __name__ == '__main__':
    c_warning("Import the module 'simple_colors' to use the feature.")
