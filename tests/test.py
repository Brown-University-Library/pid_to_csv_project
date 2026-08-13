import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import httpx

import main
from lib import bdr_api, csv_creator, terminal
from lib.data_types import CsvCreationResult, PidToCsvError


class TestMain(unittest.TestCase):
    @patch(
        'sys.argv',
        [
            'main.py',
            '--api-root',
            ' https://repo.host.brown.edu/api/// ',
            '--pid',
            'bdr:123',
            '--output',
            'output.csv',
        ],
    )
    def test_reason_argument_defaults_to_unknown(self) -> None:
        """
        Checks required arguments are normalized and optional arguments use their defaults.
        """
        args = main.parse_arguments()

        self.assertEqual('https://repo.host.brown.edu/api', args.api_root)
        self.assertEqual('unknown', args.reason)
        self.assertFalse(args.include_headers)
        self.assertFalse(args.include_all_has_parts)
        self.assertFalse(args.comprehensive)
        self.assertIsNone(args.cookie_file)

    def test_cookie_file_accepts_raw_value_and_cookie_prefix(self) -> None:
        """
        Checks both documented one-line cookie-file formats are parsed without exposing values.
        """
        with tempfile.TemporaryDirectory() as temporary_directory:
            raw_cookie_file = Path(temporary_directory) / 'raw-cookie'
            prefixed_cookie_file = Path(temporary_directory) / 'prefixed-cookie'
            raw_cookie_file.write_text('_shibsession_test=secret-value; other=value=with-equals\n', encoding='utf-8')
            prefixed_cookie_file.write_text('Cookie: _shibsession_test=secret-value; other=second\n', encoding='utf-8')

            raw_cookies = bdr_api.read_cookie_file(raw_cookie_file)
            prefixed_cookies = bdr_api.read_cookie_file(prefixed_cookie_file)

        self.assertEqual(
            {'_shibsession_test': 'secret-value', 'other': 'value=with-equals'},
            raw_cookies,
        )
        self.assertEqual(
            {'_shibsession_test': 'secret-value', 'other': 'second'},
            prefixed_cookies,
        )

    def test_cookie_file_rejects_empty_and_multiline_content(self) -> None:
        """
        Checks empty or line-wrapped browser cookies fail with safe, readable messages.
        """
        with tempfile.TemporaryDirectory() as temporary_directory:
            empty_cookie_file = Path(temporary_directory) / 'empty-cookie'
            multiline_cookie_file = Path(temporary_directory) / 'multiline-cookie'
            empty_cookie_file.write_text('', encoding='utf-8')
            multiline_cookie_file.write_text('first=secret\nsecond=secret', encoding='utf-8')

            with self.assertRaisesRegex(PidToCsvError, 'is empty'):
                bdr_api.read_cookie_file(empty_cookie_file)
            with self.assertRaisesRegex(PidToCsvError, 'on one line'):
                bdr_api.read_cookie_file(multiline_cookie_file)

    def test_http_client_limits_cookie_to_api_host(self) -> None:
        """
        Checks authenticated cookies reach the BDR host but are not sent to a redirect on another host.
        """
        with bdr_api.create_http_client(
            'https://bdr.example.test/api',
            {'_shibsession_test': 'secret-value'},
        ) as client:
            api_request = client.build_request('GET', 'https://bdr.example.test/api/search/')
            other_host_request = client.build_request('GET', 'https://login.example.test/')

        self.assertEqual('_shibsession_test=secret-value', api_request.headers['Cookie'])
        self.assertNotIn('Cookie', other_host_request.headers)

    def test_authenticated_403_suggests_refreshing_cookie_without_exposing_it(self) -> None:
        """
        Checks a rejected browser session produces actionable guidance without printing its value.
        """
        response = httpx.Response(
            403,
            request=httpx.Request('GET', 'https://bdr.example.test/api/collections/bdr:restricted/'),
            text='Forbidden',
        )
        transport = httpx.MockTransport(lambda request: response)
        client = httpx.Client(
            transport=transport,
            cookies={'_shibsession_test': 'secret-value'},
        )

        with client, self.assertRaises(PidToCsvError) as raised_error:
            bdr_api.get_json(
                client,
                'https://bdr.example.test/api/collections/bdr:restricted/',
                {},
                'Collection lookup for bdr:restricted',
            )

        error_message = str(raised_error.exception)
        self.assertIn('Log in again and refresh --cookie-file', error_message)
        self.assertNotIn('secret-value', error_message)

    def test_single_pid_uses_unknown_reason(self) -> None:
        """
        Checks that normal mode omits headers and writes the PID and default reason.
        """
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_path = Path(temporary_directory) / 'output.csv'

            result = csv_creator.create_csv('https://example.test/api', 'bdr:123', output_path, 'unknown', False)

            with output_path.open(encoding='utf-8', newline='') as output_file:
                rows = list(csv.reader(output_file))
        self.assertEqual(1, result.row_count)
        self.assertEqual([['bdr:123', 'unknown']], rows)

    def test_single_pid_uses_custom_reason(self) -> None:
        """
        Checks that --reason content is written in normal mode.
        """
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_path = Path(temporary_directory) / 'output.csv'

            csv_creator.create_csv('https://example.test/api', 'bdr:456', output_path, 'needs review', False)

            with output_path.open(encoding='utf-8', newline='') as output_file:
                rows = list(csv.reader(output_file))
        self.assertEqual([['bdr:456', 'needs review']], rows)

    def test_part_query_requests_accessible_displayable_parts(self) -> None:
        """
        Checks parts use display permission and need not be independently discoverable.
        """
        query = bdr_api.build_part_query(['test:t8qtpedx'])

        self.assertEqual(
            'display:* AND rel_is_part_of_ssim:("test:t8qtpedx")',
            query,
        )

    def test_include_headers_writes_column_names(self) -> None:
        """
        Checks that header output can be explicitly enabled.
        """
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_path = Path(temporary_directory) / 'output.csv'

            csv_creator.create_csv(
                'https://example.test/api',
                'bdr:789',
                output_path,
                'unknown',
                False,
                include_headers=True,
            )

            with output_path.open(encoding='utf-8', newline='') as output_file:
                rows = list(csv.reader(output_file))
        self.assertEqual([['PID', 'Reason'], ['bdr:789', 'unknown']], rows)

    @patch('lib.bdr_api.httpx.Client')
    def test_collection_mode_pages_and_writes_collection_reasons(self, client_class_mock: MagicMock) -> None:
        """
        Checks collection validation, paging, row order, and collection-specific reasons.
        """
        collection_response = httpx.Response(
            200,
            request=httpx.Request('GET', 'https://example.test/collection'),
            json={'pid': 'bdr:collection', 'name': 'Sample Collection'},
        )
        first_search_response = httpx.Response(
            200,
            request=httpx.Request('GET', 'https://example.test/search'),
            json={
                'response': {
                    'numFound': 3,
                    'start': 0,
                    'docs': [{'pid': 'bdr:1'}, {'pid': 'bdr:2'}],
                },
            },
        )
        second_search_response = httpx.Response(
            200,
            request=httpx.Request('GET', 'https://example.test/search'),
            json={
                'response': {
                    'numFound': 3,
                    'start': 2,
                    'docs': [{'pid': 'bdr:3'}],
                },
            },
        )
        client_mock = client_class_mock.return_value.__enter__.return_value
        client_mock.get.side_effect = [collection_response, first_search_response, second_search_response]

        with tempfile.TemporaryDirectory() as temporary_directory:
            output_path = Path(temporary_directory) / 'collection.csv'

            result = csv_creator.create_csv(
                'https://example.test/api',
                'bdr:collection',
                output_path,
                'ignored reason',
                True,
            )

            with output_path.open(encoding='utf-8', newline='') as output_file:
                rows = list(csv.reader(output_file))

        expected_rows = [
            ['bdr:collection', 'Sample Collection collection'],
            ['bdr:1', 'member of Sample Collection collection'],
            ['bdr:2', 'member of Sample Collection collection'],
            ['bdr:3', 'member of Sample Collection collection'],
        ]
        self.assertEqual(4, result.row_count)
        self.assertEqual(expected_rows, rows)
        self.assertEqual('2', client_mock.get.call_args_list[2].kwargs['params']['start'])
        self.assertTrue(client_mock.get.call_args_list[1].kwargs['params']['q'].startswith('display:* AND '))

    @patch('lib.bdr_api.httpx.Client')
    def test_comprehensive_walks_collection_tree_once_and_records_hierarchy(self, client_class_mock: MagicMock) -> None:
        """
        Checks hierarchy, cycle protection, and moving a part found early to immediately after its parent.
        """
        root_collection_response = httpx.Response(
            200,
            request=httpx.Request('GET', 'https://example.test/root-collection'),
            json={'pid': 'bdr:root', 'name': 'Root'},
        )
        root_members_response = httpx.Response(
            200,
            request=httpx.Request('GET', 'https://example.test/search'),
            json={
                'response': {
                    'numFound': 3,
                    'start': 0,
                    'docs': [
                        {
                            'pid': 'bdr:root-part',
                            'object_type': 'image',
                            'rel_is_part_of_ssim': ['bdr:root-item'],
                        },
                        {'pid': 'bdr:root-item', 'object_type': 'book'},
                        {'pid': 'bdr:sub', 'object_type': 'bdr-collection'},
                    ],
                },
            },
        )
        subcollection_response = httpx.Response(
            200,
            request=httpx.Request('GET', 'https://example.test/subcollection'),
            json={'pid': 'bdr:sub', 'name': 'Sub'},
        )
        subcollection_members_response = httpx.Response(
            200,
            request=httpx.Request('GET', 'https://example.test/search'),
            json={
                'response': {
                    'numFound': 3,
                    'start': 0,
                    'docs': [
                        {'pid': 'bdr:sub-item', 'object_type': 'image'},
                        {'pid': 'bdr:deep', 'object_type': 'bdr-collection'},
                        {'pid': 'bdr:root', 'object_type': 'bdr-collection'},
                    ],
                },
            },
        )
        deep_collection_response = httpx.Response(
            200,
            request=httpx.Request('GET', 'https://example.test/deep-collection'),
            json={'pid': 'bdr:deep', 'name': 'Deep'},
        )
        deep_collection_members_response = httpx.Response(
            200,
            request=httpx.Request('GET', 'https://example.test/search'),
            json={
                'response': {
                    'numFound': 2,
                    'start': 0,
                    'docs': [
                        {'pid': 'bdr:deep-item', 'object_type': 'audio'},
                        {'pid': 'bdr:sub', 'object_type': 'bdr-collection'},
                    ],
                },
            },
        )
        direct_parts_response = httpx.Response(
            200,
            request=httpx.Request('GET', 'https://example.test/search'),
            json={
                'response': {
                    'numFound': 3,
                    'start': 0,
                    'docs': [
                        {'pid': 'bdr:root-part', 'rel_is_part_of_ssim': ['bdr:root-item']},
                        {'pid': 'bdr:sub-part', 'rel_is_part_of_ssim': ['bdr:sub-item']},
                        {'pid': 'bdr:deep-part', 'rel_is_part_of_ssim': ['bdr:deep-item']},
                    ],
                },
            },
        )
        no_deeper_parts_response = httpx.Response(
            200,
            request=httpx.Request('GET', 'https://example.test/search'),
            json={'response': {'numFound': 0, 'start': 0, 'docs': []}},
        )
        client_mock = client_class_mock.return_value.__enter__.return_value
        client_mock.get.side_effect = [
            root_collection_response,
            root_members_response,
            subcollection_response,
            subcollection_members_response,
            deep_collection_response,
            deep_collection_members_response,
            direct_parts_response,
            no_deeper_parts_response,
        ]

        with tempfile.TemporaryDirectory() as temporary_directory:
            output_path = Path(temporary_directory) / 'comprehensive.csv'

            result = csv_creator.create_csv(
                'https://example.test/api',
                'bdr:root',
                output_path,
                'ignored reason',
                False,
                include_all_has_parts=True,
                comprehensive=True,
            )

            with output_path.open(encoding='utf-8', newline='') as output_file:
                rows = list(csv.reader(output_file))

        self.assertEqual(
            [
                ['bdr:root', 'Root collection'],
                ['bdr:root-item', 'member of Root collection'],
                ['bdr:root-part', 'part of bdr:root-item'],
                ['bdr:sub', 'collection-member of Root collection > Sub collection'],
                ['bdr:sub-item', 'member of Root collection > Sub collection'],
                ['bdr:sub-part', 'part of bdr:sub-item'],
                ['bdr:deep', 'collection-member of Root collection > Sub collection > Deep collection'],
                ['bdr:deep-item', 'member of Root collection > Sub collection > Deep collection'],
                ['bdr:deep-part', 'part of bdr:deep-item'],
            ],
            rows,
        )
        self.assertEqual(9, result.row_count)
        self.assertEqual((), result.skipped_subcollection_pids)
        self.assertEqual(8, client_mock.get.call_count)
        direct_part_query = client_mock.get.call_args_list[6].kwargs['params']['q']
        self.assertIn('bdr:root-item', direct_part_query)
        self.assertIn('bdr:sub-item', direct_part_query)
        self.assertIn('bdr:deep-item', direct_part_query)
        self.assertNotIn('bdr:sub"', direct_part_query)

    @patch('lib.bdr_api.httpx.Client')
    def test_single_pid_includes_only_direct_parts_and_reports_deeper_parent(self, client_class_mock: MagicMock) -> None:
        """
        Checks direct part rows and reports a direct part whose own child is not included.
        """
        direct_parts_response = httpx.Response(
            200,
            request=httpx.Request('GET', 'https://example.test/search'),
            json={
                'response': {
                    'numFound': 2,
                    'start': 0,
                    'docs': [
                        {'pid': 'bdr:part1', 'rel_is_part_of_ssim': ['bdr:primary']},
                        {'pid': 'bdr:part2', 'rel_is_part_of_ssim': ['bdr:primary']},
                    ],
                },
            },
        )
        deeper_parts_response = httpx.Response(
            200,
            request=httpx.Request('GET', 'https://example.test/search'),
            json={
                'response': {
                    'numFound': 1,
                    'start': 0,
                    'docs': [{'pid': 'bdr:grandchild', 'rel_is_part_of_ssim': ['bdr:part1']}],
                },
            },
        )
        client_mock = client_class_mock.return_value.__enter__.return_value
        client_mock.get.side_effect = [direct_parts_response, deeper_parts_response]

        with tempfile.TemporaryDirectory() as temporary_directory:
            output_path = Path(temporary_directory) / 'parts.csv'

            result = csv_creator.create_csv(
                'https://example.test/api',
                'bdr:primary',
                output_path,
                'unknown',
                False,
                include_all_has_parts=True,
            )

            with output_path.open(encoding='utf-8', newline='') as output_file:
                rows = list(csv.reader(output_file))

        self.assertEqual(
            [
                ['bdr:primary', 'unknown'],
                ['bdr:part1', 'part of bdr:primary'],
                ['bdr:part2', 'part of bdr:primary'],
            ],
            rows,
        )
        self.assertEqual(('bdr:part1',), result.pids_with_unincluded_parts)
        self.assertNotIn('bdr:grandchild', [row[0] for row in rows])

    @patch('lib.bdr_api.httpx.Client')
    def test_collection_parts_skip_subcollections_and_non_primary_members(self, client_class_mock: MagicMock) -> None:
        """
        Checks collection part processing targets primary items and reports skipped sub-collections.
        """
        collection_response = httpx.Response(
            200,
            request=httpx.Request('GET', 'https://example.test/collection'),
            json={'pid': 'bdr:collection', 'name': 'Sample Collection'},
        )
        members_response = httpx.Response(
            200,
            request=httpx.Request('GET', 'https://example.test/search'),
            json={
                'response': {
                    'numFound': 3,
                    'start': 0,
                    'docs': [
                        {'pid': 'bdr:primary', 'object_type': 'book'},
                        {'pid': 'bdr:subcollection', 'object_type': 'bdr-collection'},
                        {
                            'pid': 'bdr:existing-part',
                            'object_type': 'image',
                            'rel_is_part_of_ssim': ['bdr:primary'],
                        },
                    ],
                },
            },
        )
        direct_parts_response = httpx.Response(
            200,
            request=httpx.Request('GET', 'https://example.test/search'),
            json={
                'response': {
                    'numFound': 2,
                    'start': 0,
                    'docs': [
                        {'pid': 'bdr:existing-part', 'rel_is_part_of_ssim': ['bdr:primary']},
                        {'pid': 'bdr:new-part', 'rel_is_part_of_ssim': ['bdr:primary']},
                    ],
                },
            },
        )
        no_deeper_parts_response = httpx.Response(
            200,
            request=httpx.Request('GET', 'https://example.test/search'),
            json={'response': {'numFound': 0, 'start': 0, 'docs': []}},
        )
        client_mock = client_class_mock.return_value.__enter__.return_value
        client_mock.get.side_effect = [
            collection_response,
            members_response,
            direct_parts_response,
            no_deeper_parts_response,
        ]

        with tempfile.TemporaryDirectory() as temporary_directory:
            output_path = Path(temporary_directory) / 'collection-parts.csv'

            result = csv_creator.create_csv(
                'https://example.test/api',
                'bdr:collection',
                output_path,
                'ignored reason',
                True,
                include_all_has_parts=True,
            )

            with output_path.open(encoding='utf-8', newline='') as output_file:
                rows = list(csv.reader(output_file))

        self.assertEqual(
            [
                ['bdr:collection', 'Sample Collection collection'],
                ['bdr:primary', 'member of Sample Collection collection'],
                ['bdr:existing-part', 'part of bdr:primary'],
                ['bdr:new-part', 'part of bdr:primary'],
                ['bdr:subcollection', 'collection-member of Sample Collection collection'],
            ],
            rows,
        )
        self.assertEqual(('bdr:subcollection',), result.skipped_subcollection_pids)
        direct_query = client_mock.get.call_args_list[2].kwargs['params']['q']
        self.assertIn('bdr:primary', direct_query)
        self.assertNotIn('bdr:subcollection', direct_query)
        self.assertNotIn('bdr:existing-part', direct_query)

    def test_terminal_notices_display_compiled_pids(self) -> None:
        """
        Checks terminal summaries list deeper parents and skipped sub-collections.
        """
        result = CsvCreationResult(4, ('bdr:part1',), ('bdr:subcollection',))

        with patch('builtins.print') as print_mock:
            terminal.display_terminal_notices(result)

        self.assertEqual(
            [
                call('PIDs with parts that were not included because only direct parts are added:'),
                call('  bdr:part1'),
                call('Sub-collection PIDs whose contents were not processed:'),
                call('  bdr:subcollection'),
            ],
            print_mock.call_args_list,
        )

    def test_collection_lookup_failure_has_clear_error(self) -> None:
        """
        Checks that a PID not accepted by the collection API produces a readable error.
        """
        response = httpx.Response(
            404,
            request=httpx.Request('GET', 'https://example.test/collection'),
            text='Not Found',
        )
        transport = httpx.MockTransport(lambda request: response)

        with (
            httpx.Client(transport=transport) as client,
            self.assertRaisesRegex(
                PidToCsvError,
                'Collection lookup for bdr:not-a-collection failed with HTTP status 404',
            ),
        ):
            bdr_api.fetch_collection_name(client, 'https://example.test/api', 'bdr:not-a-collection')


if __name__ == '__main__':
    unittest.main()
