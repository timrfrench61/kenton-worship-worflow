# Kenton website deployment

Run this workflow from `C:\repos\kenton-worship-workflow`. Settings are in `website.json`. Code and this procedure belong in Git; release packages, receipts, and backups stay under ignored `work/`.

## One-time server permission setup

SSH and the service configuration were verified on October 2, 2026. `tim` currently needs a password for sudo, so unattended deployment remains disabled.

1. Connect from PowerShell:

   ```powershell
   ssh tim@138.68.26.140
   ```

2. At the Droplet's `tim@kenton-web-01:~$` prompt, open the rule in the Nano editor:

   ```sh
   sudo EDITOR=nano visudo -f /etc/sudoers.d/kenton-website-deploy
   ```

   Enter your sudo password if prompted (no characters appear while typing). Continue only when the Nano editor opens.

3. Paste this single line **inside the editor, not at the shell prompt**. If the file already contains this rule, do not add a duplicate:

   ```text
   tim ALL=(root) NOPASSWD: /usr/bin/systemctl stop kenton-website, /usr/bin/systemctl start kenton-website
   ```

   Press **Ctrl+O**, then **Enter** to save; press **Ctrl+X** to exit. Success returns you to `tim@kenton-web-01:~$` without a syntax error. If visudo reports an error, choose `e` to reopen and correct the line.

   If you saw `-bash: syntax error near unexpected token '('`, the rule was pasted into Bash instead of the editor. It did not install the rule; repeat steps 2 and 3.

4. Validate the rule without stopping the website:

   ```sh
   sudo visudo -cf /etc/sudoers.d/kenton-website-deploy
   sudo -n -l /usr/bin/systemctl stop kenton-website
   sudo -n -l /usr/bin/systemctl start kenton-website
   exit
   ```

   Success: syntax validates and both permission checks succeed without a password prompt.

5. Set `deployment.enabled` to `true` in this project's `website.json`. Do not enable it until the permission checks pass. SSH host-key checking remains enabled; private keys and passwords do not belong in configuration.

## Weekly release

1. Prepare the cards, review their content, then apply them to the local website:

   ```powershell
   python scripts/update-automation.py --website-only
   python scripts/publish-automation.py --website-only --reviewed
   ```

2. Run the website in Visual Studio. Review card dates/text, colors, images, links, and mobile layout. Other website development changes are included in a full release, so review those too.

3. Check configuration and build the full application:

   ```powershell
   python scripts/deploy-website.py --check
   python scripts/deploy-website.py --prepare --note "October 4 worship panels and card appearance"
   ```

   Success prints **Prepared release** with a new folder under `work/website-deploy`. It builds a Release package using .NET, hashes its files, and records the website Git revision and whether there are uncommitted changes. It does not upload anything. Replace the note for each release.

4. Set `$release` to the exact folder printed above; replace `RELEASE_ID` in this example:

   ```powershell
   $release = "work/website-deploy/RELEASE_ID"
   python scripts/deploy-website.py --deploy $release --reviewed
   ```

   Success prints **Deployment verified** and the receipt path. The script uploads a new package, verifies hashes, preserves server configuration, stops only the website service, switches the files, restarts it, and checks service state, an HTTPS GET, and the exact published panel-data hash. There is a brief service interruption during the switch. Nothing changes DNS or Caddy.

5. Open `https://kentonchurch.org` and review the live pages. Read the receipt and `work/desktop/website-maintenance.log`. Automated HTTP checks do not establish visual approval.

## Failure and recovery

An unhealthy activated release triggers automatic restoration of the previous files, followed by service and HTTP checks. Read `receipt.json`: `rolled_back` means recovery checks passed; `rollback_failed` requires manual server investigation; `unknown_check_server` means the connection did not establish a final state. Do not redeploy blindly after an unknown result.

Server evidence stays under `/home/tim/kenton-deploy/RELEASE_ID`: `remote-receipt.json`, `previous/`, and, on failed activation, `failed/`. Successful releases retain their predecessor. Local evidence stays in the matching `work/website-deploy/RELEASE_ID`. No automatic archive deletion is implemented. Retrying an already attempted release is refused; prepare a new release after diagnosing the problem. This version implements automatic failure rollback, not a separate operator command to roll back a healthy release.

