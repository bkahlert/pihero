# Card backup and restore

Date: 2026-09-28. Status: approved design, ready for planning.

## Intent

Insurance for a device whose state is not in its device file. A Raspberry Pi that has run for years carries things a reflash
cannot bring back: application data, the Tailscale node identity, SSH host keys, hand-made changes, or an installation that
predates Pi Hero 2 altogether. When such a device breaks, its owner wants it back the way it was, without deciding which state
mattered. The tool for that is a full image of the card, taken on the Mac while the Pi is off, and written back later onto the
same card or a replacement.

This replaces the standalone `backups` repository of 2024: two interactive bash scripts around `gum`, `jq`, and `sudo gdd`,
untested, and no longer working on current macOS, which lets only `authopen` open a raw disk. Pi Hero 2 already has the raw-disk
code in [flash.py](../../../testkit/src/pihero_testkit/flash.py); the backup reuses it.

Success looks like this: `make backup` with a card in the reader asks which card, names the image after the Pi and the day, and
ten minutes later `backups/mypi-2026-09-28.img.xz` exists next to a checksum. `make restore` lists the images and the cards,
confirms once, writes, verifies, and ejects. Tier 0 proves every rule without a card.

## Decisions

| Decision | Choice | Why |
|---|---|---|
| Kind of backup | Full raw image of the card | Brings back everything, including state Pi Hero 2 knows nothing about and installations it did not provision; no judgement about which files matter |
| Where it runs | On the Mac, Python standard library in `testkit/`, launched through `make` | Same place and shape as `make flash`; `sudo dd` cannot open a raw disk on current macOS, `authopen` can, and `flash.py` already does it |
| Image format | xz, the format of Raspberry Pi OS images | `flash.write_image` streams xz onto a card and `read_back` verifies it, so restore adds no imaging code; the file can also be flashed with Raspberry Pi Imager |
| Compression | `lzma` module, preset 0, single threaded | No new dependency; the card reader bounds the run anyway; piping through Homebrew's multi-threaded `xz` would save minutes and is the change to make if that ever matters |
| Card size on restore | Same size or larger only; a smaller card is refused before anything is written | Shrinking the ext4 root and the partition table needs loop devices in the tools container and a boot test of the result; planned as the follow-up, see below |
| Interaction | Prompts for whatever `make` was not given; nothing is asked when everything was given | Convenience on the Mac, scriptability like `make flash`; the design's ban on interactive CLIs concerns the device, where `gum` was too slow |
| Image name | `<hostname>-<YYYY-MM-DD>.img.xz`, hostname from the card's cloud-init `user-data` | Tells which Pi and which day without opening the file; `NAME=` overrides, a card without `user-data` is asked |
| Existing image | Never overwritten; the tool names the file and stops | A second backup on the same day is rare and deliberate; a failed run removes its partial files |
| Integrity | A TOML sidecar with the decompressed image's size and sha256 | Restore refuses a card that is too small before writing, detects a damaged backup file at no extra cost, and the interactive list shows the card size each image needs |
| Location | `backups/` in the repository, gitignored | Same convention as `devices/`, and as the old repository |

## Commands

```shell
make backup                                   # asks which card; name from the card, date from today
make backup DISK=disk9 NAME=mypi              # asks nothing
make restore                                  # asks which image, which card, then confirms
make restore IMAGE=backups/mypi-2026-09-28.img.xz DISK=disk9   # asks nothing, confirms nothing
```

Both targets are two lines in the [Makefile](../../../Makefile) in the shape of `flash`, declared `.PHONY`, and pass every
variable as an option that may be empty:

```makefile
backup: ## image an SD card into backups/<host>-<date>.img.xz (make backup [DISK=disk9] [NAME=host])
	@$(UV) python -m pihero_testkit.backup --disk="$(DISK)" --name="$(NAME)"

restore: ## write a backup image onto an SD card (make restore [IMAGE=backups/x.img.xz] [DISK=disk9])
	@$(UV) python -m pihero_testkit.restore --image="$(IMAGE)" --disk="$(DISK)"
```

### Backup

1. **Card.** Without `DISK`, the candidates are listed one per line as `disk9  USB3.0 CRW -SD  31.9 GB` and the user picks by
   number; Enter takes the first. Candidates are whole disks that `diskutil list external physical` returns and whose info says
   `RemovableMedia` and not `Internal`. An external SSD never appears; usually the list is the one card. With `DISK`, the same
   check runs on the named disk and refuses anything else, as `flash` does.
2. **Name.** Without `NAME`, the card's first partition is mounted (macOS has usually done that already), `user-data` is read if
   present, and `hostname:` is taken from it with the same kind of regular expression `flash.py` uses for the regulatory domain.
   The partition's label is not checked; a card from before Trixie has no `user-data` and the user is asked for a name. The
   image is `backups/<name>-<today>.img.xz`; if it exists, the tool says so and exits non-zero.
