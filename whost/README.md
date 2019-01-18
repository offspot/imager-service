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

## Ubuntu Install

Just a regular, fresh Ubuntu-server install. Bellow are the defaults used for tests.

* Boot off the install media & select *Install Ubuntu Server* at grub prompt.
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
  * name: whatever (`maint`)
  * server name: whatever (`bkored`)
  * username: whatever (`maint_user`)
  * password: whatever (`maint_pwd`)
* *Reboot now*
* Remove install media then `ENTER`

## Setup software

* log-in and elevate as `root` (`sudo su -`)
* set a password for `root` (`passwd`)
* Make sure internet is working
* Configure SSH tunneling for remote access
  * Generate SSH key pair for `root`, `ssh-keygen` (no passphrase)
  * Copy `/root/.ssh/id_rsa` to `/root/.ssh/tunnel`
  * Share (via email for example) public key with cardshop admin, it's located at `/root/.ssh/id_rsa.pub`.
  * This file will be append to `/home/tunnel/.ssh/authorized_keys` on the the tunneling server gateway by the cardshop admin, so the writer can connect.
* Download setup script `curl -L -o /tmp/whost-setup https://raw.githubusercontent.com/kiwix/cardshop/master/whost/whost-setup`
* Go to https://wiki.kiwix.org/wiki/Cardshop/maintenance and update the writer table
* run the setup script `chmod +x /tmp/whost-setup && REVERSE_SSH_PORT=XXX /tmp/whost-setup`

## Configure the writer

* Open a terminal as root (no su)
* Internet connectivity should work, otherwise you will need need to manually configure it with (1)
* To configure the access to the cardshop you should get from the Cardshop admin your credentials and then configure the software with (2)
* Then configure your USB microSD adapters with (3), we recommend the usage of "Kingston MobileLite G4"
* You should then finally enable your writer with (5)
* You are now ready to use the writer with the cardshop
 
