# hidusbf
1. Short description.
  This driver/program is intended to "overclock" USB mice (or 
  other devices) under Windows 98, 98SE, ME, 2000, XP, 2003, Vista, 
  7, 8, 8.1, 10, 11 including x64 versions.
  Also may be used for downclocking (and downclocking shall work always).

  !!! Warning - overclocking may not work for Low Speed USB devices which 
  controlled by non Microsoft USB stack, like OEM USB 3.x drivers
  at Windows 7 or with the newest Microsoft drivers.

  !!! Warning 2 - you SHALL disable Secure Boot or modify the Registry
  accordingly to enable loading of Microsoft unsigned drivers to load
  HIDUSBF driver successfully under Windows 10 x64 version 1607
  (Anniversary Update) or newer versions.

  Program changes rate on selected devices only, not touching other devices
  on USB.

  You can learn more about theory and the program here:
  http://www.overclockers.ru/lab/15925/Razgon_USB_myshi_ili_Software_nanosit_otvetnyj_udar.html
  (in Russian language(*))

  I have personally tested it under Windows 98SE, 2000 SP2/SP4, 
  XP RTM/SP1/SP2/SP3, XP x64 SP2, 2003 x86 SP2, Vista 32 bit RTM/SP2, 
  Vista 64 bit RTM, 7 x86 SP1, 7 x64 SP1, 8 x64, 8.1 x64,
  10 x64 1803, 1809, 1909, 20H2, 21H1, 21H2.
  The first testing on x64 platform was performed by Dark_Cloud under
  Windows XP x64 SP1.

2. Installation.
  1. Downclocking (all devices and drivers) or overclocking of Full Speed USB
  devices is possible always and there is no need to patch system code.

  So, if you use program for this purpose - take drivers
  from directories DRIVER\NTX86\NOPATCH\ and DRIVER\AMD64\NOPATCH\ 
  and replace drivers from directories DRIVER\NTX86\ and DRIVER\AMD64\

  Because Windows 2000 doesn't have restrictions for overclocking Low Speed USB
  devices in driver code for OHCI and UHCI controllers you can use the driver 
  from DRIVER\NTX86\NOPATCH\. Windows 98 and ME also don't have such 
  restrictions, so there is no patch version of driver for these OSes at all.

  If you use your device with pure EHCI controller (without companion 
  UHCI or OHCI controllers and with integrated USB2.0 Hub) or with any 
  EHCI controller through USB2.0 Hub on Windows 2000 then just use
  ordinary version of driver (with patch).
  And there is special unofficial version of USBPORT.SYS for Windows 98 and ME
  without any restrictions of polling rate for such cases.

  2. For OSes begining from Windows XP for successful overclocking of
  Low Speed USB devices is REQUIRED the presence original (not altered
  by other programs) version of system driver USBPORT.SYS 
  (%sytemroot%\system32\drivers\usbport.sys).
  Windows 8 beginning also works with USBXHCI.SYS
  (%sytemroot%\system32\drivers\usbxhci.sys).
  And under Windows 7 is supported Intel xHCI driver (IUSB3XHC.SYS)
  (see additions in HIDUSBFN.ZIP)

  3. Install my driver HIDUSBF.SYS. For this purpose execute SETUP.EXE (there
  should also be .INF and .SYS files UNZIPPED). Click [Install Service].

  In case of HIDUSBF service wasn't installed through 
  SETUP.EXE (button [Install Service]) you may try to do this by OS 
  standard possibility:
  mouse right button click on HIDUSBF.INF -> Install
  It is enough to install the service once for each OS instance.

  Then choose the row with your device and put a checkmark Filter On Device.
  Check that in the column Filter? it says Yes. After that choose desired refresh
  rate. After that push [Restart]. Check if the refresh rate has really 
  changed (for example with the program Mouse Rate Checker).

  If your rate did not change, then you should either reboot, plug-out
  and plug-in mouse cable or stop and then start your mouse in 
  Device Manager.
   
  If the rate does not increase more than 125Hz, then you should 
  try DECREASE it to 31Hz or 62Hz.
  If the rate does decrease, then the driver functions properly, however
  or you mouse is not overclockable; or USBPORT.SYS/USBXHCI.SYS was altered
  or simply too new and so unknown to the program.

