# Indigo Plugin Store publication

This document records the publication decisions and procedure for adding
Phidgets 22 to the Indigo Plugin Store.

## Store identity

- Store name: **Phidgets 22**
- GitHub repository: `berkinet/phidgets22-indigo`
- Permanent plugin identifier: `com.yikes.eric.phidgets-indigo`
- Developer identifier: `com.berkinet`
- Indigo website / Plugin Store account: `berkinet2`
- Category: **Digital/Analog I/O Modules**
- Minimum Indigo version: **2025.2** (Python 3.13)
- First Store-compatible version: **0.3.0**
- Current pre-submission release line: **0.5.x**

Version 0.3.0 begins the three-part `X.Y.Z` version scheme required by the
Store. Versions through 0.2.1.49 remain part of the development history. The
first Store submission should use a tested 0.5.x release unless the owner
chooses a different version; do not assume that 1.0.0 is required. Before
submission, verify current hardware behavior, the clean-install path, and the
current release notes. The plugin requires Indigo 2025.2's Python 3.13 and an
externally installed official Phidget22 package.

## Permanent identity and compatibility

Indigo associates devices, actions, and other objects with the plugin
identifier. Changing the identifier would cause existing objects to remain
associated with the old plugin identity and appear lost to the replacement.
For that reason, the plugin preserves the established identifier
`com.yikes.eric.phidgets-indigo`.

The identifier does not begin with the `com.berkinet` developer ID. Indigo
Domotics has confirmed that the existing developer and plugin identifiers may
be retained even though the owner created the new Indigo website account
`berkinet2`. Do not change the plugin identifier or developer identifier to
match the website login; they serve different purposes, and changing the
plugin identifier would break the association with existing Indigo objects.

## Relationship to the Phidget21 plugin

The existing [Phidgets Plugin Store entry](https://www.indigodomo.com/pluginstore/76/)
is the owner's obsolete Phidget21 plugin. Its identifier is
`com.perceptiveautomation.indigoplugin.Phidgets`, so Phidgets 22 is published
as a new Store entry rather than as an update to that plugin.

After the Phidgets 22 Store page and download have been verified, ask Indigo
Domotics staff to retire or delete the old Phidget21 listing. Only Indigo staff
can delete Store plugins and releases.

## GitHub release requirements

The Store reads published GitHub Releases; it does not publish the tip of
`main` or an ordinary Git tag.

For every Store release:

1. Update `PluginVersion` in `Phidgets22.indigoPlugin/Contents/Info.plist`.
2. Add release notes to `CHANGELOG.md`.
3. Run the complete automated test suite and plist/XML validation.
4. Commit and push `main`.
5. Create and push the corresponding annotated version tag.
6. Create a **published** GitHub Release from that tag. Do not mark a Store
   release as a draft or prerelease.
7. Confirm that the tag format is accepted as matching `PluginVersion` (for
   example, tag `v0.5.7` and plist value `0.5.7`). If the contribution form
   treats the leading `v` as a mismatch, resolve that before importing.

The repository already contains the required top-level README, license,
`.indigoPlugin` bundle, and `Contents/Resources/icon.png`. A separate plugin ZIP
is optional. When no release asset is attached, GitHub's source archive
contains the installable bundle at the repository's top level.

## Existing GitHub publication

The historical `v0.3.0` release was published before this Store submission.
It does not represent the current plugin. Verify that the tested 0.5.x tag and
published GitHub Release contain the intended candidate before importing a
version into the Store. A tag by itself is not sufficient.

## Indigo account steps

The plugin owner completes these steps in the **Plugin Contributions** section
of the Indigo account:

1. Confirm the registered developer identifier and tell Indigo Domotics that
   the established plugin ID must remain `com.yikes.eric.phidgets-indigo` to
   preserve existing Indigo objects.
2. Add a GitHub-managed plugin using owner `berkinet` and repository
   `phidgets22-indigo`.
3. Set or verify the Store name, category, minimum Indigo version, summary,
   support URL, supported-device information, and release notes.
4. Import the published, tested 0.5.x GitHub Release.
5. Verify the Store page, icon, release information, download, installation,
   and version notification behavior.
6. After the new listing is working, contact Indigo Domotics to retire or
   delete the obsolete Phidget21 listing.

Account and identity prerequisites are complete: the owner created Indigo
website account `berkinet2`, and Indigo confirmed that the established
developer identity may be retained. The Store submission itself is not yet
complete.

See Indigo's
[Plugin Store submission guidance](https://docs.indigodomo.com/2025.2/plugin-dev/guide/#adding-your-plugins-to-the-plugin-store)
for the current contribution-form requirements.
