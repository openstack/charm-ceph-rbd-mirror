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
    'config.rendered',
    'update-status',
    'upgrade-charm')


@reactive.when_all('ceph-local.connected', 'ceph-remote.connected')
@reactive.when_not_all('ceph-local.available', 'ceph-remote.available')
def request_keys():
    with charm.provide_charm_instance() as charm_instance:
        for flag in ('ceph-local.connected', 'ceph-remote.connected'):
            endpoint = reactive.endpoint_from_flag(flag)
            ch_core.hookenv.log('Ceph endpoint "{}" connected, requesting key'
                                .format(endpoint.endpoint_name),
                                level=ch_core.hookenv.INFO)
            endpoint.request_key()
        charm_instance.assess_status()


@reactive.when('config.changed')
@reactive.when('ceph-local.available')
@reactive.when('ceph-remote.available')
def config_changed():
    with charm.provide_charm_instance() as charm_instance:
        charm_instance.upgrade_if_available([
            reactive.endpoint_from_flag('ceph-local.available'),
            reactive.endpoint_from_flag('ceph-remote.available'),
        ])
        charm_instance.assess_status()


@reactive.when('ceph-local.available')
@reactive.when('ceph-remote.available')
def render_stuff(*args):
    with charm.provide_charm_instance() as charm_instance:
        for endpoint in args:
            if not endpoint.key:
                ch_core.hookenv.log('Ceph endpoint "{}" flagged available yet '
                                    'no key.  Relation is probably departing.',
                                    level=ch_core.hookenv.INFO)
                return
            ch_core.hookenv.log('Ceph endpoint "{}" available, configuring '
                                'keyring'.format(endpoint.endpoint_name),
                                level=ch_core.hookenv.INFO)
            ch_core.hookenv.log('Pools: "{}"'.format(endpoint.pools),
                                level=ch_core.hookenv.INFO)

            cluster_name = (
                'remote') if endpoint.endpoint_name == 'ceph-remote' else None
            charm_instance.configure_ceph_keyring(endpoint.key,
                                                  cluster_name=cluster_name)
        charm_instance.render_with_interfaces(args)
        reactive.set_flag('config.rendered')


@reactive.when('leadership.is_leader')
@reactive.when('refresh.pools')
@reactive.when('ceph-local.available')
@reactive.when('ceph-remote.available')
def refresh_pools():
    for endpoint in 'ceph-local', 'ceph-remote':
        endpoint = reactive.endpoint_from_name(endpoint)
        endpoint.refresh_pools()
    reactive.clear_flag('refresh.pools')


@reactive.when('leadership.is_leader')
@reactive.when('config.rendered')
@reactive.when('ceph-local.available')
@reactive.when('ceph-remote.available')
def configure_pools():
    local = reactive.endpoint_from_flag('ceph-local.available')
    remote = reactive.endpoint_from_flag('ceph-remote.available')
    with charm.provide_charm_instance() as charm_instance:
        for pool, attrs in charm_instance.eligible_pools(local.pools).items():
            if not (charm_instance.mirror_pool_enabled(pool) and
                    charm_instance.mirror_pool_has_peers(pool)):
                charm_instance.mirror_pool_enable(pool)
            pg_num = attrs['parameters'].get('pg_num', None)
            max_bytes = attrs['quota'].get('max_bytes', None)
            max_objects = attrs['quota'].get('max_objects', None)
            if 'erasure_code_profile' in attrs['parameters']:
                ec_profile = attrs['parameters'].get(
                    'erasure_code_profile', None)
                remote.create_erasure_pool(pool,
                                           erasure_profile=ec_profile,
                                           pg_num=pg_num,
                                           app_name='rbd',
                                           max_bytes=max_bytes,
                                           max_objects=max_objects)
            else:
                size = attrs['parameters'].get('size', None)
                remote.create_replicated_pool(pool, replicas=size,
                                              pg_num=pg_num,
                                              app_name='rbd',
                                              max_bytes=max_bytes,
                                              max_objects=max_objects)
