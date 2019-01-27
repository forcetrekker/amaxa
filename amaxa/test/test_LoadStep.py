import unittest
import json
from unittest.mock import Mock, MagicMock, PropertyMock, patch
from salesforce_bulk import UploadResult
from .. import amaxa


class test_LoadStep(unittest.TestCase):
    def test_stores_lookup_behaviors(self):
        l = amaxa.LoadStep('Account', ['Name', 'ParentId'])

        self.assertEqual(amaxa.OutsideLookupBehavior.INCLUDE, l.get_lookup_behavior_for_field('ParentId'))

        l.set_lookup_behavior_for_field('ParentId', amaxa.OutsideLookupBehavior.ERROR)
        self.assertEqual(amaxa.OutsideLookupBehavior.ERROR, l.get_lookup_behavior_for_field('ParentId'))

    def test_get_value_for_lookup_with_parent_available(self):
        connection = Mock()
        op = amaxa.LoadOperation(connection)
        op.register_new_id('Account', amaxa.SalesforceId('001000000000000'), amaxa.SalesforceId('001000000000001'))

        l = amaxa.LoadStep('Account', ['Name', 'ParentId'])
        l.context = op

        self.assertEqual(
            l.get_value_for_lookup('ParentId', '001000000000000', '001000000000002'),
            str(amaxa.SalesforceId('001000000000001'))
        )

    def test_get_value_for_lookup_with_blank_input(self):
        connection = Mock()
        op = amaxa.LoadOperation(connection)

        l = amaxa.LoadStep('Account', ['Name', 'ParentId'])
        l.context = op

        self.assertEqual(
            l.get_value_for_lookup('ParentId', '', '001000000000002'),
            ''
        )

    def test_get_value_for_lookup_with_include_behavior(self):
        connection = Mock()
        op = amaxa.LoadOperation(connection)

        l = amaxa.LoadStep('Account', ['Name', 'ParentId'])
        l.context = op

        self.assertEqual(
            l.get_value_for_lookup('ParentId', '001000000000000', '001000000000002'),
            '001000000000000'
        )

    def test_get_value_for_lookup_with_drop_behavior(self):
        connection = Mock()
        op = amaxa.LoadOperation(connection)

        l = amaxa.LoadStep('Account', ['Name', 'ParentId'])
        l.context = op

        l.set_lookup_behavior_for_field('ParentId', amaxa.OutsideLookupBehavior.DROP_FIELD)

        self.assertEqual(
            l.get_value_for_lookup('ParentId', '001000000000000', '001000000000002'),
            ''
        )

    def test_get_value_for_lookup_with_error_behavior(self):
        connection = Mock()
        op = amaxa.LoadOperation(connection)

        l = amaxa.LoadStep('Account', ['Name', 'ParentId'])
        l.context = op

        l.set_lookup_behavior_for_field('ParentId', amaxa.OutsideLookupBehavior.ERROR)


        with self.assertRaises(amaxa.AmaxaException, msg='{} {} has an outside reference in field {} ({}), which is not allowed by the extraction configuration.'.format(
                    'Account',
                    '001000000000002',
                    'ParentId',
                    '001000000000000'
                )
            ):
            l.get_value_for_lookup('ParentId', '001000000000000', '001000000000002')

    def test_populates_lookups(self):
        l = amaxa.LoadStep('Account', ['Name', 'ParentId'])
        l.get_value_for_lookup = Mock(return_value='001000000000002')

        record = {
            'Id': '001000000000000',
            'Name': 'Test',
            'ParentId': '001000000000001'
        }

        self.assertEqual(
            {
                'Id': '001000000000000',
                'Name': 'Test',
                'ParentId': '001000000000002'
            },
            l.populate_lookups(record, ['ParentId'], '001000000000000')
        )

    def test_converts_data_for_bulk_api(self):
        connection = Mock()
        op = amaxa.LoadOperation(connection)
        op.get_field_map = Mock(return_value={
            'Name': { 'soapType': 'xsd:string' },
            'Boolean__c': { 'soapType': 'xsd:boolean' },
            'Id': { 'soapType': 'tns:ID' },
            'Date__c': { 'soapType': 'xsd:date' },
            'DateTime__c': { 'soapType': 'xsd:dateTime' },
            'Int__c': { 'soapType': 'xsd:int' },
            'Double__c': { 'soapType': 'xsd:double' },
            'Random__c': { 'soapType': 'xsd:string' }
        })

        l = amaxa.LoadStep('Account', ['Name', 'ParentId'])
        l.context = op

        record = {
            'Name': 'Test',
            'Boolean__c': 'yes',
            'Id': '001000000000001',
            'Date__c': '2018-12-31',
            'DateTime__c': '2018-12-31T00:00:00.000Z',
            'Int__c': '100',
            'Double__c': '10.1',
            'Random__c': ''
        }

        self.assertEqual(
            {
                'Name': 'Test',
                'Boolean__c': 'true',
                'Id': '001000000000001',
                'Date__c': '2018-12-31',
                'DateTime__c': '2018-12-31T00:00:00.000Z',
                'Int__c': '100',
                'Double__c': '10.1',
                'Random__c': None
            },
            l.primitivize(record)
        )

    def test_transform_records_calls_context_mapper(self):
        connection = Mock()
        op = amaxa.LoadOperation(connection)
        op.mappers['Account'] = Mock()
        op.mappers['Account'].transform_record = Mock(
            return_value={
                'Name': 'Test2',
                'ParentId': '001000000000001'
            }
        )

        l = amaxa.LoadStep('Account', ['Name', 'ParentId'])
        l.context = op
        l.dependent_lookups = set()
        l.self_lookups = set()

        self.assertEqual(
            {
                'Name': 'Test2',
                'ParentId': '001000000000001'
            },
            l.transform_record(
                {
                    'Name': 'Test1',
                    'ParentId': '001000000000000'
                }
            )
        )
        op.mappers['Account'].transform_record.assert_called_once_with(
            {
                'Name': 'Test1',
                'ParentId': '001000000000000'
            }
        )

    def test_transform_records_cleans_excess_fields(self):
        connection = Mock()
        op = amaxa.LoadOperation(connection)

        l = amaxa.LoadStep('Account', ['Name', 'ParentId'])
        l.context = op
        l.dependent_lookups = set()
        l.self_lookups = set()

        self.assertEqual(
            {
                'Name': 'Test2',
                'ParentId': '001000000000001'
            },
            l.transform_record(
                {
                    'Name': 'Test2',
                    'ParentId': '001000000000001',
                    'Excess__c': True
                }
            )
        )

    def test_transform_records_runs_transform_before_cleaning(self):
        connection = Mock()
        op = amaxa.LoadOperation(connection)
        op.mappers['Account'] = Mock()
        op.mappers['Account'].transform_record = Mock(
            return_value={
                'Name': 'Test2',
                'ParentId': '001000000000001',
                'Excess__c': True
            }
        )

        l = amaxa.LoadStep('Account', ['Name', 'ParentId'])
        l.context = op
        l.dependent_lookups = set()
        l.self_lookups = set()

        self.assertEqual(
            {
                'Name': 'Test2',
                'ParentId': '001000000000001'
            },
            l.transform_record(
                {
                    'Account Name': 'Test2',
                    'ParentId': '001000000000001',
                    'Excess__c': True
                }
            )
        )
    def test_extract_dependent_lookups_returns_dependent_fields(self):
        l = amaxa.LoadStep('Account', ['Id', 'Name', 'ParentId'])
        l.self_lookups = set(['ParentId'])
        l.dependent_lookups = set()

        self.assertEqual(
            {
                'Id': '001000000000001',
                'ParentId': '001000000000002',
            },
            l.extract_dependent_lookups(
                {
                    'Name': 'Gemenon Gastronomics',
                    'Id': '001000000000001',
                    'ParentId': '001000000000002',
                }
            )
        )

    def test_clean_dependent_lookups_returns_clean_record(self):
        l = amaxa.LoadStep('Account', ['Id', 'Name', 'ParentId'])
        l.self_lookups = set(['ParentId'])
        l.dependent_lookups = set()

        self.assertEqual(
            {
                'Name': 'Gemenon Gastronomics',
                'Id': '001000000000001'
            },
            l.clean_dependent_lookups(
                {
                    'Name': 'Gemenon Gastronomics',
                    'Id': '001000000000001',
                    'ParentId': '001000000000002'
                }
            )
        )

    @patch('amaxa.LoadOperation.bulk', new_callable=PropertyMock())
    @patch.object(amaxa, 'JSONIterator')
    def test_execute_transforms_and_loads_records_without_lookups(self, json_iterator_proxy, bulk_proxy):
        record_list = [
            { 'Name': 'Test', 'Id': '001000000000000' },
            { 'Name': 'Test 2', 'Id': '001000000000001' }
        ]
        clean_record_list = [
            { 'Name': 'Test' },
            { 'Name': 'Test 2' }
        ]
        connection = Mock()
        op = amaxa.LoadOperation(connection)
        op.get_field_map = Mock(return_value={
            'Name': { 'type': 'string '},
            'Id': { 'type': 'string' }
        })
        op.register_new_id = Mock()
        op.get_input_file = Mock(
            return_value=record_list
        )
        op.get_result_file = Mock()
        bulk_proxy.get_batch_results = Mock(
            return_value=[
                UploadResult('001000000000002', True, True, ''),
                UploadResult('001000000000003', True, True, '')
            ]
        )
        op.mappers['Account'] = Mock()
        op.mappers['Account'].transform_record = Mock(side_effect=lambda x: x)

        l = amaxa.LoadStep('Account', ['Name'])
        l.context = op
        l.primitivize = Mock(side_effect=lambda x: x)
        l.populate_lookups = Mock(side_effect=lambda x, y, z: x)

        l.scan_fields()
        l.execute()

        op.mappers['Account'].transform_record.assert_has_calls([unittest.mock.call(x) for x in record_list])
        l.primitivize.assert_has_calls([unittest.mock.call(x) for x in clean_record_list])
        l.populate_lookups.assert_has_calls(
            [unittest.mock.call(x, set(), y['Id']) for (x, y) in zip(clean_record_list, record_list)]
        )

        json_iterator_proxy.assert_called_once_with(clean_record_list)
        bulk_proxy.post_batch.assert_called_once_with(
            bulk_proxy.create_insert_job.return_value,
            json_iterator_proxy.return_value
        )
        op.register_new_id.assert_has_calls(
            [
                unittest.mock.call('Account', amaxa.SalesforceId('001000000000000'), amaxa.SalesforceId('001000000000002')),
                unittest.mock.call('Account', amaxa.SalesforceId('001000000000001'), amaxa.SalesforceId('001000000000003'))
            ]
        )

    @patch('amaxa.LoadOperation.bulk', new_callable=PropertyMock())
    @patch.object(amaxa, 'JSONIterator')
    def test_execute_transforms_and_loads_records_with_lookups(self, json_iterator_proxy, bulk_proxy):
        record_list = [
            { 'Name': 'Test', 'Id': '001000000000000', 'Lookup__c': '003000000000000' },
            { 'Name': 'Test 2', 'Id': '001000000000001', 'Lookup__c': '003000000000001'}
        ]
        transformed_record_list = [
            { 'Name': 'Test', 'Lookup__c': str(amaxa.SalesforceId('003000000000002')) },
            { 'Name': 'Test 2', 'Lookup__c': str(amaxa.SalesforceId('003000000000003')) }
        ]

        connection = Mock()
        op = amaxa.LoadOperation(connection)
        op.get_field_map = Mock(return_value={
            'Name': { 'type': 'string '},
            'Id': { 'type': 'string' },
            'Lookup__c': { 'type': 'string' }
        })

        op.register_new_id('Account', amaxa.SalesforceId('003000000000000'), amaxa.SalesforceId('003000000000002'))
        op.register_new_id('Account', amaxa.SalesforceId('003000000000001'), amaxa.SalesforceId('003000000000003'))

        op.register_new_id = Mock()
        op.get_input_file = Mock(
            return_value=record_list
        )
        op.get_result_file = Mock()
        bulk_proxy.get_batch_results = Mock(
            return_value=[
                UploadResult('001000000000002', True, True, ''),
                UploadResult('001000000000003', True, True, '')
            ]
        )
        bulk_proxy.create_insert_job = Mock(return_value=Mock())
        op.mappers['Account'] = Mock()
        op.mappers['Account'].transform_record = Mock(side_effect=lambda x: x)

        l = amaxa.LoadStep('Account', ['Name', 'Lookup__c'])
        l.context = op
        l.primitivize = Mock(side_effect=lambda x: x)

        l.scan_fields()
        l.descendent_lookups = set(['Lookup__c'])

        l.execute()

        op.mappers['Account'].transform_record.assert_has_calls([unittest.mock.call(x) for x in record_list])
        l.primitivize.assert_has_calls([unittest.mock.call(x) for x in transformed_record_list])

        json_iterator_proxy.assert_called_once_with(transformed_record_list)
        bulk_proxy.post_batch.assert_called_once_with(
            bulk_proxy.create_insert_job.return_value,
            json_iterator_proxy.return_value
        )
        op.register_new_id.assert_has_calls(
            [
                unittest.mock.call('Account', amaxa.SalesforceId('001000000000000'), amaxa.SalesforceId('001000000000002')),
                unittest.mock.call('Account', amaxa.SalesforceId('001000000000001'), amaxa.SalesforceId('001000000000003'))
            ]
        )

    @patch('amaxa.LoadOperation.bulk', new_callable=PropertyMock())
    @patch.object(amaxa, 'JSONIterator')
    def test_execute_loads_cleaned_records(self, json_iterator_proxy, bulk_proxy):
        record_list = [
            { 'Name': 'Test', 'Id': '001000000000000', 'ParentId': '001000000000001' },
            { 'Name': 'Test 2', 'Id': '001000000000001', 'ParentId': ''}
        ]
        cleaned_record_list = [
            { 'Name': 'Test' },
            { 'Name': 'Test 2' }
        ]

        connection = Mock()
        op = amaxa.LoadOperation(connection)
        op.get_field_map = Mock(return_value={
            'Name': { 'type': 'string '},
            'Id': { 'type': 'string' },
            'ParentId': { 'type': 'string' }
        })

        op.get_input_file = Mock(
            return_value=record_list
        )
        op.get_result_file = Mock()
        bulk_proxy.get_batch_results = Mock(
            return_value=[
                UploadResult('001000000000002', True, True, ''),
                UploadResult('001000000000003', True, True, '')
            ]
        )
        bulk_proxy.create_insert_job = Mock(return_value=Mock())
        op.mappers['Account'] = Mock()
        op.mappers['Account'].transform_record = Mock(side_effect=lambda x: x)

        l = amaxa.LoadStep('Account', ['Name', 'ParentId'])
        l.context = op
        l.primitivize = Mock(side_effect=lambda x: x)

        l.scan_fields()
        l.self_lookups = set(['ParentId'])

        l.execute()

        op.mappers['Account'].transform_record.assert_has_calls([unittest.mock.call(x) for x in record_list])
        l.primitivize.assert_has_calls([unittest.mock.call(x) for x in cleaned_record_list])

        json_iterator_proxy.assert_called_once_with(cleaned_record_list)
        bulk_proxy.post_batch.assert_called_once_with(
            bulk_proxy.create_insert_job.return_value,
            json_iterator_proxy.return_value
        )

    @patch('amaxa.LoadOperation.bulk', new_callable=PropertyMock())
    def test_execute_accumulates_cleaned_dependent_records(self, bulk_proxy):
        record_list = [
            { 'Name': 'Test', 'Id': '001000000000000', 'ParentId': '001000000000001' },
            { 'Name': 'Test 2', 'Id': '001000000000001', 'ParentId': ''}
        ]
        cleaned_record_list = [
            { 'Id': '001000000000000', 'ParentId': '001000000000001' }
        ]

        connection = Mock()
        op = amaxa.LoadOperation(connection)
        op.get_field_map = Mock(return_value={
            'Name': { 'type': 'string '},
            'Id': { 'type': 'string' },
            'ParentId': { 'type': 'string' }
        })

        op.get_input_file = Mock(
            return_value=record_list
        )
        op.get_result_file = Mock()
        bulk_proxy.get_batch_results = Mock(
            return_value=[
                UploadResult('001000000000002', True, True, ''),
                UploadResult('001000000000003', True, True, '')
            ]
        )
        op.mappers['Account'] = Mock()
        op.mappers['Account'].transform_record = Mock(side_effect=lambda x: x)

        l = amaxa.LoadStep('Account', ['Name', 'ParentId'])
        l.context = op
        l.primitivize = Mock(side_effect=lambda x: x)

        l.scan_fields()
        l.self_lookups = set(['ParentId'])

        l.execute()

        self.assertEqual(cleaned_record_list, l.dependent_lookup_records)

    @patch('amaxa.LoadOperation.bulk', new_callable=PropertyMock())
    def test_execute_handles_errors(self, bulk_proxy):
        record_list = [
            { 'Name': 'Test', 'Id': '001000000000000' },
            { 'Name': 'Test 2', 'Id': '001000000000001' }
        ]
        connection = Mock()
        op = amaxa.LoadOperation(connection)
        op.get_field_map = Mock(return_value={
            'Name': { 'soapType': 'xsd:string', 'type': 'string' },
            'Id': { 'soapType': 'xsd:string', 'type': 'string' }
        })
        op.register_new_id = Mock()
        op.get_input_file = Mock(
            return_value=record_list
        )
        error = 'DUPLICATES_DETECTED'
        bulk_proxy.get_batch_results = Mock(
            return_value=[
                UploadResult(None, False, False, error),
                UploadResult(None, False, False, error)
            ]
        )

        l = amaxa.LoadStep('Account', ['Name'])
        l.context = op

        l.scan_fields()
        l.execute()

        self.assertEqual(
            {
                record_list[0]['Id']: 'Failed to load {} {}: {}'.format('Account', record_list[0]['Id'], error),
                record_list[1]['Id']: 'Failed to load {} {}: {}'.format('Account', record_list[1]['Id'], error)
            },
            l.errors
        )

    @patch('amaxa.LoadOperation.bulk', new_callable=PropertyMock())
    @patch.object(amaxa, 'JSONIterator')
    def test_execute_dependent_updates_handles_lookups(self, json_iterator_proxy, bulk_proxy):
        record_list = [
            { 'Name': 'Test', 'Id': '001000000000000', 'Lookup__c': '001000000000001' },
            { 'Name': 'Test 2', 'Id': '001000000000001', 'Lookup__c': '001000000000000'}
        ]
        cleaned_record_list = [
            { 'Id': '001000000000000', 'Lookup__c': '001000000000001' },
            { 'Id': '001000000000001', 'Lookup__c': '001000000000000'}
        ]
        transformed_record_list = [
            { 'Id': str(amaxa.SalesforceId('001000000000002')), 'Lookup__c': str(amaxa.SalesforceId('001000000000003')) },
            { 'Id': str(amaxa.SalesforceId('001000000000003')), 'Lookup__c': str(amaxa.SalesforceId('001000000000002')) }
        ]

        connection = Mock()
        op = amaxa.LoadOperation(connection)
        op.get_field_map = Mock(return_value={
            'Name': { 'type': 'string '},
            'Id': { 'type': 'string' },
            'Lookup__c': { 'type': 'string' }
        })

        op.register_new_id('Account', amaxa.SalesforceId('001000000000000'), amaxa.SalesforceId('001000000000002'))
        op.register_new_id('Account', amaxa.SalesforceId('001000000000001'), amaxa.SalesforceId('001000000000003'))

        op.register_new_id = Mock()
        op.get_input_file = Mock(
            return_value=record_list
        )
        bulk_proxy.get_batch_results = Mock(
            return_value=[
                UploadResult('001000000000002', True, True, ''),
                UploadResult('001000000000003', True, True, '')
            ]
        )

        l = amaxa.LoadStep('Account', ['Name', 'Lookup__c'])
        l.context = op

        l.scan_fields()
        l.self_lookups = set(['Lookup__c'])
        l.dependent_lookup_records = cleaned_record_list
        l.execute_dependent_updates()
        self.assertEqual({}, l.errors, 'no errors')
        bulk_proxy.create_update_job.assert_called_once_with('Account', contentType='JSON')
        json_iterator_proxy.assert_called_once_with(transformed_record_list)
        bulk_proxy.post_batch.assert_called_once_with(
            bulk_proxy.create_update_job.return_value, 
            json_iterator_proxy.return_value
        )

    @patch('amaxa.LoadOperation.bulk', new_callable=PropertyMock())
    def test_execute_dependent_updates_handles_errors(self, bulk_proxy):
        record_list = [
            { 'Name': 'Test', 'Id': '001000000000000', 'Lookup__c': '001000000000001' },
            { 'Name': 'Test 2', 'Id': '001000000000001', 'Lookup__c': '001000000000000' }
        ]
        dependent_record_list = [
            { 'Id': '001000000000000', 'Lookup__c': '001000000000001' },
            { 'Id': '001000000000001', 'Lookup__c': '001000000000000' }
        ]

        connection = Mock()
        op = amaxa.LoadOperation(connection)
        op.get_field_map = Mock(return_value={
            'Name': { 'type': 'string '},
            'Id': { 'type': 'string' },
            'Lookup__c': { 'type': 'string' }
        })

        op.register_new_id('Account', amaxa.SalesforceId('001000000000000'), amaxa.SalesforceId('001000000000002'))
        op.register_new_id('Account', amaxa.SalesforceId('001000000000001'), amaxa.SalesforceId('001000000000003'))

        op.register_new_id = Mock()
        op.get_input_file = Mock(
            return_value=record_list
        )
        error = 'DUPLICATES_DETECTED'
        bulk_proxy.get_batch_results = Mock(
            return_value=[
                UploadResult(None, False, False, error),
                UploadResult(None, False, False, error)
            ]
        )

        l = amaxa.LoadStep('Account', ['Name', 'Lookup__c'])
        l.context = op

        l.scan_fields()
        l.self_lookups = set(['Lookup__c'])
        l.dependent_lookup_records = dependent_record_list

        l.execute_dependent_updates()

        self.assertEqual(
            {
                record_list[0]['Id']: 'Failed to execute dependent updates for {} {}: {}'.format('Account', record_list[0]['Id'], error),
                record_list[1]['Id']: 'Failed to execute dependent updates for {} {}: {}'.format('Account', record_list[1]['Id'], error)
            },
            l.errors
        )