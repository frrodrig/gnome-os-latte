"""Nonblocking preparation of a GNOME OS installation."""

import dbus


def begin_installation(installer, device, oem_mode, erase, on_ready, on_error):
    """Keep GTK responsive; never start installation after failed preparation."""
    def failed(stage, error):
        on_error(f"{stage}: {error}. Disk state may have changed; collect logs before retrying")

    def install(*unused):
        try:
            installer.install(
                device, oem_mode, on_ready,
                lambda error: failed("Starting installation failed", error),
            )
        except dbus.DBusException as error:
            failed("Starting installation failed", error)

    if erase:
        try:
            installer.erase_disk(
                device,
                reply_handler=install,
                error_handler=lambda error: failed("Disk preparation failed", error),
            )
        except dbus.DBusException as error:
            failed("Disk preparation failed", error)
    else:
        install()
