"""Numbers read out of the controller firmware, in one place.

Source: `heatsynclabs/Open_Access_Control_Ethernet`,
`Open_Access_Control_Ethernet.ino`, org fork HEAD 60e499c, dated 2013-12-02.
Line numbers below name that file. Every value here was read rather than
remembered, and the two that carry no line number carry a confirmation step
instead.

Both the codec and the fake device read these, so there is one copy of each
number and the two cannot drift apart. If the controller is reflashed, this is
the file that changes.
"""
from __future__ import annotations

# Every answer starts with this, whatever happened. The status code is always
# 200: there is no 4xx and no 5xx, and errors are strings in the body.
FIXED_RESPONSE_HEADER = (b"HTTP/1.1 200 OK\r\nCache-Control: no-store\r\n"
                         b"Content-Type: text/html\r\n\r\n")

# The request is accumulated into a String capped at 100 characters, and that
# String is initialised as `String(100)`, which in Arduino constructs the
# literal text "100" rather than reserving 100 bytes. Three characters are
# spent before the request arrives, so only 97 are ever seen.
REQUEST_VISIBLE_BYTES = 97

# PRIVPASSWORD, line 112. Parsed as exactly four characters and passed to
# strtoul with base 16. The value in the public repository is a default; the
# live one is in a secret store that only the door service reads.
PASSWORD_HEX_DIGITS = 4

# login() refuses privileged mode once there have been this many consecutive
# failures, and it refuses for this long. A correct password inside the window
# is refused too, because the guard is checked before the password is. The
# window is armed only while the failure count is zero, so once the first one
# elapses it is never armed again and the throttle is spent for the life of the
# boot. The fake models that rather than quietly fixing it.
#
# ASSUMPTION: the count is 5 and the window is 300000 milliseconds.
# CONFIRM BY: read login() in `Open_Access_Control_Ethernet.ino` at the org fork
#             HEAD 60e499c. The firmware reading these came from recorded the
#             behaviour but not the line, and provoking the lockout on the live
#             controller would shut the lab's own door service out of privileged
#             mode for five minutes.
# BLAST RADIUS: the fake refuses a login after a different number of failures
#               than the hardware does. What the adapter does about a refusal is
#               the same either way, and that is what the suite checks.
LOGIN_FAILURES_BEFORE_LOCKOUT = 5
LOGIN_LOCKOUT_SECONDS = 300

# EEPROM_FIRSTUSER, line 130. Somebody will try to correct this to 1000.
EEPROM_FIRSTUSER = 24

# EEPROM_LASTUSER, line 131.
EEPROM_LASTUSER = 1024

# The ATmega328P on an Uno or a Duemilanove has 1024 bytes of EEPROM, at
# addresses 0 to 1023. EEPROM_LASTUSER is one past the end.
EEPROM_SIZE = 1024

# The AVR EEPROM address register is 10 bits, so an address past the end wraps
# rather than faulting. Arduino's EEPROM.write masks and writes somewhere else.
EEPROM_ADDRESS_MASK = 0x3FF

# Lines 1456 to 1460: 4 bytes of tag number, little endian, then 1 byte of
# permission mask.
SLOT_RECORD_BYTES = 5

# NUMUSERS, line 132: the span from EEPROM_FIRSTUSER to EEPROM_LASTUSER,
# divided by the record size, which comes to 200 slots.
NUMUSERS = (EEPROM_LASTUSER - EEPROM_FIRSTUSER) // SLOT_RECORD_BYTES

# alarmActivated and alarmArmed, persisted at EEPROM 0 and 1.
EEPROM_ALARM = 0
EEPROM_ALARM_ARMED = 1

# Trained analog baselines for alarm zones 0 to 3, EEPROM 20 to 23.
EEPROM_ALARM_ZONES = 20

# A byte that has never been written on a fresh AVR reads 0xFF, which is why an
# unwritten alarm byte reports 255 rather than 0.
EEPROM_ERASED_BYTE = 0xFF

# DOORDELAY, the relock timer after a pulse, in milliseconds.
DOOR_RELOCK_MILLISECONDS = 5000

# The firmware drives two doors and two readers. `?l=3` and any other value on
# the lock path silently locks everything, with no err:door#, so an unknown
# door has to be refused before the request is built.
DOOR_NUMBERS = (1, 2)
