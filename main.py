import argparse
import logging
import sys
from pathlib import Path

from lib.bdr_api import read_cookie_file
from lib.cli_values import non_empty_pid, normalize_api_root
from lib.csv_creator import create_csv
from lib.data_types import CsvCreationResult, PidToCsvError
from lib.terminal import display_terminal_notices

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s [%(module)s-%(funcName)s()::%(lineno)d] %(message)s',
    datefmt='%d/%b/%Y %H:%M:%S',
)
log: logging.Logger = logging.getLogger(__name__)
logging.getLogger('httpx').setLevel(logging.WARNING)


def parse_arguments() -> argparse.Namespace:
    """
    Parses the command-line options.
    Called by: main()
    """
    parser = argparse.ArgumentParser(
        description='Creates a two-column CSV containing a BDR PID and its reason.',
    )
    parser.add_argument(
        '--api-root',
        required=True,
        type=normalize_api_root,
        help='BDR API root, with or without a trailing slash (e.g., https://repo.example.edu/api/).',
    )
    parser.add_argument('--pid', required=True, type=non_empty_pid, help='BDR PID to add to the CSV.')
    parser.add_argument('--output', required=True, type=Path, help='Path of the CSV file to create.')
    parser.add_argument(
        '--reason',
        default='unknown',
        help='Reason for a single PID. Defaults to "unknown" and is ignored in collection mode.',
    )
    parser.add_argument(
        '--grab-all-collection-items',
        action='store_true',
        help='Treat --pid as a collection PID and add every accessible member PID returned by the BDR API.',
    )
    parser.add_argument(
        '--include-headers',
        action='store_true',
        help='Include the PID and Reason column headers. By default, the CSV contains only data rows.',
    )
    parser.add_argument(
        '--include-all-has-parts',
        action='store_true',
        help="Include each submitted or primary collection item's direct parts.",
    )
    parser.add_argument(
        '--cookie-file',
        type=Path,
        help='Optional file containing an authenticated browser Cookie request-header value.',
    )
    parser.add_argument(
        '--comprehensive',
        action='store_true',
        help='Validate --pid as a collection and include every descendant sub-collection and its direct members.',
    )
    args: argparse.Namespace = parser.parse_args()
    return args


def main() -> None:
    """
    Manages PID CSV creation using the command-line options.
    Called by: module guard
    """
    args: argparse.Namespace = parse_arguments()
    try:
        cookie_values: dict[str, str] | None = read_cookie_file(args.cookie_file) if args.cookie_file else None
        result: CsvCreationResult = create_csv(
            args.api_root,
            args.pid,
            args.output,
            args.reason,
            args.grab_all_collection_items,
            include_headers=args.include_headers,
            include_all_has_parts=args.include_all_has_parts,
            cookie_values=cookie_values,
            comprehensive=args.comprehensive,
        )
    except PidToCsvError as error:
        log.error(f'error, ``{error}``')
        sys.exit(1)
    display_terminal_notices(result)
    log.info(f'Created output_path, ``{args.output}``; data_row_count, ``{result.row_count}``.')


if __name__ == '__main__':
    main()
