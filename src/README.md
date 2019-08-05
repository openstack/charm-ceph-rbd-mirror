# Overview

The `ceph-rbd-mirror` charm deploys the Ceph `rbd-mirror` daemon and helps
automate remote creation and configuration of mirroring for Ceph pools used for
hosting RBD images. Actions for operator driven failover and fallback of the
RBD image pools are also provided.

> **Note**: The `ceph-rbd-mirror` charm addresses only one specific element in
  datacentre redundancy. Refer to [Ceph RADOS Gateway Multisite Replication][ceph-multisite-replication]
  and other work to arrive at a complete solution.

For more information on charms and RBD mirroring see the [Ceph RBD Mirroring][ceph-rbd-mirroring]
appendix in the [OpenStack Charms Deployment Guide][charms-deploy-guide].

# Functionality

The charm has the following major features:

- Support for a maximum of two Ceph clusters. The clusters may reside within a
  single model or be contained within two separate models.

- Specifically written for two-way replication. This provides the ability to
  fail over and fall back to/from a single secondary site. Ceph does have
  support for mirroring to any number of clusters but the charm does not
  support this.

- Automatically creates and configures (for mirroring) pools in the remote
  cluster based on any pools in the local cluster that are labelled with the
  'rbd' tag.

- Mirroring of whole pools only. Ceph itself has support for the mirroring of
  individual images but the charm does not support this.

- Network space aware. The mirror daemon can be informed about network
  configuration by binding the `public` and `cluster` endpoints. The daemon
  will use the network associated with the `cluster` endpoint for mirroring
  traffic.

Other notes on RBD mirroring:

- Supports multiple running instances of the mirror daemon in each cluster.
  Doing so allows for the dynamic re-distribution of the mirroring load amongst
  the daemons. This addresses both high availability and performance concerns.
  Leverage this feature by scaling out the `ceph-rbd-mirror` application (i.e.
  add more units).

- Requires that every RBD image within each pool is created with the
  `journaling` and `exclusive-lock` image features enabled. The charm enables
  these features by default and the `ceph-mon` charm will announce them over
  the `client` relation when it has units connected to its `rbd-mirror`
  endpoint.

- The feature first appeared in Ceph `v.12.2` (Luminous).

# Deployment

It is assumed that the two Ceph clusters have been set up (i.e. `ceph-mon` and
`ceph-osd` charms are deployed and relations added).

> **Note**: Minimal two-cluster test bundles can be found in the
  `src/tests/bundles` subdirectory where both the one-model and two-model
  scenarios are featured.

## Using one model

Deploy the charm for each cluster, giving each application a name to
distinguish one from the other (site 'a' and site 'b'):

    juju deploy ceph-rbd-mirror ceph-rbd-mirror-a
    juju deploy ceph-rbd-mirror ceph-rbd-mirror-b

Add a relation between the 'ceph-mon' of site 'a' and both the local (site 'a')
and remote (site 'b') units of 'ceph-rbd-mirror':

    juju add-relation ceph-mon-a ceph-rbd-mirror-a:ceph-local
    juju add-relation ceph-mon-a ceph-rbd-mirror-b:ceph-remote

Perform the analogous procedure for the 'ceph-mon' of site 'b':

    juju add-relation ceph-mon-b ceph-rbd-mirror-b:ceph-local
    juju add-relation ceph-mon-b ceph-rbd-mirror-a:ceph-remote

## Using two models

In model 'site-a', deploy the charm and add the local relation:

    juju switch site-a
    juju deploy ceph-rbd-mirror ceph-rbd-mirror-a
    juju add-relation ceph-mon-a ceph-rbd-mirror-a:ceph-local

To create the inter-site relation one must export one of the application
endpoints from the model by means of an "offer". Here, we make an offer for
'ceph-rbd-mirror':

    juju offer ceph-rbd-mirror-a:ceph-remote
    Application "ceph-rbd-mirror-a" endpoints [ceph-remote] available at "admin/site-a.ceph-rbd-mirror-a"

Perform the analogous procedure in the other model ('site-b'):

    juju switch site-b
    juju deploy ceph-rbd-mirror ceph-rbd-mirror-b
    juju add-relation ceph-mon-b ceph-rbd-mirror-b:ceph-local
    juju offer ceph-rbd-mirror-b:ceph-remote
    application "ceph-rbd-mirror-b" endpoints [ceph-remote] available at "admin/site-b.ceph-rbd-mirror-b"

Add the *cross model relations* by referring to the offer URLs (included in the
output above) as if they were application endpoints in each respective model.

For site 'a':

    juju switch site-a
    juju add-relation ceph-mon-a admin/site-b.ceph-rbd-mirror-b

