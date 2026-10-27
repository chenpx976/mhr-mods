import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from manager import ModManager, FIXED, atomic_json

class ManagerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.base=Path(self.tmp.name).resolve()
        self.root=self.base/'game';self.root.mkdir()
        (self.root/'MonsterHunterRise.exe').write_bytes(b'game')
        for files in FIXED.values():
            for rel in files:
                p=self.root/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(rel.encode())
        for rel in ['reframework/autorun/MHR_Overlay.lua','reframework/autorun/MHR_Overlay/Misc/config.lua','reframework/data/MHR Overlay/config.json']:
            p=self.root/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'original')
        self.running=False
        self.m=ModManager(self.root,self.base/'backups',lambda:self.running,lambda:False)
    def tearDown(self):self.tmp.cleanup()
    def mod(self,key):return next(m for m in self.m.status()['mods'] if m['id']==key)
    def test_round_trip_preserves_assets_and_config(self):
        orig=(self.root/FIXED['birds'][0]).read_bytes()
        self.m.set_enabled('birds',False);self.assertFalse(self.mod('birds')['enabled'])
        self.m=ModManager(self.root,self.base/'backups',lambda:False,lambda:False)
        self.m.set_enabled('birds',True)
        self.assertEqual((self.root/FIXED['birds'][0]).read_bytes(),orig)
        cfg=self.root/'reframework/data/MHR Overlay/config.json'
        self.m.set_enabled('overlay',False);self.assertEqual(cfg.read_bytes(),b'original')
        self.assertTrue(Path(self.m.status()['last_backup'],'sha256.json').exists())
    def test_dependencies_and_live_game_rejected(self):
        with self.assertRaisesRegex(ValueError,'先关闭'):self.m.set_enabled('framework',False)
        self.m.set_enabled("d2d",False)
        self.assertTrue(self.mod("overlay")["enabled"])
        self.assertFalse(self.mod("d2d")["enabled"])
        self.running=True
        with self.assertRaisesRegex(ValueError,'退出'):self.m.set_enabled('birds',False)
        self.assertTrue(self.mod("birds")["enabled"])
    def test_fast_return_round_trip_preserves_bindings_and_all_assets(self):
        cfg=self.root/'reframework/data/bth_settings.json'
        cfg.write_text('{"padCDSkipBtn":4096,"autoskipCountdown":false}')
        original={rel:(self.root/rel).read_bytes() for rel in FIXED['fast_return']}
        self.m.set_enabled('fast_return',False)
        self.assertFalse(self.mod('fast_return')['enabled'])
        self.assertTrue(all(not (self.root/rel).exists() for rel in original))
        self.assertEqual(json.loads(cfg.read_text())['padCDSkipBtn'],4096)
        self.m=ModManager(self.root,self.base/'backups',lambda:False,lambda:False)
        self.m.set_enabled('fast_return',True)
        self.assertTrue(self.mod('fast_return')['enabled'])
        self.assertEqual({rel:(self.root/rel).read_bytes() for rel in original},original)
        self.assertFalse(json.loads(cfg.read_text())['autoskipCountdown'])
    def test_failed_move_rolls_back_all_files(self):
        import manager
        original=manager.os.replace;count=0
        def fail_once(a,b):
            nonlocal count
            if str(b).endswith('mod_utils.lua') and '.mhrmods/disabled' in str(b) and count==0:
                count+=1;raise OSError('simulated disk error')
            return original(a,b)
        with patch('manager.os.replace',side_effect=fail_once):
            with self.assertRaises(OSError):self.m.set_enabled('skip_dango',False)
        self.assertTrue(self.mod('skip_dango')['enabled'])
        self.assertFalse(self.m.journal.exists())
    def test_crash_journal_recovery(self):
        a=self.root/FIXED['birds'][0];b=self.m.store/'disabled/birds'/FIXED['birds'][0]
        b.parent.mkdir(parents=True);a.rename(b)
        atomic_json(self.m.journal,{'moves':[[str(a.relative_to(self.root)),str(b.relative_to(self.root))]]})
        self.assertTrue(self.mod('birds')['enabled']);self.assertFalse(b.exists())
    def test_fluffy_running_rejected(self):
        self.m.other_running=lambda:True
        with self.assertRaisesRegex(ValueError,"Fluffy"):self.m.set_enabled("birds",False)

    def test_symlink_and_traversal_rejected(self):
        p=self.root/FIXED['birds'][0];p.unlink();p.symlink_to(self.base/'secret')
        with self.assertRaises(ValueError):self.m.status()
        with self.assertRaises(ValueError):self.m.safe(self.root,'../secret')
    def test_legacy_vip_stays_off_until_explicitly_enabled(self):
        p=self.root/FIXED['vip_dango'][0];p.rename(self.root/'VIP_Dango_Ticket.lua')
        self.assertFalse(self.mod('vip_dango')['enabled'])
        self.m.set_enabled('vip_dango',True)
        self.assertTrue(p.exists());self.assertFalse((self.root/'VIP_Dango_Ticket.lua').exists())
    def test_conflicting_files_not_overwritten(self):
        self.m.set_enabled('birds',False)
        (self.root/FIXED['birds'][0]).write_bytes(b'external install')
        with self.assertRaises(ValueError):self.m.set_enabled('birds',True)
        self.assertEqual((self.root/FIXED['birds'][0]).read_bytes(),b'external install')

if __name__=='__main__':unittest.main()
