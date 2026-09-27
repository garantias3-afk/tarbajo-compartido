#!/usr/bin/python3
"""CP0 read-only: print one authorized whole-disk node and its pinned volume UUID."""
import sys
import ot07_guard as g


def main():
    rows = g.diskutil('list', '-plist', 'external', 'physical').get('AllDisksAndPartitions', [])
    matches = []
    for row in rows:
        device = '/dev/' + row['DeviceIdentifier']
        # Inspect physical identity before considering volumes. Never mount anything here.
        d = g.info(device)
        if 'DataTraveler' not in d.get('MediaName', '') or d.get('TotalSize') != g.KNOWN_SIZE:
            continue
        try:
            g.identity(device, g.KNOWN_UUID)
        except ValueError as e:
            print(device + ': rechazado: ' + str(e), file=sys.stderr)
            continue
        matches.append(device)
    g.require(len(matches) == 1, 'CP0 necesita exactamente un pen autorizado; candidatos=' + repr(matches))
    print(matches[0], g.KNOWN_UUID)


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print('CP0_FAIL: ' + str(e), file=sys.stderr)
        sys.exit(1)
