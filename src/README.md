# Overview

This charm provides the Ceph RBD Mirror service for use with replication between multiple Ceph clusters.

Ceph 12.2 Luminous or later is required.

# Usage

## Recovering from abrupt shutdown

There exist failure scenarios where abrupt shutdown and/or interruptions to
communication may lead to a split-brain situation where the RBD Mirroring
process in both Ceph clusters claim to be the primary.

In such a situation the operator must decide which cluster has the most
recent data and should be elected primary by using the ``demote`` and
``promote`` (optionally with force parameter) actions.

After making this decision the secondary cluster must be resynced to track
the promoted master, this is done by running the ``resync-pools`` action on
the non-master cluster.

    juju run-action -m site-b ceph-rbd-mirror/leader --wait demote
    juju run-action -m site-a ceph-rbd-mirror/leader --wait promote force=True

    juju run-action -m site-a ceph-rbd-mirror/leader --wait status verbose=True
    juju run-action -m site-b ceph-rbd-mirror/leader --wait status verbose=True

    juju run-action -m site-b ceph-rbd-mirror/leader --wait resync-pools i-really-mean-it=True

__NOTE__ When using Ceph Luminous, the mirror state information will not be
accurate after recovering from unclean shutdown.  Regardless of the output of
the status information you will be able to write to images after a forced
promote.

# Bugs

Please report bugs on [Launchpad](https://bugs.launchpad.net/charm-ceph-rbd-mirror/+filebug).

For general questions please refer to the OpenStack [Charm Guide](https://docs.openstack.org/charm-guide/latest/).
