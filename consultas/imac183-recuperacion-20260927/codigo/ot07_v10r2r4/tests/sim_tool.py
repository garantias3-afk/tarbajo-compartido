#!/usr/bin/python3
"""Test double only. All state/files live below the harness temporary directory."""
import json
import os
from pathlib import Path
import shutil
import sys

root=Path(os.environ['OT07_SIM_ROOT']).resolve()
case=os.environ['OT07_SIM_CASE']
statefile=root/'state.json'
state=json.loads(statefile.read_text()) if statefile.exists() else {}
kind=sys.argv[1]; a=sys.argv[2:]
def save(): statefile.write_text(json.dumps(state))
def event(s):
    with (root/'events').open('a') as f: f.write(s+'\n')
def local(p):
    p=Path(p).resolve()
    if root not in p.parents and p!=root: raise RuntimeError('non-fixture path blocked')
    return p
def stop(code=1): save(); sys.exit(code)
event(kind+' '+' '.join(a))

if kind=='guard':
    cmd=a[0]
    if cmd=='identity':
        state['identities']=state.get('identities',0)+1
        if case=='identity-change' and state['identities']>1: stop()
        print('{"physical":"synthetic"}')
    elif cmd=='prepare': print('{"test":"policy"}')
    elif cmd=='manifest': print('{"test":"manifest"}')
    elif cmd=='need':
        if case=='oversized': stop()
        print('1000')
    elif cmd=='partition': print('disk99s1 GPT-EFI' if a[2]=='efi' else 'disk99s2 GPT-DATA')
    elif cmd=='bindings':
        if case=='bindings-fails':
            print('partial-json'); stop()
        print('{"data":"GPT-DATA","efi":"GPT-EFI"}')
    elif cmd=='diagnostic': print('{"diagnostic":"synthetic fixture"}')
    elif cmd=='installed' and case=='installer-empty': stop()
    elif cmd=='mountpoint':
        if case=='guid-change-post-cim' and state.get('cim'): stop()
        if a[2]=='disk99s1':
            state['efi-bindings']=state.get('efi-bindings',0)+1
            if case=='binding-before-cleanup' and state['efi-bindings']==3: stop()
            print(str(root/'wrong') if case=='wrong-efi-mount' else state.get('mp',''))
        else:
            if not state.get('data-mounted'): print('')
            elif state.get('cim') and state.get('delays',0)<2:
                state['delays']=state.get('delays',0)+1; print('')
            else: print(str(root/'Install Sonoma 1'))
    elif cmd=='capacity' and case=='small-esp': stop()
    elif cmd=='verify' and case=='copy-corrupt' and a[1]==state.get('mp'): stop()
    elif cmd=='verify' and case=='payload-tampered' and not state.get('erased'): stop()
    elif cmd=='verify' and case=='readback-corrupt' and state.get('readonly') and a[1]==state.get('mp'): stop()
    elif cmd=='readonly' and case=='writable-readback': stop()
elif kind=='diskutil':
    if a[0]=='eraseDisk':
        if case=='erase-fails': stop()
        state['erased']=True
    elif a[0]=='mount':
        if 'readOnly' in a: state['readonly']=True
        if '-mountPoint' in a:
            mp=local(a[a.index('-mountPoint')+1]); state['mp']=str(mp)
            store=root/'esp-store'
            if store.exists():
                for p in list(store.iterdir()): shutil.move(str(p),str(mp/p.name))
        else: state['data-mounted']=True
    elif a[0]=='unmount':
        state['unmounts']=state.get('unmounts',0)+1
        if case=='unmount-fails' and state['unmounts']==2: stop()
        mp=local(state['mp']); store=root/'esp-store'; store.mkdir(exist_ok=True)
        for p in list(mp.iterdir()): shutil.move(str(p),str(store/p.name))
elif kind=='build':
    if case=='build-fails': stop()
    if case=='unresolved-ledger':
        (local(a[0])/'process-ledger.json').write_text(json.dumps({'phase':'freezing','records':[]}))
        stop()
    if case!='missing-ledger':
        row={'pid':100,'ppid':50,'state':'S','birth':[1790409600,100],'command':'fixture'}
        if case=='false-clean-build':
            rows=[dict(row,status='uncertain')]
        elif case=='empty-capture':
            rows=[]
        elif case=='root-birth-mismatch':
            rows=[dict(row,birth=[1790409600,999],status='resumed')]
        elif case=='descendant-only':
            rows=[dict(row,pid=101,status='resumed')]
        else:
            rows=[dict(row,status='resumed')]
        (local(a[0])/'process-ledger.json').write_text(json.dumps({'version':9,'root':row,'protected':[3494,3512],'records':rows,'phase':'thawed'}))
    b=local(a[0])/'OpenCore-Build' 
    (b/'EFI/OC').mkdir(parents=True); (b/'System').mkdir()
    (b/'boot.efi').write_bytes(b'test'); (b/'EFI/OC/OpenCore.efi').write_bytes(b'test')
elif kind=='cim':
    if case=='cim-fails': stop()
    state['cim']=True
    (root/'Install Sonoma 1/Install macOS Sonoma.app').mkdir(parents=True,exist_ok=True)
elif kind=='ditto':
    if case=='copy-fails': stop()
    src,dst=local(a[-2]),local(a[-1]); shutil.copytree(src,dst,dirs_exist_ok=True)
elif kind=='version': print('2.4.1')
elif kind=='verify-installer':
    if case=='installer-invalid': stop()
else: raise RuntimeError('unknown simulator tool')
save()
