# -*- coding: utf-8 -*-
'''
Azure (ARM) Resource State Module

.. versionadded:: 2019.2.0

:maintainer: <devops@eitr.tech>
:maturity: new
:depends:
    * `azure <https://pypi.python.org/pypi/azure>`_ >= 2.0.0
    * `azure-common <https://pypi.python.org/pypi/azure-common>`_ >= 1.1.8
    * `azure-mgmt <https://pypi.python.org/pypi/azure-mgmt>`_ >= 1.0.0
    * `azure-mgmt-compute <https://pypi.python.org/pypi/azure-mgmt-compute>`_ >= 1.0.0
    * `azure-mgmt-network <https://pypi.python.org/pypi/azure-mgmt-network>`_ >= 1.7.1
    * `azure-mgmt-resource <https://pypi.python.org/pypi/azure-mgmt-resource>`_ >= 1.1.0
    * `azure-mgmt-storage <https://pypi.python.org/pypi/azure-mgmt-storage>`_ >= 1.0.0
    * `azure-mgmt-web <https://pypi.python.org/pypi/azure-mgmt-web>`_ >= 0.32.0
    * `azure-storage <https://pypi.python.org/pypi/azure-storage>`_ >= 0.34.3
    * `msrestazure <https://pypi.python.org/pypi/msrestazure>`_ >= 0.4.21
:platform: linux

:configuration: This module requires Azure Resource Manager credentials to be passed as a dictionary of
    keyword arguments to the ``connection_auth`` parameter in order to work properly. Since the authentication
    parameters are sensitive, it's recommended to pass them to the states via pillar.

    Required provider parameters:

    if using username and password:
      * ``subscription_id``
      * ``username``
      * ``password``

    if using a service principal:
      * ``subscription_id``
      * ``tenant``
      * ``client_id``
      * ``secret``

    Optional provider parameters:

    **cloud_environment**: Used to point the cloud driver to different API endpoints, such as Azure GovCloud. Possible values:
      * ``AZURE_PUBLIC_CLOUD`` (default)
      * ``AZURE_CHINA_CLOUD``
      * ``AZURE_US_GOV_CLOUD``
      * ``AZURE_GERMAN_CLOUD``

    Example Pillar for Azure Resource Manager authentication:

    .. code-block:: yaml

        azurearm:
            user_pass_auth:
                subscription_id: 3287abc8-f98a-c678-3bde-326766fd3617
                username: fletch
                password: 123pass
            mysubscription:
                subscription_id: 3287abc8-f98a-c678-3bde-326766fd3617
                tenant: ABCDEFAB-1234-ABCD-1234-ABCDEFABCDEF
                client_id: ABCDEFAB-1234-ABCD-1234-ABCDEFABCDEF
                secret: XXXXXXXXXXXXXXXXXXXXXXXX
                cloud_environment: AZURE_PUBLIC_CLOUD

    Example states using Azure Resource Manager authentication:

    .. code-block:: jinja

        {% set profile = salt['pillar.get']('azurearm:mysubscription') %}
        Ensure resource group exists:
            azurearm_resource.resource_group_present:
                - name: my_rg
                - location: westus
                - tags:
                    how_awesome: very
                    contact_name: Elmer Fudd Gantry
                - connection_auth: {{ profile }}

        Ensure resource group is absent:
            azurearm_resource.resource_group_absent:
                - name: other_rg
                - connection_auth: {{ profile }}

'''

# Import Python libs
from __future__ import absolute_import
import json
import logging

# Import Salt libs
import salt.utils.files

__virtualname__ = 'azurearm_resource'

log = logging.getLogger(__name__)


def __virtual__():
    '''
    Only make this state available if the azurearm_resource module is available.
    '''
    return __virtualname__ if 'azurearm_resource.resource_group_check_existence' in __salt__ else False


