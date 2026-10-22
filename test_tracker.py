import unittest
from damage_share import Tracker

class TrackerTests(unittest.TestCase):
    def stable(self, tracker, t, actor, value, present=True):
        tracker.push(t,actor,value,present)
        tracker.push(t+.1,actor,value,present)
    def test_lingering_damage_waits_for_number_change(self):
        t=Tracker()
        self.stable(t,0,'Firefly',491203)
        self.stable(t,1,'The Dahlia',491203)
        self.assertEqual(t.current['actor'],'Firefly')
        self.stable(t,2,'The Dahlia',171619)
        self.assertEqual(t.events[0]['damage'],491203)
        self.assertEqual(t.current['actor'],'The Dahlia')
    def test_higher_new_total_also_hands_over(self):
        t=Tracker()
        self.stable(t,0,'A',100)
        self.stable(t,1,'B',100)
        self.stable(t,2,'B',200)
        self.assertEqual(t.current['actor'],'B')
        self.assertEqual(t.events[0]['damage'],100)
    def test_unreadable_is_not_absence(self):
        t=Tracker()
        self.stable(t,0,'A',100)
        self.stable(t,1,None,None)
        self.assertEqual(t.current['damage'],100)
        self.stable(t,2,None,None,False)
        t.push(3.1,None,None,False)
        self.assertIsNone(t.current)
    def test_single_frame_number_noise_ignored(self):
        t=Tracker()
        self.stable(t,0,'A',100)
        t.push(1,'A',10,True)
        t.finish_event('interval_end')
        self.assertEqual(t.events[0]['damage'],100)
    def test_unknown_actor_remains_unattributed(self):
        t=Tracker()
        self.stable(t,0,None,100)
        self.assertIsNone(t.current['actor'])



class TurnTests(unittest.TestCase):
    def stable(self,t,sec,actor,value,faction='ally',present=True):
        t.push(sec,actor,value,present,faction)
        t.push(sec+.1,actor,value,present,faction)
    def test_non_damaging_turn_does_not_inherit_total(self):
        t=Tracker()
        self.stable(t,0,'A',100)
        self.stable(t,1,'B',100)
        self.stable(t,2,'C',100)
        self.stable(t,3,'C',200)
        self.assertEqual([(e['actor'],e['damage']) for e in t.events],[('A',100)])
        self.assertFalse(next(a for a in t.actions if a['actor']=='B')['damage_observed'])
        self.assertEqual(t.current['actor'],'C')
    def test_enemy_clears_pending_actor(self):
        t=Tracker()
        self.stable(t,0,'A',100)
        self.stable(t,1,'B',100)
        self.stable(t,2,None,100,'enemy')
        self.assertIsNone(t.pending_actor)
        self.stable(t,3,None,800,'enemy')
        self.assertIsNone(t.current)
        self.stable(t,4,'C',800)
        self.assertIsNone(t.current)
        self.stable(t,5,'C',200)
        self.assertEqual(t.current['actor'],'C')
    def test_same_actor_after_enemy_is_new_action(self):
        t=Tracker()
        self.stable(t,0,'A',100)
        self.stable(t,1,None,100,'enemy')
        self.stable(t,2,'A',100)
        self.stable(t,3,'A',200)
        self.assertEqual(t.events[0]['damage'],100)
        self.assertEqual(t.current['damage'],200)

if __name__=='__main__': unittest.main()
