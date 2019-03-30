# Copyright 2019 Canonical Ltd
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#  http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import mock

import charm.openstack.ceph_rbd_mirror as crm
import reactive.ceph_rbd_mirror_handlers as handlers

import charms_openstack.test_utils as test_utils


class TestRegisteredHooks(test_utils.TestRegisteredHooks):

    def test_hooks(self):
        defaults = [
            'charm.installed',
            'update-status',
            'upgrade-charm',
        ]
        hook_set = {
            'when': {
                'config_changed': (
                    'config.changed',
                    'ceph-local.available',
                    'ceph-remote.available',
                ),
                'render_stuff': (
                    'ceph-local.available',
                    'ceph-remote.available',
                ),
                'configure_pools': (
                    'leadership.is_leader',
                    'config.rendered',
                    'ceph-local.available',
                    'ceph-remote.available',
                ),
                'refresh_pools': (
                    'leadership.is_leader',
                    'refresh.pools',
                    'ceph-local.available',
                    'ceph-remote.available',
                ),
            },
            'when_all': {
                'request_keys': (
                    'ceph-local.connected',
                    'ceph-remote.connected',
                ),
            },
            'when_not': {
                'disable_services': (
                    'config.rendered',
                ),
            },
            'when_not_all': {
                'request_keys': (
                    'ceph-local.available',
                    'ceph-remote.available',
                ),
            },
        }
        # test that the hooks were registered
        self.registered_hooks_test_helper(handlers, hook_set, defaults)