def resource_group_present(name, location, managed_by=None, tags=None, connection_auth=None, **kwargs):
    '''
    .. versionadded:: 2019.2.0

    Ensure a resource group exists.

    :param name:
        Name of the resource group.

    :param location:
        The Azure location in which to create the resource group. This value cannot be updated once
        the resource group is created.

    :param managed_by:
        The ID of the resource that manages this resource group. This value cannot be updated once
        the resource group is created.

    :param tags:
        A dictionary of strings can be passed as tag metadata to the resource group object.

    :param connection_auth:
        A dict with subscription and authentication parameters to be used in connecting to the
        Azure Resource Manager API.

    Example usage:

    .. code-block:: yaml

        Ensure resource group exists:
            azurearm_resource.resource_group_present:
                - name: group1
                - location: eastus
                - tags:
                    contact_name: Elmer Fudd Gantry
                - connection_auth: {{ profile }}

    '''
    ret = {
        'name': name,
        'result': False,
        'comment': '',
        'changes': {}
    }

    if not isinstance(connection_auth, dict):
        ret['comment'] = 'Connection information must be specified via connection_auth dictionary!'
        return ret

    group = {}

    present = __salt__['azurearm_resource.resource_group_check_existence'](name, **connection_auth)

    if present:
        group = __salt__['azurearm_resource.resource_group_get'](name, **connection_auth)
        ret['changes'] = __utils__['dictdiffer.deep_diff'](group.get('tags', {}), tags or {})

        if not ret['changes']:
            ret['result'] = True
            ret['comment'] = 'Resource group {0} is already present.'.format(name)
            return ret

        if __opts__['test']:
            ret['comment'] = 'Resource group {0} tags would be updated.'.format(name)
            ret['result'] = None
            ret['changes'] = {
                'old': group.get('tags', {}),
                'new': tags
            }
            return ret

    elif __opts__['test']:
        ret['comment'] = 'Resource group {0} would be created.'.format(name)
        ret['result'] = None
        ret['changes'] = {
            'old': {},
            'new': {
                'name': name,
                'location': location,
                'managed_by': managed_by,
                'tags': tags,
            }
        }
        return ret

    group_kwargs = kwargs.copy()
    group_kwargs.update(connection_auth)

    group = __salt__['azurearm_resource.resource_group_create_or_update'](
        name,
        location,
        managed_by=managed_by,
        tags=tags,
        **group_kwargs
    )
    present = __salt__['azurearm_resource.resource_group_check_existence'](name, **connection_auth)

    if present:
        ret['result'] = True
        ret['comment'] = 'Resource group {0} has been created.'.format(name)
        ret['changes'] = {
            'old': {},
            'new': group
        }
        return ret

    ret['comment'] = 'Failed to create resource group {0}! ({1})'.format(name, group.get('error'))
    return ret


def resource_group_absent(name, connection_auth=None):
    '''
    .. versionadded:: 2019.2.0

    Ensure a resource group does not exist in the current subscription.

    :param name:
        Name of the resource group.

    :param connection_auth:
        A dict with subscription and authentication parameters to be used in connecting to the
        Azure Resource Manager API.
    '''
    ret = {
        'name': name,
        'result': False,
        'comment': '',
        'changes': {}
    }

    if not isinstance(connection_auth, dict):
        ret['comment'] = 'Connection information must be specified via connection_auth dictionary!'
        return ret

    group = {}

    present = __salt__['azurearm_resource.resource_group_check_existence'](name, **connection_auth)

    if not present:
        ret['result'] = True
        ret['comment'] = 'Resource group {0} is already absent.'.format(name)
        return ret

    elif __opts__['test']:
        group = __salt__['azurearm_resource.resource_group_get'](name, **connection_auth)

        ret['comment'] = 'Resource group {0} would be deleted.'.format(name)
        ret['result'] = None
        ret['changes'] = {
            'old': group,
            'new': {},
        }
        return ret

    group = __salt__['azurearm_resource.resource_group_get'](name, **connection_auth)
    deleted = __salt__['azurearm_resource.resource_group_delete'](name, **connection_auth)

    if deleted:
        present = False
    else:
        present = __salt__['azurearm_resource.resource_group_check_existence'](name, **connection_auth)

    if not present:
        ret['result'] = True
        ret['comment'] = 'Resource group {0} has been deleted.'.format(name)
        ret['changes'] = {
            'old': group,
            'new': {}
        }
        return ret

    ret['comment'] = 'Failed to delete resource group {0}!'.format(name)
    return ret