3. Uninstall.
  1. Unlink driver from mouse through SETUP.EXE (Filter = Unchecked)
  2. For removing a service and file of driver:
  mouse right button click on HIDUSBFU.INF -> Install
  3. If you have delete a driver but not unlink it from mouse
  then the mouse will stop working. To make mouse working you
  can just delete device, corresponding to mouse in Device Manager,
  then scan for new devices. Or use 
  SETUP.EXE -> [All] or [with Problem] or [with HIDUSBF] Devices ->
  [Filter On Device] is Unchecked -> [Restart]

4. Contacts.
  You can access the newest version at this link:
  https://github.com/LordOfMice/hidusbf

  Recent info
  https://www.overclock.net/threads/usb-mouse-hard-overclocking-2000-hz.1589644/
  (the end of the first post and recent posts in thread)  

  Good luck in overclocking mice :)               SweetLow

5. History.

-------------------------------------------------------------------------------

Added 2022/07/18:

1. Setup
- added message on USB Low Speed devices overclocking to higher USB Speed Class

-------------------------------------------------------------------------------

Added 2022/07/13:

1. Setup
- USB High Speed devices support
- OS Version and Bus Speed name on [Copy IDs]

-------------------------------------------------------------------------------

Added 2021/04/02:

1. Setup
- correctly shows long error messages

-------------------------------------------------------------------------------

Added 2020/06/05:

1. Setup
- added check for hidusbf service can run

-------------------------------------------------------------------------------

Added 2020/03/29:

1. Setup
- real versions of files on Copy IDs on modern OSes
- VIA xHCI Controller Driver (XHCDRV.SYS) marked as good

-------------------------------------------------------------------------------

Added 2019/10/26:

1. Setup v2.0
- literally everything is improved: 
the form is simplified,
display of the whole essential information added,
all reasonable checks are implemented

-------------------------------------------------------------------------------

Added 2019/06/21:

1. Improved Setup
- added check for the presence of an runnable driver service at the time 
of installation filter on device

-------------------------------------------------------------------------------

Added 2018/12/16:

1. Improved Setup
- added "CopyIDs" button to copy DeviceInstanceID and HardwareIDs 
(for use in any external program restarting device (using atsiv method))
- added dpiAware tag to manifest

-------------------------------------------------------------------------------

Added 2017/01/08:

1. Setup now always wants/asks to run with Admin rights under modern Windows.

2. Added a note about disabling Secure Boot to run driver under Windows 10 x64
version 1607 (Anniversary Update).

-------------------------------------------------------------------------------

Added 2016/05/01:

1. Drivers was signed by kernel mode sign - no Test Mode needed for x64 
versions now. Thanks to people from OCN (www.overclock.net):

ownage11
Bucake
kr0w
qsxcv
Regulations
Alya

And my special thanks to jeshuastarr - as signing process organizer.

2. And drivers for overclocking up to 8000 Hz included now. Details on OCN:
http://www.overclock.net/t/1589644/usb-mouse-hard-overclocking-2000-hz
(and in README.2kHz-8kHz.ENG.TXT from jeshuastarr)

-------------------------------------------------------------------------------

Added 2016/03/10:

1. Improved Setup:
- generalised code of USB HID device detection (and now it works
with the Xbox 360 controllers)
- interface was made more user-friendly and foolproof
- added command line switch: /all (setup.exe /all) - allows you to set
driver for any USB device (under your personal liability)

-------------------------------------------------------------------------------

Added 2016/01/30:

1. Fixed bug in code of patching driver of USB3.0 controller (USBXHCI.SYS)
Bug can observed, for example, when USB audio device managed by USB3.0 
controller stop working.

-------------------------------------------------------------------------------

