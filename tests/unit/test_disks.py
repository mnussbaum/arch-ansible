import json

import pytest

from arch_ansible_vm.disks import newest_medium, selected_organizations, use_disk


@pytest.fixture
def cache(tmp_path, monkeypatch):
    """An empty ARCH_ANSIBLE_CACHE."""
    monkeypatch.setenv("ARCH_ANSIBLE_CACHE", str(tmp_path))
    monkeypatch.delenv("ARCH_ANSIBLE_ORGANIZATIONS", raising=False)

    return tmp_path


@pytest.fixture
def output(cache):
    path = cache / "mkosi/images/image"
    path.mkdir(parents=True)

    return path


def add_medium(output, version, organizations=None):
    medium = output / f"image_{version}_x86-64.raw"
    medium.touch()
    if organizations is not None:
        (output / f"image_{version}_organizations").write_text(organizations + "\n")

    return medium


def make_disk(cache, name):
    """A test disk with its varstore and TPM state beside it."""
    disk = cache / name
    disk.touch()
    (cache / f"{name}.ovmf_vars.fd").touch()
    (cache / f"{name}.tpm").mkdir()
    (cache / f"{name}.tpm/tpm2-00.permall").touch()

    return disk


def disk_files_exist(cache, name):
    return [
        (cache / f"{name}{suffix}").exists() for suffix in ("", ".ovmf_vars.fd", ".tpm")
    ]


def registry(cache):
    return json.loads((cache / "mkosi/vm-disks.json").read_text())


def test_newest_medium_picks_the_highest_version_with_matching_organizations(output):
    add_medium(output, "20261101000000", "a,b")
    newest = add_medium(output, "20261102000000", "a,b")
    add_medium(output, "20261103000000", "other")

    assert newest_medium("a,b") == newest


def test_newest_medium_ignores_split_partition_artifacts(output):
    medium = add_medium(output, "20261101000000", "")
    (output / "image_20261109000000_x86-64.usr-x86-64.0123abcd.raw").touch()
    (output / "image_20261109000000_organizations").write_text("\n")

    assert newest_medium("") == medium


def test_newest_medium_treats_a_missing_record_as_no_organizations(output):
    medium = add_medium(output, "20261101000000")

    assert newest_medium("") == medium


def test_newest_medium_exits_with_the_build_command_when_nothing_matches(output):
    add_medium(output, "20261101000000", "other")

    with pytest.raises(
        SystemExit, match="run bin/build-image --organization a --organization b"
    ):
        newest_medium("a,b")


def test_selected_organizations_normalizes_flags_and_falls_back_to_the_environment(
    cache, monkeypatch
):
    assert selected_organizations(["b", "a", "b"]) == "a,b"

    monkeypatch.setenv("ARCH_ANSIBLE_ORGANIZATIONS", "y,,x")

    assert selected_organizations(None) == "x,y"


def test_use_disk_keeps_only_the_newest_disk_per_organization_set(cache):
    old = make_disk(cache, "old.raw")
    new = make_disk(cache, "new.raw")
    other = make_disk(cache, "other.raw")

    use_disk(old, print, 1000.0, orgs="")
    use_disk(other, print, 1500.0, orgs="x")
    use_disk(new, print, 2000.0, orgs="")

    assert disk_files_exist(cache, "old.raw") == [False, False, False]
    assert disk_files_exist(cache, "new.raw") == [True, True, True]
    assert disk_files_exist(cache, "other.raw") == [True, True, True]
    assert sorted(registry(cache)) == sorted([str(new), str(other)])


def test_use_disk_never_deletes_a_disk_that_is_still_open(cache):
    busy = make_disk(cache, "busy.raw")
    new = make_disk(cache, "new.raw")
    use_disk(busy, print, 1000.0, orgs="")

    with busy.open("rb"):
        use_disk(new, print, 2000.0, orgs="")

    assert busy.exists()


def test_use_disk_drops_registry_entries_whose_disk_is_gone(cache):
    gone = make_disk(cache, "gone.raw")
    new = make_disk(cache, "new.raw")
    use_disk(gone, print, 1000.0, orgs="x")
    gone.unlink()

    use_disk(new, print, 2000.0, orgs="")

    assert list(registry(cache)) == [str(new)]


def test_use_disk_registers_a_disk_only_when_given_its_organizations(cache):
    registered = make_disk(cache, "registered.raw")
    unregistered = make_disk(cache, "unregistered.raw")
    use_disk(registered, print, 1000.0, orgs="")

    use_disk(unregistered, print, 2000.0)

    assert list(registry(cache)) == [str(registered)]
    assert registered.exists()
