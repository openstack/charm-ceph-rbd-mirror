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

import socket
import subprocess

import charms.reactive as reactive

import charms_openstack.charm
import charms_openstack.adapters
import charms_openstack.plugins

import charmhelpers.core as ch_core


class CephRBDMirrorCharmRelationAdapters(
        charms_openstack.adapters.OpenStackRelationAdapters):
    relation_adapters = {
        'ceph_local': charms_openstack.plugins.CephRelationAdapter,
        'ceph_remote': charms_openstack.plugins.CephRelationAdapter,
    }


class CephRBDMirrorCharm(charms_openstack.plugins.CephCharm):
    # We require Ceph 12.2 Luminous or later for HA support in the Ceph
    # rbd-mirror daemon.  Luminous appears in UCA at pike.
    release = 'pike'
    name = 'ceph-rbd-mirror'
    python_version = 3
    packages = ['rbd-mirror']
    required_relations = ['ceph-local', 'ceph-remote']
    user = 'ceph'
    group = 'ceph'
    adapters_class = CephRBDMirrorCharmRelationAdapters
    ceph_service_name_override = 'rbd-mirror'
    ceph_key_per_unit_name = True

    def __init__(self, **kwargs):
        self.ceph_id = 'rbd-mirror.{}'.format(socket.gethostname())
        self.services = [
            'ceph-rbd-mirror@{}'.format(self.ceph_id),
        ]
        self.restart_map = {
            '/etc/ceph/ceph.conf': self.services,
            '/etc/ceph/remote.conf': self.services,
        }
        super().__init__(**kwargs)

    def custom_assess_status_check(self):
        """Provide mirrored pool statistics through juju status."""
        if (reactive.is_flag_set('config.rendered') and
                reactive.is_flag_set('ceph-local.available') and
                reactive.is_flag_set('ceph-remote.available')):
            endpoint = reactive.endpoint_from_flag('ceph-local.available')
            for pool, attrs in endpoint.pools.items():
                if 'rbd' in attrs['applications']:
                    status = self.mirror_pool_status(pool)
                    ch_core.hookenv.log('DEBUG: mirror_pool_status({}) = "{}"'
                                        .format(pool, status),
                                        level=ch_core.hookenv.INFO)
        return None, None

    def _mirror_pool_info(self, pool):
        output = subprocess.check_output(['rbd', '--id', self.ceph_id,
                                          'mirror', 'pool', 'info', pool],
                                         universal_newlines=True)
        return output

    def mirror_pool_enabled(self, pool):
        return 'Mode: pool' in self._mirror_pool_info(pool)

    def mirror_pool_has_peers(self, pool):
        return 'Peers: none' not in self._mirror_pool_info(pool)

    def mirror_pool_status(self, pool):
        output = subprocess.check_output(['rbd', '--id', self.ceph_id,
                                          'mirror', 'pool', 'status', pool],
                                         universal_newlines=True)
        result = {}
        for line in output.splitlines():
            vp = line.split(':')
            result.update({vp[0]: vp[1].lstrip().rstrip()})
        return result

    def mirror_pool_enable(self, pool):
        base_cmd = ['rbd', '--id', self.ceph_id, 'mirror', 'pool']
        subprocess.check_call(base_cmd + ['enable', pool, 'pool'])
        subprocess.check_call(base_cmd + ['peer', 'add', pool,
                                          'client.{}@remote'
                                          .format(self.ceph_id)])
