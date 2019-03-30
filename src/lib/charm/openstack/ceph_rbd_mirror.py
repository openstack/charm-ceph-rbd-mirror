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
import json
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

    def eligible_pools(self, pools):
        """Filter eligible pools.

        :param pools: Dictionary with detailed pool information as provided
                      over the ``ceph-rbd-mirror`` interface provided by the
                      ``ceph-mon`` charm.
        :type pools: dict
        :returns: Dictionary with detailed pool information for pools eligible
                  for mirroring.
        :rtype: dict
        """
        return {pool: attrs for pool, attrs in pools.items()
                if 'rbd' in attrs['applications']}

    def custom_assess_status_check(self):
        """Provide mirrored pool statistics through juju status."""
        if (reactive.is_flag_set('config.rendered') and
                reactive.is_flag_set('ceph-local.available') and
                reactive.is_flag_set('ceph-remote.available')):
            endpoint = reactive.endpoint_from_flag('ceph-local.available')
            stats = self.mirror_pools_summary(
                self.eligible_pools(endpoint.pools))
            ch_core.hookenv.log('mirror_pools_summary = "{}"'
                                .format(stats),
                                level=ch_core.hookenv.DEBUG)
            status = 'active'
            pool_msg = ''
            image_msg = ''
            for health, count in stats['pool_health'].items():
                if not pool_msg:
                    pool_msg = 'Pools '
                pool_msg += '{} ({}) '.format(health, count)
                if health != 'OK':
                    status = 'blocked'
            for state, count in stats['image_states'].items():
                if not image_msg:
                    image_msg = 'Images '
                if state == 'stopped':
                    state_name = 'Primary'
                elif state == 'replaying':
                    state_name = 'Secondary'
                else:
                    state_name = state
                image_msg += '{} ({}) '.format(state_name, count)
            msg = ''
            if pool_msg:
                msg = 'Unit is ready ({})'.format(
                    pool_msg + image_msg.rstrip())
            else:
                status = 'waiting'
                msg = 'Waiting for pools to be created'
            return status, msg
        return None, None

    def _mirror_pool_info(self, pool):
        output = subprocess.check_output(['rbd', '--id', self.ceph_id,
                                          'mirror', 'pool', 'info', '--format',
                                          'json', pool],
                                         universal_newlines=True)
        return json.loads(output)

    def mirror_pool_enabled(self, pool):
        return self._mirror_pool_info(pool).get('mode', None) == 'pool'

    def mirror_pool_has_peers(self, pool):
        return len(self._mirror_pool_info(pool).get('peers', [])) > 0

    def mirror_pool_status(self, pool):
        output = subprocess.check_output(['rbd', '--id', self.ceph_id,
                                          'mirror', 'pool', 'status',
                                          '--format', 'json', '--verbose',
                                          pool],
                                         universal_newlines=True)
        return json.loads(output)

    def mirror_pools_summary(self, pools):
        stats = {}
        stats['pool_health'] = collections.defaultdict(int)
        stats['image_states'] = collections.defaultdict(int)
        for pool in pools:
            pool_stat = self.mirror_pool_status(pool)
            stats['pool_health'][pool_stat['summary']['health']] += 1
            for state, value in pool_stat['summary']['states'].items():
                stats['image_states'][state] += value
        return stats

    def mirror_pool_enable(self, pool):
        base_cmd = ['rbd', '--id', self.ceph_id, 'mirror', 'pool']
        subprocess.check_call(base_cmd + ['enable', pool, 'pool'])
        subprocess.check_call(base_cmd + ['peer', 'add', pool,
                                          'client.{}@remote'
                                          .format(self.ceph_id)])
