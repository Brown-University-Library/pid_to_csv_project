"""
Displays informational notices after CSV creation.

The notices identify deeper parts and sub-collection contents that the selected
command mode intentionally leaves unprocessed.
"""

from lib.data_types import CsvCreationResult


def display_terminal_notices(result: CsvCreationResult) -> None:
    """
    Displays PIDs whose deeper parts or sub-collection contents were intentionally not included.
    Called by: main.main()
    """
    if result.pids_with_unincluded_parts:
        print('PIDs with parts that were not included because only direct parts are added:')
        for pid in result.pids_with_unincluded_parts:
            print(f'  {pid}')
    if result.skipped_subcollection_pids:
        print('Sub-collection PIDs whose contents were not processed:')
        for pid in result.skipped_subcollection_pids:
            print(f'  {pid}')
