# Cardshop Writer Host

Cardshop use writer hosts to download, write and ship SD-cards to recipient.
A WriterHost is an always-running, always-connected computer connected to one or more USB SD-card readers (physical device).

Writer Hosts authenticate with the cardshop to fetch tasks. The WriterHost operator is contacted (email) when an SD-card must be inserted, retrieved and shipped.

## Requirements

* always-on-capable computer
* 500GB storage or more.
* high-speed, direct, permanent connection to internet via ethernet.
* one or more good-quality USB SD-card readers ([Kingston MobileLite G4](https://www.ldlc.com/fiche/PB00171186.html))
* A `writer` account on the cardshop.
* An assigned port on the demo server (see [maintenance](http://wiki.kiwix.org/wiki/Cardshop-maintenance)).

## Ubuntu Install

Just a regular, fresh Ubuntu-server install. Bellow are the __defaults used for tests__ (you can customize them).

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
  * name: whatever (ex: `maint`)
  * server name: whatever (ex: `bkored`)
  * username: whatever (ex: `maint_user`)
  * password: whatever (ex: `maint_pwd`)
* *Reboot now*
* Remove install media then `ENTER`

## Setup software

* log-in and elevate as `root` (`sudo su -`)
* set a password for `root` (`passwd`)
* Make sure internet is working
* Configure SSH tunneling for remote access
  * Generate SSH key pair for `root` using `ssh-keygen` (no passphrase)
  * Copy `/root/.ssh/id_rsa` to `/root/.ssh/tunnel`
  * Share (via email for example) public key with cardshop admin (it's located at `/root/.ssh/id_rsa.pub`).
  * This file will be appened to `/home/tunnel/.ssh/authorized_keys` on the the tunneling server gateway by the cardshop admin, so the writer can connect.
* Download setup script `curl -L -o /tmp/whost-setup https://raw.githubusercontent.com/kiwix/cardshop/master/whost/whost-setup`
* Go to https://wiki.kiwix.org/wiki/Cardshop/maintenance, pick a port for your host and update the writers table
* run the setup script `chmod +x /tmp/whost-setup && REVERSE_SSH_PORT=XXX /tmp/whost-setup`. 

## Configure the writer

The writer is configured through a command-line tool that is launched automatically when logging-in as `root` (not via `su`).

``` sh
Hotsport Cardshop writer-host configurator
-------------------------------------------

:: Internet Connectivity: CONNECTED
:: Authentication: AUTHENTICATED
:: Host Status: ENABLED
:: Configured Writers: 2
:: Choose:
   1 Configure Network
   2 Configure Credentials
   3 Configure USB Writers
   4 Update code and restart
   5 Disable this Host
   6 Exit to a shell
   7 Exit (logout)
>
```

You can launch it on any console via `whost-config`.

__Initially__, use the *Update code and Restart* option to make sure you get all the fixes.

__First__, make sure *Internet Connectivity* shows *CONNECTED*. If not, you should configure it externally or using the *Configure Network* helper (only Ethernet).

__Second__, configure *Authentication* using *Configure Credentials*. Enter your Scheduler's username and password (should be of the `writer` role) and press enter when asked for the API URL (default should be OK).

__Then__, *Configure USB Writers*. For this, you'll need your _Kingston mobilite G4_ USB readers. Kingston readers are seen as block devices (in `/dev/sd_`) when plugged, even when no card are inserted.

**WARNING**: the *USB Writers* configuration does not accept devices being removed or reinserted while the computer is running. If you accidentaly disconnect one of the reader, reconnect it and restart.

For the initial configuration, shutdown the computer, plug the USB devices and then start the computer to proceed to the Configuration.

``` sh
> 3
:: Already configured writer devices
 * A:/dev/sdc (Generic- USB3.0 CRW   -SD at 2:0:0:1)
 * B:/dev/sde (Generic- USB3.0 CRW   -SD at 3:0:0:1)

:: Choose:
   1 Reset writers config (remove ALL)
   2 Add one device
   3 CANCEL
>
```

To configure devices, follow on-screen's instructions: remove SD-cards from all ports then, when asked, enter any card into the desired device. The configurator will detect the card, its reader and assign a *Slot Name* to it (a letter). You can now remove the SD-card and proceed to configure another device or exit.

When your host picks up writing jobs, it will (once download is complete) ask you to insert a certain capacity SD-card into *Slot X* where slot is the assigned Slot Name. Make sure you label your physical slots on your readers with their assigned names. If you don't unplug the readers, those names won't change.

_Note_: The recommended Kingston readers are actually 2 independent readers with different slots (1 x microSD and 1 x SD). You can choose to configure both of just the one you prefer but keep in mind that those are not interchangeable.

__Finally__, you can *Enable this host*. This will trigger the launch (and automatic launch upon startup) of your downloader container and one writer container per configured USB reader.

--

You can check that your host is properly configured by:

* Exiting to shell and running `docker ps` and `docker logs`.
* Check the *Scheduler* page on the Manager UI.
* Ask the cardshop admin to connect using the reverse SSH bridge (`ssh -i /root/whost-maint.priv root@localhost -p 2111`)
