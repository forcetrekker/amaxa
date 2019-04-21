import collections
import csv
import logging
from .core_loader import InputType, OperationLoader
from .. import amaxa
from .. import constants
from .. import transforms


class LoadOperationLoader(OperationLoader):
    def __init__(self, in_dict, connection, state=None):
        super().__init__(self, in_dict, InputType.LOAD_OPERATION)
        self.connection = connection
        self.state = state

    def _validate(self):
        self._validate_sobjects('createable')
        self._validate_field_mapping()

    def _load(self):
        # Create the core operation
        self.result = amaxa.LoadOperation(self.connection)

        # Create the steps and data mappers
        for entry in self.input['operation']:
            sobject = entry['sobject']

            self.result.mappers[sobject] = self._get_data_mapper(entry, 'column', 'field')
            field_scope = self._get_field_scope(entry)
            if 'load' in entry:
                id_type = amaxa.IdType.values_dict()[entry['load']['id-mode']]
            else:
                id_type = amaxa.IdType.SALESFORCE_ID

            step = amaxa.LoadStep(
                sobject,
                field_scope,
                amaxa.OutsideLookupBehavior.values_dict()[entry['outside-lookup-behavior']],
                id_type
            )

            self._populate_lookup_behaviors(step, entry)
            self.result.add_step(step)

        self.result.initialize()
        self._open_files()

    def _get_field_scope(self, entry):
        # Use the 'field-group' or 'field' items to derive the field scope

        if 'field-group' in entry:
            # Validation clamps acceptable values to 'writeable' or 'smart' by this point.
            # Don't include types we don't process: geolocations, addresses, and base64 fields.
            # Geolocations and addresses are omitted automatically (they aren't writeable)
            lam = lambda f: f['createable'] and f['type'] != 'base64'

            return set(self.result.get_filtered_field_map(entry['sobject'], lam).keys())
        else:
            # Build the field scope, taking flat lists and maps into account.
            return {f if isinstance(f, str) else f['field'] for f in entry['fields']}

    def _open_files(self):
        # Open all of the input and output files
        # Create DictReaders and populate them in the context
        for (step, entry) in zip(self.result.steps, self.input['operation']):
            try:
                file_handle = open(entry['file'], 'r')
                input_file = csv.DictReader(file_handle)
                self.result.file_store.set_file(step.sobjectname, amaxa.FileType.INPUT, file_handle)
                self.result.file_store.set_csv(step.sobjectname, amaxa.FileType.INPUT, input_file)
            except Exception as exp:
                self.errors.append('Unable to open file {} for reading ({}).'.format(entry['file'], exp))

            try:
                f = open(entry['result-file'], 'w' if not self.state else 'a')
                output = csv.DictWriter(
                    f, 
                    fieldnames=[constants.ORIGINAL_ID, constants.NEW_ID, constants.ERROR]
                )
                if not self.state:
                    output.writeheader()

                self.result.file_store.set_file(step.sobjectname, amaxa.FileType.RESULT, f)
                self.result.file_store.set_csv(step.sobjectname, amaxa.FileType.RESULT, output)
            except Exception as exp:
                self.errors.append('Unable to open file {} for writing ({})'.format(entry['result-file'], exp))

    def _post_validate(self):
        self._validate_field_permissions('createable')
        self._validate_dependent_field_permissions()
        self._validate_lookup_behaviors()
        self._validate_input_file_columns()


    def _validate_dependent_field_permissions(self):
        # Validate that dependent lookups are updateable.
        for step in self.result.steps:
            field_map = self.result.get_field_map(step.sobjectname)
            for f in step.dependent_lookups | step.self_lookups:
                if not field_map[f]['updateable']:
                    self.errors.append('Field {}.{} is a dependent lookup, but is not updateable.'.format(step.sobjectname, f))


    def _validate_lookup_behaviors(self):
        # Validate that lookup behaviors are associated with lookups of the correct type (outside or self)
        for step in self.result.steps:
            for f in step.lookup_behaviors:
                if (f in step.dependent_lookups and step.lookup_behaviors[f] not in amaxa.OutsideLookupBehavior) \
                    or (f in step.self_lookups and step.lookup_behaviors[f] not in amaxa.SelfLookupBehavior):
                    self.errors.append('Lookup behavior \'{}\' specified for field {}.{} is not valid for this lookup type.'.format(
                        step.lookup_behaviors[f].value,
                        step.sobjectname,
                        f
                    ))

    def _validate_input_file_columns(self):
        # Validate the column sets in the input files.
        # For each file, if validation is active, check as follows.
        # For field group steps, validate that each column in the input file
        # is mapped to a field within the field group, but allow "missing" columns.
        # For explicit field list steps, require that the mapped column set and field scope be 1:1
        for (step, entry) in zip(self.result.steps, self.input['operation']):
            if entry['input-validation'] == 'none':
                continue

            input_file = self.result.file_store.get_csv(step.sobjectname, amaxa.FileType.INPUT)
            file_field_set = set(input_file.fieldnames)
            if 'Id' in file_field_set:
                file_field_set.remove('Id')

            # If we have transforms in place, transform all the column names into field names.
            if step.sobjectname in self.result.mappers:
                file_field_set = {self.result.mappers[step.sobjectname].transform_key(f) for f in file_field_set}

            if 'field-group' in entry and entry['input-validation'] == 'default':
                # Field group validation: file can omit columns but can't have extra
                # For the 'smart' field group, we permit any readable (but not writeable) fields
                # to be in the file, since the file was likely pulled with 'smart'=='readable'
                if entry['field-group'] == 'smart':
                    comparand = set(
                        self.result.get_filtered_field_map(
                            step.sobjectname,
                            lambda f: f['type'] not in ['location', 'address', 'base64']
                        ).keys()
                    )
                else:
                    comparand = step.field_scope

                if not comparand.issuperset(file_field_set):
                    self.errors.append(
                        'Input file for sObject {} contains excess columns over field group \'{}\': {}'.format(
                            step.sobjectname,
                            entry['field-group'],
                            ', '.join(sorted(file_field_set.difference(comparand)))
                        )
                    )
            else:
                # Field scope validation, or strict-mode group validation.
                # File columns must match field scope precisely.
                if step.field_scope != file_field_set:
                    self.errors.append(
                        'Input file for sObject {} does not match specified field scope.\nScope: {}\nFile Columns: {}\n'.format(
                            step.sobjectname,
                            ', '.join(sorted(step.field_scope)),
                            ', '.join(sorted(file_field_set))
                        )
                    )