#!/usr/bin/env python3
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

import os
import subprocess
import sys

# Load basic layer module from $CHARM_DIR/lib
sys.path.append('lib')
from charms.layer import basic

# setup module loading from charm venv
basic.bootstrap_charm_deps()

import charms.reactive as reactive
import charmhelpers.core as ch_core
import charms_openstack.bus
import charms_openstack.charm

# load reactive interfaces
reactive.bus.discover()
# load Endpoint based interface data
ch_core.hookenv._run_atstart()

# load charm class
charms_openstack.bus.discover()


def rbd_mirror_action(args):
    """Perform RBD command on pools in local Ceph endpoint."""
    action_name = os.path.basename(args[0])
    with charms_openstack.charm.provide_charm_instance() as charm:
        ceph_local = reactive.endpoint_from_name('ceph-local')
        pools = (pool for pool, attrs in ceph_local.pools.items()
                 if 'rbd' in attrs['applications'])
        result = []
        cmd = ['rbd', '--id', charm.ceph_id, 'mirror', 'pool', action_name]
        if ch_core.hookenv.action_get('force'):
            cmd += ['--force']
        for pool in pools:
            output = subprocess.check_output(cmd + [pool],
                                             stderr=subprocess.STDOUT,
                                             universal_newlines=True)
            result.append('{}: {}'.format(pool, output.rstrip()))
        ch_core.hookenv.action_set({'output': '\n'.join(result)})


def refresh_pools(args):
    """Refresh list of pools from Ceph.

    This is done by updating data on relations to ceph-mons which lead to them
    updating the relation data they have with us as a response.

    Due to how the reactive framework handles publishing of relation data we
    must do this by setting a flag and runnnig the reactive handlers, emulating
    a full hook execution.
    """
    if not reactive.is_flag_set('leadership.is_leader'):
        ch_core.hookenv.action_fail('run action on the leader unit')
        return

    # set and flush flag to disk
    reactive.set_flag('refresh.pools')
    ch_core.unitdata._KV.flush()

    # run reactive handlers to deal with flag
    return reactive.main()


ACTIONS = {
    'demote': rbd_mirror_action,
    'promote': rbd_mirror_action,
    'refresh-pools': refresh_pools,
}


def main(args):
    action_name = os.path.basename(args[0])
    try:
        action = ACTIONS[action_name]
    except KeyError:
        return 'Action {} is undefined'.format(action_name)

    try:
        action(args)
    except Exception as e:
        ch_core.hookenv.action_fail(str(e))


if __name__ == '__main__':
    sys.exit(main(sys.argv))
