# Copyright 2018 Canonical Ltd
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

import collections
import mock
import subprocess

import charms_openstack.test_utils as test_utils

import charm.openstack.ceph_rbd_mirror as ceph_rbd_mirror


class Helper(test_utils.PatchHelper):

    def setUp(self):
        super().setUp()
        self.patch_release(ceph_rbd_mirror.CephRBDMirrorCharm.release)


class TestCephRBDMirrorCharm(Helper):

    def test_custom_assess_status_check(self):
        self.patch_object(ceph_rbd_mirror.socket, 'gethostname')
        self.patch_object(ceph_rbd_mirror.reactive, 'is_flag_set')
        self.is_flag_set.return_value = False
        crmc = ceph_rbd_mirror.CephRBDMirrorCharm()
        self.assertEqual(crmc.custom_assess_status_check(), (None, None))
        self.is_flag_set.return_value = True
        self.patch_object(ceph_rbd_mirror.reactive, 'endpoint_from_flag')
        self.assertEqual(crmc.custom_assess_status_check(),
                         ('waiting', 'Waiting for pools to be created'))
        self.endpoint_from_flag.assert_called_once_with(
            'ceph-local.available')
        crmc.mirror_pools_summary = mock.MagicMock()
        crmc.mirror_pools_summary.return_value = collections.OrderedDict({
            'pool_health': collections.OrderedDict(
                {'OK': 1, 'WARN': 1, 'ERROR': 1}),
            'image_states': collections.OrderedDict(
                {'stopped': 2, 'replaying': 2}),
        })
        result = crmc.custom_assess_status_check()
        self.assertTrue('blocked' in result[0])
        # the order of which the statuses appear in the string is undefined
        self.assertTrue('OK (1)' in result[1])
        self.assertTrue('WARN (1)' in result[1])
        self.assertTrue('ERROR (1)' in result[1])
        self.assertTrue('Primary (2)' in result[1])
        self.assertTrue('Secondary (2)' in result[1])
        crmc.mirror_pools_summary.return_value = collections.OrderedDict({
            'pool_health': collections.OrderedDict({'OK': 1}),
            'image_states': collections.OrderedDict({'stopped': 2}),
        })
        self.assertEqual(crmc.custom_assess_status_check(),
                         ('active', 'Unit is ready (Pools OK (1) '
                                    'Images Primary (2))'))
        crmc.mirror_pools_summary.side_effect = subprocess.CalledProcessError(
            42, [])
        self.assertEqual(crmc.custom_assess_status_check(), (None, None))

    def test__mirror_pool_info(self):
        self.patch_object(ceph_rbd_mirror.socket, 'gethostname')
        self.patch_object(ceph_rbd_mirror.subprocess, 'check_output')
        self.gethostname.return_value = 'ahostname'
        self.check_output.return_value = '{}'
        crmc = ceph_rbd_mirror.CephRBDMirrorCharm()
        crmc._mirror_pool_info('apool')
        self.check_output.assert_called_once_with(
            ['rbd', '--id', 'rbd-mirror.ahostname', 'mirror', 'pool', 'info',
             '--format', 'json', 'apool'], universal_newlines=True)

    def test_mirror_pool_enabled(self):
        self.patch_object(ceph_rbd_mirror.socket, 'gethostname')
        crmc = ceph_rbd_mirror.CephRBDMirrorCharm()
        _mirror_pool_info = mock.MagicMock()
        _mirror_pool_info.return_value = {
            'mode': 'pool',
            'peers': [{
                'uuid': '0e4dfe58-93fc-44f8-8c74-7e700f950118',
                'cluster_name': 'remote',
                'client_name':
                    'client.rbd-mirror.juju-c50b1a-zaza-4ce96f1e7e43-12'}]
        }
        crmc._mirror_pool_info = _mirror_pool_info
        self.assertTrue(crmc.mirror_pool_enabled('apool'))
        _mirror_pool_info.assert_called_once_with('apool')
        _mirror_pool_info.return_value = {'mode': 'disabled'}
        self.assertFalse(crmc.mirror_pool_enabled('apool'))

    def test_mirror_pool_has_peers(self):
        self.patch_object(ceph_rbd_mirror.socket, 'gethostname')
        crmc = ceph_rbd_mirror.CephRBDMirrorCharm()
        _mirror_pool_info = mock.MagicMock()
        _mirror_pool_info.return_value = {
            'mode': 'pool',
            'peers': [{
                'uuid': '0e4dfe58-93fc-44f8-8c74-7e700f950118',
                'cluster_name': 'remote',
                'client_name':
                    'client.rbd-mirror.juju-c50b1a-zaza-4ce96f1e7e43-12'}]
        }
        crmc._mirror_pool_info = _mirror_pool_info
        self.assertTrue(crmc.mirror_pool_has_peers('apool'))
        _mirror_pool_info.assert_called_once_with('apool')
        _mirror_pool_info.return_value = {
            'mode': 'pool',
            'peers': []}
        self.assertFalse(crmc.mirror_pool_has_peers('apool'))