class TestCephRBDMirrorHandlers(test_utils.PatchHelper):

    def setUp(self):
        super().setUp()
        self.patch_release(crm.CephRBDMirrorCharm.release)
        self.crm_charm = mock.MagicMock()
        self.patch_object(handlers.charm, 'provide_charm_instance',
                          new=mock.MagicMock())
        self.provide_charm_instance().__enter__.return_value = \
            self.crm_charm
        self.provide_charm_instance().__exit__.return_value = None

    def test_request_keys(self):
        self.patch_object(handlers.reactive, 'endpoint_from_flag')
        endpoint_local = mock.MagicMock()
        endpoint_remote = mock.MagicMock()
        endpoint_local.endpoint_name = 'ceph-local'
        endpoint_remote.endpoint_name = 'ceph-remote'
        self.endpoint_from_flag.side_effect = [endpoint_local,
                                               endpoint_remote]
        handlers.request_keys()
        self.endpoint_from_flag.assert_has_calls([
            mock.call('ceph-local.connected'),
            mock.call('ceph-remote.connected'),
        ])
        endpoint_local.request_key.assert_called_once_with()
        endpoint_remote.request_key.assert_called_once_with()
        self.crm_charm.assess_status.assert_called_once_with()

    def test_config_changed(self):
        self.patch_object(handlers.reactive, 'endpoint_from_flag')
        handlers.config_changed()
        self.endpoint_from_flag.assert_has_calls([
            mock.call('ceph-local.available'),
            mock.call('ceph-remote.available'),
        ])
        self.crm_charm.upgrade_if_available.assert_called_once_with(
            [self.endpoint_from_flag(), self.endpoint_from_flag()])
        self.crm_charm.assess_status.assert_called_once_with()

    def test_disable_services(self):
        self.patch_object(handlers.ch_core.host, 'service')
        self.crm_charm.services = ['aservice']
        handlers.disable_services()
        self.service.assert_has_calls([
            mock.call('disable', 'aservice'),
            mock.call('stop', 'aservice'),
        ])
        self.crm_charm.assess_status.assert_called_once_with()

    def test_render_stuff(self):
        self.patch_object(handlers.ch_core.host, 'service')
        endpoint_local = mock.MagicMock()
        endpoint_remote = mock.MagicMock()
        endpoint_local.endpoint_name = 'ceph-local'
        endpoint_local.pools = {}
        endpoint_remote.endpoint_name = 'ceph-remote'
        endpoint_remote.pools = {}
        self.crm_charm.services = ['aservice']
        endpoint_local.key = None
        handlers.render_stuff(endpoint_local, endpoint_remote)
        self.assertFalse(self.crm_charm.configure_ceph_keyring.called)
        endpoint_local.key = 'akey'
        handlers.render_stuff(endpoint_local, endpoint_remote)
        self.crm_charm.configure_ceph_keyring.assert_has_calls([
            mock.call(endpoint_local, cluster_name=None),
            mock.call(endpoint_remote, cluster_name='remote'),
        ])
        self.crm_charm.render_with_interfaces.assert_called_once_with(
            (endpoint_local, endpoint_remote))
        self.service.assert_has_calls([
            mock.call('enable', 'aservice'),
            mock.call('start', 'aservice'),
        ])
        self.crm_charm.assess_status.assert_called_once_with()

    def test_refresh_pools(self):
        self.patch_object(handlers.reactive, 'endpoint_from_name')
        self.patch_object(handlers.reactive, 'clear_flag')
        endpoint_local = mock.MagicMock()
        endpoint_remote = mock.MagicMock()
        self.endpoint_from_name.side_effect = [endpoint_local, endpoint_remote]
        handlers.refresh_pools()
        self.endpoint_from_name.assert_has_calls([
            mock.call('ceph-local'),
            mock.call('ceph-remote'),
        ])
        endpoint_local.refresh_pools.assert_called_once_with()
        endpoint_remote.refresh_pools.assert_called_once_with()
        self.clear_flag.assert_called_once_with('refresh.pools')

    def test_configure_pools(self):
        self.patch_object(handlers.reactive, 'endpoint_from_flag')
        endpoint_local = mock.MagicMock()
        endpoint_remote = mock.MagicMock()
        endpoint_local.endpoint_name = 'ceph-local'
        endpoint_local.pools = {
            'cinder-ceph': {
                'applications': {'rbd': {}},
                'parameters': {'pg_num': 42, 'size': 3},
                'quota': {'max_bytes': 1024, 'max_objects': 51},
            },
        }
        endpoint_remote.endpoint_name = 'ceph-remote'
        self.endpoint_from_flag.side_effect = [endpoint_local,
                                               endpoint_remote]
        self.crm_charm.eligible_pools.return_value = endpoint_local.pools
        self.crm_charm.mirror_pool_enabled.return_value = False
        handlers.configure_pools()
        self.endpoint_from_flag.assert_has_calls([
            mock.call('ceph-local.available'),
            mock.call('ceph-remote.available'),
        ])
        self.crm_charm.eligible_pools.assert_called_once_with(
            endpoint_local.pools)
        self.crm_charm.mirror_pool_enabled.assert_called_once_with(
            'cinder-ceph')
        self.crm_charm.mirror_pool_enable.assert_called_once_with(
            'cinder-ceph')
        endpoint_remote.create_replicated_pool.assert_called_once_with(
            'cinder-ceph', replicas=3, pg_num=42, app_name='rbd',
            max_bytes=1024, max_objects=51)
        self.assertFalse(endpoint_remote.create_erasure_pool.called)
        self.endpoint_from_flag.side_effect = [endpoint_local,
                                               endpoint_remote]
        self.crm_charm.mirror_pool_enabled.return_value = True
        self.crm_charm.mirror_pool_has_peers.return_value = True
        self.crm_charm.mirror_pool_enabled.reset_mock()
        self.crm_charm.mirror_pool_enable.reset_mock()
        handlers.configure_pools()
        self.crm_charm.mirror_pool_enabled.assert_called_once_with(
            'cinder-ceph')
        self.crm_charm.mirror_pool_has_peers.assert_called_once_with(
            'cinder-ceph')
        self.assertFalse(self.crm_charm.mirror_pool_enable.called)
        endpoint_local.pools = {
            'cinder-ceph': {
                'applications': {'rbd': {}},
                'parameters': {'pg_num': 42, 'erasure_code_profile': 'prof'},
                'quota': {'max_bytes': 1024, 'max_objects': 51},
            },
        }
        self.endpoint_from_flag.side_effect = [endpoint_local,
                                               endpoint_remote]
        endpoint_remote.create_replicated_pool.reset_mock()
        self.crm_charm.eligible_pools.return_value = endpoint_local.pools
        handlers.configure_pools()
        endpoint_remote.create_erasure_pool.assert_called_once_with(
            'cinder-ceph', erasure_profile='prof', pg_num=42, app_name='rbd',
            max_bytes=1024, max_objects=51)