Added 2016/01/23:

1. Now Setup can install driver for Composite USB device
- use checkbox "Process Parent". Note, there is overclocked
all functional devices from composite device, not the mouse only.
For this feature functioning recompiled old drivers for Win 98&ME, 2000.

2. I was surprised to learn that some people use driver to change rate of
Full Speed USB mice. So, nonpatching version of x64 driver returned to package
and such kind of using described in Installation section.

-------------------------------------------------------------------------------

Added 2016/01/02:

1. Driver now compatible with Windows 8, 8.1, 10. And both USB stacks supported:
USB2.0 (USBPORT.SYS) and USB3.0 (USBXHCI.SYS)

-------------------------------------------------------------------------------

Added 2015/04/06:

1. Much of fixing and enhancement in Setup:
  - "Restart" button now really :) works under x64; 
  - USB HID mouse detected in multifunctional devices;
  - installed filter can be undoned on nonstarting devices
    (unsigned driver at x64...) - with unchecked "Mice Only";
  - add parent device column.

-------------------------------------------------------------------------------

Added 2009/02/11:

1. Driver (patcher of USBPORT.SYS) works in Windows 7 x64 now.

-------------------------------------------------------------------------------

Added 2009/02/03:

1. To load driver under Vista x64 SP1 you can use "Test Mode" method.
See DSEO program:
http://www.ngohq.com/home.php?page=dseo

-------------------------------------------------------------------------------

Added 2008/04/22:

1. Setup now aware of Windows x64. Don't forget - under Windows Vista 64 bit
driver will load only with disabled driver signature enforcement.

-------------------------------------------------------------------------------

Added 2008/04/19:

1. Windows Vista 64 bit checked and work (with disabled driver 
signature enforcement).

-------------------------------------------------------------------------------

Added 2007/05/16:

1. Windows Vista 32 bit checked and work. In principle, version for XP x64 
may work under Vista 64 bit, however AFAIK there is required 
digitally signed driver...
2. Documentation rewritten.
3. Patched USBPORT.SYS move into separate archive.

--------------------------------------------------------------------------------

Added 2006/09/30:

1. Drivers for 98/ME and 2000 shrink to fit in one page.
2. DRIVER folder and HIDUSBF.INF reordered.

--------------------------------------------------------------------------------

Added 2006/01/12:

1. Below-mentioned development is executed for XP x64.
Thank Dark_Cloud once again for recurrent testing.

--------------------------------------------------------------------------------

Added 2005/12/26:

1. Driver was enhanced - for its installation under XP is NOT 
required to install corrected USBPORT.SYS. However, if there is observed
some anomalies - you may go back to old working sequence
(corrected USBPORT.SYS + driver in the folder DRIVER\STD).
Thank Alan 'Strider' Kivlin for the idea of patching the code 
of USBPORT.SYS on the fly.
Thank Root for valuable link for implementation.
The same development for Windows XP x64 is still not done - there is a
difficulties with testing.

--------------------------------------------------------------------------------

Added 2005/08/08:

1. Translation was executed into English.
Job was done by TimFortress (email: mofey@front.ru) 2005/07/22
(*) in text above is translator additions.

2. In case of HIDUSBF service wasn't installed under Win x64 through Setup.EXE
(button "Install Service") you may try to do this by OS standard possibility:
mouse right button click on HIDUSBF.INF -> Install

3. There was added possibility to uninstall HIDUSBF service and file:
mouse right button click on HIDUSBFU.INF -> Install

--------------------------------------------------------------------------------

Added 2005/05/31:
Written documentation (in Russian).

--------------------------------------------------------------------------------

Added 2005/04/10:
Developed driver for Windows XP x64. Tested by Dark_Cloud.

--------------------------------------------------------------------------------

Added 2005/01/19:
Written GUI installer - SETUP.EXE

--------------------------------------------------------------------------------

2004/12/28:
Initial version, presented in article on overclockers.ru

--------------------------------------------------------------------------------
