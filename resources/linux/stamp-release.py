#!/usr/bin/env python3
"""Ensure the AppStream metainfo lists the version being built.

GNOME Software reads the version and release notes from <releases>. The
metainfo in the source tree carries notes for the current release; this
script only steps in when a tag is built that is not listed yet, in which
case it prepends a bare <release> entry so the store still shows a version.

Usage: stamp-release.py <version> <metainfo.xml>
"""
import datetime
import sys
import xml.etree.ElementTree as ET


def main() -> int:
    version, path = sys.argv[1], sys.argv[2]

    ET.register_namespace("", "")
    tree = ET.parse(path)
    root = tree.getroot()

    releases = root.find("releases")
    if releases is None:
        releases = ET.SubElement(root, "releases")

    for release in releases.findall("release"):
        if release.get("version") == version:
            print(f"AppStream release already present: {version}")
            return 0

    entry = ET.Element("release")
    entry.set("version", version)
    entry.set("date", datetime.date.today().isoformat())
    releases.insert(0, entry)

    tree.write(path, encoding="UTF-8", xml_declaration=True)
    print(f"AppStream release stamped: {version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
