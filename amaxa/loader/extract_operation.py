import csv
import cerberus
import logging
from .core_loader import InputType, OperationLoader
from .. import amaxa
from .. import constants
from .. import transforms

class ExtractionOperationLoader(OperationLoader):
    def __init__(self, in_dict, connection):
        super().__init__(self, in_dict, connection, InputType.EXTRACT_OPERATION)

    def _validate(self):
        self._validate_sobjects('queryable')
        self._validate_field_mapping()

    def _load(self):
        # Create the core operation
        self.result = amaxa.ExtractOperation(self.connection)

        # Create the steps and data mappers
        for entry in self.input['operation']:
            sobject = entry['sobject']

            self.result.mappers[sobject] = self._get_data_mapper(entry, 'field', 'column')

            # Determine the type of extraction
            query = None
            to_extract = entry.get('extract')

            if 'ids' in to_extract:
                # Register the required IDs in the context
                try:
                    for id in to_extract.get('ids'):
                        self.result.add_dependency(sobject, amaxa.SalesforceId(id))
                except ValueError:
                    self.errors.append(
                        'One or more invalid Id values provided for sObject {}'.format(sobject))

                scope = amaxa.ExtractionScope.SELECTED_RECORDS
            elif 'query' in to_extract:
                query = to_extract['query']
                scope = amaxa.ExtractionScope.QUERY
            elif 'all' in to_extract:
                scope = amaxa.ExtractionScope.ALL_RECORDS
            else:
                scope = amaxa.ExtractionScope.DESCENDENTS

            field_scope = self._get_field_scope(entry)
            field_scope.add('Id')

            step = amaxa.ExtractionStep(
                sobject,
                scope,
                field_scope,
                query,
                amaxa.SelfLookupBehavior.values_dict()[entry['self-lookup-behavior']],
                amaxa.OutsideLookupBehavior.values_dict()[entry['outside-lookup-behavior']]
            )

            self._populate_lookup_behaviors(step, entry)
            self.result.add_step(step)

    def _get_field_scope(self, entry):
        # Use the 'field-group' or 'field' items to derive the field scope

        if 'field-group' in entry:
            # Don't include types we don't process: geolocations, addresses, and base64 fields.
            if entry['field-group'] in ['readable', 'smart']:
                lam = lambda f: f['type'] not in ['location', 'address', 'base64']
            else:
                lam = lambda f: f['createable'] and f['type'] not in ['location', 'address', 'base64']

            return set(self.result.get_filtered_field_map(entry['sobject'], lam).keys())
        else:
            # Build the field scope, taking flat lists and maps into account.
            return {f if isinstance(f, str) else f['field'] for f in entry['fields']}

    def _open_files(self):
        # Open all of the output files
        # Create DictWriters and populate them in the context
        for (step, entry) in zip(self.result.steps, self.input['operation']):
            try:
                file_handle = open(entry['file'], 'w')
                if step.sobjectname not in self.result.mappers:
                    fieldnames = step.field_scope
                else:
                    fieldnames = [self.result.mappers[step.sobjectname].transform_key(k) for k in step.field_scope]

                output = csv.DictWriter(
                    file_handle,
                    fieldnames=sorted(fieldnames, key=lambda x: x if x != 'Id' else ' Id'),
                    extrasaction='ignore'
                )
                output.writeheader()
                self.result.file_store.set_file(step.sobjectname, amaxa.FileType.OUTPUT, file_handle)
                self.result.file_store.set_csv(step.sobjectname, amaxa.FileType.OUTPUT, output)
            except Exception as exp:
                self.errors.append(
                    'Unable to open file {} for writing ({}).'.format(entry['file'], exp)
                )