# Model icons

A Pi Hero announces itself with a `model=<code>` in its `_device-info._tcp` record, and Finder draws the network
device with the icon of the Mac, AirPort, or iPad that code belongs to. This experiment answers which codes give
which icon and which sidebar icon, so that a design can be picked by eye and the code that produces it read off.
It is an experiment: two stand-alone Python scripts for the Mac's `python3`, no tests, and a layout that is still
allowed to change.

## Dump every icon

```bash
python3 experiments/model-icons/dump_model_icons.py            # into experiments/model-icons/out
python3 experiments/model-icons/dump_model_icons.py ~/Desktop/model-icons
```

The script, [dump_model_icons.py](dump_model_icons.py), reads every device model code declared in
`/System/Library/CoreServices/CoreTypes.bundle`, asks LaunchServices which type each code resolves to, takes that
type's icon and sidebar template, and writes:

| Path                              | Content                                                                                    |
| --------------------------------- | ------------------------------------------------------------------------------------------ |
| `icons/<icns name>.png`           | the largest image of each icon, written once                                               |
| `sidebar/<icns name>.png`         | each 64 px sidebar template, written once                                                  |
| `by-sidebar/<sidebar>/`           | one folder per sidebar template, wearing the template as its folder icon                   |
| `by-sidebar/<sidebar>/<icon>.png` | a link to `icons/<icon>.png` for every icon that comes with that sidebar                   |
| `index.json`                      | `sidebars`: sidebar, then icon, then codes and types; `dropped`: codes left out, by reason |

Open `out/by-sidebar` in Finder: each folder shows a sidebar icon, inside it the realistic icons that go with it.
Having chosen an icon, its codes are in `index.json`:

```json
{
  "sidebars": {
    "com.apple.macpro-2019": {
      "sidebar": "sidebar/com.apple.macpro-2019.png",
      "icons": {
        "com.apple.macpro-2019": {
          "icon": "icons/com.apple.macpro-2019.png",
          "types": ["com.apple.macpro-2023", "com.apple.macpro", "com.apple.macpro-2019", "com.apple.mac.tower"],
          "codes": ["Mac14,8", "Mac14,8@ECOLOR=0", "MacPro", "MacPro7,1", "MacPro7,1@ECOLOR=225,225,223", "Tower"]
        }
      }
    }
  },
  "dropped": {
    "unknown type": ["AppleDisplay18,2", "AppleDisplay2,1", "J120AP"],
    "no icon": [],
    "no sidebar": ["AirPods1,1", "AppleTV1,1", "Watch8,2"]
  }
}
```

The output directory is emptied first, but only when it is missing, empty, or holds an earlier dump. `out/` is
gitignored.

## How Finder gets from a code to an icon

- The code is a tag of class `com.apple.device-model-code` in the `UTExportedTypeDeclarations` of `CoreTypes.bundle`
  and the bundles nested in its `Contents/Library`, such as `MobileDevices.bundle`. Apple calls the value the model
  identifier; `sysctl hw.model` prints the one of the Mac it runs on.
- Codes are not unique: 492 of the 1048 codes are claimed by several types, mostly colour variants of one device.
  LaunchServices settles which type wins, and Finder asks it the same way the script does, through
  `UTTypeCreatePreferredIdentifierForTag` with the tag class above and `public.device` as the type to conform to.
  A code nobody claims resolves to a dynamic `dyn.*` type, and Finder shows a question mark.
- A type's icon is its `UTTypeIconFile`; a type without one inherits the nearest along `UTTypeConformsTo`. The sidebar
  template is the `_UTTypeTemplateIconFile` icns, or the `template_32x32@2x.png` inside the icon's own icns.
- Finder's Network view draws the icon. The sidebar template appears only under Locations, for a server that is
  connected.

## Preview a code in Finder

Two proxy records from the Mac itself make Finder show a device that does not exist. The instance names must match,
because Finder pairs the device-info record with the SMB one by name; the port of the device-info record must not be 0,
which mDNS treats as a placeholder; the address is from TEST-NET-1 and never answers.

```bash
dns-sd -P "MacPro7,1" _smb._tcp local 445 preview.local 192.0.2.10 &
dns-sd -P "MacPro7,1" _device-info._tcp local 1 preview.local 192.0.2.10 model=MacPro7,1 &
```

Open Network in Finder (Go, Network, or ⇧⌘K); the entry appears within a few seconds. Stop the preview with
`pkill -f 'dns-sd -P'`. The sidebar icon cannot be previewed this way, since the fake host cannot be mounted.

## Refresh docs/models

```bash
brew install pngquant
python3 experiments/model-icons/update_docs_models.py
```

The script, [update_docs_models.py](update_docs_models.py), writes the icon and sidebar template of the ten types pictured in
[devices/README.md](../../devices/README.md) and the [README](../../README.md) into [docs/models](../../docs/models):
`<identifier>.png`, `sidebar/<icns name>.png`, and the `<identifier>-sidebar.png` link. The PNGs are quantised to
8-bit palettes to keep the repository small. The READMEs reference the files, not the links, because GitHub does not
follow symbolic links. To picture another type, add its identifier to `MODELS` in the script.

## Findings on macOS 27

| Codes                                        | Count |
| -------------------------------------------- | ----: |
| declared                                     |  1048 |
| with icon and sidebar, placed in the dump    |   740 |
| resolving to no type                         |    81 |
| with icon but no sidebar                     |   227 |

- The 740 codes fall into 17 sidebar groups and 178 icons. Laptops, iPhones, iPads, and iMacs make up most of the
  icons; the AirPort, Mac Pro, Time Capsule, and Xserve groups hold one or two each.
- Related codes cluster. `MacPro7,1`, `Mac14,8`, `MacPro`, and `Tower` all give the 2019 tower; the rackmount needs
  the colour suffix, `Mac14,8@ECOLOR=1` or `MacPro7,1@ECOLOR=226,226,224`. The old Mac Pro is `MacPro1,1` to
  `MacPro5,1`, joined by the developer transition kit `ADP2,1`.
- The unresolved codes are older iPads and iPhones, as board names such as `J120AP` and `N41AP` or as `iPad4,1` and
  `iPhone6,1`, all declared in `MobileDevices.bundle` but not resolved by LaunchServices; `iMac6,1`; and the two
  display codes `AppleDisplay2,1` and `AppleDisplay18,2`, whose types conform to `public.display` rather than
  `public.device`. A display shows as a question mark in Finder.
- Without a sidebar template are Apple Watch, Apple TV, AirPods, HomePod, Power Mac, and Vision. They do show their
  icon in the Network view.
- One code per sidebar group was checked in Finder with the preview above; every one rendered the icon the dump
  predicts.
- Three sidebar groups carry an icon's name instead of a `Sidebar…` name, because their template lives inside the
  icon's own icns: `com.apple.ipad`, `com.apple.macpro-2019`, `com.apple.macpro-2019-rackmount`.

## To mature

- Tests, once the layout has settled; until then the check is running both scripts and looking at the result.
- A script for the Finder preview, fed with codes from `index.json`.
- Checking the sidebar icon needs a host that can be mounted, that is, a Pi announcing the code.
- The folder icons are the black sidebar templates tinted grey; a version per appearance would look better.