3. **Dump.** The disk is unmounted, opened read-only through `authopen`, and read in whole-sector chunks until the end while
   hashing and compressing into the image. Progress is reported every 256 MiB with the percentage of the card's `TotalSize` and
   the rate, in the style of `flash`. Backup never opens the card for writing.
4. **Sidecar.** `backups/<name>-<today>.toml` records `size` and `sha256` of the decompressed image, in the style of
   [images.lock](../../../testkit/src/pihero_testkit/images.lock).
5. **Finish.** The card is ejected. The last line says where the image is and that a restore needs a card of at least the
   card's size.

### Restore

1. **Image.** Without `IMAGE`, `backups/*.img.xz` are listed newest first with the card size each needs, taken from the
   sidecar, and the user picks by number; Enter takes the newest.
2. **Card.** As in backup.
3. **Checks.** The card must be removable, as in `flash`, and its `TotalSize` must be at least the image's `size` from the
   sidecar; otherwise the tool names both sizes and exits before touching the card. Without a sidecar the size check and the
   file-integrity check are skipped and the tool says so; the card is still verified.
4. **Confirmation.** Unless both `IMAGE` and `DISK` were given, one question names the image and the card and requires `y` or `yes`.
5. **Write.** The disk is force-unmounted, opened through `authopen`, and `flash.write_image` streams the image onto it.
   The digest it returns is compared with the sidecar's `sha256`; a mismatch means the backup file is damaged and is reported
   as such. Then `flash.read_back` verifies the card, as `flash` does.
6. **Finish.** The card is ejected. If it is larger than the image, the last line says that the root filesystem still has the
   old card's size and that `sudo raspi-config --expand-rootfs` followed by a reboot grows it.

## Code

```
testkit/src/pihero_testkit/
  disk.py       # moved out of flash.py: disk_info, check_removable, open_raw (now with flags), mount of a partition,
                # unmount, eject; new: cards() and the one-line description of a card
  prompt.py     # choose(title, options) and confirm(question); read a line, validate, return the choice
  backup.py     # hostname from user-data, image name, dump, sidecar, main
  restore.py    # image list, size check, restore, main
  flash.py      # imports from disk; write_image, read_back, and the device-file steps stay here unchanged
```

- `flash.py` keeps its behaviour and its module interface for `write_image` and `read_back`; only the disk helpers move, so its
  existing tests keep passing with adjusted imports.
- `open_raw(disk, flags)` takes the open flags; backup passes `O_RDONLY`, flash and restore `O_RDWR`.
- `dump(fd, image, total, report)` mirrors `write_image`: it returns the size read and the sha256 of the bytes, and it is the
  only function that reads the card.
- Every prompt is a function over its inputs and a line reader, so tests drive it without a terminal.
- Errors are `SystemExit` with a message, as everywhere in the testkit. A failed backup removes the partial image and sidecar.

## Tests

Tier 0, file-backed like [test_flash.py](../../../testkit/tests/test_flash.py):

- `disk.cards` keeps a removable whole disk and drops partitions, internal disks, and non-removable external disks, over
  `diskutil`-shaped dictionaries.
- `backup.hostname` finds a quoted and an unquoted `hostname:`, ignores an indented one, and returns `None` when absent;
  the sample device file yields `sample`.
- The image name is `<host>-<YYYY-MM-DD>.img.xz` for a given date.
- Round trip: a file of random bytes and zeros whose length is not a multiple of the chunk size is dumped to xz, the sidecar
  holds its size and sha256, `flash.write_image` writes it back onto another file, and the bytes match.
- An existing image is refused and left untouched.
- The size check refuses a smaller card with both sizes in the message and accepts an equal and a larger one.
- `prompt.choose` returns the numbered pick, the first on Enter, and asks again on an invalid line; `prompt.confirm` accepts `y` and `yes`.
- Static checks and the `flash` tests are unchanged apart from imports.

## Documentation

- [devices/README.md](../../../devices/README.md): a section "Back up a device" after "Update devices": when to do it, both commands,
  where the images are, the card-size rule, the expand-rootfs step.
- [docs/design.md](../../design.md): a row in the decisions table; the goals bullet that bans the interactive CLI gains "on the
  device"; the layout tree gains `backups/`; the operations list gains "Backup is a card image" with the same-size rule and
  shrinking as the planned follow-up.
- [.gitignore](../../../.gitignore): `backups/`.
- The `backups` repository has no remote and four commits; nothing is migrated. Deleting the directory is the owner's call once
  this has landed.

## Follow-up: shrinking

Restoring onto a card that is nominally the same size but a few megabytes smaller fails today, and card death is the most common
reason for a restore. The follow-up shrinks the image at backup time in the tools container: `e2fsck`, `resize2fs -M` on the
root, a shorter second partition, a truncated image, and first-boot expansion armed through `cmdline.txt` as
`raspi-config --expand-rootfs` does. It needs loop devices in a privileged container and a tier-2 boot of a shrunk image. Until
then the workaround is a card of the next size up.

## Out of scope

Backups over SSH from a running device, incremental or file-level backups, scheduling, and restoring images other than the
tool's own.
