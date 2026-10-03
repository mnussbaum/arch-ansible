#!/usr/bin/python

# -*- coding: utf-8 -*-

ANSIBLE_METADATA = {
    "metadata_version": "1.1",
    "status": ["preview"],
    "supported_by": "community",
}

DOCUMENTATION = """
---
module: firefox_ext_sideloader

short_description: Installs Firefox XPI extension files

description: "Sideload" install Firefox extensions from XPI files. Follows the process described at https://cryptonomic.net/sideload-extensions-in-firefox.html.

author:
  - Michael Nussbaum (@mnussbaum)

options:
  path:
    description:
      - Path to the extensions XPI file
      - Many Arch Linux Firefox extension packages place XPI files at /usr/lib/firefox/browser/extensions
    required: true
    type: string
  user:
    description:
      - Name of the system user to install the extension for
    required: false
    type: string
    default: Current user
  profile:
    description:
      - Name of the Firefox profile to install the extension into
      - Profile names should match The `Name` field of the profiles listed in
        ~/.mozilla/firefox/profiles.ini
    required: false
    type: string
    default: Install into all available profiles
"""

EXAMPLES = """
# Install uBlock extension from XPI file. Note XPI file expected to already
# exist at the path, and might be installed there by another pacakge manager
- firefox_ext_sideloader:
    path: /usr/lib/firefox/browser/extensions/uBlock0@raymondhill.net.xpi
"""

import configparser
import json
import os
import shutil
import subprocess
import zipfile

from ansible.module_utils.basic import AnsibleModule


class FirefoxExtSideloader(object):
    def __init__(self, module):
        self.module = module

        self.result = dict(changed=False)

    def _user_firefox_dir(self):
        user = "~"
        if self.module.params["user"]:
            user = self.module.params["user"]

        return os.path.join(
            os.path.expanduser(user),
            ".mozilla",
            "firefox",
        )

    def _addon_startup_config_path(self, profile):
        return os.path.join(profile, "addonStartup.json.lz4")

    def _addon_startup_config(self, profile):
        addon_startup_config_path = self._addon_startup_config_path(profile)

        if not os.path.exists(addon_startup_config_path):
            return {}

        try:
            addon_startup_config_raw = subprocess.check_output(
                ["mozlz4", addon_startup_config_path]
            )
        except subprocess.CalledProcessError as e:
            self.module.fail_json(
                msg="Failed to mozlz4 decode {} - {}".format(
                    addon_startup_config_path, e
                ),
                **self.result
            )

        try:
            return json.loads(addon_startup_config_raw)
        except json.JSONDecodeError as e:
            self.module.fail_json(
                msg="Failed to JSON parse {} - {}".format(addon_startup_config_path, e),
                **self.result
            )

    def _install_for_profile(self, profile):
        profile_path = os.path.join(self._user_firefox_dir(), profile)
        extension_xpi_name = os.path.basename(self.module.params["path"])
        extension_name = os.path.splitext(extension_xpi_name)[0]
        extension_xpi_dest = os.path.join(profile_path, extension_xpi_name)

        if not os.path.exists(extension_xpi_dest):
            self.result["changed"] = True
            if not self.module.check_mode:
                shutil.copyfile(self.module.params["path"], extension_xpi_dest)

        with zipfile.ZipFile(extension_xpi_dest) as z:
            with z.open("manifest.json") as f:
                try:
                    extension_version = json.loads(f.read())["version"]
                except json.JSONDecodeError as e:
                    self.module.fail_json(
                        msg="Failed to JSON parse XPI manifest - {}".format(e),
                        **self.result
                    )

        addon_startup_config = self._addon_startup_config(profile_path)
        if "app-global" not in addon_startup_config:
            addon_startup_config["app-global"] = {}
        if "addons" not in addon_startup_config["app-global"]:
            addon_startup_config["app-global"]["addons"] = {}

        installed_addons = addon_startup_config["app-global"]["addons"]
        installed_version = installed_addons.get(extension_name, {}).get("version", None)

        if extension_version == installed_version:
            return

        self.result["changed"] = True
        installed_addons[extension_name] = {
            "enabled": True,
            "path": extension_xpi_name,
            "rootURI": "jar:file://{}!/".format(extension_xpi_dest),
            "version": extension_version,
        }

        if self.module.check_mode:
            return

        try:
            with open(self._addon_startup_config_path(profile_path), "w") as f:
                subprocess.run(
                    ["mozlz4", "--compress", "-"],
                    input=json.dumps(addon_startup_config),
                    stdout=f,
                    encoding="utf-8",
                    check=True,
                )
        except subprocess.CalledProcessError as e:
            self.module.fail_json(
                msg="Failed to mozlz4 encode modified addonStartup JSON - {}".format(
                    e
                ),
                **self.result
            )

    def run(self):
        if not shutil.which("mozlz4"):
            self.module.fail_json(msg="mozlz4 command not found", **self.result)

        config = configparser.ConfigParser()
        config.read(os.path.join(self._user_firefox_dir(), "profiles.ini"))

        profiles = []
        for section in config.sections():
            if self.module.params["profile"] and \
              config[section]["Name"] == self.module.params["profile"]:
                profiles.append(config[section]["Path"])

            if not self.module.params["profile"] and "Path" in config[section]:
                profiles.append(config[section]["Path"])

        for profile in profiles:
            self._install_for_profile(profile)

        self.module.exit_json(**self.result)


def main():
    module = AnsibleModule(
        argument_spec=dict(
            path=dict(type="str", required=True),
            user=dict(type="str", required=False),
            profile=dict(type="str", required=False),
        ),
        supports_check_mode=True,
    )

    return FirefoxExtSideloader(module).run()


if __name__ == "__main__":
    main()
