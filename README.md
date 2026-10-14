# Positive Mirror

A Blender add-on that mirrors objects without negative scale, with an optional live link that keeps the copies in sync.

## What it does

- Mirrors selected objects across a world axis, the 3D cursor, or another object
- Every copy keeps a positive scale, so it exports cleanly to engines that reject negative scale
- Copies share the source mesh, so instancing is kept
- Pairs left and right meshes by name, so Asset_L is mirrored with Asset_R when it exists
- Live link keeps copies in sync while you move, rotate or scale the sources
- Copies are locked while linked, and Unlink turns them back into normal objects
- Deleting a source unlinks its copies, or deletes them if you choose

## How it works

A plain mirror multiplies the transform by a reflection, which gives negative scale. Positive Mirror adds a second reflection along one of the object's own axes, the flip axis. The two reflections cancel into a normal rotation, so the copy keeps a positive scale. For a mesh that is symmetric along the flip axis, the result looks exactly like a true mirror.

## Install

1. Download the zip from the latest release
2. In Blender, open Preferences and use Install from Disk
3. Open the sidebar in the 3D viewport and find the Positive Mirror tab, or use Object ▸ Mirror ▸ Positive Mirror

The panel has a Help button that explains each option.

## Limits

- An asymmetric mesh needs a left and right pair to look mirrored
- A parent with non-uniform scale can stop a copy matching exactly, and the tool warns when this happens
- Copies follow their sources only while the add-on is enabled

## Requirements

Blender 4.2 or newer. Tested on Blender 4.2 LTS and 5.2 LTS.

## License

GPL 3.0 or later.