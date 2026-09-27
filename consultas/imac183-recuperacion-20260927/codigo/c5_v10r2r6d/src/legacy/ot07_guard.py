#!/usr/bin/python3
"""OT07 v9. Disk operations are info/list only; prepare edits the staged config only."""
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import stat
import subprocess
import sys

KNOWN_UUID = '11111111-2222-4333-8444-555555555555'
KNOWN_SIZE = 61991813120
PRODUCT = 'System/Library/CoreServices/.diagnostics/Drivers/HardwareDrivers/Product.efi'
ROOTS = ('EFI/OC', 'System', 'boot.efi')
PHYSICAL = ('DeviceIdentifier', 'DeviceNode', 'MediaName', 'TotalSize',
            'BusProtocol', 'Internal', 'WholeDisk', 'VirtualOrPhysical',
            'WritableMedia', 'DeviceTreePath')
CLUSTER_BOUND = 65536
RESERVE = 16 * 1024 * 1024
PREFLIGHT_LIMIT = 180 * 1024 * 1024


def require(ok, message):
    if not ok:
        raise ValueError(message)


def diskutil(*args):
    require(args[0] in ('info', 'list'), 'guard only permits diskutil info/list')
    r = subprocess.run(['/usr/sbin/diskutil', *args], check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    data = plistlib.loads(r.stdout)
    require(isinstance(data, dict) and not data.get('Error'), 'invalid diskutil plist')
    return data


def info(device):
    return diskutil('info', '-plist', device)


def validate_whole(d):
    require(re.fullmatch(r'disk[0-9]+', d.get('DeviceIdentifier', '')), 'not whole BSD identifier')
    require(d.get('DeviceNode') == '/dev/' + d['DeviceIdentifier'], 'DeviceNode mismatch')
    require(d.get('WholeDisk') is True and d.get('Internal') is False, 'not external whole disk')
    require(d.get('VirtualOrPhysical') == 'Physical', 'not physical')
    require(d.get('BusProtocol') == 'USB' and d.get('WritableMedia') is True, 'not writable USB')
    require('DataTraveler' in d.get('MediaName', ''), 'not DataTraveler')
    require(d.get('TotalSize') == KNOWN_SIZE, 'unexpected exact device size')
    require(bool(d.get('DeviceTreePath')), 'missing physical attachment path')
    return {k: d[k] for k in PHYSICAL}


def parts(device):
    rows = diskutil('list', '-plist', device).get('AllDisksAndPartitions', [])
    require(len(rows) == 1 and rows[0].get('DeviceIdentifier') == device.removeprefix('/dev/'),
            'ambiguous disk list')
    result = []
    for row in rows[0].get('Partitions', []):
        pid = row.get('DeviceIdentifier', '')
        require(re.fullmatch(r'disk[0-9]+s[0-9]+', pid), 'invalid partition identifier')
        p = info('/dev/' + pid)
        require(p.get('DeviceIdentifier') == pid and
                p.get('ParentWholeDisk') == rows[0]['DeviceIdentifier'], 'partition belongs elsewhere')
        name = p.get('VolumeName', '')
        require(name not in ('RESCATE_A', 'RESCATE_B', 'Rescate'), 'protected volume')
        result.append(p)
    require(result, 'no physical partitions')
    return result


def identity(device, uuid):
    require(uuid == KNOWN_UUID, 'UUID is not authorized')
    require(re.fullmatch(r'/dev/disk[0-9]+', device), 'use /dev/diskN, not a partition or alias')
    physical = validate_whole(info(device))
    children = parts(device)
    require(not any(p.get('VolumeName', '').startswith('Install macOS') for p in children),
            'already contains an installer')
    match = [p for p in children if p.get('VolumeName') == 'KINGSTON' and p.get('VolumeUUID') == uuid]
    require(len(match) == 1, 'exactly one KINGSTON with the pinned UUID is required')
    return {'physical': physical, 'volume_uuid': uuid, 'partition': match[0]['DeviceIdentifier']}


def current(snapshot):
    snap = json.loads(Path(snapshot).read_text())
    old = snap['physical']
    require(validate_whole(info(old['DeviceNode'])) == old, 'physical identity changed')
    return old


def partition(snapshot, kind):
    old = current(snapshot)
    children = parts(old['DeviceNode'])
    found = [p for p in children if
             (kind == 'efi' and p.get('Content') == 'EFI') or
             (kind == 'hfs' and p.get('FilesystemType') == 'hfs')]
    require(len(found) == 1, 'need exactly one ' + kind + ' partition')
    p = found[0]
    require(p.get('DiskUUID'), 'missing GPT partition UUID')
    return p['DeviceIdentifier'] + ' ' + p['DiskUUID']


def bound_partition(snapshot, pid, uuid):
    old = current(snapshot)
    require(re.fullmatch(r'disk[0-9]+s[0-9]+', pid), 'invalid partition')
    p = info('/dev/' + pid)
    require(p.get('DeviceIdentifier') == pid and p.get('ParentWholeDisk') == old['DeviceIdentifier']
            and p.get('DiskUUID') == uuid, 'partition identity changed')
    return p


def mountpoint(snapshot, pid, uuid):
    p = bound_partition(snapshot, pid, uuid)
    mp = p.get('MountPoint', '')
    if not mp:
        return ''
    require(os.path.isabs(mp) and os.path.ismount(mp), 'not a real volume mount')
    reverse = info(mp)
    for key in ('DeviceIdentifier', 'ParentWholeDisk', 'DiskUUID'):
        require(reverse.get(key) == p.get(key), 'mount path belongs to another partition')
    require(os.path.realpath(reverse.get('MountPoint', '')) == os.path.realpath(mp),
            'mount path mismatch')
    return mp


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()


def tree(root):
    root = Path(root)
    require(root.is_dir() and not root.is_symlink(), 'invalid payload root')
    require(not (root / 'EFI/BOOT').exists() and not (root / 'EFI/BOOT').is_symlink(),
            'EFI/BOOT prohibited for this dual-DP package')
    require(not (root / 'System/Library/CoreServices/boot.efi').exists(), 'unexpected alternate loader')
    result = {}
    seen = set()
    for rel in ROOTS:
        p = root / rel
        for ancestor in (p, *p.parents):
            if ancestor == root:
                break
            require(not ancestor.is_symlink(), 'symlink in payload path ' + str(ancestor))
        require(p.exists(), 'missing payload root ' + rel)
        paths = [p] + (list(p.rglob('*')) if p.is_dir() else [])
        for q in paths:
            name = q.relative_to(root).as_posix()
            require(name.casefold() not in seen, 'FAT case collision: ' + name)
            seen.add(name.casefold())
            mode = q.lstat().st_mode
            require(not q.is_symlink() and (stat.S_ISDIR(mode) or stat.S_ISREG(mode)),
                    'non-regular payload entry ' + name)
            result[name] = None if q.is_dir() else {'size': q.stat().st_size, 'sha256': digest(q)}
    return result


def safe_ref(base, rel):
    require(isinstance(rel, str) and rel, 'empty config path')
    rel = rel.replace('\\', '/')
    require(not rel.startswith('/') and all(x not in ('', '.', '..') for x in rel.split('/')),
            'unsafe config path ' + rel)
    p = Path(base) / rel
    require(p.is_file() and p.stat().st_size > 0, 'missing/empty enabled config resource: ' + str(p))


def validate_payload(root, disabled=True):
    root = Path(root)
    entries = tree(root)
    for rel in ('boot.efi', PRODUCT, 'EFI/OC/OpenCore.efi', 'EFI/OC/config.plist'):
        require(rel in entries and entries[rel] and entries[rel]['size'] > 0, 'missing loader/config: ' + rel)
    require(entries[PRODUCT]['sha256'] != entries['EFI/OC/OpenCore.efi']['sha256'],
            'Product.efi must not be OpenCore.efi')
    with (root / 'EFI/OC/config.plist').open('rb') as f:
        d = plistlib.load(f)
    require(d.get('#Revision', {}).get('Original-Model') == 'iMac18,3', 'wrong Original-Model')
    boot = d.get('Misc', {}).get('Boot', {})
    require(boot.get('LauncherPath') == '\\boot.efi', 'wrong LauncherPath')
    if disabled:
        require(boot.get('LauncherOption') == 'Disabled', 'LauncherOption must be Disabled')
    oc = root / 'EFI/OC'
    enabled_drivers = []
    for row in d.get('UEFI', {}).get('Drivers', []):
        require(isinstance(row, dict), 'unexpected UEFI driver schema')
        if row.get('Enabled') is True:
            safe_ref(oc / 'Drivers', row['Path'])
            enabled_drivers.append(row['Path'])
    require('OpenRuntime.efi' in enabled_drivers, 'OpenRuntime.efi not enabled')
    for row in d.get('ACPI', {}).get('Add', []):
        if row.get('Enabled') is True:
            safe_ref(oc / 'ACPI', row['Path'])
    for row in d.get('Kernel', {}).get('Add', []):
        if row.get('Enabled') is True:
            bundle = row['BundlePath']
            safe_ref(oc / 'Kexts', bundle + '/' + row['PlistPath'])
            if row.get('ExecutablePath'):
                safe_ref(oc / 'Kexts', bundle + '/' + row['ExecutablePath'])
    for row in d.get('Misc', {}).get('Tools', []):
        if row.get('Enabled') is True:
            safe_ref(oc / 'Tools', row['Path'])
    return entries


def prepare(root, backup=None):
    # Only called on the fresh mktemp build, never on original OCLP or a disk.
    validate_payload(root, disabled=False)
    p = Path(root) / 'EFI/OC/config.plist'
    before = digest(p)
    if backup is not None:
        backup = Path(backup)
        require(Path(root).resolve() not in backup.resolve().parents, 'backup must be outside payload')
        with backup.open('xb') as f:
            f.write(p.read_bytes())
    d = plistlib.loads(p.read_bytes())
    old = d['Misc']['Boot'].get('LauncherOption')
    d['Misc']['Boot']['LauncherOption'] = 'Disabled'
    p.write_bytes(plistlib.dumps(d, sort_keys=False))
    validate_payload(root)
    return {'change': 'Misc/Boot/LauncherOption', 'before': old, 'after': 'Disabled',
            'sha256_before': before, 'sha256_after': digest(p)}


def needed(entries):
    # Conservative policy, NOT a measurement of a future ESP. Includes directories/slack.
    total = RESERVE
    for record in entries.values():
        n = 0 if record is None else record['size']
        total += max(1, (n + CLUSTER_BOUND - 1) // CLUSTER_BOUND) * CLUSTER_BOUND
    require(total <= PREFLIGHT_LIMIT, 'C3 preflight: payload exceeds 180 MiB including reserve; pen intact')
    return total


def capacity(snapshot, pid, uuid, need):
    mp = mountpoint(snapshot, pid, uuid)
    require(mp, 'EFI unmounted')
    p = bound_partition(snapshot, pid, uuid)
    require(p.get('Content') == 'EFI' and p.get('WritableVolume') is True, 'not writable EFI')
    cluster = p.get('VolumeAllocationBlockSize', 0)
    require(0 < cluster <= CLUSTER_BOUND, 'allocation unit exceeds preflight model')
    require(0 < need <= PREFLIGHT_LIMIT, 'invalid payload estimate')
    v = os.statvfs(mp)
    require(v.f_bavail * v.f_frsize >= need, 'insufficient actual ESP free space (pen already erased)')


def verify(root, manifest):
    expected = json.loads(Path(manifest).read_text())
    require(validate_payload(root) == expected, 'payload differs from pre-erase SHA256 manifest')


def bindings(snapshot, data_pid, data_uuid, efi_pid, efi_uuid):
    return {'physical': current(snapshot),
            'data': bound_partition(snapshot, data_pid, data_uuid),
            'efi': bound_partition(snapshot, efi_pid, efi_uuid)}


def installed(volume):
    # Strict supported layout. Unknown native layouts fail closed, never a directory-only success.
    root = Path(volume)
    app = root / 'Install macOS Sonoma.app'
    dmg = app / 'Contents/SharedSupport/SharedSupport.dmg'
    infofile = app / 'Contents/Info.plist'
    for target in (dmg, infofile):
        require(all(not q.is_symlink() for q in (target, *target.parents) if q != root and root in q.parents),
                'symlink installer rejected')
    require(dmg.is_file() and dmg.stat().st_size > 10000000000,
            'installed SharedSupport.dmg missing or <=10 GB; unknown layout requires review')
    require(infofile.is_file() and infofile.stat().st_size > 0, 'installed Info.plist missing')
    with infofile.open('rb') as f:
        require(isinstance(plistlib.load(f), dict), 'invalid installed Info.plist')


def diagnostic(snapshot, pid, uuid):
    # Small, bounded, non-recursive inventory. Revalidate binding before every directory.
    mp = mountpoint(snapshot, pid, uuid)
    require(mp, 'diagnostic requires bound mounted data partition')
    result = {'partition': bound_partition(snapshot, pid, uuid), 'directories': {}}
    for rel in ('', 'System/Installation/Packages', 'Install macOS Sonoma.app/Contents',
                'Install macOS Sonoma.app/Contents/SharedSupport'):
        require(mountpoint(snapshot, pid, uuid) == mp, 'diagnostic mount changed')
        target = Path(mp) / rel
        require(all(not q.is_symlink() for q in (target, *target.parents)
                    if q != Path(mp) and Path(mp) in q.parents), 'diagnostic symlink rejected')
        entries = []
        if target.is_dir():
            with os.scandir(target) as scan:
                for i, entry in enumerate(scan):
                    if i == 100:
                        entries.append({'truncated': True}); break
                    st = entry.stat(follow_symlinks=False)
                    entries.append({'name': entry.name, 'size': st.st_size,
                                    'symlink': entry.is_symlink()})
        result['directories'][rel or '.'] = {'exists': target.is_dir(), 'entries': entries}
    return result


def main(args):
    cmd, *a = args
    if cmd == 'identity':
        print(json.dumps(identity(*a), sort_keys=True))
    elif cmd == 'physical':
        current(*a)
    elif cmd == 'partition':
        print(partition(*a))
    elif cmd == 'bound':
        bound_partition(*a)
    elif cmd == 'mountpoint':
        print(mountpoint(*a))
    elif cmd == 'bindings':
        print(json.dumps(bindings(*a), sort_keys=True, indent=2))
    elif cmd == 'diagnostic':
        print(json.dumps(diagnostic(*a), sort_keys=True, indent=2))
    elif cmd == 'installed':
        installed(*a)
    elif cmd == 'prepare':
        print(json.dumps(prepare(*a), sort_keys=True))
    elif cmd == 'manifest':
        print(json.dumps(validate_payload(*a), sort_keys=True, indent=2))
    elif cmd == 'need':
        print(needed(validate_payload(*a)))
    elif cmd == 'capacity':
        capacity(*a[:3], int(a[3]))
    elif cmd == 'readonly':
        require(bound_partition(*a).get('WritableVolume') is False, 'readback volume is writable')
    elif cmd == 'verify':
        verify(*a)
    else:
        raise ValueError('unknown command')


if __name__ == '__main__':
    try:
        main(sys.argv[1:])
    except Exception as e:
        print('OT07_GUARD_FAIL: ' + str(e), file=sys.stderr)
        sys.exit(1)
