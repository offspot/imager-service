# Cardshop Writer Host

Cardshop use writer hosts to download, write and ship SD-cards to recipient.
A WriterHost is an always-running, always-connected computer connected to one or more USB SD-card readers.

Writer Hosts authenticate with the cardshop fetch tasks. The WriterHost operator is contacted (email) when an SD-card must be inserted, retrieved and shipped.

## Requirements

* always-on-capable computer
* 500GB storage or more.
* high-speed, direct, permanent connection to internet via ethernet.
* one or more good-quality USB SD-card readers (Kingston)
* A `writer` account on the cardshop.
* An assigned port on the demo server (see [maintenance](http://wiki.kiwix.org/wiki/Cardshop-maintenance)).

## Setup

1. Install Ubuntu 18.04.1 LTS server with default options (see below)
* log-in and elevate as `root` (`sudo su -`)
* set a password for `root` (`passwd`)
* Make sure internet is working
* download/copy your tunnel private key to `/root/.ssh/tunnel` (chmod `600`)
* download setup script `curl -L -o /tmp/whost-setup https://raw.githubusercontent.com/kiwix/cardshop/master/whost/whost-setup`
* run the setup script `chmod +x /tmp/whost-setup && REVERSE_SSH_PORT=XXX /tmp/whost-setup`

### Ubuntu Install

Just a regular, fresh Ubuntu-server install. Bellow are the defaults used for tests.

1. Boot off the install media & select *Install Ubuntu Server* at grub prompt.
* Select language (*English*)
* Select Keyboard layout (*English (US)*, *English (US)*)
* Select *Install Ubuntu* (not cloud instance)
* Configure the network (*eth via dhcp*)
* Proxy Address: none
* Mirror Address: http://archive.ubuntu.com/ubuntu (pre-filled default)
* *Use an entire Disk*
* Choose disk to install to: *selected disk*
* Summary: confirm and continue
* Profile
 * name: `maint`
 * server name: whatever (`bkored`)
 * username: `maint`
 * password: `maint`
 * Import Identity: *from github* > `rgaudin`
* *Reboot now*
* Remove install media then `ENTER`
 
 
