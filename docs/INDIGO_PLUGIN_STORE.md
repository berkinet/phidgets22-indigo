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
- Minimum Indigo version: **2022.1**
- First Store-compatible version: **0.3.0**
- Intended first public Store release: **1.0.0** (deferred until submission)

Version 0.3.0 begins the three-part `X.Y.Z` version scheme required by the
Store. Versions through 0.2.1.49 remain part of the development history. Later
patch releases should be numbered 0.3.1, 0.3.2, and so on.

Continue using `0.3.x` versions during the present hardware-testing and
pre-publication phase. When the plugin and Store submission are ready, promote
the tested release candidate to `1.0.0` and publish its matching tag and GitHub
Release. Do not bump the plugin, tag `v1.0.0`, or create that release before the
submission milestone.

The remaining hardware work before that milestone is real-hardware verification
of the implemented SGP41 I2C profile. The BME280 profile and ADP0001 GPIO
support are implemented and hardware-tested.

The planned LCD1100 text and formula-graph support is implemented and
hardware-tested; it no longer represents a Store-submission dependency.

## Permanent identity and compatibility

Indigo associates devices, actions, and other objects with the plugin
identifier. Changing the identifier would cause existing objects to remain
associated with the old plugin identity and appear lost to the replacement.
For that reason, version 0.3.0 preserves the established identifier
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
7. Confirm that the tag format is accepted as matching `PluginVersion`. The
   initial tag is `v0.3.0` and the plist value is `0.3.0`; if the contribution
   form treats the leading `v` as a mismatch, correct the tag/release before
   importing it.

The repository already contains the required top-level README, license,
`.indigoPlugin` bundle, and `Contents/Resources/icon.png`. A separate plugin ZIP
is optional. When no release asset is attached, GitHub's source archive
contains the installable bundle at the repository's top level.

## Initial v0.3.0 publication status

- `PluginVersion` changed to `0.3.0`.
- Established plugin identifier `com.yikes.eric.phidgets-indigo` preserved.
- Changelog updated.
- All 62 automated tests passed.
- Plist, XML, and diff validation passed.
- Commit `268e8b99af1b0fcb3918b32ec5d10f158d015265` published to `main`.
- Annotated tag `v0.3.0` published and verified against that commit.
- Published GitHub Release `v0.3.0` created and verified as the latest
  production release (not a prerelease).

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
4. Import the published 0.3.0 GitHub Release.
5. Verify the Store page, icon, release information, download, installation,
   and version notification behavior.
6. After the new listing is working, contact Indigo Domotics to retire or
   delete the obsolete Phidget21 listing.

Account and identity prerequisites are complete: the owner created Indigo
website account `berkinet2`, and Indigo confirmed that the established
developer identity may be retained. The next step is to add the GitHub-managed
plugin from that account's **Plugin Contributions** page.

See Indigo's
[Plugin Store submission guidance](https://docs.indigodomo.com/2025.2/plugin-dev/guide/#adding-your-plugins-to-the-plugin-store)
for the current contribution-form requirements.
