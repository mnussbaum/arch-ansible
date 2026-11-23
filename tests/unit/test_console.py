import socket
import threading

import pytest

from arch_ansible_vm.console import Console, Shell


@pytest.fixture
def guest(tmp_path):
    """A fake guest serial port: a listening unix socket the console connects to."""
    path = tmp_path / "serial.sock"
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(path))
    server.listen(1)

    yield path, server

    server.close()


def connect(guest, tmp_path):
    path, server = guest
    console = Console(path, tmp_path / "serial.log")
    conn, _ = server.accept()

    return console, conn


def reply_to_commands(conn, reply):
    """Answer each command line the shell sends: echo it back wrapped, the
    way agetty does, then send `reply`."""
    buf = b""
    while b"\n" not in buf:
        buf += conn.recv(4096)
    line = buf.split(b"\n", 1)[0]
    echo = b"\r\n".join(line[i : i + 40] for i in range(0, len(line), 40))
    conn.sendall(echo + b"\r\n" + reply)


def test_expect_matches_across_an_escape_sequence_split_between_reads(guest, tmp_path):
    console, conn = connect(guest, tmp_path)

    conn.sendall(b"hel\x1b[3")
    conn.sendall(b"1mlo world\r\n")

    assert console.expect(r"hello world", timeout=5).group(0) == "hello world"
    assert (tmp_path / "serial.log").read_bytes() == b"hel\x1b[31mlo world\r\n"


def test_expect_times_out_with_the_recent_output_in_the_error(guest, tmp_path):
    console, conn = connect(guest, tmp_path)
    conn.sendall(b"still booting\r\n")
    console.expect(r"booting", timeout=5)

    with pytest.raises(TimeoutError, match="still booting"):
        console.expect(r"login:", timeout=0.3)


def test_expect_raises_eof_when_the_guest_goes_away(guest, tmp_path):
    console, conn = connect(guest, tmp_path)

    conn.close()

    with pytest.raises(EOFError):
        console.expect(r"login:", timeout=5)


def test_shell_run_returns_the_exit_code_and_output_without_the_echo(guest, tmp_path):
    console, conn = connect(guest, tmp_path)
    logged = []
    shell = Shell(console, logged.append)
    reply = b"__VM_BEGIN__\r\nfirst line\r\nsecond line\r\n__RC_3__END__\r\n"
    threading.Thread(target=reply_to_commands, args=(conn, reply), daemon=True).start()

    rc, out = shell.run(
        "some-command --with a-long-enough-argument-list-to-wrap", timeout=5
    )

    assert (rc, out) == (3, "first line\nsecond line")
    assert logged == [
        "$ some-command --with a-long-enough-argument-list-to-wrap",
        "first line\nsecond line",
        "[rc=3]",
    ]


def test_shell_run_with_check_raises_on_a_failed_command(guest, tmp_path):
    console, conn = connect(guest, tmp_path)
    shell = Shell(console, [].append)
    reply = b"__VM_BEGIN__\r\nno such file\r\n__RC_1__END__\r\n"
    threading.Thread(target=reply_to_commands, args=(conn, reply), daemon=True).start()

    with pytest.raises(RuntimeError, match="no such file"):
        shell.run("cat /missing", timeout=5, check=True)
