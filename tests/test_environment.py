import asyncio
import hashlib
import json
from pathlib import Path
import struct
import sys
import tarfile
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from environment import EnvironmentGuard, RUNTIME_DLLS, TESTED_RUNTIME, file_version
from manager import ModManager, FIXED, atomic_json
from main import Plugin


def dll(version):
    a,b,c,d=version
    return b'fixture-version-resource' + struct.pack('<IIII',0xFEEF04BD,0x10000,(a<<16)|b,(c<<16)|d)


class EnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.base=Path(self.temp.name)
        self.steam=self.base/'Steam';self.root=self.steam/'steamapps/common/MonsterHunterRise'
        self.root.mkdir(parents=True);(self.root/'MonsterHunterRise.exe').write_bytes(b'game')
        self.running=False;self.fluffy=False
        self.manager=ModManager(self.root,self.base/'backups',lambda:self.running,lambda:self.fluffy)
        self.assets=self.base/'assets';self.assets.mkdir()
        for name in ['vc_redist.x64.exe','reframework-d2d.dll','reframework-d2d.lua']:
            (self.assets/name).write_bytes(('trusted fixture '+name).encode())
        self.hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in self.assets.iterdir()}
        self.patcher=patch('environment.ASSET_HASHES',self.hashes);self.patcher.start()
        self.guard=EnvironmentGuard(self.manager,self.steam,self.assets,installer=self.install)
        self.system=self.guard.prefix/'pfx/drive_c/windows/system32';self.system.mkdir(parents=True)
        (self.guard.prefix/'pfx/system.reg').write_text('registry')
        self.set_versions(TESTED_RUNTIME)
        for rel in FIXED['d2d']:
            p=self.root/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((self.assets/p.name).read_bytes())
        for rel in ['dinput8.dll','reframework/autorun/MHR_Overlay.lua']:
            p=self.root/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'framework fixture')
        self.config=self.root/'reframework/data/MHR Overlay/configs/custom.json'
        atomic_json(self.config,{'global_settings':{'renderer':{'use_d2d_if_available':True},'language':'zh-cn'},'user_preference':[1,2,3]})
        atomic_json(self.config.parent.parent/'config.json',{'config':'custom'})
        self.save=self.steam/'userdata/123/1446780/remote/save.dat'
        self.save.parent.mkdir(parents=True);self.save.write_bytes(b'precious save')
        self.installs=0
    def tearDown(self):
        self.patcher.stop();self.temp.cleanup()
    def set_versions(self,version):
        for name in RUNTIME_DLLS:(self.system/name).write_bytes(dll(version))
    def install(self,backup):
        self.installs+=1
        self.assertTrue((backup/'prefix-sha256.json').is_file())
        with tarfile.open(backup/'compatdata-saves-before.tar.gz') as tar:
            self.assertEqual(tar.extractfile('userdata/123/1446780/remote/save.dat').read(),b'precious save')
            old=tar.extractfile('compatdata/1446780/pfx/drive_c/windows/system32/msvcp140.dll').read()
            self.assertIn(dll((14,28,29334,0)),old)
        self.set_versions(TESTED_RUNTIME)
    def test_healthy_environment_is_noop_and_newer_runtime_preserved(self):
        self.set_versions((14,52,40000,0));self.assertTrue(self.guard.status()['healthy'])
        self.guard.repair();self.assertEqual(self.installs,0);self.assertFalse(self.manager.backup_root.exists())
        self.assertEqual(file_version(self.system/'msvcp140.dll'),(14,52,40000,0))
    def test_old_runtime_backed_up_before_install_and_saves_unchanged(self):
        self.set_versions((14,28,29334,0));self.assertTrue(self.guard.status()['can_repair'])
        self.guard.repair();self.assertTrue(self.guard.status()['healthy']);self.assertEqual(self.installs,1)
        self.assertEqual(self.save.read_bytes(),b'precious save')
        self.assertEqual(json.loads((Path(self.guard.last_backup)/'repair.json').read_text())['state'],'done')
    def test_missing_dll_is_not_mistaken_for_healthy_runtime(self):
        (self.system/'vcruntime140_1.dll').unlink()
        self.assertFalse(self.guard.status()['healthy']);self.assertTrue(self.guard.status()['can_repair'])
    def test_restores_disabled_d2d_and_profile_without_resetting_preferences(self):
        for rel in FIXED['d2d']:
            p=self.manager.store/'disabled/d2d'/rel;p.parent.mkdir(parents=True,exist_ok=True);(self.root/rel).rename(p)
        config=json.loads(self.config.read_text());config['global_settings']['renderer']['use_d2d_if_available']=False
        atomic_json(self.config,config);original=self.config.read_bytes();mode=self.config.stat().st_mode
        self.guard.repair();self.assertEqual(self.installs,0)
        result=json.loads(self.config.read_text());self.assertTrue(result['global_settings']['renderer']['use_d2d_if_available'])
        self.assertEqual(result['user_preference'],[1,2,3]);self.assertEqual(result['global_settings']['language'],'zh-cn')
        self.assertEqual(self.config.stat().st_mode,mode)
        self.assertEqual((Path(self.guard.last_backup)/self.config.relative_to(self.root)).read_bytes(),original)
        self.assertTrue(self.guard.status()['healthy'])
    def test_unknown_d2d_version_is_never_overwritten(self):
        p=self.root/FIXED['d2d'][1];p.write_bytes(b'newer external release')
        self.assertFalse(self.guard.status()['can_repair'])
        with self.assertRaisesRegex(ValueError,'人工'):self.guard.repair()
        self.assertEqual(p.read_bytes(),b'newer external release');self.assertFalse(self.manager.backup_root.exists())
    def test_tampered_repair_asset_is_rejected_before_backup_or_execution(self):
        (self.assets/'vc_redist.x64.exe').write_bytes(b'untrusted');self.assertFalse(self.guard.status()['can_repair'])
        with self.assertRaises(ValueError):self.guard.repair()
        self.assertEqual(self.installs,0);self.assertFalse(self.manager.backup_root.exists())
    def test_live_game_and_fluffy_are_rejected_before_writes(self):
        self.running=True
        with self.assertRaisesRegex(ValueError,'退出 MHR'):self.guard.repair()
        self.running=False;self.fluffy=True
        with self.assertRaisesRegex(ValueError,'Fluffy'):self.guard.repair()
        self.assertFalse(self.manager.backup_root.exists())
    def test_game_launch_during_backup_cancels_before_install(self):
        self.set_versions((14,28,29334,0))
        def progress(**update):
            if 'backup' in update:self.running=True
        with self.assertRaisesRegex(RuntimeError,'退出 MHR'):self.guard.repair(progress)
        self.assertEqual(self.installs,0);self.assertEqual(file_version(self.system/'msvcp140.dll'),(14,28,29334,0))
    def test_install_failure_preserves_mods_and_records_backup(self):
        self.set_versions((14,28,29334,0));original=self.config.read_bytes()
        self.guard.installer=Mock(side_effect=RuntimeError('installer failed'))
        with self.assertRaisesRegex(RuntimeError,'备份'):self.guard.repair()
        self.assertEqual(self.config.read_bytes(),original)
        self.assertEqual(json.loads((Path(self.guard.last_backup)/'repair.json').read_text())['state'],'failed')
    def test_profile_traversal_and_missing_prefix_require_manual_action(self):
        atomic_json(self.config.parent.parent/'config.json',{'config':'../../secret'})
        self.assertFalse(self.guard.status()['can_repair'])
        (self.guard.prefix/'pfx/system.reg').unlink();self.assertFalse(self.guard.status()['can_repair'])
    def test_truncated_version_resource_is_not_accepted(self):
        p=self.system/'msvcp140.dll';p.write_bytes(struct.pack('<II',0xFEEF04BD,0x10000))
        self.assertIsNone(file_version(p));self.assertFalse(self.guard.status()['healthy'])


