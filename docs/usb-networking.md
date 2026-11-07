# Networking over USB

AroundOS runs with a normal Ethernet or Wi-Fi connection. A Raspberry Pi 4 configured as a USB Ethernet gadget can also receive network access through a host computer. The desktop installer leaves the network configuration to the OS.

## Connect a configured gadget

1. Configure the Pi for USB device mode with a USB Ethernet gadget supported by both the host and the Pi kernel. Use a data-capable cable and check the available power budget.
2. On a Mac, open **System Settings → General → Sharing → Internet Sharing**. Choose the upstream connection and the USB network interface. Enable sharing.
3. At the Pi's terminal, run `ip -br address` to find the USB interface and its assigned address. Check the default route with `ip route`.
4. If you enabled SSH in Raspberry Pi OS, connect from the host with your own username and the assigned USB address. Verify a new SSH host fingerprint against the one obtained on the Pi console.

If the Pi has a link but no route, check that Internet Sharing targets the current USB interface. Use the Pi's local console before changing gadget mode or interfaces, since those changes can interrupt the connection.
