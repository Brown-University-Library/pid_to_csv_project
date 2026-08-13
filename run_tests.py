"""
Runs tests for this script.

Usage examples:
    (all) uv run ./run_tests.py
    (file) uv run ./run_tests.py tests.test
    (class) uv run ./run_tests.py tests.test.TestMain
    (method) uv run ./run_tests.py tests.test.TestMain.test_single_pid_uses_unknown_reason

    Add -v or --verbose to show each test name and docstring.
"""

import argparse
import sys
import unittest


def main() -> None:
    """
    Loads the requested tests and exits with their result code.
    Called by: module guard
    """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        'test_path',
        nargs='?',
        default='tests',
        help='Optional test module/class/method, or a directory to discover tests from.',
    )
    parser.add_argument('-v', '--verbose', action='store_true', help='Increase verbosity to level 2.')
    args = parser.parse_args()

    args.test_path = args.test_path.removesuffix('.py')

    if args.test_path in {'tests', 'test', '.'}:
        suite = unittest.defaultTestLoader.discover('tests')
    else:
        suite = unittest.defaultTestLoader.loadTestsFromName(args.test_path)

    verbosity = 2 if args.verbose else 1
    runner = unittest.TextTestRunner(verbosity=verbosity)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)


if __name__ == '__main__':
    main()
