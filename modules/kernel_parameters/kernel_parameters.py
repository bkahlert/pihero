#!/usr/bin/python
# -*- coding: utf-8 -*-
# Kernel parameters are documented here:
# https://www.kernel.org/doc/html/latest/admin-guide/kernel-parameters.html
from ansible.module_utils.basic import AnsibleModule  # noqa: 402
from ansible.module_utils.common.arg_spec import ArgumentSpecValidator  # noqa: 402
from typing import Optional  # noqa: 402


class KernelParams:
    params: list = []

    def __init__(self, cmdline: str):
        self.params = self._tokenize(cmdline)

    def _tokenize(self, input: str) -> list:
        tokens = input.split()
        parsed = []
        for token in tokens:
            option, *value = token.split("=", 1)
            parsed.append({'option': option, 'value': value if value else None})
        return parsed

    def add_param(
        self,
        option: str,
        value: Optional[str],
        before: Optional[str],
        after: Optional[str],
    ) -> 'KernelParams':
        existing_index: Optional[int] = self.exclusify_param(option)
        if existing_index is not None:
            self.params[existing_index]['value'] = value
            return self

        insertion_index: int = len(self.params)
        if after is not None:
            index = self.find_param(after)
            if index is not None:
                insertion_index = index + 1
        elif before is not None:
            index = self.find_param(before)
            if index is not None:
                insertion_index = index
        self.params.insert(insertion_index, {'option': option, 'value': value})
        return self

    # returns True if the given option is present, False otherwise
    def has_param(self, option: str) -> bool:
        for param in self.params:
            if param['option'] == option:
                return True
        return False

    # removes all params with the given option
    def remove_param(self, option: str) -> 'KernelParams':
        self.params = [param for param in self.params if param['option'] != option]
        return self

    # returns the index of the first param with the given option, or None otherwise
    def find_param(self, option: str) -> Optional[int]:
        for i, param in enumerate(self.params):
            if param['option'] == option:
                return i
        return None

    # removes all params but the first with the given option, and
    # returns the index of the kept param
    def exclusify_param(self, option: str) -> Optional[int]:
        index_kept: int = None
        params = []
        for i, param in enumerate(self.params):
            if param['option'] != option:
                params.append(param)
            elif param['option'] == option and index_kept is None:
                index_kept = i
                params.append(param)
        self.params = params
        return index_kept

    def to_string(self) -> str:
        ret = ""
        for param in self.params:
            option = param['option']
            value = param['value']
            if value is None:
                ret += f"{option} "
            elif isinstance(value, list):
                ret += f"{option}={','.join(value)} "
            else:
                ret += f"{option}={value} "
        return ret.strip()


# -------------------------------------------------------------------------- #


def run_module():
    module_args = dict(
        cmdline=dict(type='str', default="/boot/cmdline.txt"),
        option=dict(type='str'),
        value=dict(type='str', default=None),
        state=dict(type='str', default="present"),
        after=dict(type='str', default=None),
        before=dict(type='str', default=None),
    )
    mutually_exclusive = [
        ('before', 'after'),
    ]
    required_one_of = []
    required_together = []

    result = dict(
        changed=False,
        original_message='',
        message='',
    )

    module = AnsibleModule(
        argument_spec=module_args,
        mutually_exclusive=mutually_exclusive,
        required_one_of=required_one_of,
        required_together=required_together,
        supports_check_mode=False,
    )

    validator = ArgumentSpecValidator(
        argument_spec=module_args,
        mutually_exclusive=mutually_exclusive,
        required_one_of=required_one_of,
        required_together=required_together,
    )

    validation_result = validator.validate(
        {k: v for k, v in module.params.items() if v is not None}
    )

    if validation_result.error_messages:
        result['message'] = ",".join(validation_result.error_messages)
        module.fail_json(
            msg="Failed parameter validation",
            **result
        )

    filename = module.params['cmdline']
    option = module.params['option']
    value = module.params['value']
    state = module.params['state']
    after = module.params['after']
    before = module.params['before']

    try:
        with open(filename, 'r') as f:
            cmdline = f.read().strip()

        params = KernelParams(cmdline)
        if state == "present":
            params.add_param(option, value, before, after)
        elif state == "absent":
            params.remove_param(option)
        else:
            module.fail_json(msg=f"Unknown state: {state}", **result)

        new_cmdline = params.to_string()

        with open(filename, 'w') as f:
            f.write(f"{new_cmdline}")

        result['changed'] = cmdline != new_cmdline
        result['message'] = f"New cmdline: '{new_cmdline}'"
        result['original_message'] = f"Old cmdline: '{cmdline}'"
    except IOError as e:
        module.fail_json(msg=f"Unable to modify {filename}: {e}", **result)

    module.exit_json(**result)


def main():
    run_module()


if __name__ == "__main__":
    main()
