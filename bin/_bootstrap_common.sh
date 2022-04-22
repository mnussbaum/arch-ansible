set -o errexit
set -o nounset
set -o xtrace

bootstrap() {
  hostnamectl set-hostname $HOSTNAME

  NO_ASK_BECOME_PASS=1 \
    ANSIBLE_PLAYBOOK=bootstrap.yml \
    exec ./bin/ansible \
    --extra-args new_hostname=$HOSTNAME \
    --extra-args bootstrap="true" \
    --tags bootstrap \
    $@
}
