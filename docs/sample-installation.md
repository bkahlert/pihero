# Sample installation Ansible log

When you run the Ansible playbook with the provided [sample inventory](../inventory/hosts.yml):

```shell
ansible-playbook playbook.yml -i inventory/hosts.yml
```

Then you should see an output similar to this one:

```text
PLAY [all] ********************************************************************************************

TASK [device_info : install avahi] ********************************************************************
ok: [bar.local]
ok: [foo.local]

TASK [device_info : set device_info.model] ************************************************************
skipping: [bar.local]
ok: [foo.local]

TASK [device_info : compute device_info.machine] ******************************************************
changed: [foo.local]
changed: [bar.local]

TASK [device_info : set device_info.machine] **********************************************************
ok: [foo.local]
ok: [bar.local]

TASK [device_info : copy avahi services] **************************************************************
changed: [foo.local] => (item=.../pi-polisher/roles/device_info/templates/device-info.service.j2)
changed: [foo.local] => (item=.../pi-polisher/roles/device_info/templates/ssh.service.j2)
changed: [bar.local] => (item=.../pi-polisher/roles/device_info/templates/device-info.service.j2)
changed: [bar.local] => (item=.../pi-polisher/roles/device_info/templates/ssh.service.j2)

TASK [smb_shares : install samba] *********************************************************************
changed: [foo.local]
changed: [bar.local]

TASK [smb_shares : copy samba configs] ****************************************************************
changed: [foo.local] => (item=.../pi-polisher/roles/smb_shares/templates/smb.conf.j2)
changed: [bar.local] => (item=.../pi-polisher/roles/smb_shares/templates/smb.conf.j2)

TASK [smb_shares : set passwords] *********************************************************************
ok: [foo.local] => {}

MSG:

Don't forget to run 'sudo smbpasswd -a $USER' for each user who should have access to the Samba shares.
ok: [bar.local] => {}

MSG:

Don't forget to run 'sudo smbpasswd -a $USER' for each user who should have access to the Samba shares.

TASK [smb_shares : copy avahi services] ***************************************************************
changed: [foo.local] => (item=.../pi-polisher/roles/smb_shares/templates/smb.service.j2)
changed: [bar.local] => (item=.../pi-polisher/roles/smb_shares/templates/smb.service.j2)

TASK [smb_shares : convert markers to latin1] *********************************************************
ok: [foo.local] => (item={'regexp': '⸺̲͞\\ \\(\\(\\(ꎤ\\ ✧曲✧\\)—̠͞o', 'replace': 'MARKER_BEGIN'})
ok: [foo.local] => (item={'regexp': '\u200b\u200b\u200b', 'replace': 'MARKER_END'})
ok: [bar.local] => (item={'regexp': '⸺̲͞\\ \\(\\(\\(ꎤ\\ ✧曲✧\\)—̠͞o', 'replace': 'MARKER_BEGIN'})
ok: [bar.local] => (item={'regexp': '\u200b\u200b\u200b', 'replace': 'MARKER_END'})

TASK [smb_shares : update block] **********************************************************************
changed: [foo.local]
changed: [bar.local]

TASK [smb_shares : convert markers to unicode] ********************************************************
changed: [foo.local] => (item={'regexp': 'MARKER_BEGIN', 'replace': '⸺̲͞ (((ꎤ ✧曲✧)—̠͞o'})
changed: [foo.local] => (item={'regexp': 'MARKER_END', 'replace': '\u200b\u200b\u200b'})
changed: [bar.local] => (item={'regexp': 'MARKER_BEGIN', 'replace': '⸺̲͞ (((ꎤ ✧曲✧)—̠͞o'})
changed: [bar.local] => (item={'regexp': 'MARKER_END', 'replace': '\u200b\u200b\u200b'})

TASK [usb_gadget : set usb_gadget_features] ***********************************************************
ok: [foo.local]
ok: [bar.local]

TASK [usb_gadget : compute usb_gadget.product] ********************************************************
changed: [foo.local]
changed: [bar.local]

TASK [usb_gadget : set usb_gadget.product] ************************************************************
ok: [foo.local]
ok: [bar.local]

TASK [usb_gadget : set usb_gadget.manufacturer] *******************************************************
ok: [foo.local]
ok: [bar.local]

TASK [usb_gadget : compute usb_gadget.serialnumber] ***************************************************
changed: [foo.local]
changed: [bar.local]

TASK [usb_gadget : set usb_gadget.serialnumber] *******************************************************
ok: [foo.local]
ok: [bar.local]

TASK [usb_gadget : update /boot/config.txt] ***********************************************************
changed: [foo.local] => (item={'option': 'dtoverlay', 'value': 'dwc2'})
changed: [bar.local] => (item={'option': 'dtoverlay', 'value': 'dwc2'})

TASK [usb_gadget : set options in /boot/cmdline.txt] **************************************************
changed: [foo.local] => (item=modules-load=dwc2)
changed: [bar.local] => (item=modules-load=dwc2)

TASK [usb_gadget : remove trailing line breaks from /boot/cmdline.txt] ********************************
changed: [foo.local]
changed: [bar.local]

TASK [usb_gadget : copy usb-gadget setup script] ******************************************************
changed: [foo.local]
changed: [bar.local]

TASK [usb_gadget : copy usb-gadget setup custom script] ***********************************************
changed: [foo.local]
changed: [bar.local]

TASK [usb_gadget : copy usb-gadget setup service] *****************************************************
changed: [foo.local]
changed: [bar.local]

TASK [usb_gadget : enable usb-gadget setup service] ***************************************************
changed: [foo.local]
changed: [bar.local]

TASK [usb_gadget : copy usb-gadget diagnosis script] **************************************************
changed: [foo.local]
changed: [bar.local]

TASK [usb_gadget : convert markers to latin1] *********************************************************
changed: [foo.local] => (item={'regexp': '⸺̲͞\\ \\(\\(\\(ꎤ\\ ✧曲✧\\)—̠͞o', 'replace': 'MARKER_BEGIN'})
changed: [foo.local] => (item={'regexp': '\u200b\u200b\u200b', 'replace': 'MARKER_END'})
changed: [bar.local] => (item={'regexp': '⸺̲͞\\ \\(\\(\\(ꎤ\\ ✧曲✧\\)—̠͞o', 'replace': 'MARKER_BEGIN'})
changed: [bar.local] => (item={'regexp': '\u200b\u200b\u200b', 'replace': 'MARKER_END'})

TASK [usb_gadget : update block] **********************************************************************
changed: [foo.local]
changed: [bar.local]

TASK [usb_gadget : convert markers to unicode] ********************************************************
changed: [foo.local] => (item={'regexp': 'MARKER_BEGIN', 'replace': '⸺̲͞ (((ꎤ ✧曲✧)—̠͞o'})
changed: [foo.local] => (item={'regexp': 'MARKER_END', 'replace': '\u200b\u200b\u200b'})
changed: [bar.local] => (item={'regexp': 'MARKER_BEGIN', 'replace': '⸺̲͞ (((ꎤ ✧曲✧)—̠͞o'})
changed: [bar.local] => (item={'regexp': 'MARKER_END', 'replace': '\u200b\u200b\u200b'})

TASK [usb_gadget : compute IP settings] ***************************************************************
ok: [bar.local]
ok: [foo.local]

TASK [usb_gadget : prevent dhcpcd from configuring usb0 network interface] ****************************
changed: [foo.local]
changed: [bar.local]

TASK [usb_gadget : install dnsmasq] *******************************************************************
changed: [foo.local]
changed: [bar.local]

TASK [usb_gadget : set options with values] ***********************************************************
changed: [foo.local] => (item={'option': 'interface', 'value': 'usb0'})
changed: [foo.local] => (item={'option': 'dhcp-range', 'value': '10.10.10.9,10.10.10.14,255.255.255.248
changed: [bar.local] => (item={'option': 'interface', 'value': 'usb0'})
changed: [foo.local] => (item={'option': 'dhcp-option', 'value': '3'})
changed: [bar.local] => (item={'option': 'dhcp-range', 'value': '10.10.20.17,10.10.20.22,255.255.255.24
changed: [bar.local] => (item={'option': 'dhcp-option', 'value': '3'})

TASK [usb_gadget : set options without values] ********************************************************
changed: [foo.local] => (item={'option': 'dhcp-authoritative'})
changed: [foo.local] => (item={'option': 'dhcp-rapid-commit'})
changed: [bar.local] => (item={'option': 'dhcp-authoritative'})
changed: [foo.local] => (item={'option': 'leasefile-ro'})
changed: [bar.local] => (item={'option': 'dhcp-rapid-commit'})
changed: [bar.local] => (item={'option': 'leasefile-ro'})

TASK [usb_gadget : copy usb0 network interface config] ************************************************
changed: [foo.local]
changed: [bar.local]

TASK [usb_gadget : convert markers to latin1] *********************************************************
changed: [foo.local] => (item={'regexp': '⸺̲͞\\ \\(\\(\\(ꎤ\\ ✧曲✧\\)—̠͞o', 'replace': 'MARKER_BEGIN'})
changed: [foo.local] => (item={'regexp': '\u200b\u200b\u200b', 'replace': 'MARKER_END'})
changed: [bar.local] => (item={'regexp': '⸺̲͞\\ \\(\\(\\(ꎤ\\ ✧曲✧\\)—̠͞o', 'replace': 'MARKER_BEGIN'})
changed: [bar.local] => (item={'regexp': '\u200b\u200b\u200b', 'replace': 'MARKER_END'})

TASK [usb_gadget : update block] **********************************************************************
changed: [foo.local]
changed: [bar.local]

TASK [usb_gadget : convert markers to unicode] ********************************************************
changed: [foo.local] => (item={'regexp': 'MARKER_BEGIN', 'replace': '⸺̲͞ (((ꎤ ✧曲✧)—̠͞o'})
changed: [foo.local] => (item={'regexp': 'MARKER_END', 'replace': '\u200b\u200b\u200b'})
changed: [bar.local] => (item={'regexp': 'MARKER_BEGIN', 'replace': '⸺̲͞ (((ꎤ ✧曲✧)—̠͞o'})
changed: [bar.local] => (item={'regexp': 'MARKER_END', 'replace': '\u200b\u200b\u200b'})

RUNNING HANDLER [device_info : restart avahi] *********************************************************
changed: [foo.local]
changed: [bar.local]

RUNNING HANDLER [smb_shares : restart samba] **********************************************************
changed: [foo.local]
changed: [bar.local]

RUNNING HANDLER [usb_gadget : reboot system] **********************************************************
fatal: [foo.local]: FAILED! => {
    "changed": false,
    "elapsed": 0,
    "rebooted": true
}

MSG:

Timed out waiting for last boot time check (timeout=0)
...ignoring
fatal: [bar.local]: FAILED! => {
    "changed": false,
    "elapsed": 0,
    "rebooted": true
}

MSG:

Timed out waiting for last boot time check (timeout=0)
...ignoring

PLAY RECAP ********************************************************************************************
bar.local                  : ok=40   changed=30   unreachable=0    failed=0    skipped=1    rescued=0  
foo.local                  : ok=41   changed=30   unreachable=0    failed=0    skipped=0    rescued=0  
```

You can ignore the failing reboot tasks. The timeout is set to 0, to speed up things.
