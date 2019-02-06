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

import charms.reactive as reactive

import charms_openstack.bus
import charms_openstack.charm as charm

import charmhelpers.core as ch_core


charms_openstack.bus.discover()

# Use the charms.openstack defaults for common states and hooks
charm.use_defaults(
    'charm.installed',
    'config.changed',
    'update-status',
    'upgrade-charm')


@reactive.when_all('ceph-local.connected', 'ceph-remote.connected')
@reactive.when_not_all('ceph-local.available', 'ceph-remote.available')
def ceph_connected():
    for flag in ('ceph-local.connected', 'ceph-remote.connected'):
        endpoint = reactive.relations.endpoint_from_flag(flag)
        endpoint.request_key()

    with charm.provide_charm_instance() as charm_instance:
        ch_core.hookenv.log('Ceph connected, charm_instance @ {}'
                            .format(charm_instance),
                            level=ch_core.hookenv.DEBUG)
        charm_instance.assess_status()


@reactive.when_all('ceph-local.available', 'ceph-remote.available')
def ceph_available():
    mon_hosts = {}
    for flag in ('ceph-local.available', 'ceph-remote.available'):
        endpoint = reactive.relations.endpoint_from_flag(flag)
        mon_hosts[endpoint.endpoint_name] = endpoint.mon_hosts
        for relation in endpoint.relations:
            for unit in relation.units:
                ch_core.hookenv.log('{}: "{}"'.format(flag, unit.received),
                                    level=ch_core.hookenv.INFO)

    with charm.provide_charm_instance() as charm_instance:
        ch_core.hookenv.log('Ceph available, mon_hosts: "{}" '
                            'charm_instance @ {}'
                            .format(mon_hosts, charm_instance),
                            level=ch_core.hookenv.DEBUG)
        charm_instance.assess_status()