class BackendRepairTests(unittest.IsolatedAsyncioTestCase):
    async def test_background_progress_blocks_toggles_and_deduplicates(self):
        plugin=Plugin();ready=threading.Event();release=threading.Event();calls=[]
        plugin.manager=Mock();plugin.manager.status.return_value={'ok':True,'mods':[],'running':False}
        plugin.environment=Mock(spec=EnvironmentGuard);plugin.environment.status.return_value={'healthy':False,'can_repair':True,'checks':[]}
        def repair(progress):
            calls.append(True);progress(message='backup in progress');ready.set();release.wait(3);return 'done'
        plugin.environment.repair.side_effect=repair
        try:
            self.assertTrue((await asyncio.wait_for(plugin.repair_environment(),1))['ok']);await asyncio.to_thread(ready.wait,1)
            result=await asyncio.wait_for(plugin.get_status(),1)
            self.assertEqual(result['environment']['job']['state'],'running')
            self.assertFalse((await plugin.set_enabled('d2d',False))['ok'])
            await plugin.repair_environment();self.assertEqual(len(calls),1);plugin.manager.set_enabled.assert_not_called()
        finally:
            release.set()
            if plugin.repair_task:await plugin.repair_task
        self.assertEqual(plugin.repair_job['state'],'done')

if __name__=='__main__':unittest.main()
