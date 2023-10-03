# (c) 2012-2014, Michael DeHaan <michael.dehaan@gmail.com>
#
# This file is part of Ansible
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible.  If not, see <http://www.gnu.org/licenses/>.

# Make coding more python3-ish
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import ansible.constants as C
from ansible.errors import AnsibleParserError
from ansible.playbook.block import Block
from ansible.playbook.task import Task
from ansible.utils.display import Display
from ansible.utils.sentinel import Sentinel

__all__ = ['TaskInclude']

display = Display()


class TaskInclude(Task):

    """
    A task include is derived from a regular task to handle the special
    circumstances related to the `- include_*: ...` task.
    """

    BASE = frozenset(('file', '_raw_params'))  # directly assigned
    OTHER_ARGS = frozenset(('apply',))  # assigned to matching property
    VALID_ARGS = BASE.union(OTHER_ARGS)  # all valid args
    VALID_INCLUDE_KEYWORDS = frozenset(('action', 'args', 'collections', 'debugger', 'ignore_errors', 'loop', 'loop_control',
                                        'loop_with', 'name', 'no_log', 'register', 'run_once', 'tags', 'timeout', 'vars',
                                        'when'))

    def __init__(self, block=None, role=None, task_include=None):
        super(TaskInclude, self).__init__(block=block, role=role, task_include=task_include)
        self.statically_loaded = False

    @staticmethod
    def load(data, block=None, role=None, task_include=None, variable_manager=None, loader=None):
        ti = TaskInclude(block=block, role=role, task_include=task_include)
        task = ti.check_options(
            ti.load_data(data, variable_manager=variable_manager, loader=loader),
            data
        )

        return task

    def check_options(self, task, data):
        '''
        Method for options validation to use in 'load_data' for TaskInclude and HandlerTaskInclude
        since they share the same validations. It is not named 'validate_options' on purpose
        to prevent confusion with '_validate_*" methods. Note that the task passed might be changed
        as a side-effect of this method.
        '''
        my_arg_names = frozenset(task.args.keys())

        # validate bad args, otherwise we silently ignore
        bad_opts = my_arg_names.difference(self.VALID_ARGS)
        if bad_opts and task.action in C._ACTION_ALL_PROPER_INCLUDE_IMPORT_TASKS:
            raise AnsibleParserError('Invalid options for %s: %s' % (task.action, ','.join(list(bad_opts))), obj=data)

        if not task.args.get('_raw_params'):
            task.args['_raw_params'] = task.args.pop('file', None)
            if not task.args['_raw_params']:
                raise AnsibleParserError('No file specified for %s' % task.action)

        apply_attrs = task.args.get('apply', {})
        if apply_attrs and task.action not in C._ACTION_INCLUDE_TASKS:
            raise AnsibleParserError('Invalid options for %s: apply' % task.action, obj=data)
        elif not isinstance(apply_attrs, dict):
            raise AnsibleParserError('Expected a dict for apply but got %s instead' % type(apply_attrs), obj=data)

        return task

    def preprocess_data(self, ds):
        """
        Preprocess the given data by checking for invalid attributes and ignoring them.

        This method takes the given data and checks for attributes that are not
        included in the VALID_INCLUDE_KEYWORDS list. If an attribute is found, and
        it is not an 'include' attribute, and the 'action' attribute is in the
        C._ACTION_ALL_INCLUDE_ROLE_TASKS list, the attribute is considered invalid and
        will be ignored. If the C.INVALID_TASK_ATTRIBUTE_FAILED is True, an
        AnsibleParserError exception will be raised. Otherwise, a warning message will
        be displayed.

        Parameters:
            ds (dict): The data to be preprocessed.

        Returns:
            dict: The preprocessed data.
        """
        ds = super(TaskInclude, self).preprocess_data(ds)

        diff = set(ds.keys()).difference(self.VALID_INCLUDE_KEYWORDS)
        for k in diff:
            # This check doesn't handle ``include`` as we have no idea at this point if it is static or not
            if ds[k] is not Sentinel and ds['action'] in C._ACTION_ALL_INCLUDE_ROLE_TASKS:
                if C.INVALID_TASK_ATTRIBUTE_FAILED:
                    raise AnsibleParserError("'%s' is not a valid attribute for a %s" % (k, self.__class__.__name__), obj=ds)
                else:
                    display.warning("Ignoring invalid attribute: %s" % k)

        return ds

    def copy(self, exclude_parent=False, exclude_tasks=False):
        """
        Create a new instance of the TaskInclude class and copy attributes from the
        original instance.

        This method creates a new instance of the TaskInclude class and copies the
        attributes from the original instance. The 'exclude_parent' and
        'exclude_tasks' parameters can be used to exclude certain attributes from
        being copied.

        Parameters:
            exclude_parent (bool): Whether to exclude parent attributes.
            exclude_tasks (bool): Whether to exclude task attributes.

        Returns:
            TaskInclude: The copied instance.
        """
        new_me = super(TaskInclude, self).copy(exclude_parent=exclude_parent, exclude_tasks=exclude_tasks)
        new_me.statically_loaded = self.statically_loaded
        return new_me

    def build_parent_block(self):
        '''
        This method is used to create the parent block for the included tasks
        when ``apply`` is specified
        '''
        apply_attrs = self.args.pop('apply', {})
        if apply_attrs:
            apply_attrs['block'] = []
            p_block = Block.load(
                apply_attrs,
                play=self._parent._play,
                task_include=self,
                role=self._role,
                variable_manager=self._variable_manager,
                loader=self._loader,
            )
        else:
            p_block = self

        return p_block