If only workbook logging fails, deployment remains recorded as successful with `workbook_log: pending`. Close Excel/resolve Drive access and retry logging only:

```powershell
python scripts/deploy-website.py --log-only $release
```

Release IDs prevent duplicate maintenance rows. Logging backs up the workbook before editing and detects changes made while it saves. Planning sheets remain intact. Do not run deployment again merely to retry logging.

## Confirmed configuration

| Parameter | Value / behavior |
| --- | --- |
| DigitalOcean project / Droplet | kenton-church / kenton-web-01 |
| SSH host / user | 138.68.26.140 / tim, port 22 |
| Public URL | https://kentonchurch.org; Caddy also serves www.kentonchurch.org |
| OS / architecture | Ubuntu 24.04.4 / x86_64 |
| Installed runtime | ASP.NET Core and .NET 10.0.12 |
| Service | kenton-website, active, runs as tim |
| Service directory | /var/www/kenton |
| Executable | /usr/bin/dotnet /var/www/kenton/kenton_website.dll |
| Proxy | Caddy 2.6.2 ? 127.0.0.1:5000 |
| Local project | C:/repos/kenton_website/kenton_website.csproj |
| Build | Release, framework-dependent, no Windows apphost; full application, not just wwwroot |
| Server-only settings preserved | Existing appsettings.json, appsettings.Production.json, appsettings.Development.json |
| Local history | work/website-deploy plus work/desktop/website-maintenance.log |
| Workbook logging | deployment.maintenance_workbook settings; separate Website Maintenance sheet |

If you introduce uploads, databases, or other runtime-written files, add an explicit preservation design before deploying; this release procedure replaces website content and retains the old copy in the release archive. It does not migrate server settings. The `--inspect` command can refresh a read-only host report:

```powershell
python scripts/deploy-website.py --inspect
```

## Card appearance

1. Edit `website.json` in this project. Under `cards`, choose one of `last-sunday-morning`, `last-sunday-evening`, `next-sunday-morning`, or `next-sunday-evening`.
2. Set `backgroundImage` to an existing filename under `C:/repos/kenton_website/wwwroot/images/card-background`. Under `appearance`, set colors using `#RRGGBB` or `#RRGGBBAA` (the final pair controls opacity). `imageOpacity` is a quoted value from `"0"` to `"1"`.
3. Prepare the panels:

   ```powershell
   python scripts/update-automation.py --website-only
   ```

4. Review the data and apply it to the local website:

   ```powershell
   python scripts/publish-automation.py --website-only --reviewed
   ```

5. Rebuild/restart the website in Visual Studio after the renderer update, then inspect its four cards. This command changes the local website only.

Supported colors: `backgroundColor`, `overlayColor`, `textColor`, `headingColor`, `accentColor`, `borderColor`, `linkColor`. Text and card content continue to come from the worship planner. Settings are applied by card slot after date rollover, so a last-Sunday card receives that slot's appearance. Existing metadata and sermon-text colors retain the website's styling.

The website renderer validates values before using them as CSS variables. Existing website styling remains the fallback for cards without appearance settings. Changing `website.json` after preparation requires preparing again before local publication.



## Implementation and verification

Entry point: `scripts/deploy-website.py`. Local release/history/logging: `scripts/_website_release.py`. Uploaded activation and automatic rollback: `scripts/_website_remote.py`. Regression tests: `tests/test_website_deploy.py`.

Verified: live SSH inspection, local .NET Release build, and isolated CLI tests of activation, hash rejection before stopping the service, failed-health rollback, and workbook-log idempotency. Service actions and HTTP responses in those tests are simulated. No live activation or real planning-workbook write has been performed during implementation.

References: [DigitalOcean OpenSSH](https://docs.digitalocean.com/products/droplets/how-to/connect-with-ssh/openssh/) and [Microsoft ASP.NET Core Linux hosting](https://learn.microsoft.com/en-us/aspnet/core/host-and-deploy/linux-nginx?view=aspnetcore-10.0). The latter documents application publishing/systemd; this server's Caddy configuration was independently inspected.
