# Operations

## Services and checks

Inspect the registered unit and service state with systemd:

```bash
systemctl cat club3090-control.service
sudo systemctl status club3090-control.service
sudo systemctl start club3090-control.service
```

After starting the control service, check the admin route in a browser at `http://HOST:8008/admin` and test the proxy with:

```bash
curl http://HOST:8009/v1/models
```

Use systemd's journal to inspect service output, for example `journalctl -u club3090-control.service`. Services execute directly from the repository checkout, so do not move or remove the checkout while they are installed.

## Updating

The updater reports the checked-out server revision and does not perform self-updates. For a reviewed update, run `git pull` in the server repository, then `sudo ./install.sh` from that checkout to refresh service registration. Update the separate upstream `club-3090` checkout deliberately when needed; the installer never fetches or updates either repository.

## Troubleshooting

- If installation reports missing prerequisites, install the named commands/modules with your distribution package manager, then run `sudo ./install.sh` again.
- If the upstream checkout is not found, set `CLUB3090_DIR` to its existing absolute path.
- Check `systemctl cat club3090-control.service` to verify the service points to the expected checkout and configured environment file (default `/etc/club3090-server.env`).
- Check the service journal and confirm the configured mutable data directory is writable and has sufficient space.

## Uninstallation

Run the repository's root uninstaller:

```bash
sudo ./uninstall.sh
```

It removes registered service units and `/etc/club3090-server.env`, while keeping the repository checkout and mutable runtime data intact. Dependency packages remain installed; uninstallation does not remove them. Preserve or remove runtime data separately according to your retention needs.

See [Removed Model Manager](removed-model-manager.md) for remaining model-resource cleanup controls and their effect on shared assets.
