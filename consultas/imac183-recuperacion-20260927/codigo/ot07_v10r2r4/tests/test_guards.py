"""Synthetic tests. Never mount, erase, signal, run OCLP or download installers."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

BASE = Path(__file__).resolve().parents[1]
def module(name):
    spec = importlib.util.spec_from_file_location(name, BASE / (name + '.py'))
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj
g = module('ot07_guard')
installer = module('verificar_instalador')


class Guards(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='ot07_test_')
        self.root = Path(self.tmp.name)
        self.src = self.root / 'source'
        self.config = {
            '#Revision': {'Original-Model': 'iMac18,3'},
            'Misc': {'Boot': {'LauncherPath': '\\boot.efi', 'LauncherOption': 'Disabled'},
                     'Tools': [{'Enabled': True, 'Path': 'Shell.efi'}]},
            'UEFI': {'Drivers': [{'Enabled': True, 'Path': 'OpenRuntime.efi'}]},
            'ACPI': {'Add': [{'Enabled': True, 'Path': 'SSDT.aml'}]},
            'Kernel': {'Add': [{'Enabled': True, 'BundlePath': 'A.kext',
                               'ExecutablePath': 'Contents/MacOS/A', 'PlistPath': 'Contents/Info.plist'}]}}
        self.files = {'boot.efi': b'diagnostics', g.PRODUCT: b'bootstrap',
                      'EFI/OC/OpenCore.efi': b'opencore', 'EFI/OC/Drivers/OpenRuntime.efi': b'runtime',
                      'EFI/OC/Tools/Shell.efi': b'shell', 'EFI/OC/ACPI/SSDT.aml': b'acpi',
                      'EFI/OC/Kexts/A.kext/Contents/MacOS/A': b'kext',
                      'EFI/OC/Kexts/A.kext/Contents/Info.plist': b'plist'}
        for name, data in self.files.items():
            p = self.src / name; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(data)
        self.write_config()
        self.whole = {'DeviceIdentifier': 'disk99', 'DeviceNode': '/dev/disk99',
            'MediaName': 'DataTraveler 3.0', 'TotalSize': g.KNOWN_SIZE, 'BusProtocol': 'USB',
            'Internal': False, 'WholeDisk': True, 'VirtualOrPhysical': 'Physical',
            'WritableMedia': True, 'DeviceTreePath': 'test-usb-port'}
        self.part = {'DeviceIdentifier': 'disk99s1', 'ParentWholeDisk': 'disk99',
                     'VolumeName': 'KINGSTON', 'VolumeUUID': g.KNOWN_UUID}
        self.snap = self.root / 'snapshot.json'
        self.snap.write_text(json.dumps({'physical': self.whole}))
        # Catch any unmocked subprocess: tests cannot reach real diskutil or other executables.
        self.no_real_process = patch.object(g.subprocess, 'run', side_effect=AssertionError('REAL_PROCESS_FORBIDDEN'))
        self.no_real_process.start()

    def tearDown(self):
        self.no_real_process.stop()
        self.tmp.cleanup()

    def write_config(self):
        (self.src / 'EFI/OC/config.plist').write_bytes(plistlib.dumps(self.config))

    def test_valid_payload(self):
        self.assertTrue(g.validate_payload(self.src))

    def test_missing_enabled_resources(self):
        for name in ('EFI/OC/Drivers/OpenRuntime.efi', 'EFI/OC/ACPI/SSDT.aml',
                     'EFI/OC/Kexts/A.kext/Contents/MacOS/A', 'EFI/OC/Tools/Shell.efi'):
            with self.subTest(name=name):
                p=self.src/name; data=p.read_bytes(); p.unlink()
                with self.assertRaises(ValueError): g.validate_payload(self.src)
                p.write_bytes(data)

    def test_wrong_model(self):
        self.config['#Revision']['Original-Model']='prefix iMac18,3 suffix'; self.write_config()
        with self.assertRaises(ValueError): g.validate_payload(self.src)

    def test_wrong_launcher(self):
        self.config['Misc']['Boot']['LauncherPath']='Default'; self.write_config()
        with self.assertRaises(ValueError): g.validate_payload(self.src)

    def test_launcher_policy_explicit_derived_copy(self):
        self.config['Misc']['Boot']['LauncherOption']='Full'; self.write_config()
        with self.assertRaises(ValueError): g.validate_payload(self.src)
        record=g.prepare(self.src)
        self.assertEqual(record['before'],'Full'); self.assertEqual(record['after'],'Disabled')
        self.assertNotEqual(record['sha256_before'],record['sha256_after'])
        g.validate_payload(self.src)

    def test_direct_opencore_product_rejected(self):
        (self.src/g.PRODUCT).write_bytes((self.src/'EFI/OC/OpenCore.efi').read_bytes())
        with self.assertRaises(ValueError): g.validate_payload(self.src)

    def test_fallback_and_core_services_rejected(self):
        for name in ('EFI/BOOT/BOOTx64.efi','System/Library/CoreServices/boot.efi'):
            with self.subTest(name=name):
                p=self.src/name; p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(b'stub')
                with self.assertRaises(ValueError): g.validate_payload(self.src)
                p.unlink()
                if name.startswith('EFI/BOOT'): p.parent.rmdir()

    def test_symlink_rejected(self):
        (self.src/'EFI/OC/alias').symlink_to(self.root)
        with self.assertRaises(ValueError): g.validate_payload(self.src)

    def test_symlink_ancestor_rejected(self):
        (self.src/'EFI').rename(self.root/'external-efi')
        (self.src/'EFI').symlink_to(self.root/'external-efi',target_is_directory=True)
        with self.assertRaises(ValueError): g.validate_payload(self.src)

    def test_case_collision_rejected(self):
        # Simulate case-sensitive source enumeration even on case-insensitive APFS.
        a=self.src/'EFI/OC/CASE'; b=self.src/'EFI/OC/case'; a.write_bytes(b'a'); b.write_bytes(b'b')
        original=Path.rglob
        def listed(path, pattern):
            return [a,b] if path==self.src/'EFI/OC' else original(path,pattern)
        with patch.object(Path,'rglob',new=listed):
            with self.assertRaises(ValueError): g.tree(self.src)

    def test_path_traversal_rejected(self):
        self.config['UEFI']['Drivers'][0]['Path']='../OpenCore.efi'; self.write_config()
        with self.assertRaises(ValueError): g.validate_payload(self.src)

    def test_preflight_capacity_boundary(self):
        n=(g.PREFLIGHT_LIMIT-g.RESERVE)//g.CLUSTER_BOUND
        self.assertEqual(g.needed({'a': {'size': n*g.CLUSTER_BOUND}}),g.PREFLIGHT_LIMIT)
        with self.assertRaises(ValueError): g.needed({'a': {'size': n*g.CLUSTER_BOUND+1}})

    def test_empty_files_consume_cluster(self):
        self.assertEqual(g.needed({'dir':None,'empty':{'size':0}}),g.RESERVE+2*g.CLUSTER_BOUND)

    def test_readback_detects_same_size_corruption(self):
        manifest=self.root/'manifest.json'; manifest.write_text(json.dumps(g.validate_payload(self.src)))
        dest=self.root/'destination'; shutil.copytree(self.src,dest)
        g.verify(dest,manifest)
        (dest/'EFI/OC/Drivers/OpenRuntime.efi').write_bytes(b'RUNTIME')
        with self.assertRaises(ValueError): g.verify(dest,manifest)

    def test_readback_detects_extra_file(self):
        manifest=self.root/'manifest.json'; manifest.write_text(json.dumps(g.validate_payload(self.src)))
        (self.src/'EFI/OC/unexpected').write_bytes(b'extra')
        with self.assertRaises(ValueError): g.verify(self.src,manifest)

    def test_uuid_pin_before_disk_access(self):
        with self.assertRaisesRegex(ValueError,'not authorized'): g.identity('/dev/disk99','wrong')

    def test_partition_alias_rejected_before_disk_access(self):
        with self.assertRaises(ValueError): g.identity('/dev/disk99s1',g.KNOWN_UUID)

    def test_valid_identity(self):
        with patch.object(g,'info',return_value=self.whole), patch.object(g,'parts',return_value=[self.part]):
            self.assertEqual(g.identity('/dev/disk99',g.KNOWN_UUID)['partition'],'disk99s1')

    def test_hardware_guards_fail_closed(self):
        changes={'MediaName':'SanDisk','TotalSize':g.KNOWN_SIZE+512,'BusProtocol':'Thunderbolt',
                 'Internal':True,'WholeDisk':False,'VirtualOrPhysical':'Virtual',
                 'WritableMedia':False,'DeviceTreePath':''}
        for key,value in changes.items():
            with self.subTest(key=key):
                d=dict(self.whole); d[key]=value
                with self.assertRaises(ValueError): g.validate_whole(d)

    def test_missing_fields_fail_closed(self):
        for key in g.PHYSICAL:
            with self.subTest(key=key):
                d=dict(self.whole); del d[key]
                with self.assertRaises((ValueError,KeyError)): g.validate_whole(d)

    def test_duplicate_uuid_rejected(self):
        with patch.object(g,'info',return_value=self.whole), patch.object(g,'parts',return_value=[self.part,self.part]):
            with self.assertRaises(ValueError): g.identity('/dev/disk99',g.KNOWN_UUID)

    def test_wrong_volume_name_rejected(self):
        self.part['VolumeName']='RESCATE_A'
        with patch.object(g,'info',return_value=self.whole), patch.object(g,'parts',return_value=[self.part]):
            with self.assertRaises(ValueError): g.identity('/dev/disk99',g.KNOWN_UUID)

    def test_revalidation_physical_change(self):
        changed=dict(self.whole); changed['DeviceTreePath']='another-port'
        with patch.object(g,'info',return_value=changed):
            with self.assertRaises(ValueError): g.current(self.snap)

    def test_partition_parent_and_uuid(self):
        p=dict(self.part,DiskUUID='gpt-one')
        with patch.object(g,'current',return_value=self.whole),patch.object(g,'info',return_value=p):
            g.bound_partition(self.snap,'disk99s1','gpt-one')
            for field,bad in [('ParentWholeDisk','disk98'),('DiskUUID','changed')]:
                old=p[field]; p[field]=bad
                with self.assertRaises(ValueError): g.bound_partition(self.snap,'disk99s1','gpt-one')
                p[field]=old

    def test_mount_point_with_spaces(self):
        p=dict(self.part,DiskUUID='gpt',MountPoint='/Volumes/Install Sonoma 1')
        with patch.object(g,'bound_partition',return_value=p),patch.object(g,'info',return_value=p),patch.object(g.os.path,'ismount',return_value=True):
            self.assertEqual(g.mountpoint(self.snap,'disk99s1','gpt'),p['MountPoint'])

    def test_mount_name_collision_rejected(self):
        p=dict(self.part,DiskUUID='gpt',MountPoint='/Volumes/InstallSonoma')
        wrong=dict(p,DeviceIdentifier='disk98s2')
        with patch.object(g,'bound_partition',return_value=p),patch.object(g,'info',return_value=wrong),patch.object(g.os.path,'ismount',return_value=True):
            with self.assertRaises(ValueError): g.mountpoint(self.snap,'disk99s1','gpt')

    def test_unmounted_partition_returns_empty(self):
        with patch.object(g,'bound_partition',return_value=self.part):
            self.assertEqual(g.mountpoint(self.snap,'disk99s1','gpt'),'')

    def test_ordinary_directory_is_not_mount(self):
        p=dict(self.part,MountPoint=str(self.root))
        with patch.object(g,'bound_partition',return_value=p),patch.object(g.os.path,'ismount',return_value=False):
            with self.assertRaises(ValueError): g.mountpoint(self.snap,'disk99s1','gpt')

    def test_actual_esp_space(self):
        p={'Content':'EFI','WritableVolume':True,'VolumeAllocationBlockSize':4096}
        v=type('V',(),{'f_bavail':100,'f_frsize':4096})()
        with patch.object(g,'mountpoint',return_value='/mock'),patch.object(g,'bound_partition',return_value=p),patch.object(g.os,'statvfs',return_value=v):
            g.capacity(self.snap,'disk99s1','gpt',100)
            with self.assertRaises(ValueError): g.capacity(self.snap,'disk99s1','gpt',1000000)
            p['VolumeAllocationBlockSize']=131072
            with self.assertRaises(ValueError): g.capacity(self.snap,'disk99s1','gpt',100)

    def test_readonly_required(self):
        with patch.object(g,'bound_partition',return_value={'WritableVolume':True}):
            with self.assertRaises(ValueError): g.main(['readonly',str(self.snap),'disk99s1','gpt'])

    def test_sonoma_metadata(self):
        self.assertEqual(installer.metadata_versions({'Assets':[{'OSVersion':'14.7.1','Build':'23H222'}]})[0]['version'],'14.7.1')
        for data in ({}, {'Assets':[{'OSVersion':'15.0','Build':'24A1'}]}, {'Assets':[{'OSVersion':'14.7','Build':'24A1'}]}):
            with self.assertRaises(ValueError): installer.metadata_versions(data)

    def test_script_order_and_no_false_ready(self):
        s=(BASE/'CREAR_PEN_BOOTEO.sh').read_text()
        self.assertLess(s.index('guard need'),s.index('eraseDisk JHFS+'))
        self.assertLess(s.index('identity.final.json'),s.index('eraseDisk JHFS+'))
        self.assertLess(s.index('guard capacity'),s.index('createinstallmedia" --volume'))
        self.assertLess(s.index('guard readonly'),s.index('MEDIO_CREADO_INTEGRIDAD_VERIFICADA'))
        self.assertLess(s.index('guard installed'),s.index('MEDIO_CREADO_INTEGRIDAD_VERIFICADA'))
        self.assertNotIn('PEN BOOTEO LISTO',s)
        self.assertNotIn('EFI/BOOT/BOOTx64.efi',s)

    def test_prepare_preserves_original_and_changes_only_launcher(self):
        self.config['Misc']['Boot']['LauncherOption']='Full'
        self.config['Blob']=b'\x00\x01binary'
        self.write_config()
        original=(self.src/'EFI/OC/config.plist').read_bytes()
        backup=self.root/'original.plist'
        g.prepare(self.src,backup)
        self.assertEqual(backup.read_bytes(),original)
        actual=plistlib.loads((self.src/'EFI/OC/config.plist').read_bytes())
        expected=copy.deepcopy(self.config); expected['Misc']['Boot']['LauncherOption']='Disabled'
        self.assertEqual(actual,expected)
        with self.assertRaises(FileExistsError): g.prepare(self.src,backup)

    def test_partition_ambiguity_and_unexpected_filesystem(self):
        row=dict(self.part,DiskUUID='gpt',FilesystemType='hfs')
        for rows in ([row,row],[dict(row,FilesystemType='apfs')]):
            with patch.object(g,'current',return_value=self.whole),patch.object(g,'parts',return_value=rows):
                with self.assertRaises(ValueError): g.partition(self.snap,'hfs')

    def test_extra_empty_directory_detected(self):
        manifest=self.root/'manifest.json'; manifest.write_text(json.dumps(g.validate_payload(self.src)))
        (self.src/'EFI/OC/extra-empty').mkdir()
        with self.assertRaises(ValueError): g.verify(self.src,manifest)

    def test_capacity_exact_boundary(self):
        p={'Content':'EFI','WritableVolume':True,'VolumeAllocationBlockSize':4096}
        v=type('V',(),{'f_bavail':100,'f_frsize':4096})()
        with patch.object(g,'mountpoint',return_value='/mock'),patch.object(g,'bound_partition',return_value=p),patch.object(g.os,'statvfs',return_value=v):
            g.capacity(self.snap,'disk99s1','gpt',409600)
            with self.assertRaises(ValueError): g.capacity(self.snap,'disk99s1','gpt',409601)

    def test_diskutil_plist_parsing_and_read_only_command_allowlist(self):
        result=type('R',(),{'stdout':plistlib.dumps(self.whole)})()
        with patch.object(g.subprocess,'run',return_value=result) as run:
            self.assertEqual(g.info('/dev/disk99'),self.whole)
            self.assertEqual(run.call_args[0][0],['/usr/sbin/diskutil','info','-plist','/dev/disk99'])
            with self.assertRaises(ValueError): g.diskutil('eraseDisk','bad')
            self.assertEqual(run.call_count,1)
            for raw in (b'bad plist',plistlib.dumps({'Error':True}),plistlib.dumps([])):
                result.stdout=raw
                with self.assertRaises((ValueError,plistlib.InvalidFileException)): g.info('/dev/disk99')

    def test_cli_identity_dispatch_uses_real_plist_parser(self):
        from contextlib import redirect_stdout
        import io
        listing={'AllDisksAndPartitions':[{'DeviceIdentifier':'disk99','Partitions':[{'DeviceIdentifier':'disk99s1'}]}]}
        def fake_run(args,**kwargs):
            payload=listing if args[1]=='list' else self.whole if args[-1]=='/dev/disk99' else self.part
            return type('R',(),{'stdout':plistlib.dumps(payload)})()
        out=io.StringIO()
        with patch.object(g.subprocess,'run',side_effect=fake_run),redirect_stdout(out):
            g.main(['identity','/dev/disk99',g.KNOWN_UUID])
        self.assertEqual(json.loads(out.getvalue())['physical'],self.whole)

    def test_bindings_records_generated_guids(self):
        import io
        from contextlib import redirect_stdout
        out=io.StringIO()
        rows={'disk99s1':dict(self.part,DiskUUID='new-efi'),'disk99s2':dict(self.part,DeviceIdentifier='disk99s2',DiskUUID='new-data')}
        with patch.object(g,'current',return_value=self.whole),patch.object(g,'info',side_effect=lambda device:rows[device[5:]]),redirect_stdout(out):
            g.main(['bindings',str(self.snap),'disk99s2','new-data','disk99s1','new-efi'])
        result=json.loads(out.getvalue())
        self.assertEqual(result['data']['DiskUUID'],'new-data'); self.assertEqual(result['efi']['DiskUUID'],'new-efi')

    def test_empty_installer_and_package_only_rejected(self):
        app=self.root/'Install macOS Sonoma.app'; app.mkdir()
        package=self.root/'System/Installation/Packages/OSInstall.mpkg'
        package.parent.mkdir(parents=True); package.write_bytes(b'package')
        with self.assertRaises(ValueError): g.installed(self.root)
        dmg=app/'Contents/SharedSupport/SharedSupport.dmg'; dmg.parent.mkdir(parents=True)
        # Sparse synthetic data; does not contain an installer, just tests this structural gate.
        with dmg.open('wb') as f: f.truncate(10000000001)
        (app/'Contents/Info.plist').write_bytes(plistlib.dumps({'test':'fixture'}))
        g.installed(self.root)
        with dmg.open('wb') as f: f.truncate(10000000000)
        with self.assertRaises(ValueError): g.installed(self.root)

    def test_diagnostic_is_bounded_and_refuses_mount_change(self):
        for i in range(105): (self.root/('file-%03d'%i)).touch()
        with patch.object(g,'mountpoint',return_value=str(self.root)),patch.object(g,'bound_partition',return_value={'DiskUUID':'gpt'}):
            result=g.diagnostic(self.snap,'disk99s1','gpt')
            self.assertEqual(len(result['directories']['.']['entries']),101)
            self.assertEqual(result['directories']['.']['entries'][-1],{'truncated':True})
        with patch.object(g,'mountpoint',side_effect=[str(self.root),'/other']),patch.object(g,'bound_partition',return_value={}):
            with self.assertRaises(ValueError): g.diagnostic(self.snap,'disk99s1','gpt')

    def test_diagnostic_does_not_follow_directory_symlinks(self):
        (self.root/'System').symlink_to(self.src,target_is_directory=True)
        with patch.object(g,'mountpoint',return_value=str(self.root)),patch.object(g,'bound_partition',return_value={}):
            with self.assertRaises(ValueError): g.diagnostic(self.snap,'disk99s1','gpt')


if __name__=='__main__':
    unittest.main(verbosity=2)
