"""
Provides validation and normalization for command-line argument values.

The functions return cleaned values for argparse or raise readable argument
errors before CSV processing begins.
"""

import argparse


def non_empty_pid(value: str) -> str:
    """
    Validates and trims a PID supplied on the command line.
    Called by: main.parse_arguments()
    """
    pid = value.strip()
    if not pid:
        raise argparse.ArgumentTypeError('PID cannot be empty.')
    return pid


def normalize_api_root(value: str) -> str:
    """
    Trims whitespace and trailing slashes from an API root supplied on the command line.
    Called by: main.parse_arguments()
    """
    api_root = value.strip().rstrip('/')
    if not api_root:
        raise argparse.ArgumentTypeError('API root cannot be empty.')
    return api_root
