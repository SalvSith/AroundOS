#!/usr/bin/env python3
"""Regression checks for Sony raw reports and the Linux ABS_X aliasing bug."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src/navcon'))
from core import Engine, Report, default_profile
from linux_input import Device, REPORT_BUTTONS, decode_report


def packet(x=128, y=128, buttons=(), padding_x=125, trigger=0):
    data = bytearray(49)
    data[0]=1;data[6]=x;data[7]=y;data[8]=padding_x;data[9]=128;data[18]=trigger
    for name in buttons:
        offset, mask = REPORT_BUTTONS[name]
        data[offset] |= mask
    return bytes(data)


class Sink:
    def __init__(self):self.moves=[]
    def move(self, x, y):self.moves.append((x,y))
    def key(self,*args):pass
    def button(self,*args):pass
    def scroll(self,*args):pass


class Tests(unittest.TestCase):
    def test_real_stick_ignores_unused_ds3_axis(self):
        for x in (0,255):
            sink=Sink();engine=Engine(sink,default_profile());engine.connect(True)
            engine.receive(decode_report(packet()))
            for n in range(1250):
                # Real capture: X stays 0/255 while unused DS3 axis jitters
                # near 125/126 and overwrites Linux's evdev ABS_X value.
                engine.receive(decode_report(packet(x=x,padding_x=125+n%2)))
                engine.tick(.008,n*.008)
            self.assertEqual(len(sink.moves),1250)
            self.assertTrue(all(dx<0 if x==0 else dx>0 for dx,_ in sink.moves))
            engine.receive(decode_report(packet()));engine.tick(.008,11)
            self.assertEqual(len(sink.moves),1250)

    def test_all_buttons_and_trigger(self):
        report=decode_report(packet(buttons=REPORT_BUTTONS,trigger=255))
        self.assertEqual(report.buttons,set(REPORT_BUTTONS))
        self.assertEqual(report.trigger,1)
        self.assertEqual(decode_report(packet()).buttons,set())

    def test_ignore_noninput_and_incomplete_reports(self):
        for data in (b'',b'\x01'*18,b'\x02'+packet()[1:],b'\x01\xff'+bytes(47)):
            self.assertIsNone(decode_report(data))

    def test_read_full_reports_preserves_button_release(self):
        device=Device.__new__(Device);device.fd=123;device.events=0;device.report=None
        with patch('linux_input.os.read',side_effect=[packet(buttons=['l1']),packet(x=255),BlockingIOError()]):
            reports=device.read()
        self.assertEqual(reports[0].buttons,{'l1'})
        self.assertEqual(reports[1].buttons,set())
        self.assertEqual(device.snapshot().x,255)
        self.assertEqual(device.events,2)

    def test_first_held_report_does_not_arm(self):
        engine=Engine(Sink(),default_profile());engine.connect(True)
        engine.receive(decode_report(packet(x=255)))
        self.assertFalse(engine.armed)
        engine.receive(decode_report(packet()))
        self.assertTrue(engine.armed)


if __name__=='__main__':unittest.main(verbosity=2)
