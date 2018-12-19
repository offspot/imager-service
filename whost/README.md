# Cardshop Writer Host

## Setup

1. Install Ubuntu 18.04.1 LTS server with default options (see bellow)
* log-in and elevate as `root` (`sudo su -`)
* Make sure internet is working
* download/copy your tunnel private key to `/root/.ssh/tunnel`
* download setup script `curl -O /tmp/whost-setup https://raw.githubusercontent.com/kiwix/cardshop/master/whost/whost-setup`
* run the setup script `chmod +x /tmp/whost-config && REVERSE_SSH_PORT=XXX /tmp/whost-config`

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
 
 
