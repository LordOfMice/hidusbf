# ControllerSupercharge

**by Christian Pruitt**

A simple Windows app that raises your controller's USB polling rate, for example from 250 Hz to 1000 Hz, and lets you watch the controller live to check the difference.

It's a friendly front end for [hidusbf](https://github.com/LordOfMice/hidusbf) by SweetLow. That driver does the actual work.

## Using it

1. Run `ControllerSupercharge.exe` and click **Yes** when Windows asks for admin rights.
2. **Driver:** click **Install driver**. This is needed only once per PC. *Standard* works for almost every controller and is fine with Memory Integrity turned on.
3. **Pick the controller.** Plug it in with a cable, or use its wireless dongle. Bluetooth can't be changed.
4. **Choose a rate**, such as 1000 Hz, and click **Apply**. The controller restarts by itself.
5. Open **Live Test**, press **Start 5-second test** and spin a stick. Run the test before and after the change to compare.

To undo everything, use **Remove all**. It takes the filter off every device and uninstalls the driver.

Minimizing the window, or clicking **Minimize to tray**, hides it in the system tray. Double-click the tray icon to bring it back.

### Notes

- The Live Test tab reads controllers through XInput: Xbox controllers, and anything that shows up as one (Steam Input, DS4Windows and so on).
- If the rate doesn't change, tick **Apply to the whole composite device**, or unplug and replug the controller.
- **Stuck at the same rate?** Pick 125 Hz and test again. If the rate drops, the driver works and the controller has a fixed internal rate that no software can raise. For example, the PowerA wired Xbox Series controller (20D6:2035) tops out at 250 Hz: setting 62 Hz measured 62.5 Hz, but 1000 Hz still measured 250 Hz.
- After **Remove all**, restart the PC before installing the driver again.

## How it works

The app does the same things as hidusbf's own `Setup.exe`:

| Step | What happens |
|---|---|
| Install driver | Copies `hidusbf.sys` to `System32\drivers` and creates the `hidusbf` kernel service |
| Apply | Adds `hidusbf` to the device's **LowerFilters** and writes **bInterval** (1 = 1000 Hz, 2 = 500, 4 = 250, 8 = 125) to the device's driver registry key |
| Restart | Power-cycles the USB port, like a replug, which apps like XBOX Input Service can't block. Falls back to `pnputil /restart-device` |

## Building from source

```bat
pip install -r requirements.txt
build.bat
```

The result is `dist\ControllerSupercharge.exe`, a single file with the drivers bundled inside.

To run from source, use `python app.py`. It asks for admin rights; add `--no-admin` to just look around.

## Credits

- hidusbf driver: SweetLow ([original README](README.hidusbf.md)) (public domain binaries). The drivers are signed thanks to Battle Beaver Customs.
- App: Christian Pruitt

Changing USB polling rates is at your own risk.
