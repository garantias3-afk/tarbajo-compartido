"""Installer metadata and detach diagnostics; all hdiutil calls substituted."""
import json
from pathlib import Path
import plistlib
import tempfile
import unittest
from unittest.mock import patch
from test_guards import module
m=module('verificar_instalador')


class Installer(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)
        self.block=patch.object(m.subprocess,'run',side_effect=AssertionError('REAL_PROCESS_FORBIDDEN'))
        self.block.start()
    def tearDown(self): self.block.stop(); self.tmp.cleanup()
    def put(self,rel,version='14.7.1',build='23H222',extra=None):
        p=self.root/rel; p.parent.mkdir(parents=True,exist_ok=True)
        p.write_bytes(plistlib.dumps({'Assets':[{'OSVersion':version,'Build':build}]+(extra or [])}))
    def test_sfr_fallback_includes_sfr_directory(self):
        self.put(m.SFR_METADATA)
        self.assertEqual(m.read_metadata(self.root)['path'],m.SFR_METADATA)
    def test_mac_metadata_precedence(self):
        self.put(m.SFR_METADATA,'14.6','23G1'); self.put(m.METADATA)
        self.assertEqual(m.read_metadata(self.root)['versions'][0]['version'],'14.7.1')
    def test_assets_zero_matches_oclp(self):
        self.put(m.METADATA,extra=[{'OSVersion':'1.0','Build':'Firmware'}])
        self.assertEqual(m.read_metadata(self.root)['asset_index'],0)
    def test_invalid_primary_not_hidden_by_fallback(self):
        self.put(m.METADATA,'15.0','24A1'); self.put(m.SFR_METADATA)
        with self.assertRaises(ValueError): m.read_metadata(self.root)
    def test_malformed_missing_metadata_rejected(self):
        for data in (None,[],{'Assets':{}},{'Assets':[None]},{'Assets':[{'OSVersion':14,'Build':23}]}):
            with self.subTest(data=data),self.assertRaises(ValueError): m.metadata_versions(data)
        with self.assertRaises(ValueError): m.read_metadata(self.root)
    def test_detach_failure_preserves_original_error_and_device(self):
        mp=self.root/'mount'; mp.mkdir()
        attachment=plistlib.dumps({'system-entities':[{'dev-entry':'/dev/disk99'},{'dev-entry':'/dev/disk99s1','mount-point':str(mp)}]})
        response=type('R',(),{'stdout':attachment})()
        with patch.object(m.tempfile,'mkdtemp',return_value=str(mp)),patch.object(m.subprocess,'run',side_effect=[response,OSError('detach failed')]) as run:
            with self.assertRaises(RuntimeError) as caught: m.read_dmg('synthetic.dmg')
            self.assertIn('/dev/disk99',str(caught.exception)); self.assertIn('sin metadatos',str(caught.exception))
            self.assertIn('detach failed',str(caught.exception)); self.assertTrue(mp.exists())
            self.assertEqual(run.call_args_list[-1][0][0],['/usr/bin/hdiutil','detach','/dev/disk99'])
    def test_success_requires_detach_before_return(self):
        mp=self.root/'mount'; mp.mkdir()
        attachment=plistlib.dumps({'system-entities':[{'dev-entry':'/dev/disk99'},{'mount-point':str(mp)}]})
        with patch.object(m.tempfile,'mkdtemp',return_value=str(mp)),patch.object(m.subprocess,'run',return_value=type('R',(),{'stdout':attachment})()) as run,patch.object(m,'read_metadata',return_value={'ok':True}):
            self.assertEqual(m.read_dmg('synthetic.dmg'),{'ok':True})
            self.assertFalse(mp.exists()); self.assertEqual(run.call_count,2)
    def test_unidentified_device_never_detached_by_guess(self):
        mp=self.root/'mount'; mp.mkdir()
        response=type('R',(),{'stdout':plistlib.dumps({'system-entities':[]})})()
        with patch.object(m.tempfile,'mkdtemp',return_value=str(mp)),patch.object(m.subprocess,'run',return_value=response) as run:
            with self.assertRaisesRegex(RuntimeError,'DMG_CIERRE_PENDIENTE'): m.read_dmg('synthetic.dmg')
            self.assertEqual(run.call_count,1); self.assertTrue(mp.exists())
