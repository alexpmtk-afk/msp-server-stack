import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/'payload'))
import start_root as install
class TimerTests(unittest.TestCase):
 def test_running_enabled_timer_can_temporarily_have_no_next_timestamp(self):
  self.assertTrue(install.timer_installed(dict(ActiveState='active',UnitFileState='enabled',SubState='running',NextElapseUSecRealtime='')))
 def test_disabled_or_inactive_timer_is_not_installed(self):
  self.assertFalse(install.timer_installed(dict(ActiveState='inactive',UnitFileState='enabled',NextElapseUSecRealtime='tomorrow')))
  self.assertFalse(install.timer_installed(dict(ActiveState='active',UnitFileState='disabled',NextElapseUSecRealtime='tomorrow')))
if __name__=='__main__':unittest.main()
