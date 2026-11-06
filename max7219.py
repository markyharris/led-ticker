# MAX7219 chain driver for Mark's ticker boards (MicroPython)
#
# Orientation - MEASURED on his hardware, Oct 30 2026:
#   Viewing the FRONT of a quad with its DIN feed entering at the RIGHT:
#     - digit register (1+r), r=0  -> TOP row of the module
#     - data byte bit 7 (0x80)     -> LEFTMOST column of that row
#   So per module: rows top-down, MSB = leftmost pixel (no rotation needed).
#   Chain: data enters at the viewer's RIGHT, so the first word sent in a
#   frame lands in the LEFTMOST module. show() therefore sends modules
#   left-to-right. If a build is ever fed from the left instead, set
#   FEED_FROM_RIGHT = False and send order reverses.
#
# Canvas: framebuf MONO_VLSB, x=0 at viewer's left, y=0 at top.

from machine import Pin, SPI
import framebuf
import time

FEED_FROM_RIGHT = True

_REG_DECODE    = 0x09
_REG_INTENSITY = 0x0A
_REG_SCANLIMIT = 0x0B
_REG_SHUTDOWN  = 0x0C
_REG_TEST      = 0x0F


class Chain:
    def __init__(self, spi, cs_pin, num_modules, intensity=6):
        self.spi = spi
        self.cs = Pin(cs_pin, Pin.OUT, value=1)
        self.num = num_modules
        self.width = num_modules * 8
        self.intensity = max(0, min(15, intensity))
        self.buf = bytearray(self.width)          # 1 byte per column, bit0 = top
        self.fb = framebuf.FrameBuffer(self.buf, self.width, 8,
                                       framebuf.MONO_VLSB)
        self.init()

    # -- low level ------------------------------------------------------
    def _send(self, words):
        """words: list of (reg, value) tuples, one per module, in SEND order."""
        self.cs.value(0)
        for reg, val in words:
            self.spi.write(bytes((reg, val)))
        self.cs.value(1)

    def _all(self, reg, val):
        self._send([(reg, val)] * self.num)

    # -- configuration --------------------------------------------------
    def init(self):
        """(Re)write every config register. Safe to call any time - it does
        not touch the digit data, so a running picture is undisturbed.
        Calling this about once a second makes the chain self-healing:
        a module whose registers were scrambled by a noise glitch
        (the blank-square fault) recovers within a second."""
        self._all(_REG_TEST, 0)
        self._all(_REG_SCANLIMIT, 7)
        self._all(_REG_DECODE, 0)
        self._all(_REG_INTENSITY, self.intensity)
        self._all(_REG_SHUTDOWN, 1)

    def set_intensity(self, v):
        self.intensity = max(0, min(15, v))
        self._all(_REG_INTENSITY, self.intensity)

    def clear(self):
        self.fb.fill(0)
        self.show()

    # -- frame output ---------------------------------------------------
    def show(self):
        order = range(self.num) if FEED_FROM_RIGHT else range(self.num - 1, -1, -1)
        for r in range(8):
            words = []
            for m in order:
                b = 0
                base = m * 8
                for lx in range(8):
                    if (self.buf[base + lx] >> r) & 1:
                        b |= 0x80 >> lx
                words.append((1 + r, b))
            self._send(words)


def make_chain(num_modules=4, intensity=6):
    """Bench/sign wiring: DIN=GPIO12, CLK=GPIO18, CS=GPIO13 (ESP32-S3: no GPIO23 exists)."""
    spi = SPI(1, baudrate=1_000_000, polarity=0, phase=0,
              sck=Pin(18), mosi=Pin(12))
    return Chain(spi, 13, num_modules, intensity)