For site 'b':

    juju switch site-b
    juju add-relation ceph-mon-b admin/site-a.ceph-rbd-mirror-a

# Usage

Usage procedures covered here touch upon pool creation, failover & fallback,
and recovery. In all cases we presuppose that each cluster resides within a
separate model.

## Pools

As of the 19.04 OpenStack Charms release, due to Ceph Luminous, any pool
associated with the RBD application during its creation will automatically be
labelled with the 'rbd' tag. The following occurs together:

Pool creation ==> RBD application-association ==> 'rbd' tag

RBD pools can be created by either a supporting charm (through the Ceph broker
protocol) or manually by the operator:

1. A charm-created pool (e.g. via `glance`) will automatically be detected and
acted upon (i.e. a remote pool will be set up).

1. A manually-created pool, whether done via the `ceph-mon` application or
through Ceph directly, will require an action to be run on the
`ceph-rbd-mirror` application leader in order for the remote pool to come
online.

For example, a pool is created manually in site 'a' via `ceph-mon` and then
`ceph-rbd-mirror` (of site 'a') is informed about it:

    juju run-action -m site-a ceph-mon-a/leader --wait create-pool name=mypool app-name=rbd
    juju run-action -m site-a ceph-rbd-mirror-a/leader --wait refresh-pools

## Failover and fallback

To manage failover and fallback, the `demote` and `promote` actions are applied
to the `ceph-rbd-mirror` application leader.

Here, we fail over from site 'a' to site 'b' by demoting site 'a' and promoting
site 'b'. The rest of the commands are status checks:

    juju run-action -m site-a ceph-rbd-mirror-a/leader --wait status verbose=True
    juju run-action -m site-b ceph-rbd-mirror-b/leader --wait status verbose=True

    juju run-action -m site-a ceph-rbd-mirror-a/leader --wait demote

    juju run-action -m site-a ceph-rbd-mirror-a/leader --wait status verbose=True
    juju run-action -m site-b ceph-rbd-mirror-b/leader --wait status verbose=True

    juju run-action -m site-b ceph-rbd-mirror-b/leader --wait promote

To fall back to site 'a':

    juju run-action -m site-b ceph-rbd-mirror-b/leader --wait demote
    juju run-action -m site-a ceph-rbd-mirror-a/leader --wait promote

> **Note**: When using Ceph Luminous, the mirror status information may not be
  accurate. Specifically, the `entries_behind_master` counter may never get to
  `0` even though the image has been fully synchronised.

## Recovering from abrupt shutdown

It is possible that an abrupt shutdown and/or an interruption to communication
channels may lead to a "split-brain" condition. This may cause the mirroring
daemon in each cluster to claim to be the primary. In such cases, the operator
must make a call as to which daemon is correct. Generally speaking, this
means deciding which cluster has the most recent data.

Elect a primary by applying the `demote` and `promote` actions to the
appropriate `ceph-rbd-mirror` leader. After doing so, the `resync-pools`
action must be run on the secondary cluster leader. The `promote` action may
require a force option.

Here, we make site 'a' be the primary by demoting site 'b' and promoting site
'a':

    juju run-action -m site-b ceph-rbd-mirror/leader --wait demote
    juju run-action -m site-a ceph-rbd-mirror/leader --wait promote force=True

    juju run-action -m site-a ceph-rbd-mirror/leader --wait status verbose=True
    juju run-action -m site-b ceph-rbd-mirror/leader --wait status verbose=True

    juju run-action -m site-b ceph-rbd-mirror/leader --wait resync-pools i-really-mean-it=True

> **Note**: When using Ceph Luminous, the mirror state information will not be
  accurate after recovering from unclean shutdown. Regardless of the output of
  the status information, you will be able to write to images after a forced
  promote.

# Bugs

Please report bugs for the `ceph-rbd-mirror` charm on [Launchpad][charm-ceph-rbd-mirror-bugs].

For general questions, refer to the [OpenStack Charm Guide][charms-guide].

<!-- LINKS -->

[ceph-multisite-replication]: https://docs.openstack.org/project-deploy-guide/charm-deployment-guide/latest/app-rgw-multisite.html
[ceph-rbd-mirroring]: https://docs.openstack.org/project-deploy-guide/charm-deployment-guide/latest/app-ceph-rbd-mirror.html
[charms-deploy-guide]: https://docs.openstack.org/project-deploy-guide/charm-deployment-guide/latest/index.html
[charm-ceph-rbd-mirror-bugs]: https://bugs.launchpad.net/charm-ceph-rbd-mirror/+filebug
[charms-guide]: https://docs.openstack.org/charm-guide/latest/
