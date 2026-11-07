#!/usr/bin/env python3
"""Behavior tests for cursor feel, neutral arming, shared holds, and cleanup."""
from copy import deepcopy
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src/navcon'))
from core import Engine, Profiles, Report, default_profile, mapping, sanitize, velocity


class Sink:
    def __init__(self):self.events=[]
    def key(self,*args):self.events.append(('key',*args))
    def button(self,*args):self.events.append(('button',*args))
    def move(self,*args):self.events.append(('move',*args))
    def scroll(self,*args):self.events.append(('scroll',*args))


class Tests(unittest.TestCase):
    def setUp(self):
        self.sink=Sink();self.profile=default_profile();self.engine=Engine(self.sink,self.profile)
        self.engine.connect(True);self.engine.receive(Report())

    def press(self,*buttons,x=128,y=128):self.engine.receive(Report(x,y,buttons=set(buttons)))

    def test_owner_mappings(self):
        self.assertEqual(self.profile['speed'],1450)
        self.press('cross');self.press();self.press('circle');self.press()
        self.assertEqual(self.sink.events,[('key',1,True),('key',1,False),('key',28,True),('key',28,False)])
        self.assertEqual(self.profile['mappings']['ps']['kind'],'none')
        self.assertEqual(self.profile['mappings']['l1']['kind'],'leftClick')
        self.assertEqual(self.profile['mappings']['l2']['kind'],'rightClick')
        self.assertEqual(self.profile['mappings']['circle']['key'],28)

    def test_velocity_deadzone_diagonal_calibration_and_boost(self):
        p=self.profile
        self.assertEqual(velocity(Report(129,126),p),(0,0))
        a=velocity(Report(255,255),p)
        self.assertAlmostEqual(math.hypot(*a),1450*1.5)
        self.assertEqual(velocity(Report(255,255),p,True),(a[0]*2,a[1]*2))
        p['centerX']=125;p['centerY']=130;p['invertY']=True
        self.assertEqual(velocity(Report(125,130),p),(0,0))
        self.assertLess(velocity(Report(255,255),p)[1],0)

    def test_neutral_required_after_reconnect_and_edit(self):
        self.engine.connect(True);self.press('l1',x=255);self.assertEqual(self.sink.events,[])
        self.press(x=255);self.assertFalse(self.engine.armed)
        self.press();self.press('l1');self.assertIn(('button',272,True),self.sink.events)
        self.engine.set_editing(True);self.assertEqual(self.sink.events[-1],('button',272,False))
        self.engine.set_editing(False);self.press('l1');self.assertFalse(self.engine.active)
        self.press();self.press('l1');self.assertTrue(self.engine.active)

    def test_shared_mouse_hold_releases_only_last_owner(self):
        self.profile['mappings']['cross']=mapping('leftClick')
        self.press('l1');self.press('l1','cross');self.press('cross')
        self.assertEqual(self.sink.events,[('button',272,True)])
        self.press();self.assertEqual(self.sink.events[-1],('button',272,False))

    def test_shared_shortcuts_and_modifier_order(self):
        self.profile['mappings']['cross']=mapping('shortcut',46,[29])
        self.profile['mappings']['circle']=mapping('shortcut',46,[29])
        self.press('cross');self.press('cross','circle');self.press('circle');self.press()
        self.assertEqual(self.sink.events,[('key',29,True),('key',46,True),('key',46,False),('key',29,False)])

    def test_disconnect_releases_everything(self):
        self.press('l1','l2','circle','l3');self.engine.connect(False)
        self.assertEqual(self.engine.keys,set());self.assertEqual(self.engine.mouse,set())
        self.assertIn(('key',28,False),self.sink.events)
        self.assertIn(('button',272,False),self.sink.events)
        self.assertIn(('button',273,False),self.sink.events)

    def test_pause_release_and_rearm(self):
        self.profile['mappings']['ps']=mapping('pause')
        self.press('l1');self.press('l1','ps')
        self.assertFalse(self.engine.enabled);self.assertEqual(self.engine.mouse,set())
        self.press();self.press('ps');self.assertTrue(self.engine.enabled)
        self.assertFalse(self.engine.armed);self.press();self.assertTrue(self.engine.armed)

    def test_smoothing_stops_immediately_at_neutral(self):
        self.press(x=255);self.engine.tick(.01,1)
        self.assertTrue(self.sink.events[-1][1]>0)
        self.press();count=len(self.sink.events);self.engine.tick(.01,2)
        self.assertEqual(len(self.sink.events),count);self.assertEqual(self.engine.smooth_x,0)

    def test_steady_stick_keeps_moving_without_new_reports(self):
        for x,y in [(0,128),(255,128),(128,0),(128,255)]:
            with self.subTest(x=x,y=y):
                self.engine.connect(True);self.press();self.sink.events.clear()
                self.press(x=x,y=y)
                for n in range(1250):self.engine.tick(.008,n*.008)
                moves=[event[1:] for event in self.sink.events if event[0]=='move']
                self.assertEqual(len(moves),1250)
                vx,vy=velocity(Report(x,y),self.profile)
                self.assertAlmostEqual(moves[-1][0],vx*.008)
                self.assertAlmostEqual(moves[-1][1],vy*.008)
                self.press();count=len(self.sink.events);self.engine.tick(.008,11)
                self.assertEqual(len(self.sink.events),count)

    def test_profile_change_releases_held_input(self):
        self.press('l1');p=default_profile();p['mappings']['l1']=mapping('none')
        self.engine.set_profile(p);self.assertEqual(self.sink.events[-1],('button',272,False))
        self.assertFalse(self.engine.armed)

    def test_saved_profile_receives_new_buttons_once(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'profiles.json'
            profile = default_profile()
            profile['mappings']['cross'] = mapping('none')
            profile['mappings']['circle'] = mapping('rightClick')
            path.write_text(json.dumps({'version':1,'profiles':[profile],'selected':profile['id']}))
            store = Profiles(path)
            self.assertEqual(store.current['mappings'],default_profile()['mappings'])
            store.current['mappings']['cross'] = mapping('none')
            store.save()
            self.assertEqual(Profiles(path).current['mappings']['cross'],mapping('none'))

    def test_profiles_roundtrip_corruption_and_sanitize(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'profiles.json';store=Profiles(path);store.save();store.duplicate()
            store.current['speed']=float('nan');store.current['deadZone']=1;store.save()
            reread=Profiles(path);self.assertEqual(len(reread.profiles),2)
            self.assertEqual(reread.current['speed'],1450);self.assertEqual(reread.current['deadZone'],.4)
            reread.delete();self.assertEqual(len(reread.profiles),1)
            path.write_text('broken');new=Profiles(path);self.assertTrue(new.notice)
            self.assertEqual(next(Path(d).glob('*.invalid-*')).read_text(),'broken')


if __name__=='__main__':unittest.main(verbosity=2)
