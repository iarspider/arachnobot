import asyncio
import evdev
from evdev import ecodes
from loguru import logger

# USB Vendor:Product ID for your keyboard
TARGET_VENDOR = 0x1C4F
TARGET_PRODUCT = 0x0002


def find_target_keyboard() -> evdev.InputDevice | None:
    """Find the keyboard matching the target vendor/product ID."""
    # for path in evdev.list_devices():
    #     device = evdev.InputDevice(path)
    #     info = device.info
    #     if info.vendor == TARGET_VENDOR and info.product == TARGET_PRODUCT:
    #         # Verify it has key capabilities
    #         caps = device.capabilities()
    #         if ecodes.EV_KEY in caps:
    #             return device
    #     device.close()
    # return None
    return evdev.InputDevice("/dev/input/by-id/usb-SIGMACHIP_USB_Keyboard-event-kbd")


async def keyboard_listener(twitch_bot) -> None:
    """
    Exclusively capture input from the target USB keyboard.
    Triggers RIP command when Enter is pressed.
    """
    device = find_target_keyboard()
    if device is None:
        logger.error(f"Keyboard {TARGET_VENDOR:04x}:{TARGET_PRODUCT:04x} not found!")
        return

    logger.info(f"Found keyboard: {device.name} at {device.path}")

    # Grab the device exclusively - no other programs will receive its input
    device.grab()
    logger.info("Device grabbed exclusively")

    try:
        async for event in device.async_read_loop():
            # logger.info(f"{event.type=} =?= {ecodes.EV_KEY} , {event.value=} =?= 1")
            # Only handle key press events (value=1), not release (0) or repeat (2)
            if event.type == ecodes.EV_KEY and event.value == 1:
                # logger.info(
                #     f"{event.code=} =?= {ecodes.KEY_KPENTER}, {ecodes.KEY_ENTER}"
                # )
                if event.code == ecodes.KEY_ENTER or event.code == ecodes.KEY_KPENTER:
                    # logger.debug("Enter pressed - triggering RIP")
                    try:
                        ripcog = twitch_bot.get_component("RIPCog")
                        msg = await ripcog.do_rip(n=1)
                        await twitch_bot.send_message(msg)
                    except Exception as e:
                        logger.error(f"Error executing RIP command: {e}")
                else:
                    pass
                    # logger.debug("Wrong code")
            else:
                pass
                # logger.debug("Wrong type and/or value")
    except asyncio.CancelledError:
        logger.warning("Keyboard listener cancelled")
        raise
    finally:
        device.ungrab()
        device.close()
        logger.info("Device released")
